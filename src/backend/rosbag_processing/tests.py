import os
import tempfile
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase
from rest_framework.test import APIClient

from .chunks import build_chunks, load_manifest, save_manifest
from .data_utils import get_rosbag_duration


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
