"""Contract/regression tests with real cache I/O and fake ROS records."""
import json
import os
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from rosbag_processing.rosbag_reader import RosbagReader
from rosbag_processing.processing_sessions import ProcessingRequest
from rosbag_processing.view_processor import DataViewProcessor, ViewContext, ViewUnavailable
from rosbag_processing.view_workflow import process_views
from rosbag_processing.data_view_processors import VideoProcessor, AudioProcessor, TranscriptProcessor
from rosbag_processing.view_cache import ViewCache, atomic_json


def stamp(value):
    return SimpleNamespace(to_sec=lambda: value)


def message(value, frame='camera'):
    return SimpleNamespace(header=SimpleNamespace(stamp=stamp(value), frame_id=frame), data=b'payload')


class FakeBag:
    def __init__(self, records=None, types=None):
        self.entries = records if records is not None else [('/custom', message(101), stamp(102))]
        self.types = types if types is not None else {'/custom': ('test/Sample', len(self.entries))}
        self.closed = False

    def get_start_time(self):
        return 100.0

    def get_end_time(self):
        return 110.0

    def get_type_and_topic_info(self):
        return SimpleNamespace(topics={name: SimpleNamespace(msg_type=t, message_count=n)
                                      for name, (t, n) in self.types.items()})

    def read_messages(self, topics):
        return (entry for entry in self.entries if entry[0] in topics)

    def close(self):
        self.closed = True


class SampleProcessor(DataViewProcessor):
    view_id = 'sample'
    supported_message_types = ('test/Sample',)

    def __init__(self):
        self.calls = 0

    def extract(self, context, topics):
        self.calls += 1
        values = [(r.seconds, r.frame_id) for r in context.reader.records(topics)]
        if not values:
            raise ViewUnavailable('No records in this range')
        return context.reader.ordered(values)

    def preprocess(self, context, extracted):
        return {'samples': extracted}


class FailedProcessor(SampleProcessor):
    view_id = 'broken'

    def preprocess(self, context, extracted):
        raise RuntimeError('Decoder failed')


