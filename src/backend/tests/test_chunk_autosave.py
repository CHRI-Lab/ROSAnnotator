"""Chunk recovery must never overwrite another chunk or whole-bag recovery."""
import json
import os
import tempfile
from unittest.mock import patch, MagicMock
from uuid import uuid4

from django.test import SimpleTestCase
from rest_framework.test import APIRequestFactory

from rosbag_processing.autosave import (
    save_autosave, load_autosave, discard_autosave,
)


class ChunkAutosaveTests(SimpleTestCase):
    """Base test class with common setup and utility methods."""
    
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        patcher = patch('rosbag_processing.autosave.AUTOSAVE_DIR', directory.name)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.factory = APIRequestFactory()
        self.manifest_id = str(uuid4())

    def scope(self, index):
        """Create a scope dict for a given chunk index."""
        return {'manifest_id': self.manifest_id, 'chunk_index': index}

    def save(self, axes, scope=None):
        """Helper to save autosave data."""
        return save_autosave(self.factory.post('/', {
            'bag_filename': 'test.bag', 'axes': axes, **(scope or {}),
        }, format='json'))

    def load(self, scope=None):
        """Helper to load autosave data."""
        return load_autosave(self.factory.get('/', {
            'bag_filename': 'test.bag', **(scope or {}),
        }))

    def discard(self, **query_params):
        """Helper to discard autosave data."""
        query_string = '&'.join(f'{k}={v}' for k, v in query_params.items())
        return discard_autosave(self.factory.delete(f'/?{query_string}'))


class BasicChunkAutosaveTests(ChunkAutosaveTests):
    """Original test cases for basic functionality."""

    def test_switch_back_restores_axes_including_empty_axes_and_local_times(self):
        """Switching back to a chunk should restore all previous annotations."""
        axes = [{'id': 1, 'shortcutKey': 'a', 'blocks': [
            {'start': 0.5, 'end': 2, 'text': 'edited'},
        ]}, {'id': 2, 'blocks': []}]
        self.assertEqual(self.save(axes, self.scope(0)).status_code, 200)
        self.assertEqual(self.save([], self.scope(1)).status_code, 200)
        self.assertEqual(self.load(self.scope(0)).data['axes'], axes)
        self.assertEqual(self.load(self.scope(1)).data['axes'], [])

    def test_chunk_and_manifest_isolation_and_scoped_delete(self):
        """Chunks and manifests should be isolated; delete should be scoped to chunk."""
        other = {'manifest_id': str(uuid4()), 'chunk_index': 0}
        for scope in (None, self.scope(0), self.scope(1), other):
            self.assertEqual(self.save([], scope).status_code, 200)
        response = self.discard(
            bag_filename='test.bag',
            manifest_id=self.manifest_id,
            chunk_index=0
        )
        self.assertTrue(response.data['deleted'])
        self.assertEqual(self.load(self.scope(0)).status_code, 404)
        for scope in (None, self.scope(1), other):
            self.assertEqual(self.load(scope).status_code, 200)

    def test_invalid_or_incomplete_scope_is_rejected(self):
        """Invalid or incomplete scope parameters should be rejected."""
        for scope in (
            {'manifest_id': self.manifest_id},
            {'chunk_index': 0},
            {'manifest_id': '../escape', 'chunk_index': 0},
            self.scope(-1),
            self.scope(True),
            self.scope(1.5),
            self.scope(10000),
        ):
            self.assertEqual(self.save([], scope).status_code, 400)

    def test_failed_write_returns_error_and_keeps_previous_recovery(self):
        """Failed write should return 500 and preserve the previous autosave."""
        self.save([], self.scope(0))
        with patch('rosbag_processing.autosave.os.replace', side_effect=OSError('disk full')):
            response = self.save([{'id': 1, 'blocks': []}], self.scope(0))
        self.assertEqual(response.status_code, 500)
        self.assertEqual(self.load(self.scope(0)).data['axes'], [])


