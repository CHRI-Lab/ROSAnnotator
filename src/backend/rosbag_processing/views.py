from .data_utils import get_rosbag_duration, load_annotation, transcribe_audio_to_srt, read_annotation_metadata
from django.core.cache import cache
from django.conf import settings
from uuid import UUID, uuid4
import json
import hashlib
import math
import os
import re
import base64
import math
import subprocess
from pathlib import Path
import cv2
from django.http import JsonResponse
from datetime import datetime, timezone
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
from .serializers import (
    BooklistSerializer, 
    InputInspectionSerializer, 
    SaveAnnotationSerializer,
    TranscriptionRequestSerializer)
import csv
import fcntl
import tempfile
from django.views.decorators.csrf import csrf_exempt
from dotenv import load_dotenv
from openai import APIConnectionError, APIStatusError
from .ai_assistant import (
    LocalInferenceError,
    RemoteAPI,
    RemoteAuthenticationError,
    RemoteResponseError,
    create_local_ai,
)

load_dotenv()

# Backward-compatible fallback for clients that do not yet send a context ID.
gpt_history = ""
gpt_history_generation = 0
video_frames = []

openai_api_key = os.getenv("OPENAI_API_KEY")
ROSBAG_DATA_DIR = '/app/datas/rosbag-data/'
PROCESSED_DATA_DIR = '/app/processed_data'

# These views either use dedicated, server-controlled contexts below or do not
# yet have a supported model-content route (audio/waveform). Never accept a raw
# client-provided full-chunk copy through the generic context channel.
DEDICATED_ASSISTANT_CONTEXT_VIEWS = {
    "audio", "video", "transcript", "waveform", "annotations",
    "statistics-annotations", "statistics-tiers", "codebook",
}


def select_video_frame_indices(timestamps, max_frames=50,
                               start_seconds=None, end_seconds=None):
    """Choose at most max_frames by actual presentation timestamp."""
    candidates = [
        index for index, seconds in enumerate(timestamps)
        if (start_seconds is None or seconds >= start_seconds)
        and (end_seconds is None or seconds < end_seconds)
    ]
    if not candidates:
        return []
    count = min(len(candidates), max_frames)
    offsets = sorted({
        round(index * (len(candidates) - 1) / max(count - 1, 1))
        for index in range(count)
    })
    return [candidates[offset] for offset in offsets]


def video_frame_timestamps(path):
    """Read each decoded frame's presentation timestamp without estimating FPS."""
    try:
        result = subprocess.run(
            [
                'ffprobe', '-v', 'error', '-select_streams', 'v:0',
                '-show_entries', 'frame=best_effort_timestamp_time',
                '-of', 'json', str(path),
            ],
            check=True, capture_output=True, text=True,
        )
        frames = json.loads(result.stdout).get('frames', [])
        timestamps = [float(frame['best_effort_timestamp_time']) for frame in frames]
    except (OSError, subprocess.CalledProcessError, ValueError, KeyError,
            TypeError, json.JSONDecodeError) as error:
        raise ValueError('Selected video frame timestamps could not be read.') from error
    if not timestamps or any(not math.isfinite(value) or value < 0 for value in timestamps):
        raise ValueError('Selected video has no valid frame timestamps.')
    return timestamps


def frames_for_video(video_path, max_frames=50, start_seconds=None, end_seconds=None):
    """Return JPEG data and an audit trail for frames inside the selected range."""
    if not isinstance(video_path, str) or not video_path or Path(video_path).is_absolute():
        raise ValueError('Invalid video path.')
    root = Path(PROCESSED_DATA_DIR).resolve()
    path = (root / video_path).resolve()
    if root not in path.parents or path.suffix.lower() != '.mp4' or not path.is_file():
        raise ValueError('Selected video was not found.')

    capture = cv2.VideoCapture(str(path))
    try:
        if not capture.isOpened():
            raise ValueError('Selected video could not be opened.')
        timestamps = video_frame_timestamps(path)
        positions = select_video_frame_indices(
            timestamps, max_frames=max_frames,
            start_seconds=start_seconds, end_seconds=end_seconds,
        )
        if not positions:
            raise ValueError('Selected time range has no readable video frames.')
        frames = []
        audit = []
        for position in positions:
            capture.set(cv2.CAP_PROP_POS_FRAMES, position)
            success, frame = capture.read()
            if not success:
                continue
            encoded, buffer = cv2.imencode('.jpg', frame)
            if encoded:
                jpeg = buffer.tobytes()
                frames.append(base64.b64encode(jpeg).decode('ascii'))
                audit.append({
                    'frame_index': position,
                    'chunk_relative_seconds': timestamps[position],
                    'sha256': hashlib.sha256(jpeg).hexdigest(),
                })
        if not frames:
            raise ValueError('Selected video has no readable frames.')
        return frames, audit
    finally:
        capture.release()


def validate_context_time_range(value, duration):
    if value is None:
        return None
    if not isinstance(value, dict) or set(value) != {'start', 'end'}:
        raise ValueError('time_range must contain start and end seconds.')
    start, end = value.get('start'), value.get('end')
    if (type(start) not in (int, float) or type(end) not in (int, float)
            or not math.isfinite(start) or not math.isfinite(end)):
        raise ValueError('Time range boundaries must be finite seconds.')
    if type(duration) not in (int, float) or not math.isfinite(duration) or duration <= 0:
        raise ValueError('A valid current chunk duration is required.')
    if start < 0 or start >= end or end > duration:
        raise ValueError('Select a time range within the current chunk.')
    return float(start), float(end)


