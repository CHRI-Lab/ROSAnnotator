"""
Complete autosave test suite based on functional requirements.

Part A: Autosave Writing
Part B: Detection and Restore
Part C: Clearing on Real Save
Part D: Failure Handling
Part E: Crash Recovery
"""

import json
import os
import tempfile
import time
from datetime import datetime
from unittest.mock import patch

import pytest
from django.test import TestCase, Client

from rosbag_processing.autosave import (
    write_autosave,
    read_autosave,
    delete_autosave,
    _autosave_paths,
    _autosave_stem,
    AutosaveNameError,
)


# ============================================================================
# Core Functional Tests
# ============================================================================

class TestCachedResultsNeverOverwriteManualSave(TestCase):
    """Test list: "results cached - should not overwrite manually saved
    results". autosave.py's own docstring guarantees this by naming
    convention (autosaves are *.autosave.json, manual saves are *.csv),
    but that guarantee was never actually exercised until now: this
    writes a real .csv alongside an autosave and checks it survives
    untouched, no matter how many autosave writes happen.
    """

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()

    def test_writing_autosave_does_not_touch_a_same_stem_csv(self):
        """A manually-saved CSV with the same bag stem must be untouched by
        any number of autosave writes for that bag."""
        csv_path = os.path.join(self.temp_dir, 'test.csv')
        original_csv_content = 'axis,start,end,code\nSpeech,0.0,5.0,greeting\n'
        with open(csv_path, 'w') as f:
            f.write(original_csv_content)

        payload = {
            'schema_version': 1,
            'bag_filename': 'test.bag',
            'axes': [{'name': 'axis1', 'type': 'select', 'blocks': []}],
            'saved_at': '2024-01-01T12:00:00+11:00',
        }

        with patch('rosbag_processing.autosave.AUTOSAVE_DIR', self.temp_dir):
            write_autosave('test.bag', payload)
            write_autosave('test.bag', dict(payload, annotation_name='v2'))
            write_autosave('test.bag', dict(payload, annotation_name='v3'))

        with open(csv_path) as f:
            self.assertEqual(f.read(), original_csv_content,
                "A manually-saved CSV must never be modified by autosave writes")

    def test_autosave_suffix_cannot_collide_with_csv_namespace(self):
        """The two file families must be structurally distinct, not just
        distinct by convention -- this backs the guarantee above."""
        from rosbag_processing.autosave import AUTOSAVE_SUFFIX, BACKUP_SUFFIX
        self.assertFalse(AUTOSAVE_SUFFIX.endswith('.csv'))
        self.assertFalse(BACKUP_SUFFIX.endswith('.csv'))


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
            'axes': [{'name': 'Speech Acts', 'type': 'select', 'blocks': []}],
            'saved_at': '2024-01-01T12:00:00+11:00',
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

            write_autosave('test.bag', modified_payload)
            updated = read_autosave('test.bag')

            self.assertEqual(len(updated['axes'][0]['blocks']), 1)
            self.assertEqual(updated['axes'][0]['blocks'][0]['code'], 'greeting')


class Test2_IdempotentSave(TestCase):
    """Scenario 2: No changes during interval - save remains idempotent.

    Idempotency is enforced by the save_autosave view, which compares the
    incoming state against the stored primary before writing.
    """

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.client = Client()

    def test_identical_save_reports_unchanged(self):
        """Posting identical state twice should be reported as unchanged."""
        body = {
            'bag_filename': 'test.bag',
            'annotation_name': 'Session 1',
            'axes': [{'name': 'axis1', 'type': 'select', 'blocks': []}],
            'saved_at': '2024-01-01T12:00:00+11:00',
        }

        with patch('rosbag_processing.autosave.AUTOSAVE_DIR', self.temp_dir):
            first = self.client.post(
                '/api/autosave/save/',
                data=json.dumps(body),
                content_type='application/json',
            )
            second = self.client.post(
                '/api/autosave/save/',
                data=json.dumps(body),
                content_type='application/json',
            )

        self.assertEqual(first.status_code, 200)
        self.assertTrue(first.json()['saved'])
        self.assertFalse(first.json()['unchanged'])

        self.assertEqual(second.status_code, 200)
        self.assertFalse(second.json()['saved'], "Identical state must not be rewritten")
        self.assertTrue(second.json()['unchanged'])