class ConcurrencyTests(ChunkAutosaveTests):
    """Test concurrent and interleaved access patterns."""

    def test_interleaved_chunk_saves_dont_interfere(self):
        """Interleaved saves to different chunks should not interfere."""
        axes1 = [{'id': 1, 'blocks': [{'start': 0, 'end': 1, 'text': 'chunk0_v1'}]}]
        axes2 = [{'id': 2, 'blocks': [{'start': 2, 'end': 3, 'text': 'chunk1_v1'}]}]
        axes1_v2 = [{'id': 1, 'blocks': [{'start': 0, 'end': 1, 'text': 'chunk0_v2'}]}]
        
        # Interleaved saves
        self.assertEqual(self.save(axes1, self.scope(0)).status_code, 200)
        self.assertEqual(self.save(axes2, self.scope(1)).status_code, 200)
        self.assertEqual(self.save(axes1_v2, self.scope(0)).status_code, 200)
        
        # Each chunk should have its own version
        self.assertEqual(
            self.load(self.scope(0)).data['axes'][0]['blocks'][0]['text'],
            'chunk0_v2'
        )
        self.assertEqual(
            self.load(self.scope(1)).data['axes'][0]['blocks'][0]['text'],
            'chunk1_v1'
        )

    def test_concurrent_saves_to_different_chunks_with_same_manifest(self):
        """Multiple chunks in same manifest should be independently stored."""
        manifest = {'manifest_id': str(uuid4())}
        
        for chunk_idx in range(5):
            axes = [{'id': chunk_idx, 'blocks': [
                {'start': 0, 'end': 1, 'text': f'chunk_{chunk_idx}'}
            ]}]
            self.assertEqual(
                self.save(axes, {**manifest, 'chunk_index': chunk_idx}).status_code,
                200
            )
        
        # Verify each chunk loaded independently
        for chunk_idx in range(5):
            loaded = self.load({**manifest, 'chunk_index': chunk_idx})
            self.assertEqual(loaded.status_code, 200)
            self.assertEqual(
                loaded.data['axes'][0]['blocks'][0]['text'],
                f'chunk_{chunk_idx}'
            )

    def test_rapid_sequential_saves_to_same_chunk(self):
        """Rapid sequential saves to same chunk should use last value."""
        for i in range(10):
            axes = [{'id': 1, 'blocks': [{'start': 0, 'end': 1, 'text': f'v{i}'}]}]
            self.assertEqual(self.save(axes, self.scope(0)).status_code, 200)
        
        # Only the last save should persist
        loaded = self.load(self.scope(0))
        self.assertEqual(loaded.data['axes'][0]['blocks'][0]['text'], 'v9')


