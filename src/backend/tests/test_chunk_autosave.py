"""Chunk recovery must never overwrite another chunk or whole-bag recovery."""
import tempfile
from unittest.mock import patch
from uuid import uuid4

from django.test import SimpleTestCase
from rest_framework.test import APIRequestFactory

from rosbag_processing.autosave import (
    save_autosave, load_autosave, discard_autosave,
)


class ChunkAutosaveTests(SimpleTestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        patcher = patch('rosbag_processing.autosave.AUTOSAVE_DIR', directory.name)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.factory = APIRequestFactory()
        self.manifest_id = str(uuid4())

    def scope(self, index):
        return {'manifest_id': self.manifest_id, 'chunk_index': index}

    def save(self, axes, scope=None):
        return save_autosave(self.factory.post('/', {
            'bag_filename': 'test.bag', 'axes': axes, **(scope or {}),
        }, format='json'))

    def load(self, scope=None):
        return load_autosave(self.factory.get('/', {
            'bag_filename': 'test.bag', **(scope or {}),
        }))

    def test_switch_back_restores_axes_including_empty_axes_and_local_times(self):
        axes = [{'id': 1, 'shortcutKey': 'a', 'blocks': [
            {'start': 0.5, 'end': 2, 'text': 'edited'},
        ]}, {'id': 2, 'blocks': []}]
        self.assertEqual(self.save(axes, self.scope(0)).status_code, 200)
        self.assertEqual(self.save([], self.scope(1)).status_code, 200)
        self.assertEqual(self.load(self.scope(0)).data['axes'], axes)
        self.assertEqual(self.load(self.scope(1)).data['axes'], [])

    def test_chunk_and_manifest_isolation_and_scoped_delete(self):
        other = {'manifest_id': str(uuid4()), 'chunk_index': 0}
        for scope in (None, self.scope(0), self.scope(1), other):
            self.assertEqual(self.save([], scope).status_code, 200)
        response = discard_autosave(self.factory.delete(
            '/?bag_filename=test.bag&manifest_id=' + self.manifest_id + '&chunk_index=0'
        ))
        self.assertTrue(response.data['deleted'])
        self.assertEqual(self.load(self.scope(0)).status_code, 404)
        for scope in (None, self.scope(1), other):
            self.assertEqual(self.load(scope).status_code, 200)

    def test_invalid_or_incomplete_scope_is_rejected(self):
        for scope in (
            {'manifest_id': self.manifest_id}, {'chunk_index': 0},
            {'manifest_id': '../escape', 'chunk_index': 0},
            self.scope(-1), self.scope(True), self.scope(1.5), self.scope(10000),
        ):
            self.assertEqual(self.save([], scope).status_code, 400)

    def test_failed_write_returns_error_and_keeps_previous_recovery(self):
        self.save([], self.scope(0))
        with patch('rosbag_processing.autosave.os.replace', side_effect=OSError('disk full')):
            response = self.save([{'id': 1, 'blocks': []}], self.scope(0))
        self.assertEqual(response.status_code, 500)
        self.assertEqual(self.load(self.scope(0)).data['axes'], [])
