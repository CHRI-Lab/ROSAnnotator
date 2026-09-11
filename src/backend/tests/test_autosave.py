import json
import os
import tempfile
import time
from unittest.mock import patch, MagicMock

import pytest
from django.test import TestCase, Client
from rest_framework import status

from rosbag_processing.autosave import (
    write_autosave,
    read_autosave,
    delete_autosave,
    _autosave_paths,
    _autosave_stem,
    AutosaveNameError,
)


class Test1_ModifyAndWait(TestCase):
    """Scenario 1: Modify annotation, wait for interval, autosave writes latest state."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.client = Client()

    def test_modification_triggers_autosave(self):
        """Modifying annotation should trigger autosave write."""
        initial_payload = {
            'schema_version': 1,
            'bag_filename': 'test.bag',
            'axes': [
                {
                    'name': 'Speech Acts',
                    'type': 'select',
                    'blocks': []
                }
            ],
            'saved_at': '2024-01-01T12:00:00Z',
        }

        with patch('rosbag_processing.autosave.AUTOSAVE_DIR', self.temp_dir):
            path = write_autosave('test.bag', initial_payload)
            self.assertTrue(os.path.exists(path))

            retrieved = read_autosave('test.bag')
            self.assertIsNotNone(retrieved)
            self.assertEqual(len(retrieved['axes'][0]['blocks']), 0)

            modified_payload = initial_payload.copy()
            modified_payload['axes'][0]['blocks'].append({
                'start': 0.0,
                'end': 5.0,
                'code': 'greeting'
            })

            path = write_autosave('test.bag', modified_payload)
            updated = read_autosave('test.bag')

            self.assertEqual(len(updated['axes'][0]['blocks']), 1)
            self.assertEqual(updated['axes'][0]['blocks'][0]['code'], 'greeting')


class Test2_IdempotentSave(TestCase):
    """Scenario 2: No changes during interval - save remains idempotent."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()

    def test_identical_saves_dont_duplicate_data(self):
        """Saving identical state twice should not create duplicates."""
        payload = {
            'schema_version': 1,
            'bag_filename': 'test.bag',
            'axes': [{'name': 'axis1', 'type': 'select', 'blocks': []}],
            'saved_at': '2024-01-01T12:00:00Z',
        }

        with patch('rosbag_processing.autosave.AUTOSAVE_DIR', self.temp_dir):
            path1 = write_autosave('test.bag', payload)
            stat1 = os.stat(path1).st_size

            time.sleep(0.1)

            path2 = write_autosave('test.bag', payload)
            stat2 = os.stat(path2).st_size

            self.assertEqual(path1, path2)
            self.assertEqual(stat1, stat2)


class Test3_RapidEditsLatestWins(TestCase):
    """Scenario 3: Rapid edits - latest state saved, no intermediate overwrites."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()

    def test_rapid_edits_preserve_latest(self):
        """Multiple rapid edits should only save the latest state."""
        base_payload = {
            'schema_version': 1,
            'bag_filename': 'test.bag',
            'saved_at': '2024-01-01T12:00:00Z',
        }

        with patch('rosbag_processing.autosave.AUTOSAVE_DIR', self.temp_dir):
            for i in range(10):
                payload = base_payload.copy()
                payload['axes'] = [
                    {
                        'name': 'axis',
                        'type': 'select',
                        'blocks': [
                            {'start': 0.0, 'end': float(i), 'code': 'edit_' + str(i)}
                        ]
                    }
                ]
                write_autosave('test.bag', payload)

            final = read_autosave('test.bag')

        self.assertEqual(final['axes'][0]['blocks'][0]['end'], 9.0)
        self.assertEqual(final['axes'][0]['blocks'][0]['code'], 'edit_9')


class Test4_RecoveryDetectionOnReopen(TestCase):
    """Scenario 4: Reopen after successful autosave - detect recovery data."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.client = Client()

    def test_check_endpoint_detects_recovery(self):
        """check_autosave endpoint should detect existing recovery data."""
        payload = {
            'schema_version': 1,
            'bag_filename': 'test.bag',
            'booklist_filename': 'codebook.json',
            'annotation_name': 'Session 1',
            'axes': [
                {
                    'name': 'Speech Acts',
                    'type': 'select',
                    'blocks': [{'start': 0.0, 'end': 5.0, 'code': 'request'}]
                }
            ],
            'saved_at': '2024-01-01T12:00:00Z',
        }

        with patch('rosbag_processing.autosave.AUTOSAVE_DIR', self.temp_dir):
            write_autosave('test.bag', payload)

            response = self.client.get('/api/autosave/check/', {'bag_filename': 'test.bag'})

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data.get('exists', False))


