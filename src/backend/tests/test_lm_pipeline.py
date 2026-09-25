"""Acceptance tests for local and remote language-model routing."""

import json
from types import SimpleNamespace
from unittest.mock import patch

from django.test import RequestFactory, SimpleTestCase

from rosbag_processing.ai_assistant import (
    LocalInferenceError,
    RemoteAPI,
    RemoteResponseError,
)


class LMPipelineAcceptanceTests(SimpleTestCase):
    """Focused acceptance tests for provider routing without real inference."""

    def setUp(self):
        self.factory = RequestFactory()

    def make_request(self, **overrides):
        body = {
            "chat_context_id": "test-context",
            "message": "Annotate the greeting",
            "audio_transcript": "Speaker 1: Hello",
            "Axeinfo": [{"axisId": 1, "axisName": "Topics"}],
            "Codebook": {"Speech": ["Greeting"]},
            "assistant_mode": "local",
            "context_routes": {
                "transcript": "local",
                "frames": "local",
                "codebook": "local",
                "timeline": "local",
            },
        }
        body.update(overrides)
        return self.factory.post(
            "/api/gpt_chat/",
            data=json.dumps(body, ensure_ascii=False),
            content_type="application/json",
        )

    def test_local_success_uses_only_local_provider(self):
        '''select local processing for entire input, nothing should be send through network, even when remote credential is available'''
        from rosbag_processing import views

        views.cache.set('chat:test-context', {'history': "", 'frames': []})
        views.cache.set('chat:test-context', {**views.cache.get('chat:test-context'), 'frames': ["private-frame"]})
        request = self.make_request()
        metadata = {
            "model": {
                "provider": "local",
                "requested": "test-local-model",
                "resolved": "test-local-model",
            },
            "parameters": {"temperature": 0},
            "prompts": {"user": "Annotate the greeting"},
        }

        with patch.dict(
            "os.environ", {"LOCAL_AI_CHECKPOINT_PATH": "/models/test.gguf"}
        ), patch.object(views, "openai_api_key", "unused-remote-key"), patch.object(
            views, "RemoteAPI"
        ) as remote_api, patch.object(views, "create_local_ai") as local_ai:
            local_ai.return_value.respond.return_value = "local result"
            local_ai.return_value.get_run_metadata.return_value = metadata

            response = views.gpt_chat(request)

        response_data = json.loads(response.content)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response_data["response"], "local result")
        self.assertEqual(response_data["assistant_mode"], "local")
        self.assertEqual(response_data["ai_record"]["model"], metadata["model"])
        remote_api.assert_not_called()
        local_ai.assert_called_once_with(
            transcriptContext="Speaker 1: Hello",
            frameContext=["private-frame"],
            codebookContext={"Speech": ["Greeting"]},
            timelineContext=[{"axisId": 1, "axisName": "Topics"}],
            checkpointPath="/models/test.gguf",
        )
        local_ai.return_value.respond.assert_called_once_with(
            "Annotate the greeting", ""
        )

    def test_local_failure_preserves_history_and_does_not_call_remote(self):
        '''local mode fails when remote fall back is available: failure message shown, with remote fallback. fallback does not start automatically'''
        '''if user reject local to remote fall back, no remote request is made'''
        from rosbag_processing import views

        views.cache.set('chat:test-context', {'history': "existing history", 'frames': []})
        views.cache.set('chat:test-context', {**views.cache.get('chat:test-context'), 'frames': ["private-frame"]})
        request = self.make_request(message="Keep this request local")

        with patch.object(views, "openai_api_key", "configured-remote-key"), patch.object(
            views, "RemoteAPI"
        ) as remote_api, patch.object(views, "create_local_ai") as local_ai:
            local_ai.return_value.respond.side_effect = LocalInferenceError(
                "Local inference failed."
            )

            response = views.gpt_chat(request)

        response_data = json.loads(response.content)
        self.assertEqual(response.status_code, 501)
        self.assertEqual(response_data["assistant_mode"], "local")
        self.assertTrue(response_data["can_fallback_to_remote"])
        self.assertIn("Local inference failed.", response_data["error"])
        self.assertEqual(views.cache.get('chat:test-context')['history'], "existing history")
        remote_api.assert_not_called()

    def test_remote_timeout_does_not_start_local_automatically(self):
        '''remote API timeout or unreachable shows failure message and offer local fallback; fallback does not start automatically'''
        from rosbag_processing import views

        views.cache.set('chat:test-context', {'history': "", 'frames': []})
        views.cache.set('chat:test-context', {**views.cache.get('chat:test-context'), 'frames': ["frame-1"]})
        request = self.make_request(
            message="Use the remote provider",
            assistant_mode="remote",
            context_routes={
                "transcript": "remote",
                "frames": "remote",
                "codebook": "remote",
                "timeline": "remote",
            },
        )

        with patch.object(views, "openai_api_key", "test-key"), patch.object(
            views, "RemoteAPI"
        ) as remote_api, patch.object(views, "create_local_ai") as local_ai:
            remote_api.return_value.respond.side_effect = TimeoutError(
                "remote timed out"
            )

            response = views.gpt_chat(request)

        self.assertEqual(response.status_code, 503)
        response_data = json.loads(response.content)
        self.assertIn("remote timed out", response_data["error"])
        self.assertTrue(response_data["can_fallback_to_local"])
        local_ai.assert_not_called()
        self.assertEqual(views.cache.get('chat:test-context')['history'], "")

    def test_multiline_unicode_prompt_round_trips_through_request_and_record(self):
        '''multiline prompt or unicode prompt preserves content without breaking request serialization or audit records.'''
        from rosbag_processing import views

        message = "First line\n第二行：café 🤖"
        response_text = "完成\nResult preserved ✅"
        views.cache.set('chat:test-context', {'history': "", 'frames': []})
        views.cache.set('chat:test-context', {**views.cache.get('chat:test-context'), 'frames': []})
        request = self.make_request(message=message)
        metadata = {
            "model": {
                "provider": "local",
                "requested": "unicode-test-model",
                "resolved": "unicode-test-model",
            },
            "parameters": {"stop": ["終"]},
            "prompts": {"system": "System café", "user": message},
        }

        with patch.object(views, "RemoteAPI") as remote_api, patch.object(
            views, "create_local_ai"
        ) as local_ai:
            local_ai.return_value.respond.return_value = response_text
            local_ai.return_value.get_run_metadata.return_value = metadata

            response = views.gpt_chat(request)

        response_data = json.loads(response.content)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response_data["response"], response_text)
        self.assertEqual(response_data["ai_record"]["prompts"]["user"], message)
        self.assertEqual(
            response_data["ai_record"]["parameters"], {"stop": ["終"]}
        )
        local_ai.return_value.respond.assert_called_once_with(message, "")
        remote_api.assert_not_called()

    def test_invalid_assistant_mode_calls_no_provider(self):
        '''invalid model provider call'''
        from rosbag_processing import views

        request = self.make_request(assistant_mode="unknown")

        with patch.object(views, "RemoteAPI") as remote_api, patch.object(
            views, "create_local_ai"
        ) as local_ai:
            response = views.gpt_chat(request)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            json.loads(response.content), {"error": "Invalid assistant mode"}
        )
        remote_api.assert_not_called()
        local_ai.assert_not_called()

    def test_mixed_context_routes_call_no_provider(self):
        '''A request cannot route some context to a different provider.'''
        from rosbag_processing import views

        request = self.make_request(
            assistant_mode="remote",
            context_routes={
                "transcript": "local",
                "frames": "remote",
                "codebook": "remote",
            },
        )

        with patch.object(views, "RemoteAPI") as remote_api, patch.object(
            views, "create_local_ai"
        ) as local_ai:
            response = views.gpt_chat(request)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            json.loads(response.content), {"error": "Invalid context routes"}
        )
        remote_api.assert_not_called()
        local_ai.assert_not_called()

    def test_remote_invalid_responses_are_rejected_and_can_be_resubmitted(self):
        """Malformed and unsupported replies must not poison a later retry."""
        invalid_responses = {
            "malformed JSON": "{bad json",
            "unsupported action": json.dumps(
                {
                    "type": "instruction",
                    "steps": [{"action": "runShell", "parameters": {}}],
                }
            ),
        }
        valid_response = json.dumps(
            {
                "type": "instruction",
                "steps": [
                    {
                        "action": "addAxi",
                        "parameters": {
                            "axisId": 2,
                            "axisName": "Safe retry",
                            "axistype": "Type-in",
                        },
                    }
                ],
            }
        )

        for case_name, invalid_response in invalid_responses.items():
            with self.subTest(case=case_name), patch(
                "rosbag_processing.ai_assistant.OpenAI"
            ) as openai_class:
                timeline = [{"axisId": 1, "axisName": "Existing"}]
                original_timeline = json.loads(json.dumps(timeline))
                openai_class.return_value.chat.completions.create.side_effect = [
                    SimpleNamespace(
                        model="gpt-4o",
                        choices=[
                            SimpleNamespace(
                                message=SimpleNamespace(content=invalid_response)
                            )
                        ],
                    ),
                    SimpleNamespace(
                        model="gpt-4o",
                        choices=[
                            SimpleNamespace(
                                message=SimpleNamespace(content=valid_response)
                            )
                        ],
                    ),
                ]
                assistant = RemoteAPI(
                    APIKey="test-key",
                    transcriptContext="Speaker 1: Hello",
                    frameContext=[],
                    codebookContext={},
                    timelineContext=timeline,
                )

                with self.assertRaisesRegex(
                    RemoteResponseError, "No annotation changes were applied"
                ):
                    assistant.respond("Create an annotation axis")

                self.assertEqual(timeline, original_timeline)
                self.assertEqual(
                    assistant.respond("Create an annotation axis"), valid_response
                )
                self.assertEqual(
                    openai_class.return_value.chat.completions.create.call_count, 2
                )