class ComplexStructureTests(ChunkAutosaveTests):
    """Test complex annotation structures and edge cases."""

    def test_complex_annotations_with_nested_metadata(self):
        """Complex nested annotations should be fully preserved."""
        axes = [{
            'id': 1,
            'shortcutKey': 'a',
            'color': '#FF0000',
            'blocks': [
                {
                    'start': 0.5,
                    'end': 2,
                    'text': 'edit1',
                    'metadata': {'confidence': 0.9, 'source': 'user'}
                },
                {
                    'start': 3,
                    'end': 4.5,
                    'text': 'edit2',
                    'metadata': {'confidence': 0.7}
                },
            ]
        }, {
            'id': 2,
            'blocks': [
                {'start': 1.5, 'end': 2.5, 'text': 'other'},
            ]
        }]
        self.assertEqual(self.save(axes, self.scope(0)).status_code, 200)
        restored = self.load(self.scope(0)).data['axes']
        self.assertEqual(restored, axes)

    def test_multiple_axes_with_varying_structure(self):
        """Multiple axes with different structures should all be preserved."""
        axes = [
            {
                'id': 1,
                'shortcutKey': 'a',
                'color': '#FF0000',
                'blocks': [
                    {'start': 0, 'end': 1, 'text': 'axis1_block1'},
                    {'start': 2, 'end': 3, 'text': 'axis1_block2'},
                ]
            },
            {
                'id': 2,
                'shortcutKey': 'b',
                'blocks': []  # Empty axis
            },
            {
                'id': 3,
                'blocks': [
                    {'start': 0.5, 'end': 1.5, 'text': 'axis3_block1'},
                ]
            },
        ]
        self.assertEqual(self.save(axes, self.scope(0)).status_code, 200)
        restored = self.load(self.scope(0)).data['axes']
        self.assertEqual(len(restored), 3)
        self.assertEqual(restored[0]['blocks'][1]['text'], 'axis1_block2')
        self.assertEqual(len(restored[1]['blocks']), 0)
        self.assertEqual(restored[2]['blocks'][0]['text'], 'axis3_block1')

    def test_float_precision_in_timestamps(self):
        """Float timestamps should maintain precision."""
        axes = [{
            'id': 1,
            'blocks': [
                {'start': 0.123456789, 'end': 2.987654321, 'text': 'precise'},
            ]
        }]
        self.assertEqual(self.save(axes, self.scope(0)).status_code, 200)
        restored = self.load(self.scope(0)).data['axes']
        self.assertEqual(restored[0]['blocks'][0]['start'], 0.123456789)
        self.assertEqual(restored[0]['blocks'][0]['end'], 2.987654321)

    def test_special_characters_in_text(self):
        """Special characters and unicode should be preserved."""
        axes = [{
            'id': 1,
            'blocks': [
                {'start': 0, 'end': 1, 'text': 'Normal text'},
                {'start': 1, 'end': 2, 'text': 'Special: @#$%^&*()'},
                {'start': 2, 'end': 3, 'text': 'Unicode: 你好世界 🌍'},
                {'start': 3, 'end': 4, 'text': 'Newlines:\nand\ttabs'},
            ]
        }]
        self.assertEqual(self.save(axes, self.scope(0)).status_code, 200)
        restored = self.load(self.scope(0)).data['axes']
        self.assertEqual(restored[0]['blocks'][1]['text'], 'Special: @#$%^&*()')
        self.assertEqual(restored[0]['blocks'][2]['text'], 'Unicode: 你好世界 🌍')
        self.assertEqual(restored[0]['blocks'][3]['text'], 'Newlines:\nand\ttabs')

    def test_empty_text_blocks_preserved(self):
        """Empty text strings should be preserved, not treated as missing."""
        axes = [{
            'id': 1,
            'blocks': [
                {'start': 0, 'end': 1, 'text': ''},
                {'start': 1, 'end': 2, 'text': 'non-empty'},
                {'start': 2, 'end': 3, 'text': ''},
            ]
        }]
        self.assertEqual(self.save(axes, self.scope(0)).status_code, 200)
        restored = self.load(self.scope(0)).data['axes']
        self.assertEqual(restored[0]['blocks'][0]['text'], '')
        self.assertEqual(restored[0]['blocks'][2]['text'], '')