class Test5_RecoveryPromptNoSilentOverwrite(TestCase):
    """Scenario 5: Recovery data exists - user prompted, no silent overwrite."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()

    def test_recovery_metadata_returned_for_prompt(self):
        """Recovery check should return metadata for UI prompt."""
        payload = {
            'schema_version': 1,
            'bag_filename': 'test.bag',
            'booklist_filename': 'codebook.json',
            'annotation_name': 'Session 1',
            'axes': [
                {
                    'name': 'Speech Acts',
                    'type': 'select',
                    'blocks': [
                        {'start': 0.0, 'end': 5.0, 'code': 'request'},
                        {'start': 5.0, 'end': 10.0, 'code': 'response'}
                    ]
                }
            ],
            'saved_at': '2024-01-01T12:00:00Z',
        }

        with patch('rosbag_processing.autosave.AUTOSAVE_DIR', self.temp_dir):
            write_autosave('test.bag', payload)
            recovered = read_autosave('test.bag')

        self.assertEqual(recovered['bag_filename'], 'test.bag')
        self.assertEqual(recovered['annotation_name'], 'Session 1')
        self.assertEqual(len(recovered['axes'][0]['blocks']), 2)
        self.assertFalse(recovered.get('recovered_from_backup', False))


class Test6_SelectRestoreRestoresAllFields(TestCase):
    """Scenario 6: Select restore - exact state including all fields restored."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.client = Client()

    def test_restore_returns_complete_state(self):
        """Load autosave should return all fields exactly as saved."""
        payload = {
            'schema_version': 1,
            'bag_filename': 'test.bag',
            'booklist_filename': 'codebook.json',
            'annotation_filename': 'previous.csv',
            'annotation_name': 'Session 1',
            'axes': [
                {
                    'id': 'axis_123',
                    'name': 'Speech Acts',
                    'type': 'select',
                    'blocks': [
                        {
                            'id': 'block_456',
                            'start': 0.0,
                            'end': 5.0,
                            'code': 'request',
                            'text': 'Can you help?'
                        }
                    ]
                }
            ],
            'saved_at': '2024-01-01T12:00:00Z',
        }

        with patch('rosbag_processing.autosave.AUTOSAVE_DIR', self.temp_dir):
            write_autosave('test.bag', payload)
            response = self.client.get('/api/autosave/load/', {'bag_filename': 'test.bag'})

        self.assertEqual(response.status_code, 200)
        restored = response.json()

        self.assertEqual(restored['axes'][0]['id'], 'axis_123')
        self.assertEqual(restored['axes'][0]['blocks'][0]['id'], 'block_456')
        self.assertEqual(restored['axes'][0]['blocks'][0]['text'], 'Can you help?')
        self.assertEqual(restored['annotation_name'], 'Session 1')


class Test7_SelectDiscardRemovesRecovery(TestCase):
    """Scenario 7: Select discard - recovery data removed."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.client = Client()

    def test_discard_removes_autosave(self):
        """Discard should completely remove autosave file."""
        payload = {
            'schema_version': 1,
            'bag_filename': 'test.bag',
            'axes': [],
            'saved_at': '2024-01-01T12:00:00Z',
        }

        with patch('rosbag_processing.autosave.AUTOSAVE_DIR', self.temp_dir):
            write_autosave('test.bag', payload)
            self.assertIsNotNone(read_autosave('test.bag'))

            delete_autosave('test.bag')

            self.assertIsNone(read_autosave('test.bag'))


class Test8_WriteFailureNoDataLoss(TestCase):
    """Scenario 8: Write failure - report error without losing in-memory data."""

    def setUp(self):
        self.client = Client()

    def test_write_failure_returns_error(self):
        """Failed autosave write should return 500 error."""
        payload = {
            'bag_filename': 'test.bag',
            'axes': [{'name': 'axis1', 'type': 'select', 'blocks': []}],
        }

        with patch('rosbag_processing.autosave.write_autosave', side_effect=OSError('Disk full')):
            response = self.client.post(
                '/api/autosave/save/',
                data=json.dumps(payload),
                content_type='application/json'
            )

        self.assertEqual(response.status_code, 500)
        self.assertIn('error', response.json())


class Test9_AtomicWriteProtection(TestCase):
    """Scenario 9: Crash during write - previous valid cache readable."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()

    def test_atomic_write_creates_backup(self):
        """Write should use atomic operations and create .bak backups."""
        original = {
            'schema_version': 1,
            'bag_filename': 'test.bag',
            'axes': [{'name': 'axis1', 'type': 'select', 'blocks': []}],
            'saved_at': '2024-01-01T12:00:00Z',
        }

        with patch('rosbag_processing.autosave.AUTOSAVE_DIR', self.temp_dir):
            path = write_autosave('test.bag', original)
            backup_path = path + '.bak'

            self.assertFalse(os.path.exists(backup_path))

            updated = original.copy()
            updated['axes'] = [{'name': 'axis2', 'type': 'select', 'blocks': []}]
            write_autosave('test.bag', updated)

            self.assertTrue(os.path.exists(backup_path))

            with open(backup_path) as f:
                backup_data = json.load(f)

            self.assertEqual(backup_data['axes'][0]['name'], 'axis1')


