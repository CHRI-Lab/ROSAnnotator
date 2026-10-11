"""Common whole-bag/chunk workflow with independent failures and per-view caches."""
import logging
from .rosbag_reader import RosbagReader
from .view_cache import ViewCache, atomic_json
from .view_processor import ViewContext, ViewUnavailable
from .view_registry import PROCESSORS

logger = logging.getLogger(__name__)


def process_views(request, processors=None, reader_factory=RosbagReader):
    processors = tuple(PROCESSORS if processors is None else processors)
    if request.view_ids is not None:
        registry = {p.view_id: p for p in processors}
        selected = set(request.view_ids)
        if not selected or not selected.issubset(registry):
            raise ValueError('Unknown or empty view selection')
        while True:
            expanded = selected | {d for name in selected for d in registry[name].dependencies}
            if expanded == selected:
                break
            selected = expanded
        processors = tuple(p for p in processors if p.view_id in selected)
    cache = ViewCache(request.processed_root, request.bag_path, request.chunk)
    results = {}
    legacy = {'video_path': '', 'audio_path': None, 'waveform_image_path': None,
              'audio_transcript': '', 'speaker_data': []}
    with reader_factory(request.bag_path, request.chunk) as reader:
        pending = {p.view_id: p for p in processors}
        if len(pending) != len(processors) or any(not name for name in pending):
            raise ValueError('View IDs must be nonempty and unique')
        while pending:
            ready = [p for p in pending.values() if all(d not in pending for d in p.dependencies)]
            if not ready:
                raise ValueError('Cyclic view dependencies')
            for processor in ready:
                topics = []
                reader.warnings = []
                options = (request.view_options or {}).get(processor.view_id, {})
                context = ViewContext(reader, cache.root, options, results)
                try:
                    topics = processor.check_availability(context)
                    dependencies = {d: results.get(d) for d in processor.dependencies}
                    identity = cache.identity(processor, topics, options, dependencies)
                    context.cache_id = str(cache.identifier(identity))
                    context.directory = cache.directory(processor, topics, options, dependencies)
                    legacy_directory = cache.legacy_directory(
                        processor, topics, options, dependencies,
                    )
                    with cache.lock(context.directory):
                        # Prefer established media during migration. This avoids
                        # regenerating working artifacts merely to rename their
                        # internal identity, while all new writes use UUID6.
                        result = cache.load(legacy_directory)
                        if result is None:
                            result = cache.load(context.directory)
                        if result is None:
                            extracted = processor.extract(context, topics)
                            data = processor.preprocess(context, extracted)
                            result = processor.serialize(context, topics, data, reader.warnings)
                            atomic_json(context.directory / 'result.json', result)
                    legacy.update(processor.legacy_fields(result['processed_data']))
                except Exception as exc:
                    if not isinstance(exc, ViewUnavailable):
                        logger.exception('View %s failed', processor.view_id)
                    result = {'view_id': processor.view_id, 'status': 'unavailable' if isinstance(exc, ViewUnavailable) else 'failed',
                              'available': False, 'reason': str(exc) or type(exc).__name__,
                              'selected_topics': topics, 'duration': reader.duration,
                              'time_origin': reader.time_origin, 'processed_data': None,
                              'warnings': list(reader.warnings)}
                results[processor.view_id] = result
                del pending[processor.view_id]
        available = sum(r['available'] for r in results.values())
        return {**legacy, 'views': results, 'duration_seconds': reader.duration,
                'time_origin': reader.time_origin, 'topics': list(reader.topics.values()),
                'status': 'ready' if available else 'unavailable',
                'error': None if available else {'code': 'no_available_views', 'message': 'No usable data views are available.'}}
