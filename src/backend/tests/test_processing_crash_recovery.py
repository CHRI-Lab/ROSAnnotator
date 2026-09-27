"""Crash recovery: same input + chunk setting processed twice, the first run
crashes -> the second run must not be permanently blocked.

Covers the three ways a crashed first run could block the second one:
  1. A failed extraction must not be cached as a result (second run re-extracts).
  2. Leftovers from a crash mid-write (.lock file, stray *.tmp, truncated or
     stale result.json, result.json pointing at a missing artifact) must not be
     treated as a valid cache.
  3. A worker killed while holding ViewCache.lock must not leave the lock held.
Plus the chunk-level summary layer (_process_chunk) recovering after a crash.

Runnable without ROS, GPU or model downloads: fake reader + fake processor are
injected through process_views(processors=..., reader_factory=...).

Run: python3 manage.py test tests.test_processing_crash_recovery -v 2
"""
import json
import multiprocessing
import os
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from rosbag_processing.chunk_processing import _process_chunk
from rosbag_processing.processing_sessions import ProcessingRequest
from rosbag_processing.view_cache import ViewCache
from rosbag_processing.view_workflow import process_views

CHUNK = {'index': 0, 'start_seconds': 0.0, 'end_seconds': 10.0}
TOPICS = ['/camera']


class FakeReader:
    """Stands in for RosbagReader: only the attributes process_views reads."""

    def __init__(self, bag_path, chunk):
        self.warnings = []
        self.duration = 10.0
        self.time_origin = 0.0
        self.topics = {'/camera': {'name': '/camera'}}

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class FakeProcessor:
    """A view processor whose extract() crashes for the first `fail_times` calls."""
    view_id = 'video'
    dependencies = ()
    cache_version = 1

    def __init__(self, fail_times=0):
        self.fail_times = fail_times
        self.extract_calls = 0

    def check_availability(self, context):
        return list(TOPICS)

    def extract(self, context, topics):
        self.extract_calls += 1
        if self.extract_calls <= self.fail_times:
            raise RuntimeError('simulated crash during extraction')
        return {'frames': 3}

    def preprocess(self, context, extracted):
        return extracted

    def serialize(self, context, topics, data, warnings):
        return {'view_id': self.view_id, 'status': 'ready', 'available': True,
                'reason': None, 'selected_topics': topics, 'duration': 10.0,
                'time_origin': 0.0,
                'processed_data': {'frames': data['frames'], 'artifacts': []},
                'warnings': list(warnings)}

    def legacy_fields(self, processed_data):
        return {}


def _hold_lock_until_killed(directory, locked):
    """Child process: take the cache lock, signal, then hang until killed."""
    with ViewCache.lock(Path(directory)):
        locked.set()
        time.sleep(60)


def _acquire_lock(directory, acquired):
    with ViewCache.lock(Path(directory)):
        acquired.set()


class CrashRecoveryBase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.bag = Path(self.temp.name) / 'sample.bag'
        self.bag.write_bytes(b'bag')
        self.root = Path(self.temp.name) / 'processed'
        self.request = ProcessingRequest(str(self.bag), str(self.root),
                                         manifest_id='manifest', chunk=CHUNK)

    def run_views(self, processor):
        return process_views(self.request, processors=[processor], reader_factory=FakeReader)

    def cache_directory(self, processor):
        return ViewCache(str(self.root), str(self.bag), CHUNK).directory(processor, TOPICS, {}, {})


class FailedRunIsNotCachedTests(CrashRecoveryBase):
    def test_second_run_succeeds_after_first_run_crashes(self):
        processor = FakeProcessor(fail_times=1)

        with self.assertLogs('rosbag_processing.view_workflow', level='ERROR'):
            first = self.run_views(processor)
        self.assertEqual(first['status'], 'unavailable')
        self.assertEqual(first['views']['video']['status'], 'failed')
        self.assertIsNone(ViewCache.load(self.cache_directory(processor)),
                          'a crashed run must not leave a usable cache entry')

        second = self.run_views(processor)
        self.assertEqual(second['status'], 'ready')
        self.assertTrue(second['views']['video']['available'])
        self.assertEqual(processor.extract_calls, 2, 'second run must re-extract, not reuse the failure')

    def test_third_run_reuses_cache_once_recovered(self):
        processor = FakeProcessor(fail_times=1)
        with self.assertLogs('rosbag_processing.view_workflow', level='ERROR'):
            self.run_views(processor)
        self.run_views(processor)
        third = self.run_views(processor)
        self.assertEqual(third['status'], 'ready')
        self.assertEqual(processor.extract_calls, 2, 'after recovery the good result is cached')


