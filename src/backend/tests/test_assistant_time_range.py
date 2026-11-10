import json
from unittest.mock import patch

from django.test import RequestFactory, SimpleTestCase

from rosbag_processing import views


class AssistantTimeRangeTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def request(self, selected_range, message='Annotate this range'):
        return self.factory.post(
            '/api/gpt_chat/',
            data=json.dumps({
                'message': message,
                'audio_transcript': (
                    '[00:00] Speaker A: Before\n'
                    '[00:10] Speaker A: Selected\n'
                    '[00:20] Speaker A: After'
                ),
                'Axeinfo': [{'id': 1, 'blocks': [
                    {'start': 2, 'end': 4, 'text': 'before'},
                    {'start': 12, 'end': 14, 'text': 'selected'},
                ]}],
                'Codebook': [],
                'video_path': 'chunks/selected/output.mp4',
                'context_duration': 30,
                'time_range': selected_range,
            }),
            content_type='application/json',
        )

    def test_valid_range_filters_transcript_frames_and_timeline(self):
        with patch.object(views, 'frames_for_video', return_value=(
                 ['range-frame'], [{
                     'frame_index': 3,
                     'chunk_relative_seconds': 12.0,
                     'sha256': 'frame-hash',
                 }],
             )) as sample, \
             patch.object(views, 'openai_api_key', 'test-key'), \
             patch.object(views, 'RemoteAPI') as remote_api:
            remote_api.return_value.respond.return_value = 'done'
            response = views.gpt_chat(self.request({'start': 10, 'end': 20}))

        self.assertEqual(response.status_code, 200)
        sample.assert_called_once_with(
            'chunks/selected/output.mp4', start_seconds=10.0, end_seconds=20.0,
        )
        context = remote_api.call_args.kwargs
        self.assertIn('Selected', context['transcriptContext'])
        self.assertNotIn('Before', context['transcriptContext'])
        self.assertNotIn('After', context['transcriptContext'])
        self.assertEqual(context['timelineContext'][0]['blocks'], [
            {'start': 12, 'end': 14, 'text': 'selected', 'blockIndex': 1},
        ])

    def test_video_sampling_uses_half_open_presentation_time_range(self):
        timestamps = [0.0, 8.0, 14.999, 15.0, 15.08, 20.0]

        selected = views.select_video_frame_indices(
            timestamps, start_seconds=0, end_seconds=15,
        )

        self.assertEqual(selected, [0, 1, 2])

    def test_filtered_timeline_keeps_full_annotation_block_index(self):
        timeline = [{
            'id': 1,
            'annotationBlocks': [
                {'start': 2, 'end': 4, 'text': 'before'},
                {'start': 12, 'end': 14, 'text': 'selected'},
                {'start': 22, 'end': 24, 'text': 'after'},
            ],
        }]

        filtered = views.timeline_for_time_range(timeline, 10, 20)

        self.assertEqual(filtered[0]['annotationBlocks'], [
            {'start': 12, 'end': 14, 'text': 'selected', 'blockIndex': 1},
        ])

    def test_invalid_ranges_are_rejected_before_lm_call(self):
        for selected_range in (
            {'start': -1, 'end': 10},
            {'start': 20, 'end': 10},
            {'start': 0, 'end': 31},
            {'start': 4, 'end': 4},
        ):
            with self.subTest(selected_range=selected_range), \
                 patch.object(views, 'RemoteAPI') as remote_api:
                response = views.gpt_chat(self.request(selected_range))
                self.assertEqual(response.status_code, 400)
                remote_api.assert_not_called()

    def test_prompt_timestamp_outside_selection_is_rejected_before_sampling(self):
        for message in (
            'Describe what happens at 00:25',
            'Annotate from 25 to 28 seconds',
            'Review between 0.5 and 1 minutes',
        ):
            with self.subTest(message=message), \
                 patch.object(views, 'frames_for_video') as sample, \
                 patch.object(views, 'RemoteAPI') as remote_api:
                response = views.gpt_chat(
                    self.request({'start': 10, 'end': 20}, message=message)
                )

            self.assertEqual(response.status_code, 400)
            error = json.loads(response.content)['error']
            self.assertIn('outside the selected time range 00:10–00:20', error)
            self.assertIn('Update Range start and Range end', error)
            sample.assert_not_called()
            remote_api.assert_not_called()

    def test_prompt_range_equal_to_selection_is_allowed(self):
        with patch.object(views, 'frames_for_video', return_value=(
                 ['range-frame'], [{
                     'frame_index': 3,
                     'chunk_relative_seconds': 12.0,
                     'sha256': 'frame-hash',
                 }],
             )), \
             patch.object(views, 'openai_api_key', 'test-key'), \
             patch.object(views, 'RemoteAPI') as remote_api:
            remote_api.return_value.respond.return_value = 'done'
            response = views.gpt_chat(self.request(
                {'start': 10, 'end': 20},
                message='Describe 00:10–00:20',
            ))

        self.assertEqual(response.status_code, 200)
        remote_api.assert_called_once()

    def test_point_at_selected_end_is_outside_half_open_range(self):
        with patch.object(views, 'frames_for_video') as sample, \
             patch.object(views, 'RemoteAPI') as remote_api:
            response = views.gpt_chat(self.request(
                {'start': 10, 'end': 20},
                message='Describe the frame at 20 seconds',
            ))

        self.assertEqual(response.status_code, 400)
        self.assertIn('00:20', json.loads(response.content)['error'])
        sample.assert_not_called()
        remote_api.assert_not_called()