class Test3_RapidEditsLatestWins(TestCase):
    """Scenario 3: Rapid edits - latest state saved, no intermediate overwrites."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()

    def test_rapid_edits_preserve_latest(self):
        """Multiple rapid edits should only save the latest state."""
        base_payload = {
            'schema_version': 1,
            'bag_filename': 'test.bag',
            'saved_at': '2024-01-01T12:00:00+11:00',
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
            'saved_at': '2024-01-01T12:00:00+11:00',
        }

        with patch('rosbag_processing.autosave.AUTOSAVE_DIR', self.temp_dir):
            write_autosave('test.bag', payload)
            response = self.client.get('/api/autosave/check/', {'bag_filename': 'test.bag'})

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json().get('exists', False))


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
            'saved_at': '2024-01-01T12:00:00+11:00',
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
            'saved_at': '2024-01-01T12:00:00+11:00',
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
    """Scenario 7: Select discard - recovery data removed, main annotation
    loads unchanged.
    """

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()

    def test_discard_removes_autosave(self):
        """Discard should completely remove autosave file."""
        payload = {
            'schema_version': 1,
            'bag_filename': 'test.bag',
            'axes': [],
            'saved_at': '2024-01-01T12:00:00+11:00',
        }

        with patch('rosbag_processing.autosave.AUTOSAVE_DIR', self.temp_dir):
            write_autosave('test.bag', payload)
            self.assertIsNotNone(read_autosave('test.bag'))

            delete_autosave('test.bag')

            self.assertIsNone(read_autosave('test.bag'))

    def test_discard_leaves_main_annotation_csv_untouched(self):
        """The "main annotation loads unchanged" half of the scenario:
        discarding the autosave must not delete or modify a real,
        already-saved annotation CSV for the same bag."""
        csv_path = os.path.join(self.temp_dir, 'test.csv')
        csv_content = 'axis,start,end,code\nSpeech,0.0,5.0,greeting\n'
        with open(csv_path, 'w') as f:
            f.write(csv_content)

        payload = {
            'schema_version': 1,
            'bag_filename': 'test.bag',
            'axes': [{'name': 'axis1', 'type': 'select', 'blocks': []}],
            'saved_at': '2024-01-01T12:00:00+11:00',
        }

        with patch('rosbag_processing.autosave.AUTOSAVE_DIR', self.temp_dir):
            write_autosave('test.bag', payload)
            delete_autosave('test.bag')

        with open(csv_path) as f:
            self.assertEqual(f.read(), csv_content,
                "Discarding the autosave must not affect the saved CSV")


class Test8_WriteFailureNoDataLoss(TestCase):
    """Scenario 8: Write failure - report error without losing in-memory data."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.client = Client()

    def test_write_failure_returns_error(self):
        """Failed autosave write should return 500 error."""
        body = {
            'bag_filename': 'test.bag',
            'axes': [{'name': 'axis1', 'type': 'select', 'blocks': []}],
        }

        with patch('rosbag_processing.autosave.write_autosave', side_effect=OSError('Disk full')):
            response = self.client.post(
                '/api/autosave/save/',
                data=json.dumps(body),
                content_type='application/json'
            )

        self.assertEqual(response.status_code, 500)
        self.assertIn('error', response.json())

    def test_write_failure_preserves_previously_saved_state(self):
        """"Without losing in-memory annotations" also means: whatever was
        successfully saved before the failure must still be exactly what
        read_autosave returns afterwards -- the failed attempt must not
        corrupt or erase the last good save."""
        good_payload = {
            'bag_filename': 'test.bag',
            'axes': [{'name': 'good_state', 'type': 'select', 'blocks': [
                {'start': 0.0, 'end': 5.0, 'code': 'kept'}
            ]}],
            'saved_at': '2024-01-01T12:00:00+11:00',
        }

        with patch('rosbag_processing.autosave.AUTOSAVE_DIR', self.temp_dir):
            first = self.client.post(
                '/api/autosave/save/',
                data=json.dumps(good_payload),
                content_type='application/json',
            )
            self.assertTrue(first.json()['saved'])

            with patch('rosbag_processing.autosave.write_autosave',
                       side_effect=OSError('disk full')):
                failed = self.client.post(
                    '/api/autosave/save/',
                    data=json.dumps({
                        'bag_filename': 'test.bag',
                        'axes': [{'name': 'lost_edit', 'type': 'select', 'blocks': []}],
                        'saved_at': '2024-01-01T12:05:00+11:00',
                    }),
                    content_type='application/json',
                )
            self.assertEqual(failed.status_code, 500)

            still_there = read_autosave('test.bag')

        self.assertIsNotNone(still_there)
        self.assertEqual(still_there['axes'][0]['name'], 'good_state')
        self.assertEqual(still_there['axes'][0]['blocks'][0]['code'], 'kept')


class Test9_AtomicWriteProtection(TestCase):
    """Scenario 9: Crash during write - previous valid cache readable, no
    partially written cache is treated as valid.
    """

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()

    def test_atomic_write_creates_backup(self):
        """Write should use atomic operations and create .bak backups."""
        original = {
            'schema_version': 1,
            'bag_filename': 'test.bag',
            'axes': [{'name': 'axis1', 'type': 'select', 'blocks': []}],
            'saved_at': '2024-01-01T12:00:00+11:00',
        }

        with patch('rosbag_processing.autosave.AUTOSAVE_DIR', self.temp_dir):
            path = write_autosave('test.bag', original)
            _, backup_path = _autosave_paths('test.bag')

            self.assertFalse(os.path.exists(backup_path))

            updated = dict(original)
            updated['axes'] = [{'name': 'axis2', 'type': 'select', 'blocks': []}]
            write_autosave('test.bag', updated)

            self.assertTrue(os.path.exists(backup_path))

            with open(backup_path) as f:
                backup_data = json.load(f)

            self.assertEqual(backup_data['axes'][0]['name'], 'axis1')

    def test_stray_tmp_file_is_ignored_when_no_primary_exists(self):
        """The "no partially written cache is treated as valid" half of
        this scenario: a dangling .autosave-*.tmp file left behind by a
        write that crashed before os.replace() could run must never be
        surfaced as recoverable data."""
        with patch('rosbag_processing.autosave.AUTOSAVE_DIR', self.temp_dir):
            os.makedirs(self.temp_dir, exist_ok=True)
            stray_tmp = os.path.join(self.temp_dir, '.autosave-abc123.tmp')
            with open(stray_tmp, 'w') as f:
                json.dump({
                    'schema_version': 1,
                    'bag_filename': 'test.bag',
                    'axes': [{'name': 'half_written', 'type': 'select', 'blocks': []}],
                }, f)

            result = read_autosave('test.bag')

        self.assertIsNone(result,
            "A stray incomplete .tmp file must never be treated as a valid autosave")

    def test_stray_tmp_file_does_not_shadow_a_valid_primary(self):
        """If a crash leaves a stray .tmp file NEXT TO a completed, valid
        primary, the valid primary must still be what gets returned -- the
        incomplete .tmp must never be preferred over it."""
        good_payload = {
            'schema_version': 1,
            'bag_filename': 'test.bag',
            'axes': [{'name': 'complete_write', 'type': 'select', 'blocks': []}],
            'saved_at': '2024-01-01T12:00:00+11:00',
        }

        with patch('rosbag_processing.autosave.AUTOSAVE_DIR', self.temp_dir):
            write_autosave('test.bag', good_payload)

            stray_tmp = os.path.join(self.temp_dir, '.autosave-crashed.tmp')
            with open(stray_tmp, 'w') as f:
                f.write('{"incomplete')

            result = read_autosave('test.bag')

        self.assertIsNotNone(result)
        self.assertEqual(result['axes'][0]['name'], 'complete_write')


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

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.client = Client()

    def test_different_bag_recovery_not_offered(self):
        """An autosave for one bag must not be offered for another bag."""
        payload = {
            'schema_version': 1,
            'bag_filename': 'project-a.bag',
            'axes': [{'name': 'axis1', 'type': 'select', 'blocks': []}],
            'saved_at': '2024-01-01T12:00:00+11:00',
        }

        with patch('rosbag_processing.autosave.AUTOSAVE_DIR', self.temp_dir):
            write_autosave('project-a.bag', payload)

            own = self.client.get('/api/autosave/check/',
                                  {'bag_filename': 'project-a.bag'})
            other = self.client.get('/api/autosave/check/',
                                    {'bag_filename': 'project-b.bag'})

        self.assertTrue(own.json().get('exists', False),
                        "Bag with an autosave should report exists=True")
        self.assertFalse(other.json().get('exists', False),
                         "A different bag must not be offered project-a's autosave")