class CrashLeftoversAreIgnoredTests(CrashRecoveryBase):
    def leftover_cases(self, directory):
        missing_artifact = {'view_id': 'video', 'status': 'ready', 'available': True,
                            'processed_data': {'artifacts': [str(directory / 'output.mp4')]}}
        return {
            'truncated_result_json': '{"view_id": "video", "status": "rea',
            'failed_result_json': json.dumps({'view_id': 'video', 'status': 'failed',
                                              'available': False, 'processed_data': None}),
            'ready_but_artifact_missing': json.dumps(missing_artifact),
            'no_result_json_only_lock_and_tmp': None,
        }

    def test_leftovers_from_crashed_run_do_not_block_second_run(self):
        directory = self.cache_directory(FakeProcessor())
        for name, result_json in self.leftover_cases(directory).items():
            with self.subTest(leftover=name):
                if directory.exists():
                    for path in directory.iterdir():
                        path.unlink()
                directory.mkdir(parents=True, exist_ok=True)
                (directory / '.lock').write_bytes(b'0')
                (directory / 'tmpcrash.tmp').write_text('{"half written', encoding='utf-8')
                if result_json is not None:
                    (directory / 'result.json').write_text(result_json, encoding='utf-8')

                processor = FakeProcessor()
                result = self.run_views(processor)

                self.assertEqual(result['status'], 'ready')
                self.assertEqual(processor.extract_calls, 1, 'leftover must not be treated as valid cache')
                self.assertIsNotNone(ViewCache.load(directory), 'second run writes a valid cache entry')


@unittest.skipIf(os.name == 'nt', 'uses fork + fcntl; run inside the Linux container')
class LockReleasedAfterWorkerKilledTests(unittest.TestCase):
    def test_lock_held_by_killed_worker_is_released(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp) / 'views' / 'key'
            ctx = multiprocessing.get_context('fork')
            locked = ctx.Event()
            worker = ctx.Process(target=_hold_lock_until_killed, args=(str(directory), locked))
            worker.start()
            self.addCleanup(lambda: worker.is_alive() and worker.kill())
            self.assertTrue(locked.wait(5), 'worker never acquired the lock')

            acquired = threading.Event()
            waiter = threading.Thread(target=_acquire_lock, args=(directory, acquired), daemon=True)
            waiter.start()
            self.assertFalse(acquired.wait(0.5), 'lock must be exclusive while the worker is alive')

            worker.kill()  # simulate a crash: no finally/unlock runs in the worker
            worker.join(5)
            self.assertTrue(acquired.wait(5), 'lock stayed held after the worker was killed')
            self.assertTrue((directory / '.lock').exists(), 'leftover .lock file is present but harmless')


class ChunkSummaryRecoversAfterCrashTests(unittest.TestCase):
    def test_chunk_processing_succeeds_on_second_run_after_crash(self):
        ready = {'video_path': 'chunks/example/output.mp4', 'audio_path': None,
                 'waveform_image_path': None, 'audio_transcript': '', 'speaker_data': [],
                 'views': {'video': {'view_id': 'video', 'available': True, 'status': 'ready'}},
                 'status': 'ready'}
        with tempfile.TemporaryDirectory() as root:
            summary = Path(root) / 'manifest' / '0000' / 'result.json'
            with patch('rosbag_processing.view_workflow.process_views',
                       side_effect=[RuntimeError('simulated crash'), ready]):
                with self.assertRaisesRegex(RuntimeError, 'simulated crash'):
                    _process_chunk('bag', 'manifest', CHUNK, root)
                self.assertFalse(summary.exists(), 'crash must not write a chunk summary')

                result = _process_chunk('bag', 'manifest', CHUNK, root)

            self.assertEqual(result['status'], 'ready')
            saved = json.loads(summary.read_text(encoding='utf-8'))
            self.assertEqual(saved['status'], 'ready')


if __name__ == '__main__':
    unittest.main()