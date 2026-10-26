"""User corrections stored separately from generated transcript cache entries."""
import json
import math
from datetime import datetime, timezone
from pathlib import Path

from .view_cache import ViewCache, atomic_json


class TranscriptConflict(ValueError):
    pass


def validate_segments(segments, duration):
    if not isinstance(segments, list):
        raise ValueError('speaker_data must be a list of transcript segments.')
    if type(duration) not in (int, float) or not math.isfinite(duration) or duration <= 0:
        raise ValueError('A valid transcript duration is required.')
    validated = []
    for index, segment in enumerate(segments, start=1):
        if not isinstance(segment, dict):
            raise ValueError(f'Segment {index} must be an object.')
        start, end = segment.get('start_time'), segment.get('end_time')
        if (any(type(value) not in (int, float) or not math.isfinite(value) for value in (start, end))
                or start < 0 or end < start or end > duration):
            raise ValueError(f'Segment {index} must have valid start/end seconds within 0 to {duration}.')
        speaker, text = segment.get('speaker_label'), segment.get('text')
        if not isinstance(speaker, str) or not speaker.strip() or '\n' in speaker or '\r' in speaker:
            raise ValueError(f'Segment {index} needs a nonempty, single-line speaker label.')
        if not isinstance(text, str):
            raise ValueError(f'Segment {index} needs transcript text.')
        validated.append({'speaker_label': speaker.strip(), 'text': text,
                          'start_time': start, 'end_time': end})
    return sorted(validated, key=lambda segment: segment['start_time'])


def format_transcript(segments):
    def timestamp(seconds):
        minutes, seconds = divmod(int(seconds), 60)
        return f'[{minutes:02}:{seconds:02}]'
    return '\n'.join(
        f"{timestamp(segment['start_time'])} Speaker {segment['speaker_label']}: "
        f"{' '.join(segment['text'].splitlines())} {timestamp(segment['end_time'])}"
        for segment in segments
    )


def load_transcript_view(directory, scope, generated=None):
    directory = Path(directory)
    generated = generated if generated is not None else ViewCache.load(directory)
    if not generated or generated.get('view_id') != 'transcript' or not generated.get('available'):
        raise FileNotFoundError('Processed transcript not found. Load the transcript first.')
    data = {**generated['processed_data'], 'revision': 0,
            'edit_ref': {'scope': scope, 'key': directory.name}}
    try:
        edits = json.loads((directory / 'transcript.edits.json').read_text(encoding='utf-8'))
    except FileNotFoundError:
        return {**generated, 'processed_data': data}
    if not isinstance(edits, dict) or type(edits.get('revision')) is not int or edits['revision'] < 1:
        raise ValueError('Saved transcript edits are invalid.')
    segments = validate_segments(edits.get('speaker_data'), generated['duration'])
    data.update(speaker_data=segments, transcript=format_transcript(segments),
                revision=edits['revision'], edited_at=edits.get('edited_at'))
    return {**generated, 'processed_data': data}


def save_transcript_edits(directory, scope, segments, revision):
    directory = Path(directory)
    if type(revision) is not int or revision < 0:
        raise ValueError('A valid transcript revision is required.')
    if not (directory / 'result.json').is_file():
        raise FileNotFoundError('Processed transcript not found. Load the transcript first.')
    with ViewCache.lock(directory):
        current = load_transcript_view(directory, scope)
        if current['processed_data']['revision'] != revision:
            raise TranscriptConflict('This transcript was changed in another session. Reload it before saving again.')
        segments = validate_segments(segments, current['duration'])
        atomic_json(directory / 'transcript.edits.json', {
            'revision': revision + 1, 'speaker_data': segments,
            'edited_at': datetime.now(timezone.utc).isoformat(),
        })
        return load_transcript_view(directory, scope)
