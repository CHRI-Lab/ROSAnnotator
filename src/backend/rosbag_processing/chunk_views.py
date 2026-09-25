import logging
import ssl
from pathlib import Path
from urllib.error import URLError
from uuid import uuid4

from requests.exceptions import SSLError as RequestsSSLError

from django.conf import settings
from django.core.cache import cache
from rest_framework import serializers, status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from .ai_records import build_ai_record_annotation_name
from .chunk_processing import process_chunk
from .chunks import load_manifest, save_manifest
from .serializers import InputInspectionSerializer
from .view_metadata import attach_metadata

logger = logging.getLogger(__name__)

class ChunkRequestSerializer(InputInspectionSerializer):
    chunking_enabled = serializers.BooleanField(default=True)
    chunk_seconds = serializers.FloatField(min_value=0.001, required=False)
    booklist_filename = serializers.CharField(required=False, allow_blank=True, max_length=255)
    annotation_filename = serializers.CharField(required=False, allow_blank=True, max_length=255)

    def validate(self, values):
        if values['chunking_enabled'] and 'chunk_seconds' not in values:
            raise serializers.ValidationError({'chunk_seconds': 'This field is required when chunking is enabled.'})
        return values

    def validate_bag_filename(self, value):
        value = super().validate_bag_filename(value)
        if any(character in value for character in ('/', '\\', ':', '\x00')):
            raise serializers.ValidationError('A .bag filename without a path is required.')
        return value

    def _validate_optional_filename(self, value, extension):
        if value and (
            value != Path(value).name
            or any(character in value for character in ('/', '\\', ':', '\x00'))
            or not value.lower().endswith(extension)
        ):
            raise serializers.ValidationError(f'A valid {extension} filename is required.')
        return value or None

    def validate_booklist_filename(self, value):
        return self._validate_optional_filename(value, '.json')

    def validate_annotation_filename(self, value):
        return self._validate_optional_filename(value, '.csv')


def manifest_directory():
    return getattr(settings, 'CHUNK_MANIFEST_DIR', '/app/processed_data/chunks')


def read_duration(path):
    # Chunk retrieval and validation do not need the media/ML runtime.
    from .data_utils import get_rosbag_duration
    return get_rosbag_duration(str(path))


def with_processing_status(manifest):
    manifest = {**manifest, 'chunks': [dict(chunk) for chunk in manifest['chunks']]}
    root = Path(manifest_directory()) / manifest['id']
    for chunk in manifest['chunks']:
        chunk['status'] = (
            'ready'
            if (root / f"{chunk['index']:04d}" / 'result.json').is_file()
            else 'not_processed'
        )
    return manifest


@api_view(['POST'])
def create_chunks(request):
    serializer = ChunkRequestSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    values = serializer.validated_data
    root = Path(getattr(settings, 'ROSBAG_DATA_DIR', '/app/datas/rosbag-data')).resolve()
    bag_path = (root / values['bag_filename']).resolve()
    if bag_path.parent != root or not bag_path.is_file():
        return Response({'error': 'ROSBag file not found.'}, status=404)
    for field, directory, label in (
        ('booklist_filename', '/app/datas/booklist', 'Booklist'),
        ('annotation_filename', '/app/datas/annotation', 'Annotation'),
    ):
        filename = values.get(field)
        if filename and not (Path(directory) / filename).is_file():
            return Response({'error': f'{label} file not found.'}, status=404)
    try:
        duration = read_duration(bag_path)
    except Exception:
        return Response({'error': 'Unable to read ROSBag duration.'}, status=400)
    try:
        chunking_enabled = values['chunking_enabled']
        chunk_seconds = values.get('chunk_seconds', duration)
        if chunking_enabled and chunk_seconds >= duration:
            return Response(
                {'error': 'Chunk duration must be shorter than the input duration.'},
                status=400,
            )
        manifest = save_manifest(
            manifest_directory(), values['bag_filename'], duration, chunk_seconds,
            chunking_enabled=chunking_enabled,
            source_size=bag_path.stat().st_size,
            source_mtime_ns=bag_path.stat().st_mtime_ns,
            booklist_filename=values.get('booklist_filename'),
            annotation_filename=values.get('annotation_filename'),
            view_options=values.get('view_options'),
        )
    except ValueError as exc:
        return Response({'error': str(exc)}, status=400)
    except OSError:
        return Response({'error': 'Unable to save chunk manifest.'}, status=500)
    return Response(with_processing_status(manifest), status=status.HTTP_201_CREATED)