class Test12_SpecialCharactersPreserved(TestCase):
    """Scenario 12: Unicode/special chars - all content preserved."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()

    def test_unicode_content_preserved(self):
        """Non-ASCII text should survive a write/read round trip."""
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
                            'code': 'greeting',
                            'text': 'Hello - Bonjour - Gruezi - Ola'
                        }
                    ]
                }
            ],
            'saved_at': '2024-01-01T12:00:00+11:00',
        }

        with patch('rosbag_processing.autosave.AUTOSAVE_DIR', self.temp_dir):
            write_autosave('test.bag', payload)
            retrieved = read_autosave('test.bag')

        self.assertEqual(
            retrieved['axes'][0]['blocks'][0]['text'],
            'Hello - Bonjour - Gruezi - Ola'
        )

    def test_special_characters_in_text(self):
        """Commas, quotes, newlines, tabs should be preserved exactly."""
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
            'saved_at': '2024-01-01T12:00:00+11:00',
        }

        with patch('rosbag_processing.autosave.AUTOSAVE_DIR', self.temp_dir):
            write_autosave('test.bag', payload)
            retrieved = read_autosave('test.bag')

        expected = 'Line 1, "quoted", more\nLine 2\tTab'
        self.assertEqual(retrieved['axes'][0]['blocks'][0]['text'], expected)

    def test_empty_axes_preserved(self):
        """Empty axes list should be preserved."""
        payload = {
            'schema_version': 1,
            'bag_filename': 'test.bag',
            'axes': [],
            'saved_at': '2024-01-01T12:00:00+11:00',
        }

        with patch('rosbag_processing.autosave.AUTOSAVE_DIR', self.temp_dir):
            write_autosave('test.bag', payload)
            retrieved = read_autosave('test.bag')

        self.assertEqual(len(retrieved['axes']), 0)


class Test13_MissingTimestampFallback(TestCase):
    """Scenario: missing/invalid 'saved_at' timestamp - replaced with a
    safe server-side default.

    NOTE: this is a different requirement from the "autosave interval"
    test list item (see module docstring above for why that item is not
    covered here). This one is specifically about the 'saved_at' field
    on each save request, not about how often autosave fires.
    """

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.client = Client()

    def test_schema_version_constant(self):
        """Schema version should be defined."""
        from rosbag_processing.autosave import SCHEMA_VERSION
        self.assertEqual(SCHEMA_VERSION, 1)

    def test_missing_saved_at_gets_server_fallback(self):
        """A save with no saved_at must still produce a usable timestamp."""
        body = {
            'bag_filename': 'test.bag',
            'axes': [{'name': 'axis1', 'type': 'select', 'blocks': []}],
        }

        with patch('rosbag_processing.autosave.AUTOSAVE_DIR', self.temp_dir):
            response = self.client.post(
                '/api/autosave/save/',
                data=json.dumps(body),
                content_type='application/json',
            )

        self.assertEqual(response.status_code, 200)
        saved_at = response.json().get('saved_at', '')

        self.assertTrue(saved_at, "saved_at must never be empty")
        try:
            datetime.fromisoformat(saved_at)
        except ValueError:
            self.fail(f"Fallback saved_at is not ISO 8601: {saved_at}")

    def test_rejects_non_list_axes(self):
        """axes must be a list; anything else is a 400."""
        body = {'bag_filename': 'test.bag', 'axes': 'not-a-list'}

        with patch('rosbag_processing.autosave.AUTOSAVE_DIR', self.temp_dir):
            response = self.client.post(
                '/api/autosave/save/',
                data=json.dumps(body),
                content_type='application/json',
            )

        self.assertEqual(response.status_code, 400)


class Test14_ManualSaveClearsRecovery(TestCase):
    """Scenario 14: User manually saves - recovery cleared."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.client = Client()

    def test_discard_endpoint_clears_autosave(self):
        """The discard endpoint should clear the autosave after a real save."""
        payload = {
            'schema_version': 1,
            'bag_filename': 'test.bag',
            'axes': [{'name': 'axis1', 'type': 'select', 'blocks': []}],
            'saved_at': '2024-01-01T12:00:00+11:00',
        }

        with patch('rosbag_processing.autosave.AUTOSAVE_DIR', self.temp_dir):
            write_autosave('test.bag', payload)
            self.assertIsNotNone(read_autosave('test.bag'))

            response = self.client.delete(
                '/api/autosave/delete/?bag_filename=test.bag'
            )

            self.assertEqual(response.status_code, 200)
            self.assertTrue(response.json().get('deleted', False))
            self.assertIsNone(read_autosave('test.bag'))


class TestPathHandleSecurityValidation(TestCase):
    """Path handling and filename validation."""

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

    def test_empty_filename_rejected(self):
        """Empty or None filename should be rejected."""
        with self.assertRaises(AutosaveNameError):
            _autosave_stem('')
        with self.assertRaises(AutosaveNameError):
            _autosave_stem(None)

    def test_traversal_rejected_at_api_layer(self):
        """A traversal attempt through the API should return 400, not 500."""
        client = Client()
        response = client.get('/api/autosave/check/',
                              {'bag_filename': '../../etc/passwd.bag'})
        self.assertEqual(response.status_code, 400)


