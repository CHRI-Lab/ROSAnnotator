"""Session contract tests, runnable without Django, ROS, GPU or model downloads.

From src/backend: python -m unittest tests.test_processing_sessions
"""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import rosbag_processing
from rosbag_processing.processing_sessions import (
    BaseDataProcessingSession, ProcessingError, ProcessingRequest,
)
from rosbag_processing.rosbag_session import RosbagProcessingSession
from rosbag_processing.chunk_processing import ChunkProcessingSession, process_chunk


def artifacts(**extras):
    return {
        'video_path': 'chunks/example/output.mp4', 'audio_path': None,
        'waveform_image_path': None, 'audio_transcript': '', 'speaker_data': [],
        **extras,
    }


class SessionContractTests(unittest.TestCase):
    def test_parent_requires_processing_implementation(self):
        with self.assertRaises(TypeError):
            BaseDataProcessingSession()

    def test_rejects_missing_or_wrong_result_fields(self):
        class BrokenSession(BaseDataProcessingSession):
            def _run(self, request):
                return self.result

        session = BrokenSession()
        for result in ({}, artifacts(audio_path=123), artifacts(speaker_data=None),
                       artifacts(speaker_data=['invalid segment'])):
            session.result = result
            with self.subTest(result=result), self.assertRaises(TypeError):
                session.process(ProcessingRequest('example.bag'))

    def test_validation_precedes_cache_and_processing(self):
        session = ChunkProcessingSession()
        with patch.object(session, '_load_cached') as cached, patch.object(session, '_run') as run:
            for chunk in (None, {'index': 0, 'start_seconds': 10, 'end_seconds': 5},
                          {'index': 0, 'start_seconds': 0, 'end_seconds': float('nan')}):
                with self.subTest(chunk=chunk), self.assertRaises(ValueError):
                    session.process(ProcessingRequest('bag', manifest_id='id', chunk=chunk))
            cached.assert_not_called()
            run.assert_not_called()

    def test_cached_results_are_finalized_and_validated_by_parent(self):
        class CachedSession(BaseDataProcessingSession):
            def _load_cached(self, request):
                return artifacts()

            def _run(self, request):
                raise AssertionError('Cache hit must skip processing')

            def _finalize(self, request, result):
                return {**result, 'speaker_data': None}

        with self.assertRaisesRegex(TypeError, 'speaker_data'):
            CachedSession().process(ProcessingRequest('example.bag'))


class ChunkSessionTests(unittest.TestCase):
    def test_chunk_adapter_preserves_bounds_and_options(self):
        chunk = {'index': 2, 'start_seconds': 60, 'end_seconds': 90,
                 'duration_seconds': 30, 'previous_index': 1, 'next_index': 3}
        expected = artifacts(**chunk, status='ready')
        with tempfile.TemporaryDirectory() as root:
            with patch('rosbag_processing.chunk_processing._process_chunk', return_value=expected) as worker:
                actual = process_chunk(Path('example.bag'), 'manifest', chunk, root)
                worker.assert_called_once_with('example.bag', 'manifest', chunk, root, None, None)
                self.assertEqual(actual, expected)

    def test_lock_and_operational_errors_reach_http_adapter(self):
        chunk = {'index': 0, 'start_seconds': 0, 'end_seconds': 10}
        with tempfile.TemporaryDirectory() as root:
            with patch('rosbag_processing.chunk_processing._process_chunk',
                       side_effect=RuntimeError('This chunk is already being processed.')):
                with self.assertRaisesRegex(RuntimeError, 'already being processed'):
                    process_chunk('bag', 'manifest', chunk, root)


class WholeBagSessionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.bag = Path(self.temp.name) / 'sample.bag'
        self.bag.touch()
        self.request = ProcessingRequest(str(self.bag), str(Path(self.temp.name) / 'processed'))
        self.folder = Path(self.request.processed_root) / self.bag.name
        self.media = MagicMock()
        self.video = self.media.cv2.VideoCapture.return_value
        self.video.isOpened.return_value = False
        self.video.get.return_value = 25
        self.runtime = patch.dict('sys.modules', {
            'rosbag_processing.data_utils': self.media, 'cv2': self.media.cv2,
        })
        self.runtime.start()
        self.addCleanup(self.runtime.stop)
        self.package_runtime = patch.object(rosbag_processing, 'data_utils', self.media, create=True)
        self.package_runtime.start()
        self.addCleanup(self.package_runtime.stop)

    def test_whole_bag_uses_shared_workflow_and_preserves_metadata(self):
        speakers = [{'start_time': 1, 'end_time': 2, 'speaker_label': 'SPEAKER_00', 'text': 'Hello'}]
        expected = artifacts(speaker_data=speakers)
        with patch('rosbag_processing.view_workflow.process_views', return_value=expected) as workflow:
            result = RosbagProcessingSession().process(self.request)
        workflow.assert_called_once_with(self.request)
        self.assertEqual(result['speaker_data'], speakers)
        self.assertEqual(result['booklist_data'], {})
        self.assertIsNone(result['annotation_data'])

    def test_legacy_cache_without_source_identity_does_not_bypass_workflow(self):
        self.folder.mkdir(parents=True)
        for name in ('output.mp4', 'audio.mp3', 'output_waveform.png', 'transcript_with_speakers.srt'):
            (self.folder / name).touch()
        with patch('rosbag_processing.view_workflow.process_views', return_value=artifacts()) as workflow:
            RosbagProcessingSession().process(self.request)
        workflow.assert_called_once()

    def test_missing_bag_retains_legacy_error(self):
        with self.assertRaises(ProcessingError) as error:
            RosbagProcessingSession().process(ProcessingRequest(str(self.bag) + '.missing'))
        self.assertEqual(str(error.exception), 'Invalid bag filename')
        self.assertEqual(error.exception.status_code, 400)

    def test_chat_preview_failure_preserves_video_and_releases_decoder(self):
        self.video.isOpened.return_value = True
        self.video.read.side_effect = RuntimeError('decoder failed')
        session = RosbagProcessingSession()
        with patch.object(session, '_load_cached', return_value=artifacts()), patch.dict('sys.modules', {'cv2': self.media.cv2}):
            result = session.process(self.request)
        self.assertEqual(result['video_path'], artifacts()['video_path'])
        self.video.release.assert_called_once()


if __name__ == '__main__':
    unittest.main()