class ReaderTests(unittest.TestCase):
    def test_header_preference_fallback_order_and_duplicate_policy(self):
        bag = FakeBag([
            ('/custom', message(103), stamp(104)),
            ('/custom', message(float('nan')), stamp(102)),
            ('/custom', message(0), stamp(102)),
            ('/custom', message(900), stamp(105)),
        ])
        with RosbagReader('unused', bag_factory=lambda *_: bag) as reader:
            records = list(reader.records(['/custom']))
            self.assertEqual([r.seconds for r in records], [3, 2, 2, 5])
            self.assertEqual([p[0] for p in reader.ordered([(r.seconds, r.frame_id) for r in records])], [2, 2, 3, 5])
            self.assertEqual(records[0].frame_id, 'camera')
            self.assertEqual(len(reader.warnings), 2)
        self.assertTrue(bag.closed)

    def test_chunk_uses_header_even_when_recorded_outside_chunk(self):
        bag = FakeBag([
            ('/custom', message(102), stamp(109)),
            ('/custom', message(105), stamp(103)),
        ])
        with RosbagReader('unused', {'start_seconds': 2, 'end_seconds': 5}, lambda *_: bag) as reader:
            self.assertEqual([r.seconds for r in reader.records(['/custom'])], [0])
            self.assertEqual(reader.time_origin['reference'], 'chunk_start')
            self.assertEqual(reader.time_origin['bag_offset_seconds'], 2)

    def test_last_chunk_includes_bag_endpoint(self):
        bag = FakeBag([('/custom', message(110), stamp(110))])
        with RosbagReader('unused', {'start_seconds': 5, 'end_seconds': 10}, lambda *_: bag) as reader:
            self.assertEqual([r.seconds for r in reader.records(['/custom'])], [5])

    def test_closes_when_metadata_or_iteration_fails(self):
        for stage in ('get_type_and_topic_info', 'read_messages'):
            bag = FakeBag()
            with patch.object(bag, stage, side_effect=RuntimeError('bad bag')):
                with self.assertRaises(RuntimeError):
                    with RosbagReader('unused', bag_factory=lambda *_: bag) as reader:
                        list(reader.records(['/custom']))
            self.assertTrue(bag.closed)


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.bag_path = self.root / 'input.bag'
        self.bag_path.write_bytes(b'bag')
        self.request = ProcessingRequest(str(self.bag_path), str(self.root / 'processed'))
        self.bag = FakeBag()

    def process(self, processors, request=None):
        return process_views(request or self.request, processors,
                             lambda path, chunk: RosbagReader(path, chunk, lambda *_: self.bag))

    def test_new_registered_processor_needs_no_workflow_changes(self):
        result = self.process([SampleProcessor()])
        view = result['views']['sample']
        self.assertEqual(view['selected_topics'], ['/custom'])
        self.assertEqual(view['duration'], 10)
        self.assertEqual(view['processed_data']['samples'], [(1, 'camera')])
        self.assertTrue(view['available'])
        self.assertIsNone(result['error'])

    def test_failure_isolated_and_other_view_cached(self):
        valid, failed = SampleProcessor(), FailedProcessor()
        with self.assertLogs('rosbag_processing.view_workflow', level='ERROR'):
            result = self.process([failed, valid])
        self.assertTrue(result['views']['sample']['available'])
        self.assertEqual(result['views']['broken']['status'], 'failed')
        self.assertIn('Decoder failed', result['views']['broken']['reason'])
        self.assertIsNone(result['error'])

    def test_unsupported_and_empty_types_return_structured_zero_views(self):
        for types in ({'/unknown': ('other/Type', 99)}, {'/custom': ('test/Sample', 0)}):
            self.bag = FakeBag(types=types)
            result = self.process([SampleProcessor()])
            self.assertEqual(result['error']['code'], 'no_available_views')
            self.assertEqual(result['views']['sample']['status'], 'unavailable')
            self.assertTrue(result['views']['sample']['reason'])

    def test_cache_reused_across_manifest_ids_and_invalidated_by_source(self):
        processor = SampleProcessor()
        first = self.process([processor], replace(self.request, manifest_id='one'))
        second = self.process([processor], replace(self.request, manifest_id='two'))
        self.assertEqual(processor.calls, 1)
        self.assertEqual(json.dumps(first, sort_keys=True), json.dumps(second, sort_keys=True))
        self.bag_path.write_bytes(b'changed')
        self.process([processor])
        self.assertEqual(processor.calls, 2)
        stat = self.bag_path.stat()
        os.utime(self.bag_path, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1000000))
        self.process([processor])
        self.assertEqual(processor.calls, 3)

    def test_topics_options_and_chunk_bounds_separate_cache(self):
        processor = SampleProcessor()
        self.bag = FakeBag(types={'/custom': ('test/Sample', 1), '/other': ('test/Sample', 1)},
                           records=[('/custom', message(103), stamp(103)), ('/other', message(103), stamp(103))])
        self.process([processor])
        self.process([processor], replace(self.request, view_options={'sample': {'topics': ['/other']}}))
        self.process([processor], replace(self.request, view_options={'sample': {'quality': 2}}))
        result = self.process([processor], replace(self.request, chunk={'index': 0, 'start_seconds': 2, 'end_seconds': 5}))
        self.assertEqual(result['views']['sample']['processed_data']['samples'][0][0], 1)
        self.assertEqual(processor.calls, 4)

    def test_invalid_topic_is_unavailable_without_extracting(self):
        processor = SampleProcessor()
        result = self.process([processor], replace(self.request, view_options={'sample': {'topics': ['/missing']}}))
        self.assertFalse(result['views']['sample']['available'])
        self.assertEqual(processor.calls, 0)

    def test_corrupt_cache_rebuilt(self):
        processor = SampleProcessor()
        self.process([processor])
        next((self.root / 'processed').rglob('result.json')).write_text('{broken')
        self.process([processor])
        self.assertEqual(processor.calls, 2)

    def test_single_view_selection_loads_dependencies_only(self):
        class Derived(SampleProcessor):
            view_id = 'derived'
            dependencies = ('sample',)
        result = self.process([Derived(), FailedProcessor(), SampleProcessor()],
                              replace(self.request, view_ids=['derived']))
        self.assertEqual(set(result['views']), {'derived', 'sample'})
        with self.assertRaises(ValueError):
            self.process([SampleProcessor()], replace(self.request, view_ids=['unknown']))

    def test_concurrent_requests_share_one_processing_run(self):
        processor = SampleProcessor()
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: self.process([processor]), range(2)))
        self.assertTrue(all(r['views']['sample']['available'] for r in results))
        self.assertEqual(processor.calls, 1)

    def test_audio_missing_does_not_require_ml_runtime(self):
        result = self.process([AudioProcessor(), TranscriptProcessor()])
        self.assertEqual(result['views']['audio']['status'], 'unavailable')
        self.assertEqual(result['views']['transcript']['status'], 'unavailable')

    def test_incompatible_frames_rejected_only_in_video(self):
        self.bag = FakeBag(types={'/camera': ('sensor_msgs/Image', 2)}, records=[
            ('/camera', message(101, 'left'), stamp(101)),
            ('/camera', message(102, 'right'), stamp(102)),
        ])
        cv2, bridge = MagicMock(), MagicMock()
        with patch.dict('sys.modules', {'cv2': cv2, 'cv_bridge': bridge}):
            result = self.process([VideoProcessor()])
        self.assertEqual(result['views']['video']['status'], 'unavailable')
        self.assertIn('coordinate frames', result['views']['video']['reason'])

    def test_atomic_publication_uses_unique_temporary_files(self):
        destination = self.root / 'summary.json'
        def publish(n):
            with ViewCache.lock(self.root):
                atomic_json(destination, {'n': n})
        with ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(publish, range(12)))
        self.assertIn(json.loads(destination.read_text())['n'], range(12))
        self.assertFalse(list(self.root.glob('*.tmp')))


if __name__ == '__main__':
    unittest.main()
