import os
import tempfile
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase
from rest_framework.test import APIClient

from .chunks import build_chunks, load_manifest, save_manifest
from .chunk_views import annotations_for_chunk
from .data_utils import configure_huggingface_compatibility, get_rosbag_duration


class ProcessingSessionApiTests(SimpleTestCase):
    @patch('rosbag_processing.rosbag_session.RosbagProcessingSession')
    def test_whole_bag_adapter_preserves_request_and_response(self, session_class):
        session = session_class.return_value
        session.video_frames = []
        session.video_fps = 25
        result = {
            'video_path': 'sample.bag/output.mp4',
            'audio_path': 'sample.bag/audio.mp3',
            'waveform_image_path': 'sample.bag/output_waveform.png',
            'audio_transcript': '', 'speaker_data': [],
            'booklist_data': {}, 'annotation_data': None,
            'message': 'File already processed',
        }
        session.process.return_value = result
        response = APIClient().post('/api/process_rosbag/', {
            'bag_filename': 'sample.bag', 'booklist_filename': 'codes.json',
            'annotation_filename': 'annotations.csv',
        }, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, result)
        request = session.process.call_args.args[0]
        self.assertEqual(request.bag_path, os.path.join('/app/datas/rosbag-data/', 'sample.bag'))
        self.assertEqual(request.booklist_filename, 'codes.json')
        self.assertEqual(request.annotation_filename, 'annotations.csv')

    @patch('rosbag_processing.rosbag_session.RosbagProcessingSession')
    def test_expected_processing_error_keeps_legacy_http_shape(self, session_class):
        from .processing_sessions import ProcessingError
        session_class.return_value.process.side_effect = ProcessingError('Invalid bag filename')
        response = APIClient().post('/api/process_rosbag/', {'bag_filename': 'missing.bag'}, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data, {'error': 'Invalid bag filename'})

    @patch('rosbag_processing.rosbag_session.RosbagProcessingSession')
    def test_missing_filename_does_not_start_a_session(self, session_class):
        response = APIClient().post('/api/process_rosbag/', {}, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data, {'error': 'bag_filename is required'})
        session_class.assert_not_called()


class GetRosbagDurationTests(SimpleTestCase):
    @patch('rosbag_processing.data_utils.Bag')
    def test_returns_duration_and_closes_bag(self, bag_class):
        bag = MagicMock()
        bag.get_start_time.return_value = 100.25
        bag.get_end_time.return_value = 460.75
        bag_class.return_value = bag

        duration = get_rosbag_duration('/tmp/example.bag')

        self.assertEqual(duration, 360.5)
        bag.close.assert_called_once_with()

    @patch('rosbag_processing.data_utils.Bag')
    def test_never_returns_negative_duration(self, bag_class):
        bag = MagicMock()
        bag.get_start_time.return_value = 20
        bag.get_end_time.return_value = 10
        bag_class.return_value = bag

        self.assertEqual(get_rosbag_duration('/tmp/example.bag'), 0.0)
        bag.close.assert_called_once_with()


class HuggingFaceCompatibilityTests(SimpleTestCase):
    @patch('rosbag_processing.data_utils.hf_hub_download')
    def test_maps_legacy_auth_argument_to_token(self, download_mock):
        configure_huggingface_compatibility()

        from pyannote.audio.core import pipeline as pipeline_module
        pipeline_module.hf_hub_download(
            'owner/model', 'config.yaml', use_auth_token='secret-token'
        )

        download_mock.assert_called_once_with(
            'owner/model', 'config.yaml', token='secret-token'
        )