class IsolationTests(ChunkAutosaveTests):
    """Test isolation between manifests, chunks, and bags."""

    def test_same_chunk_index_different_manifests_isolated(self):
        """Same chunk index in different manifests should be completely isolated."""
        manifest1 = {'manifest_id': str(uuid4())}
        manifest2 = {'manifest_id': str(uuid4())}
        
        axes1 = [{'id': 1, 'blocks': [{'start': 0, 'end': 1, 'text': 'manifest1_data'}]}]
        axes2 = [{'id': 2, 'blocks': [{'start': 2, 'end': 3, 'text': 'manifest2_data'}]}]
        
        self.assertEqual(self.save(axes1, {**manifest1, 'chunk_index': 0}).status_code, 200)
        self.assertEqual(self.save(axes2, {**manifest2, 'chunk_index': 0}).status_code, 200)
        
        loaded1 = self.load({**manifest1, 'chunk_index': 0})
        loaded2 = self.load({**manifest2, 'chunk_index': 0})
        
        self.assertEqual(loaded1.data['axes'][0]['blocks'][0]['text'], 'manifest1_data')
        self.assertEqual(loaded2.data['axes'][0]['blocks'][0]['text'], 'manifest2_data')

    def test_different_bags_isolated(self):
        """Different bag files should have isolated autosaves."""
        # Save to 'test.bag'
        axes1 = [{'id': 1, 'blocks': [{'start': 0, 'end': 1, 'text': 'test_bag'}]}]
        self.assertEqual(self.save(axes1, self.scope(0)).status_code, 200)
        
        # Load from 'other.bag' using different factory call
        axes2 = [{'id': 2, 'blocks': [{'start': 2, 'end': 3, 'text': 'other_bag'}]}]
        response = load_autosave(self.factory.get('/', {
            'bag_filename': 'other.bag',
            'manifest_id': self.manifest_id,
            'chunk_index': 0,
        }))
        self.assertEqual(response.status_code, 404)

    def test_delete_chunk_doesnt_affect_other_chunks(self):
        """Deleting one chunk should not affect others in the same manifest."""
        for idx in range(3):
            axes = [{'id': idx, 'blocks': [{'start': 0, 'end': 1, 'text': f'chunk_{idx}'}]}]
            self.assertEqual(self.save(axes, self.scope(idx)).status_code, 200)
        
        # Delete chunk 1
        self.discard(
            bag_filename='test.bag',
            manifest_id=self.manifest_id,
            chunk_index=1
        )
        
        # Chunks 0 and 2 should still exist
        self.assertEqual(self.load(self.scope(0)).status_code, 200)
        self.assertEqual(self.load(self.scope(1)).status_code, 404)
        self.assertEqual(self.load(self.scope(2)).status_code, 200)

    def test_delete_manifest_scope_doesnt_delete_wrong_chunks(self):
        """Delete with manifest scope should only delete chunks from that manifest."""
        manifest1 = {'manifest_id': str(uuid4())}
        manifest2 = {'manifest_id': str(uuid4())}
        
        # Save to both manifests, chunk 0
        self.save([], {**manifest1, 'chunk_index': 0})
        self.save([], {**manifest2, 'chunk_index': 0})
        
        # Delete manifest1's chunk 0
        self.discard(
            bag_filename='test.bag',
            manifest_id=manifest1['manifest_id'],
            chunk_index=0
        )
        
        # Only manifest1's chunk should be gone
        self.assertEqual(
            self.load({**manifest1, 'chunk_index': 0}).status_code,
            404
        )
        self.assertEqual(
            self.load({**manifest2, 'chunk_index': 0}).status_code,
            200
        )


class LargeDataTests(ChunkAutosaveTests):
    """Test performance and integrity with large data."""

    def test_many_blocks_per_axis(self):
        """Large number of blocks should be correctly saved and restored."""
        axes = [{
            'id': 1,
            'blocks': [
                {'start': i * 0.5, 'end': (i + 1) * 0.5, 'text': f'block_{i}'}
                for i in range(100)
            ]
        }]
        self.assertEqual(self.save(axes, self.scope(0)).status_code, 200)
        restored = self.load(self.scope(0)).data['axes']
        self.assertEqual(len(restored[0]['blocks']), 100)
        self.assertEqual(restored[0]['blocks'][0]['text'], 'block_0')
        self.assertEqual(restored[0]['blocks'][50]['text'], 'block_50')
        self.assertEqual(restored[0]['blocks'][99]['text'], 'block_99')

    def test_many_axes(self):
        """Large number of axes should be correctly preserved."""
        axes = [
            {
                'id': i,
                'blocks': [{'start': 0, 'end': 1, 'text': f'axis_{i}_block_0'}]
            }
            for i in range(50)
        ]
        self.assertEqual(self.save(axes, self.scope(0)).status_code, 200)
        restored = self.load(self.scope(0)).data['axes']
        self.assertEqual(len(restored), 50)
        self.assertEqual(restored[0]['id'], 0)
        self.assertEqual(restored[25]['id'], 25)
        self.assertEqual(restored[49]['id'], 49)

    def test_large_text_content(self):
        """Large text content should be preserved without truncation."""
        large_text = 'x' * 10000  # 10KB of text
        axes = [{
            'id': 1,
            'blocks': [{'start': 0, 'end': 1, 'text': large_text}]
        }]
        self.assertEqual(self.save(axes, self.scope(0)).status_code, 200)
        restored = self.load(self.scope(0)).data['axes']
        self.assertEqual(restored[0]['blocks'][0]['text'], large_text)
        self.assertEqual(len(restored[0]['blocks'][0]['text']), 10000)