_CLOCK_TOKEN = r'\d{1,3}:\d{2}(?::\d{2})?'
_CLOCK_RANGE = re.compile(
    rf'(?P<start>{_CLOCK_TOKEN})\s*(?:-|–|—|to)\s*(?P<end>{_CLOCK_TOKEN})',
    re.IGNORECASE,
)
_CLOCK_POINT = re.compile(_CLOCK_TOKEN)
_NUMBER_RANGE = re.compile(
    r'(?:(?:from|between)\s+)?(?P<start>\d+(?:\.\d+)?)\s*'
    r'(?P<start_unit>hours?|hrs?|h|minutes?|mins?|m|seconds?|secs?|s)?\s*'
    r'(?:-|–|—|to|and)\s*(?P<end>\d+(?:\.\d+)?)\s*'
    r'(?P<end_unit>hours?|hrs?|h|minutes?|mins?|m|seconds?|secs?|s)\b',
    re.IGNORECASE,
)
_NUMBER_POINT = re.compile(
r'\b(?:at\s+(?:time\s+)?|timestamp\s*[:=]?\s*|t\s*=\s*)'
r'(?P\d+(?:.\d+)?)\s*'
r'(?Phours?|hrs?|h|minutes?|mins?|m|seconds?|secs?|s)\b',
re.IGNORECASE,
)


def _clock_seconds(value):
    parts = [int(part) for part in value.split(':')]
    if len(parts) == 2:
        minutes, seconds = parts
        if seconds >= 60:
            return None
        return minutes * 60 + seconds
    hours, minutes, seconds = parts
    if minutes >= 60 or seconds >= 60:
        return None
    return hours * 3600 + minutes * 60 + seconds


def _unit_seconds(value, unit):
    normalized = unit.casefold()
    multiplier = 3600 if normalized.startswith('h') else 60 if normalized.startswith('m') else 1
    return float(value) * multiplier


def prompt_time_references(message):
    """Return explicit chunk-local time points/ranges mentioned in a prompt."""
    text = str(message or '')
    references = []
    consumed = []

    for match in _CLOCK_RANGE.finditer(text):
        start = _clock_seconds(match.group('start'))
        end = _clock_seconds(match.group('end'))
        if start is not None and end is not None:
            references.append(('range', float(min(start, end)), float(max(start, end))))
            consumed.append(match.span())

    for match in _NUMBER_RANGE.finditer(text):
        end_unit = match.group('end_unit')
        start_unit = match.group('start_unit') or end_unit
        start = _unit_seconds(match.group('start'), start_unit)
        end = _unit_seconds(match.group('end'), end_unit)
        references.append(('range', min(start, end), max(start, end)))
        consumed.append(match.span())

    def already_consumed(span):
        return any(span[0] >= start and span[1] <= end for start, end in consumed)

    for match in _CLOCK_POINT.finditer(text):
        if already_consumed(match.span()):
            continue
        seconds = _clock_seconds(match.group(0))
        if seconds is not None:
            references.append(('point', float(seconds), float(seconds)))

    for match in _NUMBER_POINT.finditer(text):
        if already_consumed(match.span()):
            continue
        seconds = _unit_seconds(match.group('value'), match.group('unit'))
        references.append(('point', seconds, seconds))
    return references


def _format_context_time(seconds):
    whole = int(seconds)
    hours, remainder = divmod(whole, 3600)
    minutes, value = divmod(remainder, 60)
    return f'{hours:02}:{minutes:02}:{value:02}' if hours else f'{minutes:02}:{value:02}'


def prompt_time_range_error(message, selected_range):
    """Explain explicit prompt times that escape the selected half-open range."""
    if selected_range is None:
        return None
    selected_start, selected_end = selected_range
    outside = []
    for kind, start, end in prompt_time_references(message):
        if kind == 'range':
            if start < selected_start or end > selected_end:
                outside.append(f'{_format_context_time(start)}–{_format_context_time(end)}')
        elif start < selected_start or start >= selected_end:
            outside.append(_format_context_time(start))
    if not outside:
        return None
    requested = ', '.join(dict.fromkeys(outside))
    selected = f'{_format_context_time(selected_start)}–{_format_context_time(selected_end)}'
    return (
        f'Your prompt references {requested}, outside the selected time range {selected}. '
        'Update Range start and Range end to include the requested time, then try again.'
    )


def transcript_for_time_range(transcript, start, end):
    """Keep timestamped transcript entries overlapping a chunk-relative range."""
    entries = []
    matches = list(re.finditer(r'\[(\d+):(\d{2})\]', transcript or ''))
    for index, match in enumerate(matches):
        entry_start = int(match.group(1)) * 60 + int(match.group(2))
        entry_end = (
            int(matches[index + 1].group(1)) * 60 + int(matches[index + 1].group(2))
            if index + 1 < len(matches) else math.inf
        )
        if entry_start < end and entry_end > start:
            boundary = matches[index + 1].start() if index + 1 < len(matches) else len(transcript)
            entries.append(transcript[match.start():boundary].strip())
    return '\n'.join(entries)


def timeline_for_time_range(timeline, start, end):
    if not isinstance(timeline, list):
        return timeline
    filtered = []
    for axis in timeline:
        if not isinstance(axis, dict):
            continue
        block_key = 'blocks' if isinstance(axis.get('blocks'), list) else 'annotationBlocks'
        blocks = axis.get(block_key, [])
        # Deletion instructions are applied to the full client-side block array.
        # Keep that position when exposing only the selected range to the model.
        selected = [
            {**block, 'blockIndex': block_index}
            for block_index, block in enumerate(blocks)
            if isinstance(block, dict)
            and type(block.get('start')) in (int, float)
            and type(block.get('end')) in (int, float)
            and block['start'] < end and block['end'] > start
        ]
        filtered.append({**axis, block_key: selected})
    return filtered