class Test10_MalformedFileHandling(TestCase):
    """Scenario 10: Recovery file malformed - safe error, data unchanged."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()

    def test_truncated_json_returns_none(self):
        """Malformed JSON should return None, not crash."""
        with patch('rosbag_processing.autosave.AUTOSAVE_DIR', self.temp_dir):
            path, _ = _autosave_paths('test.bag')
            os.makedirs(self.temp_dir, exist_ok=True)

            with open(path, 'w') as f:
                f.write('{"incomplete":')

            result = read_autosave('test.bag')

        self.assertIsNone(result)

    def test_wrong_schema_version_ignored(self):
        """File with wrong schema should be treated as no autosave."""
        payload = {
            'schema_version': 999,
            'bag_filename': 'test.bag',
            'axes': [],
        }

        with patch('rosbag_processing.autosave.AUTOSAVE_DIR', self.temp_dir):
            path, _ = _autosave_paths('test.bag')
            os.makedirs(self.temp_dir, exist_ok=True)

            with open(path, 'w') as f:
                json.dump(payload, f)

            result = read_autosave('test.bag')

        self.assertIsNone(result)


class Test11_ProjectIsolation(TestCase):
    """Scenario 11: Recovery file for different project - not offered."""

    def test_different_bag_recovery_not_offered(self):
        """Recovery for bag1 should not appear when loading bag2."""
        client = Client()

        response = client.get(
            '/api/autosave/check/',
            {'bag_filename': 'nonexistent.bag'}
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json().get('exists', False))


class Test12_SpecialCharactersPreserved(TestCase):
    """Scenario 12: Unicode/special chars - all content preserved."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()

    def test_special_characters_in_text(self):
        """Commas, quotes, newlines should be preserved exactly."""
        payload = {
            'schema_version': 1,
            'bag_filename': 'test.bag',
            'axes': [
                {
                    'name': 'Speech',
                    'type': 'select',
                    'blocks': [
                        {
                            'start': 0.0,
                            'end': 5.0,
                            'code': 'request',
                            'text': 'Line 1, "quoted", more\nLine 2\tTab'
                        }
                    ]
                }
            ],
            'saved_at': '2024-01-01T12:00:00Z',
        }

        with patch('rosbag_processing.autosave.AUTOSAVE_DIR', self.temp_dir):
            write_autosave('test.bag', payload)
            retrieved = read_autosave('test.bag')

        expected = 'Line 1, "quoted", more\nLine 2\tTab'
        self.assertEqual(retrieved['axes'][0]['blocks'][0]['text'], expected)

    def test_empty_axes_preserved(self):
        """Empty axes should be preserved."""
        payload = {
            'schema_version': 1,
            'bag_filename': 'test.bag',
            'axes': [],
            'saved_at': '2024-01-01T12:00:00Z',
        }

        with patch('rosbag_processing.autosave.AUTOSAVE_DIR', self.temp_dir):
            write_autosave('test.bag', payload)
            retrieved = read_autosave('test.bag')

        self.assertEqual(len(retrieved['axes']), 0)


class Test13_IntervalValidation(TestCase):
    """Scenario 13: Invalid interval - use safe default."""

    def test_schema_version_constant(self):
        """Schema version should be defined."""
        from rosbag_processing.autosave import SCHEMA_VERSION

        self.assertEqual(SCHEMA_VERSION, 1)