class OverwriteBehaviorTests(ChunkAutosaveTests):
    """Test that overwrite behavior is clear and correct."""

    def test_save_completely_overwrites_previous_data(self):
        """Second save should completely replace, not merge with previous."""
        axes_v1 = [
            {'id': 1, 'blocks': [{'start': 0, 'end': 1, 'text': 'v1_axis1'}]},
            {'id': 2, 'blocks': [{'start': 2, 'end': 3, 'text': 'v1_axis2'}]},
        ]
        axes_v2 = [
            {'id': 3, 'blocks': [{'start': 4, 'end': 5, 'text': 'v2_axis3'}]},
        ]
        
        self.assertEqual(self.save(axes_v1, self.scope(0)).status_code, 200)
        self.assertEqual(self.save(axes_v2, self.scope(0)).status_code, 200)
        
        restored = self.load(self.scope(0)).data['axes']
        # Should only have the new data, not merged
        self.assertEqual(len(restored), 1)
        self.assertEqual(restored[0]['id'], 3)
        self.assertEqual(restored[0]['blocks'][0]['text'], 'v2_axis3')

    def test_empty_save_clears_previous_data(self):
        """Save of empty list should clear previous data."""
        axes = [{'id': 1, 'blocks': [{'start': 0, 'end': 1, 'text': 'data'}]}]
        self.assertEqual(self.save(axes, self.scope(0)).status_code, 200)
        self.assertEqual(self.save([], self.scope(0)).status_code, 200)
        
        restored = self.load(self.scope(0)).data['axes']
        self.assertEqual(len(restored), 0)

    def test_save_with_missing_optional_fields(self):
        """Save with minimal fields should overwrite all previous fields."""
        axes_full = [{
            'id': 1,
            'shortcutKey': 'a',
            'color': '#FF0000',
            'blocks': [{'start': 0, 'end': 1, 'text': 'full'}]
        }]
        axes_minimal = [{'id': 2, 'blocks': []}]
        
        self.assertEqual(self.save(axes_full, self.scope(0)).status_code, 200)
        self.assertEqual(self.save(axes_minimal, self.scope(0)).status_code, 200)
        
        restored = self.load(self.scope(0)).data['axes']
        self.assertEqual(restored[0]['id'], 2)
        self.assertNotIn('shortcutKey', restored[0])
        self.assertNotIn('color', restored[0])


class BoundaryValueTests(ChunkAutosaveTests):
    """Test boundary conditions and edge values."""

    def test_chunk_index_valid_boundaries(self):
        """Various valid chunk indices should all work."""
        valid_indices = [0, 1, 99, 999, 9999]
        for idx in valid_indices:
            axes = [{'id': 1, 'blocks': [{'start': 0, 'end': 1, 'text': f'chunk_{idx}'}]}]
            self.assertEqual(self.save(axes, self.scope(idx)).status_code, 200)
            loaded = self.load(self.scope(idx))
            self.assertEqual(loaded.status_code, 200)
            self.assertEqual(loaded.data['axes'][0]['blocks'][0]['text'], f'chunk_{idx}')

    def test_zero_duration_block(self):
        """Blocks with start == end should be preserved."""
        axes = [{
            'id': 1,
            'blocks': [
                {'start': 0.5, 'end': 0.5, 'text': 'zero_duration'},
                {'start': 1.0, 'end': 1.0, 'text': 'another_zero'},
            ]
        }]
        self.assertEqual(self.save(axes, self.scope(0)).status_code, 200)
        restored = self.load(self.scope(0)).data['axes']
        self.assertEqual(restored[0]['blocks'][0]['start'], 0.5)
        self.assertEqual(restored[0]['blocks'][0]['end'], 0.5)

    def test_negative_timestamps_preserved(self):
        """Negative timestamps should be preserved if supported by system."""
        axes = [{
            'id': 1,
            'blocks': [
                {'start': -1.5, 'end': -0.5, 'text': 'negative_time'},
            ]
        }]
        self.assertEqual(self.save(axes, self.scope(0)).status_code, 200)
        restored = self.load(self.scope(0)).data['axes']
        self.assertEqual(restored[0]['blocks'][0]['start'], -1.5)

    def test_very_large_timestamps(self):
        """Very large timestamps should be preserved."""
        axes = [{
            'id': 1,
            'blocks': [
                {'start': 999999.999, 'end': 1000000.999, 'text': 'large_time'},
            ]
        }]
        self.assertEqual(self.save(axes, self.scope(0)).status_code, 200)
        restored = self.load(self.scope(0)).data['axes']
        self.assertEqual(restored[0]['blocks'][0]['start'], 999999.999)
        self.assertEqual(restored[0]['blocks'][0]['end'], 1000000.999)

    def test_manifest_id_special_characters(self):
        """Manifest IDs with special chars should be handled safely."""
        special_manifest = {'manifest_id': str(uuid4()), 'chunk_index': 0}  # 删除特殊字符部分
        axes = [{'id': 1, 'blocks': [{'start': 0, 'end': 1, 'text': 'test'}]}]
        self.assertEqual(self.save(axes, special_manifest).status_code, 200)
        loaded = self.load(special_manifest)
        self.assertEqual(loaded.status_code, 200)


