"""Persistent chunk manifests; timestamps are seconds from the bag start."""
import json
import math
import os
from decimal import Decimal, ROUND_CEILING
from pathlib import Path
from uuid import uuid4


MAX_CHUNKS = 10000


def build_chunks(duration_seconds, chunk_seconds):
    for value in (duration_seconds, chunk_seconds):
        if isinstance(value, bool) or not math.isfinite(value) or value <= 0:
            raise ValueError('Duration and chunk size must be finite positive seconds.')
    duration = Decimal(str(duration_seconds))
    size = Decimal(str(chunk_seconds))
    count = int((duration / size).to_integral_value(rounding=ROUND_CEILING))
    if count > MAX_CHUNKS:
        raise ValueError(f'A maximum of {MAX_CHUNKS} chunks is supported.')
    return [
        {
            'index': index,
            'start_seconds': float(index * size),
            'end_seconds': float(min((index + 1) * size, duration)),
            'duration_seconds': float(min(size, duration - index * size)),
            'previous_index': index - 1 if index else None,
            'next_index': index + 1 if index + 1 < count else None,
        }
        for index in range(count)
    ]


def save_manifest(
    directory, bag_filename, duration_seconds, chunk_seconds,
    chunking_enabled=True, source_size=None, source_mtime_ns=None,
    booklist_filename=None, annotation_filename=None,
    view_options=None,
):
    chunks = build_chunks(duration_seconds, chunk_seconds)
    manifest = {
        'id': str(uuid4()),
        'bag_filename': bag_filename,
        'chunking_enabled': chunking_enabled,
        'time_reference': 'bag_start',
        'duration_seconds': duration_seconds,
        'chunk_seconds': chunk_seconds,
        'chunk_count': len(chunks),
        'chunks': chunks,
        'booklist_filename': booklist_filename,
        'annotation_filename': annotation_filename,
        'view_options': view_options or {},
    }
    if source_size is not None:
        manifest['source_size'] = source_size
    if source_mtime_ns is not None:
        manifest['source_mtime_ns'] = source_mtime_ns
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    destination = directory / f"{manifest['id']}.json"
    temporary = destination.with_suffix('.tmp')
    try:
        with temporary.open('x', encoding='utf-8') as stream:
            json.dump(manifest, stream, allow_nan=False, indent=2)
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)
    return manifest


def load_manifest(directory, manifest_id):
    # Callers supply a UUID, not a filesystem path.
    from uuid import UUID
    identifier = UUID(str(manifest_id))
    with (Path(directory) / f'{identifier}.json').open(encoding='utf-8') as stream:
        return json.load(stream)