# ============================================================================
# Part A: Autosave Writing
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
        """Verify autosave file is created with the expected name."""
        payload = {
            'schema_version': 1,
            'bag_filename': 'test.bag',
            'axes': [{'name': 'Test Axis', 'type': 'select', 'blocks': [
                {'start': 0.0, 'end': 5.0, 'code': 'test'}
            ]}],
            'saved_at': '2024-01-01T12:00:00+11:00',
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

    Backend scope: every distinct state that arrives must land on disk, and the
    latest one must win. Debounce itself is frontend timing and is verified
    manually.
    """

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()

    def test_latest_state_wins_after_burst(self):
        """After a burst of distinct states, the last one is what persists."""
        base_payload = {
            'schema_version': 1,
            'bag_filename': 'test.bag',
            'saved_at': '2024-01-01T12:00:00+11:00',
        }

        with patch('rosbag_processing.autosave.AUTOSAVE_DIR', self.temp_dir):
            for i in range(10):
                payload = base_payload.copy()
                payload['axes'] = [{'name': f'axis_{i}', 'type': 'select', 'blocks': []}]
                write_autosave('test.bag', payload)

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
        """Empty axes and shortcut keys must survive the round trip."""
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
            'saved_at': '2024-01-01T12:00:00+11:00',
        }

        with patch('rosbag_processing.autosave.AUTOSAVE_DIR', self.temp_dir):
            write_autosave('test.bag', payload)
            retrieved = read_autosave('test.bag')

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
    4. Pass: timestamp unchanged (ceiling timer fires, unchanged-state check
       skips the write)

    The unchanged-state check lives in the save_autosave view, so this test
    goes through the API rather than calling write_autosave() directly.
    """

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.client = Client()

    def test_idle_repost_does_not_touch_file(self):
        """Reposting identical state must not rewrite the file on disk."""
        body = {
            'bag_filename': 'test.bag',
            'annotation_name': 'Session 1',
            'axes': [{'name': 'axis1', 'type': 'select', 'blocks': []}],
            'saved_at': '2024-01-01T12:00:00+11:00',
        }

        with patch('rosbag_processing.autosave.AUTOSAVE_DIR', self.temp_dir):
            self.client.post(
                '/api/autosave/save/',
                data=json.dumps(body),
                content_type='application/json',
            )
            path, _ = _autosave_paths('test.bag')
            mtime_before = os.stat(path).st_mtime

            time.sleep(0.1)

            response = self.client.post(
                '/api/autosave/save/',
                data=json.dumps(body),
                content_type='application/json',
            )
            mtime_after = os.stat(path).st_mtime

        self.assertTrue(response.json()['unchanged'])
        self.assertEqual(mtime_before, mtime_after,
                         "Idle repost must not rewrite the autosave file")

    def test_idle_repost_preserves_backup(self):
        """An unchanged repost must not clobber the .bak with a duplicate."""
        first = {
            'bag_filename': 'test.bag',
            'axes': [{'name': 'axis1', 'type': 'select', 'blocks': []}],
            'saved_at': '2024-01-01T12:00:00+11:00',
        }
        second = {
            'bag_filename': 'test.bag',
            'axes': [{'name': 'axis2', 'type': 'select', 'blocks': []}],
            'saved_at': '2024-01-01T12:00:05+11:00',
        }

        with patch('rosbag_processing.autosave.AUTOSAVE_DIR', self.temp_dir):
            for body in (first, second, second):
                self.client.post(
                    '/api/autosave/save/',
                    data=json.dumps(body),
                    content_type='application/json',
                )

            _, backup_path = _autosave_paths('test.bag')
            with open(backup_path) as f:
                backup_data = json.load(f)

        self.assertEqual(backup_data['axes'][0]['name'], 'axis1',
                         "Backup must still hold the genuinely previous state")


class TestA5_ContinuousEditingSavesCeiling(TestCase):
    """A5: Continuous editing still saves within the ceiling

    Manual Test:
    1. Edit something every 2-3 seconds for a minute, never pausing long
       enough for the debounce
    2. Pass: file updates at least once during that minute

    Backend scope: each changed state posted during continuous editing must be
    written, not suppressed by the idempotency check.
    """

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.client = Client()

    def test_changed_state_always_writes(self):
        """Every genuinely changed state must be written, never reported unchanged."""
        with patch('rosbag_processing.autosave.AUTOSAVE_DIR', self.temp_dir):
            for i in range(5):
                body = {
                    'bag_filename': 'test.bag',
                    'axes': [{'name': f'edit_{i}', 'type': 'select', 'blocks': []}],
                    'saved_at': f'2024-01-01T12:00:0{i}+11:00',
                }
                response = self.client.post(
                    '/api/autosave/save/',
                    data=json.dumps(body),
                    content_type='application/json',
                )
                self.assertTrue(response.json()['saved'],
                                f"Changed state {i} must be written")

            final = read_autosave('test.bag')

        self.assertEqual(final['axes'][0]['name'], 'edit_4')


# ============================================================================
# Part B: Detection and Restore
# ============================================================================

class TestB1_RecoveryPromptAppears(TestCase):
    """B1: The prompt appears

    Manual Test:
    1. With autosave present, return to import page
    2. Select the same bag
    3. Pass: hint appears under bag name showing the local time
    4. Click "Load Me" - dialog names the bag, the time, the tier count and
       the annotation count, and the counts match what was created

    API contract: counts are axis_count and block_count; the time is saved_at.
    saved_at is browser-stamped and carries a UTC offset so the client can
    render it in local time.
    """

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.client = Client()

    def test_check_returns_prompt_metadata(self):
        """Recovery check should return everything the dialog needs."""
        payload = {
            'schema_version': 1,
            'bag_filename': 'test.bag',
            'booklist_filename': 'codebook.json',
            'annotation_name': 'Session 1',
            'axes': [
                {'name': 'Speech Acts', 'type': 'select', 'blocks': [
                    {'start': 0.0, 'end': 5.0, 'code': 'greeting'},
                    {'start': 5.0, 'end': 10.0, 'code': 'request'},
                ]},
                {'name': 'Emotions', 'type': 'select', 'blocks': [
                    {'start': 0.0, 'end': 10.0, 'code': 'happy'},
                ]},
            ],
            'saved_at': '2024-01-01T12:00:00+11:00',
        }

        with patch('rosbag_processing.autosave.AUTOSAVE_DIR', self.temp_dir):
            write_autosave('test.bag', payload)
            response = self.client.get('/api/autosave/check/',
                                       {'bag_filename': 'test.bag'})

        self.assertEqual(response.status_code, 200)
        data = response.json()

        self.assertTrue(data.get('exists', False))
        self.assertEqual(data['bag_filename'], 'test.bag')
        self.assertEqual(data['annotation_name'], 'Session 1')
        self.assertEqual(data['axis_count'], 2, "Dialog tier count")
        self.assertEqual(data['block_count'], 3, "Dialog annotation count")
        self.assertFalse(data['recovered_from_backup'])

    def test_saved_at_is_offset_aware_iso(self):
        """saved_at must be ISO 8601 and carry an offset so the UI can localise it."""
        payload = {
            'schema_version': 1,
            'bag_filename': 'test.bag',
            'annotation_name': 'Session 1',
            'axes': [{'name': 'Speech Acts', 'type': 'select', 'blocks': []}],
            'saved_at': '2024-01-01T12:00:00+11:00',
        }

        with patch('rosbag_processing.autosave.AUTOSAVE_DIR', self.temp_dir):
            write_autosave('test.bag', payload)
            response = self.client.get('/api/autosave/check/',
                                       {'bag_filename': 'test.bag'})

        saved_at = response.json()['saved_at']

        self.assertTrue(saved_at, "saved_at must not be empty")
        self.assertRegex(saved_at, r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}',
                         f"saved_at must be ISO 8601: {saved_at}")

        parsed = datetime.fromisoformat(saved_at)
        self.assertIsNotNone(parsed.tzinfo,
                             f"saved_at must carry an offset so the UI can "
                             f"render local time, got: {saved_at}")

    def test_no_autosave_returns_exists_false_only(self):
        """With no autosave, the check returns exists=False and no metadata."""
        with patch('rosbag_processing.autosave.AUTOSAVE_DIR', self.temp_dir):
            response = self.client.get('/api/autosave/check/',
                                       {'bag_filename': 'nothing-here.bag'})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'exists': False})


