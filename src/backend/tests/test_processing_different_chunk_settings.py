"""Same input + different chunk setting -> different manifest ID, and both runs
(especially the 2nd) get chunked into the correct selected time ranges.

Covers:
  1. manifest_id / save_manifest: a different chunk size, or chunking on vs
     off, gives a different manifest; saving the 2nd never alters the 1st.
  2. Time ranges: each manifest's chunks follow its own chunk size, are
     contiguous, cover the whole bag, and the last chunk is truncated.
     load_manifest(2nd id) returns the 2nd setting, not the 1st.
  3. process_views: the 2nd run's reader receives the 2nd setting's bounds,
     and the 2nd run does not reuse the 1st setting's cache, even for the
     same chunk index (chunk 0 = [0,300] vs [0,60]).
  4. _process_chunk: each manifest gets its own summary, carrying its own bounds.

Runnable without ROS, GPU or model downloads (fake reader + fake processor).

Run: python3 manage.py test tests.test_processing_different_chunk_settings -v 2
"""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from rosbag_processing.chunk_processing import _process_chunk
from rosbag_processing.chunks import load_manifest, manifest_id, save_manifest
from rosbag_processing.processing_sessions import ProcessingRequest
from rosbag_processing.view_cache import ViewCache
from rosbag_processing.view_workflow import process_views

BAG = 'record.bag'
DURATION = 650.0          # not divisible by either setting -> last chunk is shorter
FIRST_SECONDS = 300.0
SECOND_SECONDS = 60.0
SIZE, MTIME = 1000, 111


def bounds(chunks):
    return [(c['start_seconds'], c['end_seconds']) for c in chunks]


class FakeReader:
    """Stands in for RosbagReader and records the chunk bounds it was asked to read."""
    received = []

    def __init__(self, bag_path, chunk):
        FakeReader.received.append((chunk['start_seconds'], chunk['end_seconds']))
        self.warnings = []
        self.duration = chunk['end_seconds'] - chunk['start_seconds']
        self.time_origin = 0.0
        self.topics = {'/camera': {'name': '/camera'}}

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


class ManifestPerSettingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name) / 'manifests'

    def save(self, chunk_seconds, chunking_enabled=True):
        return save_manifest(self.directory, BAG, DURATION, chunk_seconds, chunking_enabled,
                             source_size=SIZE, source_mtime_ns=MTIME)

    def test_different_chunk_setting_gives_different_manifest_id(self):
        base = manifest_id(BAG, FIRST_SECONDS, True, SIZE, MTIME)
        for label, seconds, enabled in (('60s chunks', SECOND_SECONDS, True),
                                        ('decimal size', 299.5, True),
                                        ('chunking disabled', FIRST_SECONDS, False)):
            with self.subTest(label):
                self.assertNotEqual(base, manifest_id(BAG, seconds, enabled, SIZE, MTIME))

    def test_saving_second_setting_creates_new_manifest_and_leaves_first_untouched(self):
        first = self.save(FIRST_SECONDS)
        first_file = self.directory / f"{first['id']}.json"
        first_bytes = first_file.read_bytes()

        second = self.save(SECOND_SECONDS)

        self.assertNotEqual(first['id'], second['id'])
        self.assertEqual(len(list(self.directory.glob('*.json'))), 2)
        self.assertEqual(first_file.read_bytes(), first_bytes, '2nd save must not rewrite the 1st manifest')

    def test_each_manifest_is_chunked_into_its_own_time_ranges(self):
        first = self.save(FIRST_SECONDS)
        second = self.save(SECOND_SECONDS)

        self.assertEqual(bounds(first['chunks']), [(0.0, 300.0), (300.0, 600.0), (600.0, 650.0)])
        expected_second = [(i * 60.0, min((i + 1) * 60.0, DURATION)) for i in range(11)]
        self.assertEqual(bounds(second['chunks']), expected_second)
        self.assertEqual(second['chunk_count'], 11)
        self.assertEqual(second['chunk_seconds'], SECOND_SECONDS)

        for label, chunks in (('first', first['chunks']), ('second', second['chunks'])):
            with self.subTest(label):
                self.assertEqual(chunks[0]['start_seconds'], 0.0)
                self.assertEqual(chunks[-1]['end_seconds'], DURATION)
                for previous, current in zip(chunks, chunks[1:]):
                    self.assertEqual(previous['end_seconds'], current['start_seconds'], 'gap or overlap')
        self.assertEqual(second['chunks'][-1]['duration_seconds'], 50.0)

    def test_loading_second_id_returns_second_setting(self):
        first = self.save(FIRST_SECONDS)
        second = self.save(SECOND_SECONDS)

        self.assertEqual(bounds(load_manifest(self.directory, second['id'])['chunks']),
                         bounds(second['chunks']))
        self.assertEqual(bounds(load_manifest(self.directory, first['id'])['chunks']),
                         bounds(first['chunks']))


class ProcessingUsesSelectedRangeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.bag = Path(self.temp.name) / BAG
        self.bag.write_bytes(b'bag')
        self.root = Path(self.temp.name) / 'processed'
        manifests = Path(self.temp.name) / 'manifests'
        self.first = save_manifest(manifests, BAG, DURATION, FIRST_SECONDS, source_size=SIZE, source_mtime_ns=MTIME)
        self.second = save_manifest(manifests, BAG, DURATION, SECOND_SECONDS, source_size=SIZE, source_mtime_ns=MTIME)
        FakeReader.received = []

    def run_views(self, manifest, index, processor):
        request = ProcessingRequest(str(self.bag), str(self.root), manifest_id=manifest['id'],
                                    chunk=manifest['chunks'][index])
        return process_views(request, processors=[processor], reader_factory=FakeReader)

    def cache_directory(self, chunk, processor):
        return ViewCache(str(self.root), str(self.bag), chunk).directory(processor, ['/camera'], {}, {})

    def test_second_run_reads_the_second_settings_time_range(self):
        processor = FakeProcessor()
        self.run_views(self.first, 1, processor)
        self.run_views(self.second, 1, processor)
        self.assertEqual(FakeReader.received, [(300.0, 600.0), (60.0, 120.0)])

    def test_same_chunk_index_different_setting_is_not_served_from_first_cache(self):
        processor = FakeProcessor()
        self.run_views(self.first, 0, processor)    # [0, 300]
        second = self.run_views(self.second, 0, processor)    # [0, 60]

        self.assertEqual(FakeReader.received, [(0.0, 300.0), (0.0, 60.0)])
        self.assertEqual(processor.extract_calls, 2, "2nd setting must not reuse the 1st setting's cache")
        self.assertNotEqual(self.cache_directory(self.first['chunks'][0], processor),
                            self.cache_directory(self.second['chunks'][0], processor))
        self.assertEqual(second['duration_seconds'], 60.0)


class ChunkSummaryPerSettingTests(unittest.TestCase):
    def test_each_setting_gets_its_own_summary_with_its_own_bounds(self):
        ready = {'video_path': 'v.mp4', 'audio_path': None, 'waveform_image_path': None,
                 'audio_transcript': '', 'speaker_data': [], 'status': 'ready',
                 'views': {'video': {'view_id': 'video', 'available': True, 'status': 'ready'}}}
        with tempfile.TemporaryDirectory() as temp:
            manifests = Path(temp) / 'manifests'
            root = Path(temp) / 'processed'
            first = save_manifest(manifests, BAG, DURATION, FIRST_SECONDS, source_size=SIZE, source_mtime_ns=MTIME)
            second = save_manifest(manifests, BAG, DURATION, SECOND_SECONDS, source_size=SIZE, source_mtime_ns=MTIME)

            with patch('rosbag_processing.view_workflow.process_views', side_effect=[dict(ready), dict(ready)]) as workflow:
                _process_chunk(BAG, first['id'], first['chunks'][1], root)
                result = _process_chunk(BAG, second['id'], second['chunks'][1], root)

            sent = workflow.call_args_list[1].args[0].chunk
            self.assertEqual((sent['start_seconds'], sent['end_seconds']), (60.0, 120.0))
            self.assertEqual((result['start_seconds'], result['end_seconds']), (60.0, 120.0))
            for manifest, expected in ((first, (300.0, 600.0)), (second, (60.0, 120.0))):
                with self.subTest(manifest=manifest['chunk_seconds']):
                    summary = json.loads((root / manifest['id'] / '0001' / 'result.json').read_text(encoding='utf-8'))
                    self.assertEqual((summary['start_seconds'], summary['end_seconds']), expected)


if __name__ == '__main__':
    unittest.main()