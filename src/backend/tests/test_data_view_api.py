import tempfile
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID
from unittest.mock import patch

from django.core.cache import cache
from django.test import SimpleTestCase
from rest_framework.test import APIClient

from rosbag_processing.chunks import save_manifest
from tests.test_data_view_processing import FakeBag, SampleProcessor, FailedProcessor


class DataViewApiTests(SimpleTestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / 'sample.bag').write_bytes(b'fake bag')
        self.client = APIClient()
        self.settings_override = self.settings(ROSBAG_DATA_DIR=str(self.root),
                                               CHUNK_MANIFEST_DIR=str(self.root / 'chunks'),
                                               PROCESSED_DATA_DIR=str(self.root / 'processed'))
        self.settings_override.enable()
        self.addCleanup(self.settings_override.disable)
        for target, value in (
            ('rosbag_processing.views.ROSBAG_DATA_DIR', str(self.root)),
            ('rosbag_processing.view_registry.PROCESSORS', (SampleProcessor(), FailedProcessor())),
            ('rosbag_processing.view_workflow.PROCESSORS', (SampleProcessor(), FailedProcessor())),
        ):
            mock = patch(target, value)
            mock.start()
            self.addCleanup(mock.stop)
        runtime = patch.dict('sys.modules', {'rosbag.bag': SimpleNamespace(Bag=lambda *_: FakeBag())})
        runtime.start()
        self.addCleanup(runtime.stop)

    def test_catalog_and_inspection_include_registered_types_and_counts(self):
        catalog = self.client.get('/api/views/').data
        self.assertEqual([v['view_id'] for v in catalog['views']], ['sample', 'broken'])
        result = self.client.post('/api/inputs/inspect/', {'bag_filename': 'sample.bag'}, format='json')
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.data['topics'][0]['message_count'], 1)
        self.assertEqual(result.data['topics'][0]['message_type'], 'test/Sample')

    def test_partial_failure_is_http_success_with_per_view_reason(self):
        with self.assertLogs('rosbag_processing.view_workflow', level='ERROR'):
            response = self.client.post('/api/process_rosbag/', {'bag_filename': 'sample.bag'}, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data['views']['sample']['available'])
        self.assertEqual(response.data['views']['broken']['reason'], 'Decoder failed')
        self.assertIsNone(response.data['error'])

    def test_zero_views_returns_structured_result(self):
        with self.assertLogs('rosbag_processing.view_workflow', level='ERROR'):
            response = self.client.post('/api/process_rosbag/',
                                        {'bag_filename': 'sample.bag', 'view_ids': ['broken']}, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['error']['code'], 'no_available_views')

    def test_selected_view_and_options_flow_through_chunk_api(self):
        manifest = save_manifest(self.root / 'chunks', 'sample.bag', 10, 5,
                                 view_options={'sample': {'topics': ['/custom']}})
        response = self.client.post(f"/api/chunks/{manifest['id']}/0/process/",
                                    {'view_ids': ['sample']}, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(set(response.data['views']), {'sample'})
        self.assertEqual(response.data['views']['sample']['selected_topics'], ['/custom'])
        self.assertEqual(response.data['time_origin']['reference'], 'chunk_start')
        summary = self.client.get(f"/api/chunks/{manifest['id']}/").data
        self.assertEqual(summary['chunks'][0]['status'], 'ready')

    def test_chunk_video_responses_create_isolated_chat_contexts(self):
        manifest = save_manifest(self.root / 'chunks', 'sample.bag', 10, 5)
        processed_result = {
            'video_path': 'chunk/video.mp4', 'audio_path': None,
            'waveform_image_path': None, 'audio_transcript': '',
            'speaker_data': [], 'views': {},
        }
        with patch('rosbag_processing.chunk_views.process_chunk', return_value=processed_result):
            first = self.client.post(f"/api/chunks/{manifest['id']}/0/process/", {}, format='json')
            second = self.client.post(f"/api/chunks/{manifest['id']}/1/process/", {}, format='json')

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        first_id, second_id = first.data['chat_context_id'], second.data['chat_context_id']
        UUID(first_id)
        UUID(second_id)
        self.assertNotEqual(first_id, second_id)
        self.assertEqual(cache.get('chat:' + first_id), {'frames': [], 'history': ''})
        self.assertEqual(cache.get('chat:' + second_id), {'frames': [], 'history': ''})

    def test_unknown_view_rejected_before_processing(self):
        response = self.client.post('/api/process_rosbag/',
                                    {'bag_filename': 'sample.bag', 'view_ids': ['missing']}, format='json')
        self.assertEqual(response.status_code, 400)
