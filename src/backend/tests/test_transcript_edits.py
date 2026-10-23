import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from rosbag_processing.transcript_edits import (
    TranscriptConflict, format_transcript, load_transcript_view, save_transcript_edits, validate_segments,
)
from rosbag_processing.view_cache import atomic_json


def segment(speaker='SPEAKER_00', text='Original', start=1.25, end=2.5):
    return {'speaker_label': speaker, 'text': text, 'start_time': start, 'end_time': end}


def generated_transcript():
    return {'view_id': 'transcript', 'status': 'ready', 'available': True, 'reason': None,
            'duration': 30, 'selected_topics': ['/audio'], 'warnings': [],
            'time_origin': {'reference': 'chunk_start', 'bag_offset_seconds': 300, 'absolute_seconds': 1300},
            'processed_data': {'transcript': format_transcript([segment()]), 'speaker_data': [segment()], 'artifacts': []}}


class TranscriptEditTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name) / ('a' * 64)
        atomic_json(self.directory / 'result.json', generated_transcript())

    def test_save_reload_preserves_original_and_updates_text_speaker_and_precise_times(self):
        original = (self.directory / 'result.json').read_bytes()
        edited = [segment('田中', 'Corrected speech', 3.25, 4.75)]
        result = save_transcript_edits(self.directory, 'chunks', edited, 0)
        reloaded = load_transcript_view(self.directory, 'chunks')
        self.assertEqual(result, reloaded)
        self.assertEqual(reloaded['processed_data']['speaker_data'], edited)
        self.assertEqual(reloaded['processed_data']['transcript'], '[00:03] Speaker 田中: Corrected speech [00:04]')
        self.assertEqual(reloaded['processed_data']['revision'], 1)
        self.assertEqual(reloaded['time_origin']['bag_offset_seconds'], 300)
        self.assertEqual((self.directory / 'result.json').read_bytes(), original)

    def test_edits_are_isolated_between_chunks_and_whole_input(self):
        other = Path(self.temp.name) / ('b' * 64)
        atomic_json(other / 'result.json', generated_transcript())
        save_transcript_edits(self.directory, 'chunks', [segment('Alice')], 0)
        self.assertEqual(load_transcript_view(other, 'whole')['processed_data']['revision'], 0)
        self.assertEqual(load_transcript_view(other, 'whole')['processed_data']['speaker_data'][0]['speaker_label'], 'SPEAKER_00')

    def test_empty_transcript_is_saved_and_can_be_edited_again(self):
        cleared = save_transcript_edits(self.directory, 'chunks', [], 0)
        self.assertEqual(cleared['processed_data']['transcript'], '')
        self.assertEqual(load_transcript_view(self.directory, 'chunks')['processed_data']['speaker_data'], [])
        result = save_transcript_edits(self.directory, 'chunks', [segment()], 1)
        self.assertEqual(result['processed_data']['revision'], 2)

    def test_stale_revision_cannot_overwrite_another_save(self):
        save_transcript_edits(self.directory, 'chunks', [segment(text='First edit')], 0)
        with self.assertRaises(TranscriptConflict):
            save_transcript_edits(self.directory, 'chunks', [segment(text='Stale edit')], 0)
        self.assertEqual(load_transcript_view(self.directory, 'chunks')['processed_data']['speaker_data'][0]['text'], 'First edit')

    def test_failed_atomic_save_keeps_previous_edits(self):
        save_transcript_edits(self.directory, 'chunks', [segment(text='Saved')], 0)
        with patch('rosbag_processing.view_cache.os.replace', side_effect=OSError('disk error')):
            with self.assertRaises(OSError):
                save_transcript_edits(self.directory, 'chunks', [segment(text='Unsaved')], 1)
        self.assertEqual(load_transcript_view(self.directory, 'chunks')['processed_data']['revision'], 1)
        self.assertEqual(load_transcript_view(self.directory, 'chunks')['processed_data']['speaker_data'][0]['text'], 'Saved')

    def test_invalid_data_is_rejected_without_persisting(self):
        for value in [None, {}, [None], [segment(start=True)], [segment(start=-1)], [segment(start=5, end=4)],
                      [segment(end=31)], [segment(end=float('nan'))], [segment(end=float('inf'))],
                      [segment(speaker=' ')], [segment(speaker='a\nb')], [segment(text=None)]]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                save_transcript_edits(self.directory, 'chunks', value, 0)
        self.assertFalse((self.directory / 'transcript.edits.json').exists())

    def test_missing_and_non_transcript_views_cannot_be_edited(self):
        with self.assertRaises(FileNotFoundError):
            save_transcript_edits(Path(self.temp.name) / 'missing', 'chunks', [], 0)
        generated = generated_transcript()
        generated['view_id'] = 'video'
        atomic_json(self.directory / 'result.json', generated)
        with self.assertRaises(FileNotFoundError):
            save_transcript_edits(self.directory, 'chunks', [], 0)

    def test_corrupt_edits_do_not_silently_fall_back_to_generated_text(self):
        for contents in ['{invalid', 'null', '[]', '{"revision":true}']:
            (self.directory / 'transcript.edits.json').write_text(contents, encoding='utf-8')
            with self.subTest(contents=contents), self.assertRaises(ValueError):
                load_transcript_view(self.directory, 'chunks')

    def test_sorting_keeps_precise_times_and_handles_long_transcripts(self):
        segments = validate_segments([segment(start=6001.75, end=6002.9), segment(start=0, end=0)], 7000)
        self.assertEqual(segments[1]['start_time'], 6001.75)
        self.assertIn('[100:01]', format_transcript(segments))