class InspectInputApiTests(SimpleTestCase):
    def setUp(self):
        self.client = APIClient()
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.rosbag_directory_patch = patch(
            'rosbag_processing.views.ROSBAG_DATA_DIR',
            self.temporary_directory.name,
        )
        self.rosbag_directory_patch.start()

    def tearDown(self):
        self.rosbag_directory_patch.stop()
        self.temporary_directory.cleanup()

    def create_bag_file(self, filename='example.bag'):
        path = os.path.join(self.temporary_directory.name, filename)
        with open(path, 'wb'):
            pass
        return path

    @patch('rosbag_processing.views.get_rosbag_duration', return_value=3600.125)
    def test_returns_input_duration(self, get_duration):
        bag_path = self.create_bag_file()

        response = self.client.post(
            '/api/inputs/inspect/',
            {'bag_filename': 'example.bag'},
            format='json',
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, {
            'bag_filename': 'example.bag',
            'duration_seconds': 3600.125,
            'duration_minutes': 60.002,
            'supports_chunking': True,
        })
        get_duration.assert_called_once_with(bag_path)

    def test_rejects_path_traversal(self):
        response = self.client.post(
            '/api/inputs/inspect/',
            {'bag_filename': '../example.bag'},
            format='json',
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn('bag_filename', response.data)

    def test_returns_not_found_for_unknown_bag(self):
        response = self.client.post(
            '/api/inputs/inspect/',
            {'bag_filename': 'missing.bag'},
            format='json',
        )

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.data['error'], 'ROSBag file not found.')

    @patch(
        'rosbag_processing.views.get_rosbag_duration',
        side_effect=RuntimeError('invalid bag'),
    )
    def test_returns_bad_request_for_unreadable_bag(self, _get_duration):
        self.create_bag_file()

        response = self.client.post(
            '/api/inputs/inspect/',
            {'bag_filename': 'example.bag'},
            format='json',
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn('Unable to read ROSBag duration', response.data['error'])


class ChunkManifestTests(SimpleTestCase):
    def test_builds_navigation_and_short_final_chunk(self):
        chunks = build_chunks(610, 300)

        self.assertEqual(len(chunks), 3)
        self.assertEqual(chunks[0]['previous_index'], None)
        self.assertEqual(chunks[0]['next_index'], 1)
        self.assertEqual(chunks[2], {
            'index': 2,
            'start_seconds': 600.0,
            'end_seconds': 610.0,
            'duration_seconds': 10.0,
            'previous_index': 1,
            'next_index': None,
        })

    def test_rejects_invalid_numbers(self):
        for duration, size in ((0, 10), (10, 0), (float('nan'), 10), (True, 10)):
            with self.subTest(duration=duration, size=size):
                with self.assertRaises(ValueError):
                    build_chunks(duration, size)

    def test_persists_and_loads_manifest(self):
        with tempfile.TemporaryDirectory() as directory:
            saved = save_manifest(directory, 'example.bag', 60, 20)
            loaded = load_manifest(directory, saved['id'])

        self.assertEqual(loaded, saved)
        self.assertEqual(loaded['chunk_count'], 3)


class ChunkAnnotationTests(SimpleTestCase):
    def test_filters_clips_and_rebases_annotations(self):
        annotations = [{
            'id': 1,
            'axisType': 'Type-in',
            'axisName': 'Notes',
            'axisBooklistName': '',
            'annotationBlocks': [
                {'start': 290, 'end': 310, 'text': 'crosses start'},
                {'start': 320, 'end': 330, 'text': 'inside'},
                {'start': 590, 'end': 620, 'text': 'crosses end'},
                {'start': 700, 'end': 710, 'text': 'outside'},
            ],
        }]

        result = annotations_for_chunk(annotations, {
            'start_seconds': 300,
            'end_seconds': 600,
        })

        self.assertEqual(result[0]['annotationBlocks'], [
            {'start': 0, 'end': 10, 'text': 'crosses start'},
            {'start': 20, 'end': 30, 'text': 'inside'},
            {'start': 290, 'end': 300, 'text': 'crosses end'},
        ])


class ChunkApiTests(SimpleTestCase):
    def setUp(self):
        self.client = APIClient()
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.rosbag_directory = os.path.join(self.temporary_directory.name, 'bags')
        self.manifest_directory = os.path.join(self.temporary_directory.name, 'manifests')
        os.makedirs(self.rosbag_directory)
        with open(os.path.join(self.rosbag_directory, 'example.bag'), 'wb'):
            pass
        self.settings_patch = self.settings(
            ROSBAG_DATA_DIR=self.rosbag_directory,
            CHUNK_MANIFEST_DIR=self.manifest_directory,
        )
        self.settings_patch.enable()

    def tearDown(self):
        self.settings_patch.disable()
        self.temporary_directory.cleanup()

    @patch('rosbag_processing.chunk_views.read_duration', return_value=610)
    def test_creates_and_retrieves_chunk_manifest(self, _read_duration):
        response = self.client.post('/api/chunks/', {
            'bag_filename': 'example.bag',
            'chunking_enabled': True,
            'chunk_seconds': 300,
        }, format='json')

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data['chunk_count'], 3)
        manifest_id = response.data['id']
        chunk_response = self.client.get(f'/api/chunks/{manifest_id}/2/')
        self.assertEqual(chunk_response.status_code, 200)
        self.assertEqual(chunk_response.data['start_seconds'], 600.0)
        self.assertIsNone(chunk_response.data['next_index'])

    @patch('rosbag_processing.chunk_views.read_duration', return_value=610)
    def test_no_chunking_creates_one_full_input_chunk(self, _read_duration):
        response = self.client.post('/api/chunks/', {
            'bag_filename': 'example.bag',
            'chunking_enabled': False,
        }, format='json')

        self.assertEqual(response.status_code, 201)
        self.assertFalse(response.data['chunking_enabled'])
        self.assertEqual(response.data['chunk_count'], 1)
        self.assertEqual(response.data['chunks'][0]['end_seconds'], 610.0)

    @patch('rosbag_processing.chunk_views.read_duration', return_value=610)
    def test_rejects_chunk_size_equal_to_input(self, _read_duration):
        response = self.client.post('/api/chunks/', {
            'bag_filename': 'example.bag',
            'chunking_enabled': True,
            'chunk_seconds': 610,
        }, format='json')

        self.assertEqual(response.status_code, 400)

    @patch('rosbag_processing.chunk_views.process_chunk')
    def test_processes_selected_chunk(self, process_chunk_mock):
        manifest = save_manifest(
            self.manifest_directory, 'example.bag', 610, 300,
        )
        process_chunk_mock.return_value = {
            **manifest['chunks'][1],
            'video_path': 'chunks/id/0001/output.mp4',
            'status': 'ready',
        }

        response = self.client.post(f"/api/chunks/{manifest['id']}/1/process/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['index'], 1)
        self.assertEqual(response.data['status'], 'ready')
        process_chunk_mock.assert_called_once()

    @patch('rosbag_processing.chunk_views.process_chunk')
    def test_model_certificate_errors_explain_recovery(self, process_chunk_mock):
        import ssl
        from urllib.error import URLError
        from requests.exceptions import SSLError

        manifest = save_manifest(self.manifest_directory, 'example.bag', 610, 300)
        for error in (
            URLError(ssl.SSLCertVerificationError('certificate verify failed')),
            SSLError('certificate verify failed'),
        ):
            with self.subTest(error=type(error).__name__):
                process_chunk_mock.side_effect = error
                response = self.client.post(f"/api/chunks/{manifest['id']}/0/process/")
                self.assertEqual(response.status_code, 503)
                self.assertEqual(response.data['code'], 'model_download_tls_error')
                self.assertIn('CA certificate', response.data['error'])

    @patch('rosbag_processing.chunk_views.process_chunk')
    def test_unrelated_errors_do_not_report_certificate_failure(self, process_chunk_mock):
        manifest = save_manifest(self.manifest_directory, 'example.bag', 610, 300)
        process_chunk_mock.side_effect = ValueError('internal detail')
        response = self.client.post(f"/api/chunks/{manifest['id']}/0/process/")
        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.data, {'error': 'Unable to process chunk.'})
