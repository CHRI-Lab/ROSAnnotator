import tempfile
from pathlib import Path
from unittest.mock import patch

from django.test import SimpleTestCase
from rest_framework.test import APIRequestFactory

from rosbag_processing.transcript_views import transcript_detail
from rosbag_processing.view_cache import atomic_json
from tests.test_transcript_edits import generated_transcript, segment


class TranscriptApiTests(SimpleTestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.key = 'a' * 64
        override = self.settings(PROCESSED_DATA_DIR=str(self.root / 'whole'), CHUNK_MANIFEST_DIR=str(self.root / 'chunks'))
        override.enable()
        self.addCleanup(override.disable)
        for scope in ['whole', 'chunks']:
            atomic_json(self.root / scope / 'views' / self.key / 'result.json', generated_transcript())
        self.factory = APIRequestFactory()

    def put(self, body, scope='chunks', key=None):
        return transcript_detail(self.factory.put('/api/transcripts/', body, format='json'), scope, key or self.key)

    def get(self, scope='chunks', key=None):
        return transcript_detail(self.factory.get('/api/transcripts/'), scope, key or self.key)

    def test_save_and_get_update_all_transcript_representations(self):
        edited = [segment('Alice', 'Edited', 2.75, 3.875)]
        saved = self.put({'revision': 0, 'speaker_data': edited})
        self.assertEqual(saved.status_code, 200)
        self.assertEqual(saved.data['speaker_data'], edited)
        self.assertEqual(saved.data['view']['processed_data']['speaker_data'], edited)
        self.assertIn('Alice: Edited', saved.data['audio_transcript'])
        self.assertEqual(self.get().data, saved.data)
        self.assertEqual(self.get('whole').data['view']['processed_data']['revision'], 0)

    def test_conflict_and_invalid_times_do_not_overwrite_saved_data(self):
        self.assertEqual(self.put({'revision': 0, 'speaker_data': [segment(text='Saved')]}).status_code, 200)
        self.assertEqual(self.put({'revision': 0, 'speaker_data': []}).status_code, 409)
        self.assertEqual(self.put({'revision': 1, 'speaker_data': [segment(end=300)]}).status_code, 400)
        self.assertEqual(self.get().data['speaker_data'][0]['text'], 'Saved')

    def test_unknown_and_unsafe_references_are_rejected(self):
        self.assertEqual(self.get(key='b' * 64).status_code, 404)
        for key in ['../result.json', 'a' * 63, '/tmp/file', 'A' * 64]:
            self.assertEqual(self.put({'revision': 0, 'speaker_data': []}, key=key).status_code, 400)
        self.assertEqual(self.get(scope='elsewhere').status_code, 400)
        self.assertEqual(self.put([]).status_code, 400)

    def test_storage_failure_is_reported_without_claiming_success(self):
        with patch('rosbag_processing.transcript_edits.atomic_json', side_effect=OSError('full')):
            self.assertEqual(self.put({'revision': 0, 'speaker_data': []}).status_code, 500)
        self.assertEqual(self.get().data['view']['processed_data']['revision'], 0)

    def test_uuid6_cache_reference_can_be_loaded_and_saved(self):
        key = '1ef12345-6789-6abc-8def-0123456789ab'
        atomic_json(self.root / 'chunks' / 'views' / key / 'result.json', generated_transcript())
        self.assertEqual(self.get(key=key).status_code, 200)
        saved = self.put({'revision': 0, 'speaker_data': [segment('Alice')]}, key=key)
        self.assertEqual(saved.status_code, 200)
        self.assertEqual(self.get(key=key).data['view']['processed_data']['revision'], 1)