class TestB2_RestoreBringsWorkBack(TestCase):
    """B2: Restoring brings the work back

    Manual Test:
    1. Click "Restore work"
    2. Pass: URL ends in ?restore=autosave
    3. Pass: time axes show exactly what you had before, including the empty
       axis from A3
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
                },
                {
                    'id': 'axis_124',
                    'name': 'Empty Axis',
                    'type': 'select',
                    'shortcutKey': 'e',
                    'blocks': []
                }
            ],
            'saved_at': '2024-01-01T12:00:00+11:00',
        }

        with patch('rosbag_processing.autosave.AUTOSAVE_DIR', self.temp_dir):
            write_autosave('test.bag', payload)
            response = self.client.get('/api/autosave/load/',
                                       {'bag_filename': 'test.bag'})

        self.assertEqual(response.status_code, 200)
        restored = response.json()
        self.assertEqual(restored['axes'][0]['id'], 'axis_123')
        self.assertEqual(restored['axes'][0]['blocks'][0]['text'], 'Hello')
        self.assertEqual(restored['axes'][1]['name'], 'Empty Axis')
        self.assertEqual(restored['axes'][1]['blocks'], [])

    def test_load_missing_autosave_returns_404(self):
        """Loading a bag with no autosave should 404, not 200 with junk."""
        with patch('rosbag_processing.autosave.AUTOSAVE_DIR', self.temp_dir):
            response = self.client.get('/api/autosave/load/',
                                       {'bag_filename': 'nothing-here.bag'})

        self.assertEqual(response.status_code, 404)
        self.assertIn('error', response.json())


class TestB3_SpeakerTiersNotDuplicated(TestCase):
    """B3: Speaker tiers are not duplicated

    Manual Test:
    1. Use bag with audio (transcription produces speaker tiers)
    2. Restore an autosave made from that session
    3. Pass: each speaker tier appears once
    4. Fail: every speaker appears twice (restore branch not returning before
       the speakerData branch runs)
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
            'saved_at': '2024-01-01T12:00:00+11:00',
        }

        with patch('rosbag_processing.autosave.AUTOSAVE_DIR', self.temp_dir):
            write_autosave('test.bag', payload)
            retrieved = read_autosave('test.bag')

        self.assertEqual(len(retrieved['axes']), 3)

        names = [ax['name'] for ax in retrieved['axes']]
        self.assertEqual(len(names), len(set(names)), "Tier names must be unique")

        speaker_count = sum(1 for ax in retrieved['axes'] if ax.get('type') == 'speaker')
        self.assertEqual(speaker_count, 2)


class TestB4_AxisIdCounterResumes(TestCase):
    """B4: The axis id counter resumes correctly

    Manual Test:
    1. Immediately after restoring, click "Add New Axis"
    2. Open "Manage Axes" and try renaming the new axis
    3. Pass: only the new axis is renamed
    4. Fail: an existing axis is renamed too (globalAxisId collided)
    """

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()

    def test_restored_axis_ids_are_unique(self):
        """Restored axes must keep unique IDs for the frontend counter to resume."""
        payload = {
            'schema_version': 1,
            'bag_filename': 'test.bag',
            'axes': [
                {'id': 'axis_1', 'name': 'Axis 1', 'type': 'select', 'blocks': []},
                {'id': 'axis_2', 'name': 'Axis 2', 'type': 'select', 'blocks': []},
                {'id': 'axis_7', 'name': 'Axis 7', 'type': 'select', 'blocks': []},
            ],
            'saved_at': '2024-01-01T12:00:00+11:00',
        }

        with patch('rosbag_processing.autosave.AUTOSAVE_DIR', self.temp_dir):
            write_autosave('test.bag', payload)
            retrieved = read_autosave('test.bag')

        ids = [ax['id'] for ax in retrieved['axes']]
        self.assertEqual(len(ids), len(set(ids)), "Axis IDs must be unique")
        self.assertEqual(ids, ['axis_1', 'axis_2', 'axis_7'],
                         "IDs must survive verbatim so the counter can resume past them")


class TestB5_RestoreNotImmediatelyDirty(TestCase):
    """B5: Restoring does not immediately mark the session dirty

    Manual Test:
    1. Restore, then check the browser console
    2. Pass: "Data loaded. No unsaved edits."
    3. Fail: "Annotations modified"
    """

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()

    def test_restored_payload_carries_no_dirty_flag(self):
        """The restored payload must not carry any unsaved-edit marker."""
        payload = {
            'schema_version': 1,
            'bag_filename': 'test.bag',
            'axes': [{'name': 'axis1', 'type': 'select', 'blocks': []}],
            'saved_at': '2024-01-01T12:00:00+11:00',
        }

        with patch('rosbag_processing.autosave.AUTOSAVE_DIR', self.temp_dir):
            write_autosave('test.bag', payload)
            retrieved = read_autosave('test.bag')

        self.assertIsNotNone(retrieved)
        self.assertNotIn('unsaved_edits', retrieved)
        self.assertNotIn('dirty', retrieved)

    def test_restore_is_byte_stable(self):
        """Restoring twice returns identical state, so no phantom edit is implied."""
        payload = {
            'schema_version': 1,
            'bag_filename': 'test.bag',
            'annotation_name': 'Session 1',
            'axes': [
                {'id': 'a1', 'name': 'axis1', 'type': 'select', 'blocks': [
                    {'start': 0.0, 'end': 5.0, 'code': 'x'}
                ]}
            ],
            'saved_at': '2024-01-01T12:00:00+11:00',
        }

        with patch('rosbag_processing.autosave.AUTOSAVE_DIR', self.temp_dir):
            write_autosave('test.bag', payload)
            first = read_autosave('test.bag')
            second = read_autosave('test.bag')

        self.assertEqual(first, second)


