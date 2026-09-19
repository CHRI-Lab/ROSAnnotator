"""On-demand processing for one ROSBag time range at a time."""
import math
from pathlib import Path

from .processing_sessions import BaseDataProcessingSession, ProcessingRequest, ProcessingResult


class ChunkProcessingSession(BaseDataProcessingSession):
    def _validate(self, request: ProcessingRequest) -> None:
        super()._validate(request)
        if not request.manifest_id or request.chunk is None:
            raise ValueError('manifest_id and chunk are required')
        chunk = request.chunk
        if not all(type(chunk.get(key)) in (int, float) and math.isfinite(chunk[key])
                   for key in ('start_seconds', 'end_seconds')):
            raise ValueError('Chunk bounds must be finite seconds')
        if chunk['start_seconds'] < 0 or chunk['end_seconds'] <= chunk['start_seconds']:
            raise ValueError('Chunk must have a positive duration')
        if type(chunk.get('index')) is not int or chunk['index'] < 0:
            raise ValueError('Chunk index must be a non-negative integer')

    def _run(self, request: ProcessingRequest) -> ProcessingResult:
        return _process_chunk(request.bag_path, request.manifest_id,
                              request.chunk, request.processed_root, request.view_options, request.view_ids)


def process_chunk(bag_path, manifest_id, chunk, processed_root='/app/processed_data/chunks', view_options=None, view_ids=None):
    """Compatibility adapter; all processing goes through the parent contract."""
    return ChunkProcessingSession().process(ProcessingRequest(
        bag_path=str(bag_path), manifest_id=str(manifest_id), chunk=chunk,
        processed_root=str(processed_root),
        view_options=view_options,
        view_ids=view_ids,
    ))


def _process_chunk(bag_path, manifest_id, chunk, processed_root, view_options=None, view_ids=None):
    from .view_workflow import process_views
    from .view_cache import ViewCache, atomic_json
    import json
    result = process_views(ProcessingRequest(
        bag_path=str(bag_path), processed_root=str(processed_root),
        manifest_id=str(manifest_id), chunk=chunk,
        view_options=view_options,
        view_ids=view_ids,
    ))
    result = {**chunk, **result}
    # Status summary only; reusable artifacts live in the per-view cache.
    directory = Path(processed_root) / str(manifest_id) / f"{chunk['index']:04d}"
    with ViewCache.lock(directory):
        try:
            summary = json.loads((directory / 'result.json').read_text(encoding='utf-8'))
        except (OSError, ValueError):
            summary = {}
        merged = {**summary.get('views', {}), **result['views']}
        atomic_json(directory / 'result.json', {**result, 'views': merged,
                    'status': 'ready' if any(v['available'] for v in merged.values()) else 'unavailable'})
    return result