class TranscriptWorkflowTests(unittest.TestCase):
    def test_processing_reload_uses_edits_without_retranscribing(self):
        from tests.test_data_view_processing import FakeBag, SampleProcessor
        from rosbag_processing.processing_sessions import ProcessingRequest
        from rosbag_processing.rosbag_reader import RosbagReader
        from rosbag_processing.view_workflow import process_views

        class FakeTranscript(SampleProcessor):
            view_id = 'transcript'

            def preprocess(self, context, extracted):
                return generated_transcript()['processed_data']

            def legacy_fields(self, data):
                return {'audio_transcript': data['transcript'], 'speaker_data': data['speaker_data']}

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            bag = root / 'input.bag'
            bag.write_bytes(b'bag')
            request = ProcessingRequest(str(bag), str(root / 'processed'))
            processor = FakeTranscript()
            reader = lambda path, chunk: RosbagReader(path, chunk, lambda *_: FakeBag())
            for scope, chunk in [('whole', None), ('chunks', {'index': 0, 'start_seconds': 0, 'end_seconds': 5})]:
                current = replace(request, chunk=chunk)
                initial = process_views(current, [processor], reader)
                ref = initial['views']['transcript']['processed_data']['edit_ref']
                self.assertEqual(ref['scope'], scope)
                directory = root / 'processed' / 'views' / ref['key']
                edited = [segment('Alice', 'Edited')]
                save_transcript_edits(directory, scope, edited, 0)
                calls = processor.calls
                loaded = process_views(current, [processor], reader)
                self.assertEqual(processor.calls, calls)
                self.assertEqual(loaded['speaker_data'], edited)
                self.assertIn('Alice: Edited', loaded['audio_transcript'])
                self.assertEqual(loaded['views']['transcript']['processed_data']['speaker_data'], edited)

                legacy = directory.parent / (('c' if scope == 'whole' else 'd') * 64)
                directory.rename(legacy)
                with patch('rosbag_processing.view_cache.ViewCache.legacy_directory', return_value=legacy):
                    migrated = process_views(current, [processor], reader)
                    self.assertEqual(migrated['views']['transcript']['processed_data']['edit_ref']['key'], legacy.name)
                    self.assertEqual(migrated['speaker_data'], edited)
                    save_transcript_edits(legacy, scope, [segment('Bob')], 1)
                    self.assertEqual(process_views(current, [processor], reader)['speaker_data'][0]['speaker_label'], 'Bob')