class TestB6_DiscardingRemovesFile(TestCase):
    """B6: Discarding removes the file

    Manual Test:
    1. Create fresh autosave, return to import, select bag, click "Load Me"
    2. Click "Discard and start fresh"
    3. Pass: the JSON and its .bak are both gone
    4. Return to import and select the bag again
    5. Pass: no prompt and no hint
    """

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.client = Client()

    def test_discard_removes_both_json_and_backup(self):
        """Discard should remove autosave.json and its .bak."""
        first = {
            'schema_version': 1,
            'bag_filename': 'test.bag',
            'axes': [{'name': 'axis1', 'type': 'select', 'blocks': []}],
            'saved_at': '2024-01-01T12:00:00+11:00',
        }
        second = dict(first)
        second['axes'] = [{'name': 'axis2', 'type': 'select', 'blocks': []}]

        with patch('rosbag_processing.autosave.AUTOSAVE_DIR', self.temp_dir):
            write_autosave('test.bag', first)
            write_autosave('test.bag', second)

            path, backup_path = _autosave_paths('test.bag')
            self.assertTrue(os.path.exists(path))
            self.assertTrue(os.path.exists(backup_path))

            delete_autosave('test.bag')

            self.assertFalse(os.path.exists(path))
            self.assertFalse(os.path.exists(backup_path))

    def test_no_prompt_after_discard(self):
        """After discarding, the check endpoint must report no autosave."""
        payload = {
            'schema_version': 1,
            'bag_filename': 'test.bag',
            'axes': [{'name': 'axis1', 'type': 'select', 'blocks': []}],
            'saved_at': '2024-01-01T12:00:00+11:00',
        }

        with patch('rosbag_processing.autosave.AUTOSAVE_DIR', self.temp_dir):
            write_autosave('test.bag', payload)
            self.client.delete('/api/autosave/delete/?bag_filename=test.bag')

            response = self.client.get('/api/autosave/check/',
                                       {'bag_filename': 'test.bag'})

        self.assertFalse(response.json().get('exists', True))


# ============================================================================
# Part C: Clearing on a Real Save
# ============================================================================

class TestC1_DeliberateSaveConsumesAutosave(TestCase):
    """C1: A deliberate save consumes the autosave

    Manual Test:
    1. Make edits, wait for an autosave
    2. Click "Save and Send Data" and give it a name
    3. Pass: <name>.csv appears, and <stem>.autosave.json plus its .bak are gone
    4. Return to the import page and select the bag
    5. Pass: no prompt
    """

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.client = Client()

    def test_discard_after_save_clears_everything(self):
        """The save flow's discard call must clear both files and the prompt."""
        payload = {
            'schema_version': 1,
            'bag_filename': 'test.bag',
            'axes': [{'name': 'axis1', 'type': 'select', 'blocks': []}],
            'saved_at': '2024-01-01T12:00:00+11:00',
        }

        with patch('rosbag_processing.autosave.AUTOSAVE_DIR', self.temp_dir):
            write_autosave('test.bag', payload)
            autosave_path, backup_path = _autosave_paths('test.bag')

            response = self.client.delete(
                '/api/autosave/delete/?bag_filename=test.bag'
            )

            self.assertEqual(response.status_code, 200)
            self.assertFalse(os.path.exists(autosave_path))
            self.assertFalse(os.path.exists(backup_path))

            check = self.client.get('/api/autosave/check/',
                                    {'bag_filename': 'test.bag'})
            self.assertFalse(check.json().get('exists', True))

    def test_discard_when_nothing_to_discard(self):
        """Discarding with no autosave present must not error."""
        with patch('rosbag_processing.autosave.AUTOSAVE_DIR', self.temp_dir):
            response = self.client.delete(
                '/api/autosave/delete/?bag_filename=test.bag'
            )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()['deleted'])


class TestC2_EditingAfterSaveStartsNewAutosave(TestCase):
    """C2: Editing after a save starts a new autosave

    Manual Test:
    1. After C1, make one more edit and wait five seconds
    2. Pass: a fresh autosave file appears
    """

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.client = Client()

    def test_new_autosave_after_manual_save(self):
        """New edits after a manual save should create a fresh autosave."""
        with patch('rosbag_processing.autosave.AUTOSAVE_DIR', self.temp_dir):
            self.client.post(
                '/api/autosave/save/',
                data=json.dumps({
                    'bag_filename': 'test.bag',
                    'axes': [{'name': 'axis1', 'type': 'select', 'blocks': []}],
                    'saved_at': '2024-01-01T12:00:00+11:00',
                }),
                content_type='application/json',
            )

            self.client.delete('/api/autosave/delete/?bag_filename=test.bag')

            response = self.client.post(
                '/api/autosave/save/',
                data=json.dumps({
                    'bag_filename': 'test.bag',
                    'axes': [{'name': 'axis2', 'type': 'select', 'blocks': []}],
                    'saved_at': '2024-01-01T12:05:00+11:00',
                }),
                content_type='application/json',
            )

            self.assertTrue(response.json()['saved'],
                            "Post-save edit must write a fresh autosave")

            retrieved = read_autosave('test.bag')

        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved['axes'][0]['name'], 'axis2')


# ============================================================================
# Part D: Failure Handling
# ============================================================================

