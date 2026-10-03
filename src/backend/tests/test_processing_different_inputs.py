"""
Different input + same chunk setting -> different manifest ID, and both runs
(especially the 2nd) receive and process their own input, never the 1st one's.
"""
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from rosbag_processing.chunk_processing import _process_chunk
from rosbag_processing.chunks import manifest_id
from rosbag_processing.processing_sessions import ProcessingRequest
from rosbag_processing.view_cache import ViewCache
from rosbag_processing.view_workflow import process_views

CHUNK = {'index': 0, 'start_seconds': 0.0, 'end_seconds': 10.0}
CHUNK_SECONDS = 300.0


class FakeReader:
    """Stands in for RosbagReader. Each bag path gets its own duration/topic,
    and every opened path is recorded so tests can see what was really read."""
    opened = []
    by_path = {}

    def __init__(self, bag_path, chunk):
        FakeReader.opened.append(str(bag_path))
        duration, topic = FakeReader.by_path[str(bag_path)]
        self.warnings = []
        self.duration = duration
        self.time_origin = 0.0
        self.topics = {topic: {'name': topic}}

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class FakeProcessor:
    view_id = 'video'
    dependencies = ()
    cache_version = 1

    def __init__(self):
        self.extract_calls = 0

    def check_availability(self, context):
        return ['/camera']

    def extract(self, context, topics):
        self.extract_calls += 1
        return {'run': self.extract_calls}

    def preprocess(self, context, extracted):
        return extracted

    def serialize(self, context, topics, data, warnings):
        return {'view_id': self.view_id, 'status': 'ready', 'available': True,
                'reason': None, 'selected_topics': topics, 'duration': 0.0,
                'time_origin': 0.0,
                'processed_data': {'run': data['run'], 'artifacts': []},
                'warnings': list(warnings)}

    def legacy_fields(self, processed_data):
        return {}


class ManifestIdTests(unittest.TestCase):
    def test_different_bag_file_gives_different_manifest_id(self):
        first = manifest_id('record_a.bag', CHUNK_SECONDS, True, 1000, 111)
        second = manifest_id('record_b.bag', CHUNK_SECONDS, True, 1000, 111)
        self.assertNotEqual(first, second)

    def test_same_filename_replaced_content_gives_different_manifest_id(self):
        original = manifest_id('record.bag', CHUNK_SECONDS, True, 1000, 111)
        for label, size, mtime in (('size changed', 2000, 111),
                                   ('mtime changed', 1000, 222)):
            with self.subTest(label):
                self.assertNotEqual(original, manifest_id('record.bag', CHUNK_SECONDS, True, size, mtime))


class DifferentInputProcessingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'processed'
        self.bag_a = Path(self.temp.name) / 'record_a.bag'
        self.bag_b = Path(self.temp.name) / 'record_b.bag'
        self.bag_a.write_bytes(b'aaaa')
        self.bag_b.write_bytes(b'bbbbbbbb')
        FakeReader.opened = []
        FakeReader.by_path = {str(self.bag_a): (100.0, '/topic_a'),
                              str(self.bag_b): (200.0, '/topic_b')}

    def run_views(self, bag, processor):
        request = ProcessingRequest(str(bag), str(self.root), manifest_id='m', chunk=CHUNK)
        return process_views(request, processors=[processor], reader_factory=FakeReader)

    def cache_directory(self, bag, processor):
        return ViewCache(str(self.root), str(bag), CHUNK).directory(processor, ['/camera'], {}, {})

    def test_second_run_receives_and_processes_second_input(self):
        processor = FakeProcessor()
        first = self.run_views(self.bag_a, processor)
        second = self.run_views(self.bag_b, processor)

        self.assertEqual(FakeReader.opened, [str(self.bag_a), str(self.bag_b)])
        self.assertEqual(processor.extract_calls, 2, "2nd input must not reuse the 1st input's cache")
        self.assertEqual((first['duration_seconds'], first['topics']), (100.0, [{'name': '/topic_a'}]))
        self.assertEqual((second['duration_seconds'], second['topics']), (200.0, [{'name': '/topic_b'}]))
        self.assertEqual(second['views']['video']['processed_data']['run'], 2)

    def test_each_input_has_its_own_cache_and_first_is_untouched(self):
        processor = FakeProcessor()
        self.run_views(self.bag_a, processor)
        dir_a = self.cache_directory(self.bag_a, processor)
        cached_a = ViewCache.load(dir_a)
        self.run_views(self.bag_b, processor)
        dir_b = self.cache_directory(self.bag_b, processor)

        self.assertNotEqual(dir_a, dir_b)
        self.assertEqual(ViewCache.load(dir_a), cached_a, "2nd run must not overwrite the 1st input's cache")
        self.assertEqual(ViewCache.load(dir_b)['processed_data']['run'], 2)

    def test_same_path_replaced_with_new_recording_is_reprocessed(self):
        processor = FakeProcessor()
        self.run_views(self.bag_a, processor)
        old_dir = self.cache_directory(self.bag_a, processor)

        self.bag_a.write_bytes(b'a completely different recording')
        stat = self.bag_a.stat()
        os.utime(self.bag_a, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000_000))
        FakeReader.by_path[str(self.bag_a)] = (300.0, '/topic_new')
        second = self.run_views(self.bag_a, processor)

        self.assertNotEqual(self.cache_directory(self.bag_a, processor), old_dir)
        self.assertEqual(processor.extract_calls, 2, 'replaced file must not be served from the old cache')
        self.assertEqual(second['duration_seconds'], 300.0)


class ChunkSummaryPerManifestTests(unittest.TestCase):
    def test_second_manifest_summary_contains_only_its_own_views(self):
        def result(view_id, video_path):
            return {'video_path': video_path, 'audio_path': None, 'waveform_image_path': None,
                    'audio_transcript': '', 'speaker_data': [], 'status': 'ready',
                    'views': {view_id: {'view_id': view_id, 'available': True, 'status': 'ready'}}}

        with tempfile.TemporaryDirectory() as root:
            id_a = manifest_id('record_a.bag', CHUNK_SECONDS, True, 1000, 111)
            id_b = manifest_id('record_b.bag', CHUNK_SECONDS, True, 1000, 111)
            with patch('rosbag_processing.view_workflow.process_views',
                       side_effect=[result('view_from_a', 'a.mp4'), result('view_from_b', 'b.mp4')]) as workflow:
                _process_chunk('record_a.bag', id_a, CHUNK, root)
                second = _process_chunk('record_b.bag', id_b, CHUNK, root)

            self.assertEqual(workflow.call_args_list[1].args[0].bag_path, 'record_b.bag')
            self.assertEqual(workflow.call_args_list[1].args[0].manifest_id, id_b)
            self.assertEqual(second['video_path'], 'b.mp4')
            summary_a = json.loads((Path(root) / id_a / '0000' / 'result.json').read_text(encoding='utf-8'))
            summary_b = json.loads((Path(root) / id_b / '0000' / 'result.json').read_text(encoding='utf-8'))
            self.assertEqual(set(summary_a['views']), {'view_from_a'})
            self.assertEqual(set(summary_b['views']), {'view_from_b'}, "1st input's views leaked into 2nd summary")


if __name__ == '__main__':
    unittest.main()