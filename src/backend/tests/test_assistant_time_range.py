import json
from unittest.mock import patch

from django.test import RequestFactory, SimpleTestCase

from rosbag_processing import views


class AssistantTimeRangeTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def request(self, selected_range):
        return self.factory.post(
            '/api/gpt_chat/',
            data=json.dumps({
                'message': 'Annotate this range',
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
        with patch.object(views, 'frames_for_video', return_value=['range-frame']) as sample, \
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
            {'start': 12, 'end': 14, 'text': 'selected'},
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