class TestD1_CorruptAutosaveFallsBackToBackup(TestCase):
    """D1: A corrupt autosave is treated as absent

    Manual Test:
    1. Create an autosave, then damage it with: echo 'not json' > <file>
    2. Select the bag on the import page
    3. Pass: the dialog still appears, sourced from the .bak, with a line
       saying the most recent copy could not be read
    4. Damage both files
    5. Pass: no prompt at all, no error, page loads normally
    """

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.client = Client()

    def test_corrupt_primary_falls_back_to_backup(self):
        """A corrupt primary must fall back to the .bak and flag it."""
        first = {
            'schema_version': 1,
            'bag_filename': 'test.bag',
            'axes': [{'name': 'good_backup', 'type': 'select', 'blocks': []}],
            'saved_at': '2024-01-01T12:00:00+11:00',
        }
        second = dict(first)
        second['axes'] = [{'name': 'newer', 'type': 'select', 'blocks': []}]

        with patch('rosbag_processing.autosave.AUTOSAVE_DIR', self.temp_dir):
            write_autosave('test.bag', first)
            write_autosave('test.bag', second)

            path, _ = _autosave_paths('test.bag')
            with open(path, 'w') as f:
                f.write('this is not json at all {]')

            result = read_autosave('test.bag')

        self.assertIsNotNone(result, "Must recover from the .bak")
        self.assertEqual(result['axes'][0]['name'], 'good_backup')
        self.assertTrue(result['recovered_from_backup'],
                        "UI must be told this came from the backup")

    def test_both_files_corrupt_returns_none(self):
        """If both copies are corrupt, recovery fails quietly to the safe state."""
        with patch('rosbag_processing.autosave.AUTOSAVE_DIR', self.temp_dir):
            path, backup_path = _autosave_paths('test.bag')
            os.makedirs(self.temp_dir, exist_ok=True)

            with open(path, 'w') as f:
                f.write('broken')
            with open(backup_path, 'w') as f:
                f.write('broken')

            result = read_autosave('test.bag')

            response = self.client.get('/api/autosave/check/',
                                       {'bag_filename': 'test.bag'})

        self.assertIsNone(result)
        self.assertEqual(response.status_code, 200, "Must not error")
        self.assertFalse(response.json().get('exists', True), "Must show no prompt")


class TestD2_FutureSchemaVersionRefused(TestCase):
    """D2: A future schema version is refused

    Manual Test:
    1. Edit the JSON and change schema_version from 1 to 99
    2. Select the bag
    3. Pass: no prompt; an incompatible file is ignored rather than half-loaded
    """

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.client = Client()

    def test_future_schema_version_ignored(self):
        """A future schema version must produce no prompt."""
        payload = {
            'schema_version': 99,
            'bag_filename': 'test.bag',
            'axes': [{'name': 'axis1', 'type': 'select', 'blocks': []}],
            'saved_at': '2024-01-01T12:00:00+11:00',
        }

        with patch('rosbag_processing.autosave.AUTOSAVE_DIR', self.temp_dir):
            path, _ = _autosave_paths('test.bag')
            os.makedirs(self.temp_dir, exist_ok=True)
            with open(path, 'w') as f:
                json.dump(payload, f)

            result = read_autosave('test.bag')
            response = self.client.get('/api/autosave/check/',
                                       {'bag_filename': 'test.bag'})

        self.assertIsNone(result)
        self.assertFalse(response.json().get('exists', True))

    def test_malformed_axes_field_ignored(self):
        """A payload whose axes is not a list must be treated as unusable."""
        payload = {
            'schema_version': 1,
            'bag_filename': 'test.bag',
            'axes': 'not-a-list',
            'saved_at': '2024-01-01T12:00:00+11:00',
        }

        with patch('rosbag_processing.autosave.AUTOSAVE_DIR', self.temp_dir):
            path, _ = _autosave_paths('test.bag')
            os.makedirs(self.temp_dir, exist_ok=True)
            with open(path, 'w') as f:
                json.dump(payload, f)

            result = read_autosave('test.bag')

        self.assertIsNone(result)


class TestD3_AutosaveFilesNotInLoadableList(TestCase):
    """D3: Autosave files never appear as loadable annotations

    Manual Test:
    1. With an autosave on disk, reload the import page
    2. Pass: the "Annotation File" column lists only .csv files

    This asserts against the real list_filenames endpoint rather than a
    reimplementation of its filter. list_filenames() checks three
    hardcoded real paths (rosbag-data/, booklist/, annotation/) and
    returns 500 if any is missing, so this test ensures they exist
    rather than relying on the environment already having them.
    """

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.client = Client()
        os.makedirs('/app/datas/rosbag-data', exist_ok=True)
        os.makedirs('/app/datas/booklist', exist_ok=True)
        os.makedirs('/app/datas/annotation', exist_ok=True)

    def test_autosave_not_listed_as_annotation_file(self):
        """list_filenames must not offer .autosave.json or .bak files."""
        payload = {
            'schema_version': 1,
            'bag_filename': 'test.bag',
            'axes': [{'name': 'axis1', 'type': 'select', 'blocks': []}],
            'saved_at': '2024-01-01T12:00:00+11:00',
        }

        with patch('rosbag_processing.autosave.AUTOSAVE_DIR', self.temp_dir):
            write_autosave('test.bag', payload)
            write_autosave('test.bag', dict(payload, annotation_name='v2'))

        # The listing endpoint has separate input directories; the autosave
        # directory override alone does not create its Docker-only paths.
        with open(os.path.join(self.temp_dir, 'saved.csv'), 'w') as stream:
            stream.write('id,start,end,text\n')
        filenames = os.listdir(self.temp_dir)
        with patch('rosbag_processing.views.os.path.isdir', return_value=True), \
             patch('rosbag_processing.views.os.listdir',
                   side_effect=lambda directory: filenames if directory == '/app/datas/annotation/' else []):
            response = self.client.get('/api/list_filenames/')

        self.assertEqual(response.status_code, 200)

        body = json.dumps(response.json())
        self.assertIn('saved.csv', response.json()['annotation_files'])
        self.assertNotIn('.autosave.json', body,
                         "Autosave files must never be listed as loadable")

    def test_autosave_suffix_is_not_csv(self):
        """The autosave naming scheme must not collide with the CSV namespace."""
        from rosbag_processing.autosave import AUTOSAVE_SUFFIX, BACKUP_SUFFIX

        self.assertFalse(AUTOSAVE_SUFFIX.endswith('.csv'))
        self.assertFalse(BACKUP_SUFFIX.endswith('.csv'))
        self.assertTrue(AUTOSAVE_SUFFIX.endswith('.json'))