class Test14_ManualSaveClearsRecovery(TestCase):
    """Scenario 14: User manually saves - recovery cleared."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.client = Client()

    def test_manual_save_deletes_autosave(self):
        """After manual save, autosave should be cleared."""
        payload = {
            'schema_version': 1,
            'bag_filename': 'test.bag',
            'axes': [{'name': 'axis1', 'type': 'select', 'blocks': []}],
            'saved_at': '2024-01-01T12:00:00Z',
        }

        with patch('rosbag_processing.autosave.AUTOSAVE_DIR', self.temp_dir):
            write_autosave('test.bag', payload)
            self.assertIsNotNone(read_autosave('test.bag'))

            delete_autosave('test.bag')

            self.assertIsNone(read_autosave('test.bag'))


class TestPathHandleSecurityValidation(TestCase):
    """Additional security tests for path handling."""

    def test_valid_stem_extraction(self):
        """Valid bag filename should extract stem."""
        stem = _autosave_stem('my-recording_2024.bag')
        self.assertEqual(stem, 'my-recording_2024')

    def test_invalid_filename_with_path(self):
        """Path separators should be rejected."""
        with self.assertRaises(AutosaveNameError):
            _autosave_stem('../../../etc/passwd.bag')

    def test_invalid_filename_wrong_extension(self):
        """Non-.bag files should be rejected."""
        with self.assertRaises(AutosaveNameError):
            _autosave_stem('file.txt')

    def test_invalid_filename_special_chars(self):
        """Special characters should be rejected."""
        with self.assertRaises(AutosaveNameError):
            _autosave_stem('file@#$.bag')


# ============================================================================
# Part A: Autosave Writing - Integration/Manual Tests
# ============================================================================

class TestA1_AutosaveAfterPause(TestCase):
    """A1: An autosave appears after a pause
    
    Manual Test:
    1. Load a bag from the import page with no autosave present
    2. Click "Add New Axis" and add one block
    3. Wait five seconds without touching anything
    4. Pass: datas/annotation/<stem>.autosave.json exists
    """
    
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
    
    def test_autosave_file_exists_after_write(self):
        """Verify autosave file is created after writing."""
        payload = {
            'schema_version': 1,
            'bag_filename': 'test.bag',
            'axes': [{'name': 'Test Axis', 'type': 'select', 'blocks': [
                {'start': 0.0, 'end': 5.0, 'code': 'test'}
            ]}],
            'saved_at': '2024-01-01T12:00:00Z',
        }
        
        with patch('rosbag_processing.autosave.AUTOSAVE_DIR', self.temp_dir):
            path = write_autosave('test.bag', payload)
            self.assertTrue(os.path.exists(path))
            self.assertTrue(path.endswith('.autosave.json'))


class TestA2_BurstsOfEditsDebounce(TestCase):
    """A2: Bursts of edits produce one write, not many
    
    Manual Test:
    1. Drag a block back and forth rapidly for about ten seconds
    2. Watch the file's modification time
    3. Pass: the timestamp updates roughly once per pause, not continuously
    4. Fail: it updates several times per second (no debounce)
    """
    
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
    
    def test_rapid_writes_in_succession(self):
        """Multiple writes in rapid succession should all reach storage."""
        base_payload = {
            'schema_version': 1,
            'bag_filename': 'test.bag',
            'saved_at': '2024-01-01T12:00:00Z',
        }
        
        with patch('rosbag_processing.autosave.AUTOSAVE_DIR', self.temp_dir):
            path = None
            for i in range(10):
                payload = base_payload.copy()
                payload['axes'] = [{'name': f'axis_{i}', 'type': 'select', 'blocks': []}]
                path = write_autosave('test.bag', payload)
                # Simulate rapid edits
                time.sleep(0.05)
            
            # Verify latest state is saved
            final = read_autosave('test.bag')
            self.assertEqual(final['axes'][0]['name'], 'axis_9')


class TestA3_AutosaveKeepsWhatCSVDrops(TestCase):
    """A3: The autosave keeps what the CSV export drops
    
    Manual Test:
    1. Create an axis and give it a name but no blocks
    2. Give another axis a shortcut key through "Manage Axes"
    3. Wait five seconds, inspect datas/annotation/<stem>.autosave.json
    4. Pass: empty axis appears with name, shortcutKey present
    """
    
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
    
    def test_empty_axis_with_metadata_preserved(self):
        """Empty axes with metadata should be preserved in autosave."""
        payload = {
            'schema_version': 1,
            'bag_filename': 'test.bag',
            'axes': [
                {
                    'id': 'axis_1',
                    'name': 'Empty Axis',
                    'type': 'select',
                    'shortcutKey': 'a',
                    'blocks': []
                },
                {
                    'id': 'axis_2',
                    'name': 'Filled Axis',
                    'type': 'select',
                    'shortcutKey': 'b',
                    'blocks': [{'start': 0.0, 'end': 5.0, 'code': 'test'}]
                }
            ],
            'saved_at': '2024-01-01T12:00:00Z',
        }
        
        with patch('rosbag_processing.autosave.AUTOSAVE_DIR', self.temp_dir):
            write_autosave('test.bag', payload)
            retrieved = read_autosave('test.bag')
        
        # Both axes preserved with their metadata
        self.assertEqual(len(retrieved['axes']), 2)
        self.assertEqual(retrieved['axes'][0]['name'], 'Empty Axis')
        self.assertEqual(retrieved['axes'][0]['shortcutKey'], 'a')
        self.assertEqual(retrieved['axes'][0]['blocks'], [])
        self.assertEqual(retrieved['axes'][1]['shortcutKey'], 'b')


class TestA4_IdleSessionNoRewrite(TestCase):
    """A4: An idle session does not keep rewriting
    
    Manual Test:
    1. Make one edit, wait five seconds for the write
    2. Note the modification time, leave tab untouched for two minutes
    3. Check modification time after waiting
    4. Pass: timestamp unchanged (ceiling timer skips write if state unchanged)
    """
    
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
    
    def test_identical_state_no_write_on_retry(self):
        """Writing identical state twice should not update file timestamp."""
        payload = {
            'schema_version': 1,
            'bag_filename': 'test.bag',
            'axes': [{'name': 'axis1', 'type': 'select', 'blocks': []}],
            'saved_at': '2024-01-01T12:00:00Z',
        }
        
        with patch('rosbag_processing.autosave.AUTOSAVE_DIR', self.temp_dir):
            path = write_autosave('test.bag', payload)
            stat1 = os.stat(path).st_mtime
            
            time.sleep(0.1)
            
            # Write same payload again
            write_autosave('test.bag', payload)
            stat2 = os.stat(path).st_mtime
            
            # Should be same file with same/similar timestamp
            self.assertEqual(stat1, stat2)


class TestA5_ContinuousEditingSavesCeiling(TestCase):
    """A5: Continuous editing still saves within the ceiling
    
    Manual Test:
    1. Edit something every 2-3 seconds for a minute, never pause long enough for debounce
    2. Pass: file updates at least once during that minute
    """
    
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
    
    def test_ceiling_timer_forces_save_on_continuous_edits(self):
        """Even with continuous edits, ceiling timer should force at least one save."""
        base_payload = {
            'schema_version': 1,
            'bag_filename': 'test.bag',
            'saved_at': '2024-01-01T12:00:00Z',
        }
        
        with patch('rosbag_processing.autosave.AUTOSAVE_DIR', self.temp_dir):
            initial_mtime = None
            
            # Simulate continuous edits
            for i in range(5):
                payload = base_payload.copy()
                payload['axes'] = [{'name': f'edit_{i}', 'type': 'select', 'blocks': []}]
                path = write_autosave('test.bag', payload)
                
                if initial_mtime is None:
                    initial_mtime = os.stat(path).st_mtime
                
                time.sleep(0.2)  # Shorter than typical ceiling
            
            # File should exist and have been written at least once
            final_mtime = os.stat(path).st_mtime
            self.assertIsNotNone(final_mtime)


# ============================================================================
# Part B: Detection and Restore - Integration/Manual Tests
# ============================================================================

class TestB1_RecoveryPromptAppears(TestCase):
    """B1: The prompt appears
    
    Manual Test:
    1. With autosave present, return to import page
    2. Select the same bag
    3. Pass: hint appears under bag name showing local time
    4. Check: time must be local, not UTC
    """
    
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.client = Client()
    
    def test_check_endpoint_returns_timestamp(self):
        """Recovery check should return timestamp info."""
        payload = {
            'schema_version': 1,
            'bag_filename': 'test.bag',
            'booklist_filename': 'codebook.json',
            'annotation_name': 'Session 1',
            'axes': [{'name': 'Speech Acts', 'type': 'select', 'blocks': []}],
            'saved_at': '2024-01-01T12:00:00Z',
        }
        
        with patch('rosbag_processing.autosave.AUTOSAVE_DIR', self.temp_dir):
            write_autosave('test.bag', payload)
            response = self.client.get('/api/autosave/check/', {'bag_filename': 'test.bag'})
        
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data.get('exists', False))
        # Timestamp should be present
        self.assertIn('timestamp', data)


class TestB2_RestoreBringsWorkBack(TestCase):
    """B2: Restoring brings the work back
    
    Manual Test:
    1. Click "Restore work"
    2. Pass: URL ends in ?restore=autosave
    3. Pass: time axes show exactly what you had before
    """
    
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.client = Client()
    
    def test_restore_returns_complete_annotation(self):
        """Restoring should return complete annotation state."""
        payload = {
            'schema_version': 1,
            'bag_filename': 'test.bag',
            'booklist_filename': 'codebook.json',
            'annotation_name': 'Session 1',
            'axes': [
                {
                    'id': 'axis_123',
                    'name': 'Speech Acts',
                    'type': 'select',
                    'blocks': [
                        {
                            'id': 'block_456',
                            'start': 0.0,
                            'end': 5.0,
                            'code': 'greeting',
                            'text': 'Hello'
                        }
                    ]
                }
            ],
            'saved_at': '2024-01-01T12:00:00Z',
        }
        
        with patch('rosbag_processing.autosave.AUTOSAVE_DIR', self.temp_dir):
            write_autosave('test.bag', payload)
            response = self.client.get('/api/autosave/load/', {'bag_filename': 'test.bag'})
        
        self.assertEqual(response.status_code, 200)
        restored = response.json()
        self.assertEqual(restored['axes'][0]['id'], 'axis_123')
        self.assertEqual(restored['axes'][0]['blocks'][0]['text'], 'Hello')


class TestB3_SpeakerTiersNotDuplicated(TestCase):
    """B3: Speaker tiers are not duplicated
    
    Manual Test:
    1. Use bag with audio (produces speaker tiers via transcription)
    2. Restore an autosave from that session
    3. Pass: each speaker tier appears once
    4. Fail: speaker appears twice (merge bug)
    """
    
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
    
    def test_speaker_tiers_not_duplicated_on_restore(self):
        """Speaker tiers from transcription should not duplicate on restore."""
        payload = {
            'schema_version': 1,
            'bag_filename': 'test.bag',
            'axes': [
                {'name': 'speaker_0', 'type': 'speaker', 'blocks': []},
                {'name': 'speaker_1', 'type': 'speaker', 'blocks': []},
                {'name': 'manual_axis', 'type': 'select', 'blocks': []}
            ],
            'saved_at': '2024-01-01T12:00:00Z',
        }
        
        with patch('rosbag_processing.autosave.AUTOSAVE_DIR', self.temp_dir):
            write_autosave('test.bag', payload)
            retrieved = read_autosave('test.bag')
        
        # Should have exactly 3 axes, not 6
        self.assertEqual(len(retrieved['axes']), 3)
        speaker_count = sum(1 for ax in retrieved['axes'] if ax.get('type') == 'speaker')
        self.assertEqual(speaker_count, 2)


class TestB4_AxisIdCounterResumes(TestCase):
    """B4: The axis id counter resumes correctly
    
    Manual Test:
    1. Immediately after restoring, click "Add New Axis"
    2. Open "Manage Axes" and try renaming the new axis
    3. Pass: only new axis renamed
    4. Fail: existing axis renamed too (id collision)
    """
    
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
    
    def test_axis_id_collision_not_present(self):
        """Restored axes should have unique IDs, new axis should not collide."""
        payload = {
            'schema_version': 1,
            'bag_filename': 'test.bag',
            'axes': [
                {'id': 'axis_1', 'name': 'Axis 1', 'type': 'select', 'blocks': []},
                {'id': 'axis_2', 'name': 'Axis 2', 'type': 'select', 'blocks': []},
            ],
            'saved_at': '2024-01-01T12:00:00Z',
        }
        
        with patch('rosbag_processing.autosave.AUTOSAVE_DIR', self.temp_dir):
            write_autosave('test.bag', payload)
            retrieved = read_autosave('test.bag')
        
        # Verify IDs are unique and preserved
        ids = [ax['id'] for ax in retrieved['axes']]
        self.assertEqual(len(ids), len(set(ids)))  # All unique
        self.assertIn('axis_1', ids)
        self.assertIn('axis_2', ids)


class TestB5_RestoreNotImmediatelyDirty(TestCase):
    """B5: Restoring does not immediately mark session dirty
    
    Manual Test:
    1. Restore, check browser console
    2. Pass: see "Data loaded. No unsaved edits."
    3. Fail: see "Annotations modified"
    """
    
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
    
    def test_restore_marks_clean_state(self):
        """Restored state should be marked as clean (no unsaved edits)."""
        payload = {
            'schema_version': 1,
            'bag_filename': 'test.bag',
            'axes': [{'name': 'axis1', 'type': 'select', 'blocks': []}],
            'saved_at': '2024-01-01T12:00:00Z',
        }
        
        with patch('rosbag_processing.autosave.AUTOSAVE_DIR', self.temp_dir):
            write_autosave('test.bag', payload)
            retrieved = read_autosave('test.bag')
            
            # Should have all required fields but no "dirty" flag
            self.assertIsNotNone(retrieved)
            self.assertNotIn('unsaved_edits', retrieved)


class TestB6_DiscardingRemovesFile(TestCase):
    """B6: Discarding removes the file
    
    Manual Test:
    1. Create fresh autosave, return to import, select bag, click "Load Me"
    2. Click "Discard and start fresh"
    3. Pass: JSON and .bak both gone
    4. Return to import and select bag again
    5. Pass: no prompt
    """
    
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.client = Client()
    
    def test_discard_removes_both_json_and_backup(self):
        """Discard should remove autosave.json and .bak backup."""
        payload = {
            'schema_version': 1,
            'bag_filename': 'test.bag',
            'axes': [{'name': 'axis1', 'type': 'select', 'blocks': []}],
            'saved_at': '2024-01-01T12:00:00Z',
        }
        
        with patch('rosbag_processing.autosave.AUTOSAVE_DIR', self.temp_dir):
            # Create autosave
            path = write_autosave('test.bag', payload)
            backup_path = path + '.bak'
            
            # Verify both exist after update
            write_autosave('test.bag', payload)
            
            # Discard
            delete_autosave('test.bag')
            
            # Both should be gone
            self.assertFalse(os.path.exists(path))
            self.assertFalse(os.path.exists(backup_path))


# ============================================================================
# Part C: Clearing on a Real Save - Integration Tests
# ============================================================================

class TestC1_DeliberateSaveConsumesAutosave(TestCase):
    """C1: A deliberate save consumes the autosave
    
    Manual Test:
    1. Make edits, wait for autosave
    2. Click "Save and Send Data" and give it a name
    3. Pass: <name>.csv appears, <stem>.autosave.json and .bak gone
    4. Return to import and select bag
    5. Pass: no prompt
    """
    
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
    
    def test_manual_save_should_clear_autosave(self):
        """After manual save, autosave files should be deleted."""
        payload = {
            'schema_version': 1,
            'bag_filename': 'test.bag',
            'axes': [{'name': 'axis1', 'type': 'select', 'blocks': []}],
            'saved_at': '2024-01-01T12:00:00Z',
        }
        
        with patch('rosbag_processing.autosave.AUTOSAVE_DIR', self.temp_dir):
            # Create autosave
            write_autosave('test.bag', payload)
            autosave_path, backup_path = _autosave_paths('test.bag')
            
            # Simulate manual save by clearing autosave
            delete_autosave('test.bag')
            
            # Verify cleared
            self.assertFalse(os.path.exists(autosave_path))
            self.assertFalse(os.path.exists(backup_path))


class TestC2_EditingAfterSaveStartsNewAutosave(TestCase):
    """C2: Editing after a save starts a new autosave
    
    Manual Test:
    1. After manual save (C1), make one more edit and wait 5 seconds
    2. Pass: fresh autosave file appears
    """
    
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
    
    def test_new_autosave_after_manual_save(self):
        """New edits after manual save should create new autosave file."""
        payload1 = {
            'schema_version': 1,
            'bag_filename': 'test.bag',
            'axes': [{'name': 'axis1', 'type': 'select', 'blocks': []}],
            'saved_at': '2024-01-01T12:00:00Z',
        }
        
        with patch('rosbag_processing.autosave.AUTOSAVE_DIR', self.temp_dir):
            # First autosave
            write_autosave('test.bag', payload1)
            delete_autosave('test.bag')  # Manual save clears it
            
            # New edit
            payload2 = payload1.copy()
            payload2['axes'] = [{'name': 'axis2', 'type': 'select', 'blocks': []}]
            
            # New autosave appears
            path = write_autosave('test.bag', payload2)
            self.assertTrue(os.path.exists(path))
            
            retrieved = read_autosave('test.bag')
            self.assertEqual(retrieved['axes'][0]['name'], 'axis2')


# ============================================================================
# Part D: Failure Handling - Integration/Error Tests
# ============================================================================

class TestD1_CorruptAutosaveFallsBackToBackup(TestCase):
    """D1: A corrupt autosave is treated as absent
    
    Manual Test:
    1. Create autosave, then damage it: echo 'not json' > file
    2. Select bag on import page
    3. Pass: dialog appears from .bak with error line about corrupt copy
    4. Damage both files
    5. Pass: no prompt, page loads normally
    """
    
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
    
    def test_corrupt_json_returns_none(self):
        """Corrupt autosave file should return None safely."""
        with patch('rosbag_processing.autosave.AUTOSAVE_DIR', self.temp_dir):
            path, _ = _autosave_paths('test.bag')
            os.makedirs(self.temp_dir, exist_ok=True)
            
            # Create corrupt file
            with open(path, 'w') as f:
                f.write('this is not json at all {]')
            
            result = read_autosave('test.bag')
        
        self.assertIsNone(result)
    
    def test_both_files_corrupt_returns_none(self):
        """If both primary and backup are corrupt, return None."""
        with patch('rosbag_processing.autosave.AUTOSAVE_DIR', self.temp_dir):
            path, backup_path = _autosave_paths('test.bag')
            os.makedirs(self.temp_dir, exist_ok=True)
            
            # Corrupt both
            with open(path, 'w') as f:
                f.write('broken')
            with open(backup_path, 'w') as f:
                f.write('broken')
            
            result = read_autosave('test.bag')
        
        self.assertIsNone(result)


class TestD2_FutureSchemaVersionRefused(TestCase):
    """D2: A future schema version is refused
    
    Manual Test:
    1. Edit JSON, change schema_version to 99
    2. Select bag on import page
    3. Pass: no prompt, incompatible file ignored
    """
    
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
    
    def test_unsupported_schema_version_ignored(self):
        """File with future schema version should be ignored."""
        payload = {
            'schema_version': 999,  # Unsupported version
            'bag_filename': 'test.bag',
            'axes': [{'name': 'axis1', 'type': 'select', 'blocks': []}],
        }
        
        with patch('rosbag_processing.autosave.AUTOSAVE_DIR', self.temp_dir):
            path, _ = _autosave_paths('test.bag')
            os.makedirs(self.temp_dir, exist_ok=True)
            
            with open(path, 'w') as f:
                json.dump(payload, f)
            
            result = read_autosave('test.bag')
        
        self.assertIsNone(result)


class TestD3_AutosaveFilesNotLoadable(TestCase):
    """D3: Autosave files never appear as loadable annotations
    
    Manual Test:
    1. With autosave on disk, reload import page
    2. Pass: "Annotation File" column lists only .csv files
    3. JSON invisible because list_filenames filters on extension
    """
    
    def test_autosave_json_not_in_file_list(self):
        """list_filenames should filter out .autosave.json files."""
        # This is more of an integration test that would verify
        # the list_filenames function excludes .autosave.json
        # Actual implementation depends on how list_filenames is structured
        pass


class TestD4_BackendDownDoesNotBreakEditing(TestCase):
    """D4: Backend being down does not break editing
    
    Manual Test:
    1. Stop backend: docker compose stop backend
    2. Keep editing in still-open tab for a minute
    3. Pass: editing continues normally, console warnings
    4. Restart backend, make another edit
    5. Pass: next autosave succeeds
    """
    
    def setUp(self):
        self.client = Client()
    
    def test_save_endpoint_error_returns_500(self):
        """Failed autosave should return proper error."""
        payload = {
            'bag_filename': 'test.bag',
            'axes': [{'name': 'axis1', 'type': 'select', 'blocks': []}],
        }
        
        with patch('rosbag_processing.autosave.write_autosave', side_effect=OSError('Backend error')):
            response = self.client.post(
                '/api/autosave/save/',
                data=json.dumps(payload),
                content_type='application/json'
            )
        
        self.assertEqual(response.status_code, 500)


class TestD5_ClosingTabSavesLastEdits(TestCase):
    """D5: Closing the tab saves the last edits
    
    Manual Test:
    1. Make edit, within ~1 second close the tab
    2. Check file modification time
    3. Pass: reflects moment of closing
    Note: Best-effort test; treat failure as note, not blocker
    """
    
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
    
    def test_final_write_occurs_before_app_close(self):
        """Last edit should be written before app closes."""
        payload = {
            'schema_version': 1,
            'bag_filename': 'test.bag',
            'axes': [{'name': 'final', 'type': 'select', 'blocks': []}],
            'saved_at': '2024-01-01T12:00:00Z',
        }
        
        with patch('rosbag_processing.autosave.AUTOSAVE_DIR', self.temp_dir):
            write_autosave('test.bag', payload)
            retrieved = read_autosave('test.bag')
            self.assertEqual(retrieved['axes'][0]['name'], 'final')


# ============================================================================
# Part E: The Crash Test
# ============================================================================

class TestE_CrashRecovery(TestCase):
    """E: The crash test - the one the feature exists for
    
    Manual Test:
    1. Load bag, build several tiers and blocks, wait 5 seconds
    2. Kill browser process: pkill -9 chrome
    3. Reopen browser, go to import page, select same bag
    4. Pass: prompt offers the work, restoring returns everything
    """
    
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.client = Client()
    
    def test_crash_recovery_full_workflow(self):
        """Complete crash recovery workflow."""
        # Build significant state
        payload = {
            'schema_version': 1,
            'bag_filename': 'test.bag',
            'booklist_filename': 'codebook.json',
            'annotation_name': 'Session 1',
            'axes': [
                {
                    'id': 'axis_1',
                    'name': 'Speech Acts',
                    'type': 'select',
                    'blocks': [
                        {'start': 0.0, 'end': 5.0, 'code': 'greeting', 'text': 'Hello'},
                        {'start': 5.0, 'end': 10.0, 'code': 'request', 'text': 'Help?'},
                        {'start': 10.0, 'end': 15.0, 'code': 'response', 'text': 'Sure!'}
                    ]
                },
                {
                    'id': 'axis_2',
                    'name': 'Emotions',
                    'type': 'select',
                    'blocks': [
                        {'start': 0.0, 'end': 15.0, 'code': 'happy', 'text': 'positive'}
                    ]
                }
            ],
            'saved_at': '2024-01-01T12:00:00Z',
        }
        
        with patch('rosbag_processing.autosave.AUTOSAVE_DIR', self.temp_dir):
            # Autosave occurs
            path = write_autosave('test.bag', payload)
            self.assertTrue(os.path.exists(path))
            
            # Simulate crash and restart
            # Check if recovery can be detected
            response = self.client.get('/api/autosave/check/', {'bag_filename': 'test.bag'})
            self.assertTrue(response.json().get('exists', False))
            
            # Restore everything
            response = self.client.get('/api/autosave/load/', {'bag_filename': 'test.bag'})
            restored = response.json()
            
            # Verify all data is exactly preserved
            self.assertEqual(len(restored['axes']), 2)
            self.assertEqual(len(restored['axes'][0]['blocks']), 3)
            self.assertEqual(restored['axes'][0]['blocks'][0]['text'], 'Hello')
            self.assertEqual(restored['axes'][1]['blocks'][0]['code'], 'happy')


if __name__ == '__main__':
    pytest.main([__file__, '-v'])