@api_view(['GET'])
def get_chunks(request, manifest_id, chunk_index=None):
    try:
        manifest = load_manifest(manifest_directory(), manifest_id)
    except FileNotFoundError:
        return Response({'error': 'Chunk manifest not found.'}, status=404)
    except (OSError, ValueError):
        return Response({'error': 'Unable to read chunk manifest.'}, status=500)
    manifest = with_processing_status(manifest)
    if chunk_index is None:
        return Response(manifest)
    if chunk_index >= len(manifest['chunks']):
        return Response({'error': 'Chunk not found.'}, status=404)
    return Response({
        'manifest_id': manifest['id'],
        'bag_filename': manifest['bag_filename'],
        'time_reference': manifest['time_reference'],
        **manifest['chunks'][chunk_index],
    })


@api_view(['POST'])
def process_chunk_view(request, manifest_id, chunk_index):
    view_ids = request.data.get('view_ids')
    if view_ids is not None and (not isinstance(view_ids, list) or not view_ids or
                                 not all(isinstance(value, str) for value in view_ids)):
        return Response({'error': 'view_ids must be a nonempty list of view IDs.'}, status=400)
    if view_ids is not None:
        from .view_registry import PROCESSORS
        if not set(view_ids).issubset({p.view_id for p in PROCESSORS}):
            return Response({'error': 'Unknown view ID.'}, status=400)
    try:
        manifest = load_manifest(manifest_directory(), manifest_id)
    except FileNotFoundError:
        return Response({'error': 'Chunk manifest not found.'}, status=404)
    except (OSError, ValueError):
        return Response({'error': 'Unable to read chunk manifest.'}, status=500)
    if chunk_index >= len(manifest['chunks']):
        return Response({'error': 'Chunk not found.'}, status=404)

    root = Path(getattr(settings, 'ROSBAG_DATA_DIR', '/app/datas/rosbag-data')).resolve()
    bag_path = (root / manifest['bag_filename']).resolve()
    if bag_path.parent != root or not bag_path.is_file():
        return Response({'error': 'ROSBag file not found.'}, status=404)
    source_stat = bag_path.stat()
    if (
        manifest.get('source_size') is not None
        and (
            manifest['source_size'] != source_stat.st_size
            or manifest.get('source_mtime_ns') != source_stat.st_mtime_ns
        )
    ):
        return Response(
            {'error': 'ROSBag file changed after the chunk manifest was created.'},
            status=status.HTTP_409_CONFLICT,
        )
    try:
        result = process_chunk(
            bag_path,
            manifest_id,
            manifest['chunks'][chunk_index],
            processed_root=manifest_directory(),
            view_options=manifest.get('view_options'),
            view_ids=view_ids,
        )
    except RuntimeError as exc:
        status_code = status.HTTP_409_CONFLICT if 'already being processed' in str(exc) else 400
        return Response({'error': str(exc)}, status=status_code)
    except Exception as exc:
        logger.exception('Unable to process chunk %s from manifest %s', chunk_index, manifest_id)
        cause = exc.reason if isinstance(exc, URLError) else exc
        if isinstance(cause, (ssl.SSLError, RequestsSSLError)):
            return Response({
                'error': (
                    'Unable to download an audio model because HTTPS certificate '
                    'verification failed. Check antivirus/proxy HTTPS inspection '
                    'or configure the backend to trust its CA certificate, then retry.'
                ),
                'code': 'model_download_tls_error',
            }, status=503)
        return Response({'error': 'Unable to process chunk.'}, status=500)

    result = attach_metadata(result, manifest.get('booklist_filename'),
                             manifest.get('annotation_filename'), manifest['chunks'][chunk_index])
    booklist_filename = manifest.get('booklist_filename')
    from .views import load_ai_records
    annotation_name = build_ai_record_annotation_name(
        manifest['bag_filename'], booklist_filename,
    )
    try:
        ai_records = load_ai_records(annotation_name, manifest['id'], chunk_index)
    except (OSError, ValueError):
        return Response({'error': 'Unable to read AI records.'}, status=500)
    if result.get('video_path') and (view_ids is None or 'video' in view_ids):
        context_id = str(uuid4())
        cache.set('chat:' + context_id, {'frames': [], 'history': ''}, timeout=86400)
        result['chat_context_id'] = context_id
    return Response({
        'manifest_id': manifest['id'],
        'bag_filename': manifest['bag_filename'],
        'time_reference': manifest['time_reference'],
        'ai_records': ai_records,
        **result,
    })
