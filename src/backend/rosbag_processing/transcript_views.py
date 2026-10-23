import re
from pathlib import Path

from django.conf import settings
from rest_framework.decorators import api_view
from rest_framework.response import Response

from .transcript_edits import TranscriptConflict, load_transcript_view, save_transcript_edits


def transcript_directory(scope, cache_key):
    roots = {
        'whole': getattr(settings, 'PROCESSED_DATA_DIR', '/app/processed_data'),
        'chunks': getattr(settings, 'CHUNK_MANIFEST_DIR', '/app/processed_data/chunks'),
    }
    if scope not in roots or not re.fullmatch(r'(?:[0-9a-f]{64}|[0-9a-f]{8}-[0-9a-f]{4}-6[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12})', cache_key):
        raise ValueError('Invalid transcript reference.')
    root = (Path(roots[scope]) / 'views').resolve()
    directory = (root / cache_key).resolve()
    if directory.parent != root:
        raise ValueError('Invalid transcript reference.')
    return directory


@api_view(['GET', 'PUT'])
def transcript_detail(request, scope, cache_key):
    try:
        directory = transcript_directory(scope, cache_key)
        if request.method == 'PUT':
            if not isinstance(request.data, dict):
                raise ValueError('A transcript object is required.')
            view = save_transcript_edits(directory, scope, request.data.get('speaker_data'),
                                         request.data.get('revision'))
        else:
            view = load_transcript_view(directory, scope)
    except TranscriptConflict as exc:
        return Response({'error': str(exc)}, status=409)
    except FileNotFoundError as exc:
        return Response({'error': str(exc)}, status=404)
    except ValueError as exc:
        return Response({'error': str(exc)}, status=400)
    except OSError:
        return Response({'error': 'Unable to read or save the transcript. Please retry.'}, status=500)
    return Response({'view': view, 'audio_transcript': view['processed_data']['transcript'],
                     'speaker_data': view['processed_data']['speaker_data']})