@api_view(['POST'])
def inspect_input(request):
    """Return ROSBag duration before the user chooses a chunking strategy."""
    serializer = InputInspectionSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    bag_filename = serializer.validated_data['bag_filename']
    bag_filepath = os.path.join(ROSBAG_DATA_DIR, bag_filename)
    if not os.path.isfile(bag_filepath):
        return Response(
            {'error': 'ROSBag file not found.'},
            status=status.HTTP_404_NOT_FOUND,
        )

    try:
        from .rosbag_reader import RosbagReader
        with RosbagReader(bag_filepath) as reader:
            duration_seconds = round(reader.duration, 3)
            topics = list(reader.topics.values())
    except Exception as exc:
        return Response(
            {'error': f'Unable to read ROSBag duration: {str(exc)}'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    return Response({
        'bag_filename': bag_filename,
        'duration_seconds': duration_seconds,
        'duration_minutes': round(duration_seconds / 60, 3),
        'supports_chunking': duration_seconds > 0,
        'topics': topics,
    })
ANNOTATION_PATH = "/app/datas/annotation/"


def build_ai_record(
    assistant,
    requested_mode,
    actual_mode,
    response_text,
    context_routes,
    selected_data_views=None,
    timeline_scope=None,
    timeline_context=None,
    selected_range=None,
    current_chunk=None,
    video_frame_samples=None,
):
    """Build a secret-free record of one successful model interaction."""
    provider_metadata = assistant.get_run_metadata()
    if not isinstance(provider_metadata, dict):
        provider_metadata = {}

    scope_axis_ids = (
        timeline_scope.get("axis_ids", [])
        if isinstance(timeline_scope, dict) else []
    )
    axes_by_id = {
        axis.get("id", axis.get("axisId")): axis
        for axis in (timeline_context if isinstance(timeline_context, list) else [])
        if isinstance(axis, dict)
    }
    selected_timelines = [
        {
            "axis_id": axis_id,
            "axis_name": axes_by_id.get(axis_id, {}).get("axisName"),
        }
        for axis_id in scope_axis_ids
    ]
    chunk = current_chunk or {
        "index": 0,
        "start_seconds": 0.0,
        "end_seconds": None,
        "is_chunked": False,
    }
    recorded_range = None
    if selected_range is not None:
        start, end = selected_range
        offset = chunk["start_seconds"]
        recorded_range = {
            "chunk_relative_seconds": {"start": start, "end": end},
            "whole_video_seconds": {
                "start": offset + start,
                "end": offset + end,
            },
        }
    frame_samples = []
    for sample in video_frame_samples or []:
        seconds = sample['chunk_relative_seconds']
        frame_samples.append({
            **sample,
            'whole_video_seconds': chunk['start_seconds'] + seconds,
        })

    return {
        "schema_version": 1,
        "run_id": str(uuid4()),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "model_selection": {
            "requested": requested_mode,
            "used": actual_mode,
            "context_routes": context_routes,
        },
        "model": provider_metadata.get("model", {
            "provider": actual_mode,
            "requested": None,
            "resolved": None,
        }),
        "parameters": provider_metadata.get("parameters", {}),
        "prompts": provider_metadata.get("prompts", {}),
        "ai_response": response_text,
        "request_options": {
            "selected_data_types": list(selected_data_views or []),
            "selected_timelines": selected_timelines,
            "allow_new_timeline": bool(
                isinstance(timeline_scope, dict) and timeline_scope.get("allow_new")
            ),
            "selected_time_range": recorded_range,
            "video_frames": {
                "count": len(frame_samples),
                "samples": frame_samples,
            },
            "current_chunk": chunk,
        },
    }


def ai_records_file_path(annotation_name, manifest_id=None):
    suffix = f"_{manifest_id}" if manifest_id else ""
    return os.path.join(ANNOTATION_PATH, f"ai_records_{annotation_name}{suffix}.json")


def load_ai_records(annotation_filename, manifest_id=None, chunk_index=None):
    annotation_name = (
        annotation_filename[:-4]
        if annotation_filename.endswith(".csv")
        else annotation_filename
    )
    file_path = ai_records_file_path(annotation_name, manifest_id)
    if not os.path.exists(file_path):
        return []

    with open(file_path, "r") as record_file:
        payload = json.load(record_file)
    records = payload.get("ai_runs", []) if isinstance(payload, dict) else payload
    if not isinstance(records, list):
        return []
    if chunk_index is not None:
        return [record for record in records if isinstance(record, dict)
                and record.get('chunk_index') == chunk_index]
    return records


@api_view(['POST'])
def complete_ai_record(request):
    """Persist one completed prompt/reply/action outcome independently of annotation saves."""
    annotation_name = request.data.get('annotation_name')
    record = request.data.get('ai_record')
    outcome = request.data.get('outcome')
    manifest_id = request.data.get('manifest_id')
    chunk_index = request.data.get('chunk_index')
    try:
        manifest_id = str(UUID(str(manifest_id))) if manifest_id is not None else None
    except (ValueError, TypeError, AttributeError):
        return JsonResponse({'error': 'Invalid manifest ID'}, status=400)
    if (
        not isinstance(annotation_name, str)
        or not annotation_name.strip()
        or annotation_name != os.path.basename(annotation_name)
        or '/' in annotation_name
        or '\\' in annotation_name
        or not isinstance(record, dict)
        or not isinstance(record.get('run_id'), str)
        or not record['run_id']
        or outcome not in {'replied', 'applied', 'rejected', 'not_applied'}
        or (manifest_id is None and chunk_index is not None)
        or (chunk_index is not None and (type(chunk_index) is not int or chunk_index < 0))
    ):
        return JsonResponse({'error': 'Invalid completed AI record'}, status=400)

    completed_record = {
        **record,
        'action_outcome': outcome,
        'completed_at': datetime.now(timezone.utc).isoformat(),
    }
    if chunk_index is not None:
        completed_record['chunk_index'] = chunk_index
    os.makedirs(ANNOTATION_PATH, exist_ok=True)
    record_path = ai_records_file_path(annotation_name, manifest_id)
    lock_path = f'{record_path}.lock'
    temporary_path = None
    try:
        with open(lock_path, 'a+') as lock_file:
            fcntl.flock(lock_file, fcntl.LOCK_EX)
            existing = load_ai_records(annotation_name, manifest_id)
            if not isinstance(existing, list):
                raise ValueError('Existing AI record file is invalid')
            record_index = next(
                (index for index, item in enumerate(existing)
                 if isinstance(item, dict) and item.get('run_id') == record['run_id']),
                None,
            )
            if record_index is None:
                existing.append(completed_record)
            else:
                # Retries of the same completed request must not duplicate it.
                existing[record_index] = completed_record
            with tempfile.NamedTemporaryFile(
                mode='w', encoding='utf-8', dir=ANNOTATION_PATH,
                prefix='.ai-record-', suffix='.tmp', delete=False,
            ) as temporary_file:
                temporary_path = temporary_file.name
                json.dump({
                    'schema_version': 1,
                    'annotation_name': annotation_name,
                    'ai_runs': existing,
                }, temporary_file, indent=2)
                temporary_file.flush()
                os.fsync(temporary_file.fileno())
            os.replace(temporary_path, record_path)
            temporary_path = None
    except Exception as error:
        return JsonResponse({'error': f'Unable to save AI record: {error}'}, status=500)
    finally:
        if temporary_path and os.path.exists(temporary_path):
            os.unlink(temporary_path)
    return JsonResponse({'saved': True, 'run_id': record['run_id']})



@api_view(['POST'])
def process_rosbag(request):
    """Legacy HTTP adapter for the shared whole-bag session contract."""
    from .processing_sessions import ProcessingError, ProcessingRequest
    from .rosbag_session import RosbagProcessingSession
    from .rosbag_reader import BagReadError

    if not request.data.get('bag_filename'):
        return Response({'error': 'bag_filename is required'}, status=400)
    serializer = InputInspectionSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    bag_filename = serializer.validated_data['bag_filename']
    session = RosbagProcessingSession()
    try:
        result = session.process(ProcessingRequest(
            bag_path=os.path.join(ROSBAG_DATA_DIR, bag_filename),
            processed_root=getattr(settings, 'PROCESSED_DATA_DIR', '/app/processed_data'),
            booklist_filename=request.data.get('booklist_filename'),
            annotation_filename=request.data.get('annotation_filename'),
            view_options=serializer.validated_data['view_options'],
            view_ids=serializer.validated_data.get('view_ids'),
        ))
    except ProcessingError as exc:
        return Response({'error': str(exc)}, status=exc.status_code)
    except BagReadError as exc:
        return Response({'error': str(exc), 'code': 'invalid_rosbag'}, status=400)
    except Exception as exc:
        return Response({'error': str(exc)}, status=500)
    result['ai_records'] = load_ai_records(request.data['annotation_filename']) if request.data.get('annotation_filename') else []
    selected_views = serializer.validated_data.get('view_ids')
    if result.get('video_path') and (selected_views is None or 'video' in selected_views):
        context_id = str(uuid4())
        cache.set('chat:' + context_id, {'frames': session.video_frames[::max(1, len(session.video_frames) // 50)][:50], 'history': ''}, timeout=86400)
        result['chat_context_id'] = context_id
    return Response(result)


@api_view(['GET'])
def view_catalog(request):
    from .view_registry import PROCESSORS
    return Response({'views': [{'view_id': p.view_id,
                               'supported_message_types': p.supported_message_types}
                              for p in PROCESSORS]})


@api_view(['POST'])
def clear_gpt_history(request):
    global gpt_history, gpt_history_generation
    context_id = str(request.data.get('chat_context_id') or '')
    if context_id:
        cache.delete('chat:' + context_id)
    else:
        gpt_history = ""
        gpt_history_generation += 1
    return JsonResponse({"cleared": True})


@api_view(['POST'])
def gpt_chat(request):
    global gpt_history
    try:
        history_generation = gpt_history_generation
        data = json.loads(request.body)
        context_id = str(data.get('chat_context_id') or '')
        context = (
            cache.get('chat:' + context_id, {'frames': [], 'history': ''})
            if context_id else {'frames': video_frames, 'history': gpt_history}
        )
        context_frames = context['frames']
        conversation_history = context['history']
        message = data.get("message")
        audio_transcript = data.get("audio_transcript")
        Axiinfo = data.get("Axeinfo")
        Codebook = data.get("Codebook")
        allowed_data_views = {
            "audio", "video", "transcript", "waveform", "annotations",
            "statistics-annotations", "statistics-tiers", "codebook",
        }
        raw_selected_data_views = data.get("selected_data_views")
        selected_data_views = (
            list(allowed_data_views)
            if raw_selected_data_views is None
            else raw_selected_data_views
        )
        if (
            not isinstance(selected_data_views, list)
            or any(
                not isinstance(view_id, str) or view_id not in allowed_data_views
                for view_id in selected_data_views
            )
        ):
            return JsonResponse({"error": "Invalid selected data views"}, status=400)
        selected_data_views = list(dict.fromkeys(selected_data_views))
        selected_data_view_set = set(selected_data_views)
        raw_data_view_contexts = data.get("data_view_contexts", {})
        if not isinstance(raw_data_view_contexts, dict):
            return JsonResponse({"error": "Invalid data view contexts"}, status=400)
        def safe_view_payload(value):
            if isinstance(value, dict):
                return {
                    key: safe_view_payload(item)
                    for key, item in value.items()
                    if key != "artifacts"
                }
            if isinstance(value, list):
                return [safe_view_payload(item) for item in value]
            return value if isinstance(value, (str, int, float, bool)) or value is None else str(value)

        data_view_contexts = {
            view_id: safe_view_payload(payload)
            for view_id, payload in raw_data_view_contexts.items()
            if (
                view_id in selected_data_view_set
                and view_id not in DEDICATED_ASSISTANT_CONTEXT_VIEWS
            )
        }
        timeline_view_ids = {
            "annotations", "statistics-annotations", "statistics-tiers"
        }
        timeline_selected = bool(selected_data_view_set & timeline_view_ids)
        timeline_scope = data.get("timeline_scope")
        if timeline_scope is not None:
            if not isinstance(timeline_scope, dict):
                return JsonResponse({"error": "Invalid timeline scope"}, status=400)
            raw_axis_ids = timeline_scope.get("axis_ids", [])
            allow_new = timeline_scope.get("allow_new", False)
            if (
                not isinstance(raw_axis_ids, list)
                or any(isinstance(value, bool) or not isinstance(value, int) for value in raw_axis_ids)
                or not isinstance(allow_new, bool)
            ):
                return JsonResponse({"error": "Invalid timeline scope"}, status=400)
            timeline_scope = {
                "axis_ids": list(dict.fromkeys(raw_axis_ids)),
                "allow_new": allow_new,
            }
        scope_axis_ids = set(
            timeline_scope.get("axis_ids", [])
            if isinstance(timeline_scope, dict) else []
        )
        if not timeline_selected:
            # A selected axis is an explicit, narrow action context. Enforce
            # that scope server-side even if a client sends additional axes.
            Axiinfo = [
                axis for axis in (Axiinfo if isinstance(Axiinfo, list) else [])
                if isinstance(axis, dict)
                and axis.get("id", axis.get("axisId")) in scope_axis_ids
            ]
        timeline_context_available = timeline_selected or bool(scope_axis_ids)
        assistant_mode = data.get("assistant_mode", "remote")
        context_routes = data.get("context_routes", {})
        fallback_consent = data.get("fallback_consent")
        try:
            selected_range = validate_context_time_range(
                data.get('time_range'), data.get('context_duration'),
            )
        except ValueError as error:
            return JsonResponse({'error': str(error)}, status=400)
        prompt_range_error = prompt_time_range_error(message, selected_range)
        if prompt_range_error:
            return JsonResponse({'error': prompt_range_error}, status=400)
        raw_current_chunk = data.get("current_chunk")
        current_chunk = None
        if raw_current_chunk is not None:
            if not isinstance(raw_current_chunk, dict):
                return JsonResponse({"error": "Invalid current chunk"}, status=400)
            chunk_index = raw_current_chunk.get("index")
            chunk_start = raw_current_chunk.get("start_seconds")
            chunk_end = raw_current_chunk.get("end_seconds")
            is_chunked = raw_current_chunk.get("is_chunked")
            if (
                type(chunk_index) is not int or chunk_index < 0
                or isinstance(chunk_start, bool) or not isinstance(chunk_start, (int, float))
                or isinstance(chunk_end, bool) or not isinstance(chunk_end, (int, float))
                or chunk_start < 0 or chunk_end <= chunk_start
                or type(is_chunked) is not bool
            ):
                return JsonResponse({"error": "Invalid current chunk"}, status=400)
            current_chunk = {
                "index": chunk_index,
                "start_seconds": float(chunk_start),
                "end_seconds": float(chunk_end),
                "is_chunked": is_chunked,
            }
        requested_mode = assistant_mode
        accepted_local_to_remote = (
            isinstance(fallback_consent, dict)
            and fallback_consent.get("from") == "local"
            and fallback_consent.get("to") == "remote"
            and fallback_consent.get("user_consented") is True
        )
        accepted_remote_to_local = (
            isinstance(fallback_consent, dict)
            and fallback_consent.get("from") == "remote"
            and fallback_consent.get("to") == "local"
            and fallback_consent.get("user_consented") is True
        )
        if accepted_local_to_remote:
            requested_mode = "local"
        elif accepted_remote_to_local:
            requested_mode = "remote"


        if not message:
            return JsonResponse({"error": "No message provided"}, status=400)
        if "transcript" in selected_data_view_set and not audio_transcript:
            return JsonResponse({"error": "Selected transcript data is unavailable"}, status=400)
        if assistant_mode not in {"remote", "local"}:
            return JsonResponse({"error": "Invalid assistant mode"}, status=400)
        if not isinstance(context_routes, dict) or any(
            target != assistant_mode for target in context_routes.values()
        ):
            return JsonResponse({"error": "Invalid context routes"}, status=400)

        selected_video_path = (
            data.get('video_path') if "video" in selected_data_view_set else None
        )
        request_frame_samples = []
        try:
            if selected_video_path is not None:
                request_frames, request_frame_samples = frames_for_video(
                    selected_video_path,
                    start_seconds=selected_range[0] if selected_range is not None else None,
                    end_seconds=selected_range[1] if selected_range is not None else None,
                )
            else:
                request_frames = context_frames
        except ValueError as error:
            return JsonResponse({'error': str(error)}, status=400)

        if selected_range is not None:
            start, end = selected_range
            if "transcript" in selected_data_view_set:
                audio_transcript = transcript_for_time_range(audio_transcript, start, end)
            if timeline_context_available:
                Axiinfo = timeline_for_time_range(Axiinfo, start, end)
            if "transcript" in selected_data_view_set and not audio_transcript:
                return JsonResponse(
                    {'error': 'No transcript data exists in the selected time range.'},
                    status=400,
                )

        common_context = {
            "transcriptContext": audio_transcript if "transcript" in selected_data_view_set else "",
            "frameContext": request_frames if "video" in selected_data_view_set else [],
            "codebookContext": Codebook if "codebook" in selected_data_view_set else {},
            "timelineContext": Axiinfo if timeline_context_available else [],
        }
        if raw_selected_data_views is not None:
            common_context["selectedDataViews"] = selected_data_views
            common_context["dataViewContexts"] = data_view_contexts
        has_timeline_scope = bool(scope_axis_ids) or bool(
            isinstance(timeline_scope, dict) and timeline_scope.get("allow_new")
        )
        if not selected_data_views and not has_timeline_scope:
            # A confirmed empty selection is prompt-only: do not expose axis IDs
            # or grant model-generated timeline changes without evidence.
            common_context["timelineScope"] = {"axis_ids": [], "allow_new": False}
        elif timeline_scope is not None:
            common_context["timelineScope"] = timeline_scope
        request_history = conversation_history if selected_data_views or has_timeline_scope else ""
        if assistant_mode == "local":
            assistant = create_local_ai(
                **common_context,
                checkpointPath=os.getenv("LOCAL_AI_CHECKPOINT_PATH", ""),
            )
            try:
                response_text = assistant.respond(message, request_history)
            except LocalInferenceError as error:
                remote_configured = bool(openai_api_key)
                error_message = str(error) or "The local language model is not connected."
                return JsonResponse(
                    {
                        "error": (
                            f"{error_message} "
                            + ("Would you like to switch to Remote?" if remote_configured else "")
                        ),
                        "assistant_mode": "local",
                        "can_fallback_to_remote": remote_configured,
                    },
                    status=501,
                )
        else:
            if not openai_api_key:
                return JsonResponse(
                    {
                        "error": (
                            "Remote AI is unavailable because the OpenAI API key is "
                            "empty. Would you like to switch to Local?"
                        ),
                        "assistant_mode": "remote",
                        "can_fallback_to_local": True,
                    },
                    status=503,
                )
            try:
                assistant = RemoteAPI(
                    **common_context,
                    APIKey=openai_api_key,
                )
                response_text = assistant.respond(message, request_history)
            except RemoteAuthenticationError:
                return JsonResponse(
                    {
                        "error": (
                            "Remote AI is unavailable because the OpenAI API key is "
                            "invalid. Would you like to switch to Local?"
                        ),
                        "assistant_mode": "remote",
                        "can_fallback_to_local": True,
                    },
                    status=503,
                )
            except RemoteResponseError as error:
                return JsonResponse(
                    {"error": str(error), "assistant_mode": "remote"},
                    status=502,
                )
            except (APIConnectionError, APIStatusError, TimeoutError) as error:
                return JsonResponse(
                    {
                        "error": (
                            f"Remote AI is unavailable: {error}. "
                            "Would you like to switch to Local?"
                        ),
                        "assistant_mode": "remote",
                        "can_fallback_to_local": True,
                    },
                    status=503,
                )

        if context_id:
            cache.set(
                'chat:' + context_id,
                {**context, 'history': conversation_history + message + (response_text or '')},
                timeout=86400,
            )
        elif history_generation == gpt_history_generation:
            gpt_history = conversation_history + message + (response_text or '')
        ai_record = build_ai_record(
            assistant=assistant,
            requested_mode=requested_mode,
            actual_mode=assistant_mode,
            response_text=response_text,
            context_routes=context_routes,
            selected_data_views=selected_data_views,
            timeline_scope=timeline_scope,
            timeline_context=Axiinfo,
            selected_range=selected_range,
            current_chunk=current_chunk,
            video_frame_samples=request_frame_samples,
        )
        return JsonResponse(
            {
                "response": response_text,
                "assistant_mode": assistant_mode,
                "ai_record": ai_record,
            }
        )
    
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)
    
@api_view(['GET'])
def list_filenames(request):
    # Define folder paths
    if request.method == 'GET':
        rosbag_file_folder_path = '/app/datas/rosbag-data/'
        booklist_folder_path = '/app/datas/booklist/'
        annotation_folder_path = '/app/datas/annotation/'

        # Validate folder paths
        if not all(map(os.path.isdir, [rosbag_file_folder_path, booklist_folder_path, annotation_folder_path])):
            return JsonResponse({'error': 'Invalid folder paths'}, status=500)

        # List files in the directories
        rosbag_files = [file for file in os.listdir(rosbag_file_folder_path) if file.endswith('.bag')]
        booklist_files = [file for file in os.listdir(booklist_folder_path) if file.endswith('.json')]
        annotation_files = [file for file in os.listdir(annotation_folder_path) if file.endswith('.csv')]

        # Return the list of files as JSON response
        return Response({
            'rosbag_files': rosbag_files,
            'booklist_files': booklist_files,
            'annotation_files': annotation_files
        })


# For testing if the transcibe_audio is working 
@api_view(['POST'])
def transcribe_audio(request):
    serializer = TranscriptionRequestSerializer(data=request.data)
    if serializer.is_valid():
        audio_file_path = serializer.validated_data['audio_file_path']
        output_folder_path = serializer.validated_data['output_folder_path']
        try:
            srt_file_path = transcribe_audio_to_srt(audio_file_path, output_folder_path)
            return Response({"srt_file_path": srt_file_path}, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        
@api_view(['POST'])
def update_booklist(request):
    booklist_path = '/app/datas/booklist/'
    
    if not os.path.exists(booklist_path):
        os.makedirs(booklist_path)
    
    serializer = BooklistSerializer(data=request.data)
    
    if serializer.is_valid():
        booklist_name = serializer.validated_data['name']
        booklist_data = serializer.validated_data['data']

        print(booklist_data)
        
        booklist_file_path = os.path.join(booklist_path, booklist_name)

        try:
            with open(booklist_file_path, 'w') as f:
                json.dump(booklist_data, f, indent=4)
            
            return Response({"message": "Booklist created/updated successfully", "New BookList": booklist_data}, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    else:
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
def describe_existing_annotation(file_path, annotation_name):
    """Summarise a file that a save is about to replace.

    Returns None when nothing is there. A file that cannot be parsed is
    reported rather than silently overwritten: it may not be an annotation
    file at all.
    """
    if not os.path.isfile(file_path):
        return None

    modified_at = datetime.fromtimestamp(
        os.path.getmtime(file_path), tz=timezone.utc,
    ).isoformat()

    try:
        existing = load_annotation(f'{annotation_name}.csv', ANNOTATION_PATH)
    except Exception:
        return {
            'reason': 'file_unreadable',
            'annotation_name': annotation_name,
            'modified_at': modified_at,
        }

    return {
        'reason': 'file_exists',
        'annotation_name': annotation_name,
        'modified_at': modified_at,
        'axis_count': len(existing),
        'block_count': sum(
            len(axis.get('annotationBlocks', [])) for axis in existing
        ),
    }

def describe_chunk_conflict(file_path, annotation_name, chunk):
    """Describe what a chunk save would do to an existing file.

    Counts blocks the chunk currently displays, using the same clip_to_chunk
    rule the merge uses, so the prompt cannot describe a different set from
    the one that gets replaced.
    """
    if not os.path.isfile(file_path):
        return None

    modified_at = datetime.fromtimestamp(
        os.path.getmtime(file_path), tz=timezone.utc,
    ).isoformat()

    try:
        existing = load_annotation(f'{annotation_name}.csv', ANNOTATION_PATH)
    except Exception:
        return {
            'reason': 'file_unreadable',
            'annotation_name': annotation_name,
            'modified_at': modified_at,
        }

    from .view_metadata import clip_to_chunk

    in_chunk = sum(
        1
        for axis in existing
        for block in axis.get('annotationBlocks', [])
        if clip_to_chunk(block, chunk) is not None
    )
    total = sum(len(axis.get('annotationBlocks', [])) for axis in existing)

    return {
        'reason': 'chunk_has_annotations' if in_chunk else 'chunk_is_empty',
        'annotation_name': annotation_name,
        'modified_at': modified_at,
        'axis_count': len(existing),
        'block_count': total,
        'chunk_block_count': in_chunk,
        'chunk_index': chunk['index'],
        'chunk_start_seconds': chunk['start_seconds'],
        'chunk_end_seconds': chunk['end_seconds'],
    }

def _same_block(incoming, original, clipped):
    """True when an incoming block is the unedited clipped form of original.

    Times alone are not enough: editing only the text of a block leaves its
    bounds identical, and treating that as unedited would restore the old text.
    """
    return (
        math.isclose(incoming['start'], clipped[0], abs_tol=1e-6)
        and math.isclose(incoming['end'], clipped[1], abs_tol=1e-6)
        and (incoming.get('text') or '') == (original.get('text') or '')
    )


def _source_block(incoming, displayed):
    """Find the absolute block represented by a chunk-clipped UI block."""
    source_start = incoming.get('sourceStart')
    source_end = incoming.get('sourceEnd')
    if source_start is None or source_end is None:
        return None
    return next(
        ((original, clipped) for original, clipped in displayed
         if math.isclose(original['start'], source_start, abs_tol=1e-6)
         and math.isclose(original['end'], source_end, abs_tol=1e-6)),
        None,
    )


def _merge_source_block(incoming, original, clipped, chunk):
    """Apply visible edits without discarding an unchanged hidden edge."""
    chunk_start = chunk['start_seconds']
    chunk_end = chunk['end_seconds']
    start = (
        original['start']
        if original['start'] < chunk_start
        and math.isclose(incoming['start'], clipped[0], abs_tol=1e-6)
        else incoming['start'] + chunk_start
    )
    end = (
        original['end']
        if original['end'] > chunk_end
        and math.isclose(incoming['end'], clipped[1], abs_tol=1e-6)
        else incoming['end'] + chunk_start
    )
    return {'start': start, 'end': end, 'text': incoming.get('text', '')}


def merge_chunk_annotations(existing, incoming, chunk):
    """Replace one chunk's contribution to an absolute-time annotation set.

    incoming holds chunk-local times as annotations_for_chunk produced them.
    An incoming block still matching an existing block's clipped form is
    unedited, so the original absolute block is restored rather than replaced
    by its clipped copy. Blocks the chunk never displayed are untouched.

    Axes match on name and type: Timeline reassigns numeric ids on load, so
    they are not stable across sessions or chunks.
    """
    from .view_metadata import clip_to_chunk

    start = chunk['start_seconds']

    def key(axis):
        return (axis.get('axisName', ''), axis.get('axisType', ''))

    merged = {}
    order = []

    def slot(axis):
        axis_key = key(axis)
        if axis_key not in merged:
            order.append(axis_key)
            merged[axis_key] = {**axis, 'annotationBlocks': [], '_displayed': []}
        return merged[axis_key]

    # Carry through everything, remembering which blocks this chunk displayed.
    for axis in existing or []:
        target = slot(axis)
        for block in axis.get('annotationBlocks', []):
            clipped = clip_to_chunk(block, chunk)
            if clipped is None:
                target['annotationBlocks'].append(block)
            else:
                target['_displayed'].append((block, clipped))

    # Re-add what the chunk holds now.
    for axis in incoming or []:
        target = slot(axis)
        target.update({
            name: value for name, value in axis.items()
            if name not in ('annotationBlocks', 'id')
        })
        for block in axis.get('annotationBlocks', []):
            source = _source_block(block, target['_displayed'])
            if source is not None:
                original, clipped = source
                target['_displayed'] = [
                    pair for pair in target['_displayed'] if pair[0] is not original
                ]
                target['annotationBlocks'].append(
                    _merge_source_block(block, original, clipped, chunk)
                )
                continue
            match = next(
                (original for original, clipped in target['_displayed']
                 if _same_block(block, original, clipped)),
                None,
            )
            if match is not None:
                # Unedited: keep the original, including any part outside
                # this chunk that the user never saw.
                target['_displayed'] = [
                    pair for pair in target['_displayed'] if pair[0] is not match
                ]
                target['annotationBlocks'].append(match)
            else:
                target['annotationBlocks'].append({
                    **{name: value for name, value in block.items()
                       if name not in ('sourceStart', 'sourceEnd')},
                    'start': block['start'] + start,
                    'end': block['end'] + start,
                })

    # Anything still in _displayed was shown and is now gone: the user
    # deleted it, so it does not come back.
    result = []
    for index, axis_key in enumerate(order, start=1):
        axis = merged[axis_key]
        del axis['_displayed']
        axis['annotationBlocks'].sort(key=lambda block: block['start'])
        # load_annotation groups rows by id, so ids must be unique per axis.
        axis['id'] = index
        result.append(axis)
    return result


def annotation_bounds_error(annotation_list, duration=None):
    """Return an error when a submitted block escapes its editing timeline."""
    for axis_index, axis in enumerate(annotation_list or []):
        for block_index, block in enumerate(axis.get('annotationBlocks', [])):
            start = block['start']
            end = block['end']
            if start < 0 or end < start:
                return (
                    f'annotation_data[{axis_index}].annotationBlocks[{block_index}] '
                    'must satisfy 0 <= start <= end.'
                )
            if duration is not None and end > duration + 1e-6:
                return (
                    f'annotation_data[{axis_index}].annotationBlocks[{block_index}] '
                    f'must end at or before the timeline duration ({duration:g}s).'
                )
    return None

def resolve_chunk(manifest_id, chunk_index):
    """Return (manifest, chunk) for a manifest id and index, or raise."""
    # chunk_views imports from this module, so import inside the function.
    from .chunk_views import manifest_directory
    from .chunks import load_manifest

    manifest = load_manifest(manifest_directory(), manifest_id)
    chunks = manifest.get('chunks') or []
    if chunk_index >= len(chunks):
        raise ValueError('Chunk not found in that manifest.')
    return manifest, chunks[chunk_index]

def write_annotation_csv(file_path, annotation_list,
                         bag_filename='', source_duration=None):
    """Write atomically: the merge reads the file first, so a crash mid-write
    must not truncate a set that was complete a moment ago.

    bagFilename and sourceDuration repeat on every row. That is redundant, but
    it keeps the file a plain flat table that Excel and pandas both read without
    special handling, which is what the team already relies on.
    """
    duration_cell = '' if source_duration is None else repr(float(source_duration))
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode='w', newline='', encoding='utf-8',
            dir=os.path.dirname(file_path),
            prefix='.annotation-', suffix='.tmp', delete=False,
        ) as temporary_file:
            temporary_path = temporary_file.name
            writer = csv.DictWriter(temporary_file, fieldnames=[
                'id', 'axisType', 'axisName', 'axisBooklistName',
                'start', 'end', 'text',
                'bagFilename', 'sourceDuration',
            ])
            writer.writeheader()
            for axis in annotation_list:
                for block in axis['annotationBlocks']:
                    writer.writerow({
                        'id': axis['id'],
                        'axisType': axis.get('axisType', ''),
                        'axisName': axis.get('axisName', ''),
                        'axisBooklistName': axis.get('axisBooklistName', ''),
                        'start': block['start'],
                        'end': block['end'],
                        'text': block.get('text', ''),
                        'bagFilename': bag_filename or '',
                        'sourceDuration': duration_cell,
                    })
            temporary_file.flush()
            os.fsync(temporary_file.fileno())
        os.replace(temporary_path, file_path)
        temporary_path = None
    finally:
        if temporary_path and os.path.exists(temporary_path):
            os.unlink(temporary_path)

@csrf_exempt
@api_view(['POST'])
def save_annotation(request):
    serializer = SaveAnnotationSerializer(data=request.data)
    if not serializer.is_valid():
        return JsonResponse(serializer.errors, status=400)

    annotation_name = serializer.validated_data['annotation_name']
    annotation_list = serializer.validated_data['annotation_data']
    confirm_overwrite = serializer.validated_data['confirm_overwrite']
    manifest_id = serializer.validated_data['manifest_id']
    chunk_index = serializer.validated_data['chunk_index']
    # NEW: pulled out alongside the others, purely so the names exist.
    bag_filename = serializer.validated_data['bag_filename']
    source_duration = serializer.validated_data['source_duration']

    os.makedirs(ANNOTATION_PATH, exist_ok=True)
    file_path = os.path.join(ANNOTATION_PATH, f'{annotation_name}.csv')

    chunk = None
    manifest = None                                        
    if manifest_id is not None:
        try:
            manifest, chunk = resolve_chunk(str(manifest_id), chunk_index)   
        except FileNotFoundError:
            return JsonResponse({'error': 'Chunk manifest not found.'}, status=404)
        except (OSError, ValueError) as error:
            return JsonResponse({'error': str(error)}, status=400)

    editing_duration = (
        chunk['end_seconds'] - chunk['start_seconds']
        if chunk is not None else source_duration
    )
    bounds_error = annotation_bounds_error(annotation_list, editing_duration)
    if bounds_error:
        return JsonResponse({'annotation_data': [bounds_error]}, status=400)

    if chunk is None:
        if not confirm_overwrite:
            conflict = describe_existing_annotation(file_path, annotation_name)
            if conflict is not None:
                return JsonResponse(conflict, status=409)
    else:
        if not confirm_overwrite:
            conflict = describe_chunk_conflict(file_path, annotation_name, chunk)
            if conflict is not None:
                return JsonResponse(conflict, status=409)
        try:
            existing = load_annotation(f'{annotation_name}.csv', ANNOTATION_PATH)
        except FileNotFoundError:
            existing = []
        except Exception:
            return JsonResponse(
                describe_chunk_conflict(file_path, annotation_name, chunk),
                status=409,
            )
        
        # the merge carries through every block outside the current chunk,
        # which would restore the ones the load already discarded. It reads the
        # file, not the response, so it has to apply the same rule itself.
        from .view_metadata import clip_to_recording
        existing = clip_to_recording(existing, manifest.get('duration_seconds'))
        annotation_list = merge_chunk_annotations(existing, annotation_list, chunk)


    # a save that does not carry the source must not erase what the file
    # already recorded. Some save paths have no source to send, and silently
    # blanking provenance is worse than never having recorded it.
    if not bag_filename or source_duration is None:
        try:
            recorded = read_annotation_metadata(
                f'{annotation_name}.csv', ANNOTATION_PATH,
            )
        except (FileNotFoundError, OSError, IOError):
            recorded = {}
        bag_filename = bag_filename or recorded.get('bag_filename', '')
        if source_duration is None:
            source_duration = recorded.get('source_duration')

    try:
        # NEW: the two keyword arguments. The call itself is otherwise unchanged.
        write_annotation_csv(
            file_path, annotation_list,
            bag_filename=bag_filename,
            source_duration=source_duration,
        )
    except Exception as error:
        return JsonResponse({'error': str(error)}, status=500)

    return JsonResponse(
        {'message': 'Annotation data saved successfully'}, status=200,
    )

# testing the load_annotation function 
@api_view(['GET'])
def get_annotation(request):
    annotation_filename = request.query_params.get('annotation_filename')
    
    if not annotation_filename:
        return Response({'error': 'annotation_filename parameter is required'}, status=400)
    
    try:
        annotation_json = load_annotation(annotation_filename)
        return Response(annotation_json, status=200)
    except FileNotFoundError:
        return Response({'error': 'File not found'}, status=404)
    except Exception as e:
        return Response({'error': str(e)}, status=500)