class TestD4_BackendDownDoesNotBreakEditing(TestCase):
    """D4: The backend being down does not break editing

    Manual Test:
    1. docker compose stop backend
    2. Keep editing in the still-open tab for a minute
    3. Pass: editing continues, console warnings, no dialog or crash
    4. docker compose start backend, make another edit
    5. Pass: the next autosave succeeds

    Backend scope: a failing write must surface as a clean 500 the frontend
    can catch, and a later write must still succeed.
    """

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.client = Client()

    def test_save_failure_returns_clean_error(self):
        """A failed write returns 500 with an error message, not a stack trace."""
        body = {
            'bag_filename': 'test.bag',
            'axes': [{'name': 'axis1', 'type': 'select', 'blocks': []}],
        }

        with patch('rosbag_processing.autosave.write_autosave',
                   side_effect=OSError('Backend error')):
            response = self.client.post(
                '/api/autosave/save/',
                data=json.dumps(body),
                content_type='application/json'
            )

        self.assertEqual(response.status_code, 500)
        self.assertIn('error', response.json())

    def test_save_recovers_after_transient_failure(self):
        """Once the failure clears, the next autosave must succeed."""
        body = {
            'bag_filename': 'test.bag',
            'axes': [{'name': 'axis1', 'type': 'select', 'blocks': []}],
            'saved_at': '2024-01-01T12:00:00+11:00',
        }

        with patch('rosbag_processing.autosave.AUTOSAVE_DIR', self.temp_dir):
            with patch('rosbag_processing.autosave.write_autosave',
                       side_effect=OSError('Backend down')):
                failed = self.client.post(
                    '/api/autosave/save/',
                    data=json.dumps(body),
                    content_type='application/json'
                )
            self.assertEqual(failed.status_code, 500)

            recovered = self.client.post(
                '/api/autosave/save/',
                data=json.dumps(body),
                content_type='application/json'
            )

            self.assertEqual(recovered.status_code, 200)
            self.assertTrue(recovered.json()['saved'])
            self.assertIsNotNone(read_autosave('test.bag'))


class TestD5_ClosingTabSavesLastEdits(TestCase):
    """D5: Closing the tab saves the last edits

    Manual Test:
    1. Make an edit and, within about a second, close the tab
    2. Check the file's modification time
    3. Pass: it reflects the moment of closing

    Best-effort by design (beacon based). Backend scope: the final beacon
    write must be accepted and persisted like any other save.
    """

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.client = Client()

    def test_final_beacon_write_is_persisted(self):
        """A last-moment save must persist in full."""
        body = {
            'bag_filename': 'test.bag',
            'annotation_name': 'Session 1',
            'axes': [{'name': 'final', 'type': 'select', 'blocks': [
                {'start': 0.0, 'end': 5.0, 'code': 'last_edit'}
            ]}],
            'saved_at': '2024-01-01T12:00:00+11:00',
        }

        with patch('rosbag_processing.autosave.AUTOSAVE_DIR', self.temp_dir):
            response = self.client.post(
                '/api/autosave/save/',
                data=json.dumps(body),
                content_type='application/json',
            )
            retrieved = read_autosave('test.bag')

        self.assertTrue(response.json()['saved'])
        self.assertEqual(retrieved['axes'][0]['name'], 'final')
        self.assertEqual(retrieved['axes'][0]['blocks'][0]['code'], 'last_edit')


# ============================================================================
# Part E: The Crash Test
# ============================================================================

class TestE_CrashRecovery(TestCase):
    """E: The crash test - the one the feature exists for

    Manual Test:
    1. Load a bag, build several tiers and blocks, wait five seconds
    2. Kill the browser process outright: pkill -9 chrome
    3. Reopen the browser, go to the import page, select the same bag
    4. Pass: the prompt offers the work, and restoring returns everything up
       to the last autosave
    """

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.client = Client()

    def test_crash_recovery_full_workflow(self):
        """Save, crash, detect, restore - everything comes back."""
        body = {
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
            'saved_at': '2024-01-01T12:00:00+11:00',
        }

        with patch('rosbag_processing.autosave.AUTOSAVE_DIR', self.temp_dir):
            save = self.client.post(
                '/api/autosave/save/',
                data=json.dumps(body),
                content_type='application/json',
            )
            self.assertTrue(save.json()['saved'])

            # Browser dies here. New session starts below.

            check = self.client.get('/api/autosave/check/',
                                    {'bag_filename': 'test.bag'})
            check_data = check.json()

            self.assertTrue(check_data['exists'])
            self.assertEqual(check_data['axis_count'], 2)
            self.assertEqual(check_data['block_count'], 4)
            self.assertEqual(check_data['annotation_name'], 'Session 1')

            load = self.client.get('/api/autosave/load/',
                                   {'bag_filename': 'test.bag'})
            restored = load.json()

        self.assertEqual(len(restored['axes']), 2)
        self.assertEqual(len(restored['axes'][0]['blocks']), 3)
        self.assertEqual(restored['axes'][0]['blocks'][0]['text'], 'Hello')
        self.assertEqual(restored['axes'][1]['blocks'][0]['code'], 'happy')

    def test_prompt_counts_match_restored_data(self):
        """The counts in the prompt must match exactly what restore returns."""
        body = {
            'bag_filename': 'session.bag',
            'annotation_name': 'Interview Recording',
            'axes': [
                {
                    'id': 'axis_1',
                    'name': 'Speech Acts',
                    'type': 'select',
                    'blocks': [
                        {'start': 0.0, 'end': 5.0, 'code': 'greeting'},
                        {'start': 5.0, 'end': 10.0, 'code': 'question'},
                        {'start': 10.0, 'end': 15.0, 'code': 'answer'},
                    ]
                },
                {
                    'id': 'axis_2',
                    'name': 'Emotions',
                    'type': 'select',
                    'blocks': [
                        {'start': 0.0, 'end': 10.0, 'code': 'happy'},
                        {'start': 10.0, 'end': 15.0, 'code': 'neutral'},
                    ]
                },
                {
                    'id': 'axis_3',
                    'name': 'Empty Tier',
                    'type': 'select',
                    'blocks': []
                },
            ],
            'saved_at': '2024-01-01T12:00:00+11:00',
        }

        with patch('rosbag_processing.autosave.AUTOSAVE_DIR', self.temp_dir):
            self.client.post(
                '/api/autosave/save/',
                data=json.dumps(body),
                content_type='application/json',
            )

            check_data = self.client.get(
                '/api/autosave/check/', {'bag_filename': 'session.bag'}
            ).json()

            restored = self.client.get(
                '/api/autosave/load/', {'bag_filename': 'session.bag'}
            ).json()

        restored_axis_count = len(restored['axes'])
        restored_block_count = sum(len(ax['blocks']) for ax in restored['axes'])

        self.assertEqual(check_data['axis_count'], restored_axis_count,
                         "Prompt tier count must match what restore returns")
        self.assertEqual(check_data['block_count'], restored_block_count,
                         "Prompt annotation count must match what restore returns")

        self.assertEqual(check_data['axis_count'], 3)
        self.assertEqual(check_data['block_count'], 5)


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