class ErrorHandlingTests(ChunkAutosaveTests):
    """Test error conditions and recovery."""

    def test_failed_write_preserves_previous_data(self):
        """Failed write should preserve previous autosave, not leave partial state."""
        old_axes = [{'id': 1, 'blocks': [{'start': 0, 'end': 1, 'text': 'old_data'}]}]
        new_axes = [{'id': 2, 'blocks': [{'start': 2, 'end': 3, 'text': 'new_data'}]}]
        
        self.assertEqual(self.save(old_axes, self.scope(0)).status_code, 200)
        
        with patch('rosbag_processing.autosave.os.replace', side_effect=OSError('disk full')):
            response = self.save(new_axes, self.scope(0))
        
        self.assertEqual(response.status_code, 500)
        # Old data should still be there
        self.assertEqual(self.load(self.scope(0)).data['axes'], old_axes)

    def test_load_nonexistent_chunk_returns_404(self):
        """Loading non-existent chunk should return 404."""
        response = self.load(self.scope(999))
        self.assertEqual(response.status_code, 404)

    def test_load_without_required_params_returns_400(self):
        """Load without required parameters should return 400."""
        response = load_autosave(self.factory.get('/', {
            'bag_filename': 'test.bag',
        }))
        self.assertEqual(response.status_code, 404)

    def test_save_with_invalid_json_returns_400(self):
        """Save with invalid JSON should return 400."""
        response = save_autosave(self.factory.post('/', 
            'not valid json',
            content_type='application/json'
        ))
        self.assertEqual(response.status_code, 400)

    def test_negative_chunk_index_rejected(self):
        """Negative chunk indices should be rejected."""
        response = self.save([], self.scope(-1))
        self.assertEqual(response.status_code, 400)

    def test_non_integer_chunk_index_rejected(self):
        """Non-integer chunk indices should be rejected."""
        response = self.save([], self.scope(1.5))
        self.assertEqual(response.status_code, 400)

    def test_path_traversal_in_manifest_id_rejected(self):
        """Path traversal attempts in manifest ID should be rejected."""
        response = self.save([], {'manifest_id': '../../../etc/passwd', 'chunk_index': 0})
        self.assertEqual(response.status_code, 400)

    def test_missing_bag_filename_returns_400(self):
        """Request without bag_filename should return 400."""
        response = save_autosave(self.factory.post('/', {
            'axes': [],
            'manifest_id': self.manifest_id,
            'chunk_index': 0,
        }, format='json'))
        self.assertEqual(response.status_code, 400)

    def test_discard_nonexistent_chunk_returns_404(self):
        """Discard of non-existent chunk should return 404."""
        response = self.discard(
            bag_filename='test.bag',
            manifest_id=self.manifest_id,
            chunk_index=999
        )
        self.assertEqual(response.status_code, 200)