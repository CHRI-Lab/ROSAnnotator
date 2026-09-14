import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

from django.test import RequestFactory, SimpleTestCase

from .ai_assistant import (
    AIAssistant,
    LlamaLocalAI,
    LocalAI,
    LocalInferenceError,
    QwenLocalAI,
    RemoteAPI,
    RemoteAuthenticationError,
    SmolVLM2LocalAI,
    create_local_ai,
)


class AIAssistantTests(SimpleTestCase):
    def setUp(self):
        self.contexts = {
            "transcriptContext": "Speaker 1: Hello",
            "frameContext": [f"frame-{index}" for index in range(101)],
            "codebookContext": ["Greeting"],
            "timelineContext": [{"axisId": 1, "axisName": "Topics"}],
        }

    @patch("rosbag_processing.ai_assistant.OpenAI")
    def test_remote_api_preserves_existing_gpt_request(self, openai_class):
        response_message = '{"type":"instruction","steps":[]}'
        openai_class.return_value.chat.completions.create.return_value = (
            SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content=response_message))]
            )
        )

        assistant = RemoteAPI(APIKey="test-key", **self.contexts)
        result = assistant.respond("Add an annotation", "previous history")

        self.assertEqual(result, response_message)
        self.assertEqual(assistant.APIKey, "test-key")
        openai_class.assert_called_once_with(api_key="test-key")

        request = openai_class.return_value.chat.completions.create.call_args.kwargs
        self.assertEqual(request["model"], "gpt-4o")
        text_content = request["messages"][1]["content"][0]
        self.assertEqual(text_content["type"], "text")
        self.assertIn("Speaker 1: Hello", text_content["text"])
        self.assertIn("Add an annotation", text_content["text"])
        self.assertIn("previous history", request["messages"][0]["content"])
        self.assertIn("Greeting", request["messages"][0]["content"])
        self.assertIn("Topics", request["messages"][0]["content"])

        sent_frames = request["messages"][1]["content"][1:]
        self.assertEqual(len(sent_frames), 50)
        self.assertEqual(
            sent_frames[0],
            {
                "type": "image_url",
                "image_url": {
                    "url": "data:image/jpeg;base64,frame-0",
                    "detail": "low",
                },
            },
        )
        self.assertEqual(
            sent_frames[-1],
            {
                "type": "image_url",
                "image_url": {
                    "url": "data:image/jpeg;base64,frame-98",
                    "detail": "low",
                },
            },
        )
        metadata = assistant.get_run_metadata()
        self.assertEqual(metadata["model"]["requested"], "gpt-4o")
        self.assertEqual(metadata["prompts"]["user"], "Add an annotation")

    @patch("rosbag_processing.ai_assistant.OpenAI")
    def test_local_ai_uses_local_text_only_service(self, openai_class):
        openai_class.return_value.chat.completions.create.return_value = (
            SimpleNamespace(
                model="qwen2.5-0.5b-instruct",
                choices=[SimpleNamespace(message=SimpleNamespace(content="Greeting"))],
            )
        )
        assistant = QwenLocalAI(checkpointPath="/models/local.gguf", **self.contexts)

        result = assistant.respond("Return the applicable code", "earlier chat")

        self.assertEqual(result, "Greeting")
        openai_class.assert_called_once_with(
            base_url="http://local-llm:8080/v1", api_key="local", timeout=900
        )
        request = openai_class.return_value.chat.completions.create.call_args.kwargs
        self.assertEqual(request["temperature"], 0)
        self.assertEqual(request["max_tokens"], 256)
        self.assertNotIn("response_format", request)
        system_prompt = request["messages"][0]["content"]
        self.assertIn("Speaker 1: Hello", system_prompt)
        self.assertIn("Greeting", system_prompt)
        self.assertNotIn("Topics", system_prompt)
        self.assertIn("earlier chat", system_prompt)
        self.assertNotIn("frame-0", system_prompt)
        self.assertEqual(
            assistant.get_run_metadata()["model"]["provider"], "local"
        )

    @patch("rosbag_processing.ai_assistant.OpenAI")
    def test_local_timeline_request_uses_instruction_schema(self, openai_class):
        response_message = '{"type":"instruction","steps":[]}'
        openai_class.return_value.chat.completions.create.return_value = (
            SimpleNamespace(
                model="qwen2.5-0.5b-instruct",
                choices=[
                    SimpleNamespace(message=SimpleNamespace(content=response_message))
                ],
            )
        )
        assistant = QwenLocalAI(checkpointPath="/models/local.gguf", **self.contexts)

        result = assistant.respond("Create an annotation axis")

        self.assertEqual(json.loads(result), json.loads(response_message))
        request = openai_class.return_value.chat.completions.create.call_args.kwargs
        response_format = request["response_format"]
        self.assertEqual(response_format["type"], "json_schema")
        schema = response_format["json_schema"]["schema"]
        self.assertEqual(schema["properties"]["type"]["const"], "instruction")
        self.assertEqual(request["max_tokens"], 768)
        self.assertEqual(schema["properties"]["steps"]["maxItems"], 64)
        self.assertEqual(
            schema["properties"]["steps"]["items"]["required"],
            ["action", "parameters"],
        )

    @patch("rosbag_processing.ai_assistant.OpenAI")
    def test_invalid_local_timeline_response_is_logged(self, openai_class):
        openai_class.return_value.chat.completions.create.return_value = (
            SimpleNamespace(
                model="qwen2.5-0.5b-instruct-q4_k_m",
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(content="not valid json")
                    )
                ],
            )
        )
        assistant = QwenLocalAI(
            checkpointPath="/models/local.gguf", **self.contexts
        )

        with self.assertLogs(
            "rosbag_processing.ai_assistant", level="ERROR"
        ) as captured_logs:
            with self.assertRaisesRegex(
                LocalInferenceError, "invalid timeline instruction"
            ):
                assistant.respond("Create an annotation axis")

        self.assertIn("not valid json", "\n".join(captured_logs.output))

    @patch("rosbag_processing.ai_assistant.OpenAI")
    def test_local_summary_request_uses_general_answer_prompt(self, openai_class):
        openai_class.return_value.chat.completions.create.return_value = (
            SimpleNamespace(
                model="qwen2.5-0.5b-instruct",
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(content="The speaker says hello.")
                    )
                ],
            )
        )
        assistant = QwenLocalAI(checkpointPath="/models/local.gguf", **self.contexts)

        result = assistant.respond("Summarize the transcript")

        self.assertEqual(result, "The speaker says hello.")
        request = openai_class.return_value.chat.completions.create.call_args.kwargs
        self.assertNotIn("response_format", request)
        system_prompt = request["messages"][0]["content"]
        self.assertIn("provide a concise factual summary", system_prompt)
        self.assertIn("Speaker 1: Hello", system_prompt)
        self.assertNotIn("Return only the matching label", system_prompt)

    @patch("rosbag_processing.ai_assistant.OpenAI")
    def test_local_timeline_request_replaces_duplicate_axis_id(
        self, openai_class
    ):
        response_message = json.dumps(
            {
                "type": "instruction",
                "steps": [
                    {
                        "action": "addAxi",
                        "parameters": {
                            "axisId": 1,
                            "axisName": "Transcript",
                            "axistype": "Type-in",
                        },
                    },
                    {
                        "action": "addBlock",
                        "parameters": {
                            "axisId": 1,
                            "start": 0,
                            "end": 1,
                            "text": "Greeting",
                        },
                    },
                ],
            }
        )
        openai_class.return_value.chat.completions.create.return_value = (
            SimpleNamespace(
                model="qwen2.5-0.5b-instruct",
                choices=[
                    SimpleNamespace(message=SimpleNamespace(content=response_message))
                ],
            )
        )
        assistant = QwenLocalAI(checkpointPath="/models/local.gguf", **self.contexts)

        result = json.loads(assistant.respond("Add an axis for the transcript"))

        self.assertEqual(result["steps"][0]["parameters"]["axisId"], 2)
        self.assertEqual(result["steps"][1]["parameters"]["axisId"], 2)
        system_prompt = (
            openai_class.return_value.chat.completions.create.call_args.kwargs[
                "messages"
            ][0]["content"]
        )
        self.assertIn("next unused axisId is 2", system_prompt)
        self.assertIn("return one addAxi step and do not add blocks", system_prompt)

    @patch("rosbag_processing.ai_assistant.OpenAI")
    def test_local_model_rejects_video_annotation_with_clear_reason(
        self, openai_class
    ):
        assistant = QwenLocalAI(checkpointPath="/models/local.gguf", **self.contexts)

        with self.assertRaisesRegex(LocalInferenceError, "text-only"):
            assistant.respond("Annotate participant gestures in the video")

        openai_class.assert_not_called()

    @patch("rosbag_processing.ai_assistant.OpenAI")
    def test_smolvlm2_sends_sampled_frames_for_visual_requests(
        self, openai_class
    ):
        openai_class.return_value.chat.completions.create.return_value = (
            SimpleNamespace(
                model="SmolVLM2-500M-Video-Instruct-Q8_0",
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(content="The participant waves.")
                    )
                ],
            )
        )
        assistant = SmolVLM2LocalAI(
            checkpointPath="/models/smolvlm2.gguf", **self.contexts
        )

        result = assistant.respond("Describe the gestures in the video")

        self.assertEqual(result, "The participant waves.")
        request = openai_class.return_value.chat.completions.create.call_args.kwargs
        user_content = request["messages"][1]["content"]
        images = [item for item in user_content if item["type"] == "image_url"]
        self.assertEqual(len(images), 8)
        self.assertEqual(
            images[0]["image_url"]["url"],
            "data:image/jpeg;base64,frame-0",
        )
        self.assertIn("visual evidence", request["messages"][0]["content"])

    @patch("rosbag_processing.ai_assistant.OpenAI")
    def test_smolvlm2_classifies_frames_and_parent_builds_timeline(
        self, openai_class
    ):
        labels = ["GESTURE_WAVING", "NO_GESTURE", "GESTURE_NODDING"]
        openai_class.return_value.chat.completions.create.side_effect = [
            SimpleNamespace(
                model="SmolVLM2-500M-Video-Instruct-Q8_0",
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(
                            content=json.dumps({"label": label})
                        )
                    )
                ],
            )
            for label in labels
        ]
        contexts = {
            **self.contexts,
            "transcriptContext": "[00:00] Speaker: Hello [00:10]",
            "frameContext": ["frame-0", "frame-1", "frame-2"],
            "codebookContext": {
                "Speech attitude": ["ATTITUDE_NEUTRAL"],
                "Visible gesture": [
                    "GESTURE_WAVING",
                    "GESTURE_NODDING",
                    "GESTURE_NONE",
                ],
            },
        }
        assistant = SmolVLM2LocalAI(
            checkpointPath="/models/smolvlm2.gguf", **contexts
        )

        result = json.loads(
            assistant.respond(
                "Annotate participant gestures according to the codebook "
                "in a new timeline axis"
            )
        )

        self.assertEqual(
            [step["action"] for step in result["steps"]],
            ["addAxi", "addBlock", "addBlock"],
        )
        self.assertEqual(
            [step["parameters"]["text"] for step in result["steps"][1:]],
            ["GESTURE_WAVING", "GESTURE_NODDING"],
        )
        self.assertEqual(
            result["steps"][0]["parameters"]["axisName"],
            "Participant Gestures",
        )
        self.assertEqual(
            openai_class.return_value.chat.completions.create.call_count, 3
        )
        first_request = (
            openai_class.return_value.chat.completions.create.call_args_list[0].kwargs
        )
        schema = first_request["response_format"]["json_schema"]["schema"]
        self.assertEqual(list(schema["properties"]), ["label"])
        self.assertNotIn("GESTURE_NONE", [
            step["parameters"].get("text") for step in result["steps"]
        ])

    def test_factory_selects_smolvlm2_child(self):
        with patch.dict(
            "os.environ",
            {"LOCAL_AI_MODEL": "SmolVLM2-500M-Video-Instruct-Q8_0"},
        ):
            assistant = create_local_ai(
                checkpointPath="/models/smolvlm2.gguf", **self.contexts
            )

        self.assertIsInstance(assistant, SmolVLM2LocalAI)
        self.assertTrue(assistant.supports_visual_annotation)

    def test_local_model_children_only_declare_configuration(self):
        for model_class in (QwenLocalAI, LlamaLocalAI, SmolVLM2LocalAI):
            with self.subTest(model_class=model_class.__name__):
                self.assertIs(model_class._respond, LocalAI._respond)
                self.assertIs(model_class._user_content, LocalAI._user_content)
                self.assertIs(
                    model_class._build_request_system_prompt,
                    LocalAI._build_request_system_prompt,
                )

    def test_combined_codebook_routes_only_attitude_labels(self):
        contexts = {
            **self.contexts,
            "codebookContext": {
                "Request utterance": ["REQUEST_DIRECT"],
                "Speech attitude": ["ATTITUDE_COOPERATIVE"],
                "Visible gesture": ["GESTURE_WAVING"],
            },
        }
        assistant = QwenLocalAI(
            checkpointPath="/models/local.gguf", **contexts
        )
        message = (
            "Annotate participant attitudes in speech according to the "
            "codebook in a new axis"
        )

        selected_codebook = assistant._codebook_for_message(message)
        system_prompt = assistant._build_system_prompt(message)

        self.assertEqual(
            selected_codebook,
            {"Speech attitude": ["ATTITUDE_COOPERATIVE"]},
        )
        self.assertIn("ATTITUDE_COOPERATIVE", system_prompt)
        self.assertNotIn("REQUEST_DIRECT", system_prompt)
        self.assertNotIn("GESTURE_WAVING", system_prompt)

    @patch("rosbag_processing.ai_assistant.OpenAI")
    def test_text_only_guard_is_inherited_by_each_local_model(
        self, openai_class
    ):
        for model_class in (QwenLocalAI, LlamaLocalAI):
            with self.subTest(model_class=model_class.__name__):
                assistant = model_class(
                    checkpointPath="/models/local.gguf", **self.contexts
                )
                with self.assertRaisesRegex(
                    LocalInferenceError, "gesture annotation"
                ):
                    assistant.respond("Create gesture annotations from the frames")

        openai_class.assert_not_called()

    @patch("rosbag_processing.ai_assistant.OpenAI")
    def test_local_auto_annotation_requires_annotation_blocks(self, openai_class):
        response_message = json.dumps(
            {
                "type": "instruction",
                "steps": [
                    {
                        "action": "addAxi",
                        "parameters": {
                            "axisId": 2,
                            "axisName": "Requests",
                            "axistype": "Type-in",
                        },
                    }
                ],
            }
        )
        openai_class.return_value.chat.completions.create.return_value = (
            SimpleNamespace(
                model="qwen2.5-0.5b-instruct",
                choices=[
                    SimpleNamespace(message=SimpleNamespace(content=response_message))
                ],
            )
        )
        assistant = QwenLocalAI(checkpointPath="/models/local.gguf", **self.contexts)

        with self.assertRaisesRegex(LocalInferenceError, "annotation blocks"):
            assistant.respond(
                "Annotate all request utterances made by participants in a new axis"
            )

        request = openai_class.return_value.chat.completions.create.call_args.kwargs
        schema = request["response_format"]["json_schema"]["schema"]
        self.assertEqual(schema["properties"]["steps"]["minItems"], 2)

    @patch("rosbag_processing.ai_assistant.OpenAI")
    def test_local_auto_annotation_repairs_blocks_without_an_axis(self, openai_class):
        response_message = json.dumps(
            {
                "type": "instruction",
                "steps": [
                    {
                        "action": "addBlock",
                        "parameters": {
                            # SmolVLM2 may reuse an existing speaker axis
                            # instead of creating the requested new axis.
                            "axisId": 1,
                            "start": 7,
                            "end": 9,
                            "text": "Could you move the camera closer?",
                        },
                    }
                ],
            }
        )
        openai_class.return_value.chat.completions.create.return_value = (
            SimpleNamespace(
                model="SmolVLM2-500M-Video-Instruct-Q8_0",
                choices=[
                    SimpleNamespace(message=SimpleNamespace(content=response_message))
                ],
            )
        )
        assistant = SmolVLM2LocalAI(
            checkpointPath="/models/smolvlm2.gguf", **self.contexts
        )

        result = json.loads(
            assistant.respond(
                "Annotate all request utterances made by participants in a new time axis"
            )
        )

        self.assertEqual(result["steps"][0]["action"], "addAxi")
        self.assertEqual(result["steps"][1]["action"], "addBlock")
        self.assertEqual(
            result["steps"][0]["parameters"]["axisId"],
            result["steps"][1]["parameters"]["axisId"],
        )
        self.assertNotEqual(result["steps"][0]["parameters"]["axisId"], 1)

    @patch("rosbag_processing.ai_assistant.OpenAI")
    def test_short_request_annotation_uses_candidate_fallback(self, openai_class):
        openai_class.return_value.chat.completions.create.return_value = (
            SimpleNamespace(
                model="SmolVLM2-500M-Video-Instruct-Q8_0",
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(
                            content=json.dumps(
                                {
                                    "type": "instruction",
                                    "steps": [
                                        {
                                            "action": "addBlock",
                                            "parameters": {
                                                "axisId": 1,
                                                "blockIndex": 1,
                                            },
                                        },
                                        {
                                            "action": "deleteAxi",
                                            "parameters": {"axisId": 1},
                                        },
                                    ],
                                }
                            )
                        )
                    )
                ],
            )
        )
        contexts = {
            **self.contexts,
            "transcriptContext": (
                "[00:07] Speaker: Could you move the camera closer? [00:09]"
            ),
        }
        assistant = SmolVLM2LocalAI(
            checkpointPath="/models/smolvlm2.gguf", **contexts
        )

        result = json.loads(
            assistant.respond(
                "Can you annotate all the request utterances made by participants "
                "in a new time axis?"
            )
        )

        self.assertEqual(
            [step["action"] for step in result["steps"]],
            ["addAxi", "addBlock"],
        )
        self.assertEqual(result["steps"][1]["parameters"]["start"], 7.0)
        self.assertEqual(result["steps"][1]["parameters"]["end"], 9.0)

    @patch("rosbag_processing.ai_assistant.OpenAI")
    def test_local_auto_annotation_grounds_blocks_to_transcript_times(
        self, openai_class
    ):
        response_message = json.dumps(
            {
                "type": "instruction",
                "steps": [
                    {
                        "action": "addAxi",
                        "parameters": {
                            "axisId": 1,
                            "axisName": "Requests",
                            "axistype": "Type-in",
                        },
                    },
                    {
                        "action": "addBlock",
                        "parameters": {
                            "axisId": 1,
                            "start": 0,
                            "end": 0,
                            "text": "Could you move the camera closer?",
                        },
                    },
                ],
            }
        )
        openai_class.return_value.chat.completions.create.return_value = (
            SimpleNamespace(
                model="qwen2.5-0.5b-instruct",
                choices=[
                    SimpleNamespace(message=SimpleNamespace(content=response_message))
                ],
            )
        )
        contexts = {
            **self.contexts,
            "transcriptContext": (
                "[00:07] Speaker SPEAKER_00: Could you move the camera closer? "
                "[00:09]"
            ),
        }
        assistant = QwenLocalAI(checkpointPath="/models/local.gguf", **contexts)

        result = json.loads(
            assistant.respond(
                "Annotate all participant speech according to the codebook in a new axis"
            )
        )

        block = result["steps"][1]["parameters"]
        self.assertEqual(block["start"], 7.0)
        self.assertEqual(block["end"], 9.0)

    @patch("rosbag_processing.ai_assistant.OpenAI")
    def test_long_auto_annotation_is_chunked_and_merged(self, openai_class):
        transcript_lines = [
            f"[00:{index:02d}] Speaker: {'word ' * 120}request {index}? "
            f"[00:{index + 1:02d}]"
            for index in range(7)
        ]
        responses = [
            {
                "annotations": [
                    {"segmentId": 0, "label": "request"},
                ]
            },
            {
                "annotations": [
                    {"segmentId": 6, "label": "request"},
                ]
            },
        ]
        openai_class.return_value.chat.completions.create.side_effect = [
            SimpleNamespace(
                model="qwen2.5-0.5b-instruct",
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(content=json.dumps(response))
                    )
                ],
            )
            for response in responses
        ]
        contexts = {**self.contexts, "transcriptContext": "\n".join(transcript_lines)}
        assistant = QwenLocalAI(checkpointPath="/models/local.gguf", **contexts)

        result = json.loads(
            assistant.respond(
                "Annotate all participant speech according to the codebook in a new axis"
            )
        )

        self.assertEqual(
            [step["action"] for step in result["steps"]],
            ["addAxi", "addBlock", "addBlock"],
        )
        self.assertEqual(result["steps"][0]["parameters"]["axisId"], 2)
        self.assertEqual(result["steps"][1]["parameters"]["start"], 0.0)
        self.assertEqual(result["steps"][2]["parameters"]["start"], 6.0)
        self.assertEqual(
            assistant.get_run_metadata()["parameters"]["chunk_count"], 2
        )
        self.assertEqual(
            assistant.get_run_metadata()["parameters"]["max_tokens"], 256
        )
        self.assertEqual(
            openai_class.return_value.chat.completions.create.call_count, 2
        )

    @patch("rosbag_processing.ai_assistant.OpenAI")
    def test_request_annotation_falls_back_to_prefiltered_candidates(
        self, openai_class
    ):
        openai_class.return_value.chat.completions.create.return_value = (
            SimpleNamespace(
                model="qwen2.5-0.5b-instruct",
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(
                            content=json.dumps({"annotations": []})
                        )
                    )
                ],
            )
        )
        contexts = {
            **self.contexts,
            "transcriptContext": (
                "[00:07] Speaker SPEAKER_00: Could you move the camera closer? "
                + ("context " * 600)
                + "[00:09]"
            ),
        }
        assistant = QwenLocalAI(checkpointPath="/models/local.gguf", **contexts)

        result = json.loads(
            assistant.respond(
                "Annotate all request utterances made by participants in a new axis"
            )
        )

        self.assertEqual(
            [step["action"] for step in result["steps"]],
            ["addAxi", "addBlock"],
        )
        self.assertEqual(result["steps"][1]["parameters"]["start"], 7.0)
        self.assertEqual(result["steps"][1]["parameters"]["end"], 9.0)

    def test_all_providers_use_parent_input_and_output_contract(self):
        class ExampleAssistant(AIAssistant):
            def _respond(self, message, chatHistory=""):
                return f"{message}|{chatHistory}"

        assistant = ExampleAssistant(**self.contexts)

        self.assertEqual(
            assistant.respond("new message", "existing history"),
            "new message|existing history",
        )
        self.assertNotIn("respond", ExampleAssistant.__dict__)


class GPTChatEndpointTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def test_endpoint_keeps_request_and_response_contract(self):
        from . import views

        views.gpt_history = ""
        views.video_frames = ["frame-1"]
        body = {
            "message": "Add an annotation",
            "audio_transcript": "Speaker 1: Hello",
            "Axeinfo": [{"axisId": 1}],
            "Codebook": ["Greeting"],
        }
        request = self.factory.post(
            "/api/gpt_chat/",
            data=json.dumps(body),
            content_type="application/json",
        )

        with patch.object(views, "openai_api_key", "test-key"), patch.object(
            views, "RemoteAPI"
        ) as remote_api:
            remote_api.return_value.respond.return_value = "unchanged response"
            response = views.gpt_chat(request)

        self.assertEqual(response.status_code, 200)
        response_data = json.loads(response.content)
        self.assertEqual(response_data["response"], "unchanged response")
        self.assertEqual(response_data["assistant_mode"], "remote")
        self.assertEqual(response_data["ai_record"]["model_selection"]["used"], "remote")
        self.assertEqual(response_data["ai_record"]["ai_response"], "unchanged response")
        remote_api.assert_called_once_with(
            transcriptContext="Speaker 1: Hello",
            frameContext=["frame-1"],
            codebookContext=["Greeting"],
            timelineContext=[{"axisId": 1}],
            APIKey="test-key",
        )
        remote_api.return_value.respond.assert_called_once_with(
            "Add an annotation", ""
        )
        self.assertEqual(
            views.gpt_history, "Add an annotationunchanged response"
        )
import os
import tempfile
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase
from rest_framework.test import APIClient

from .chunks import build_chunks, load_manifest, save_manifest
from .chunk_views import annotations_for_chunk
from .data_utils import configure_huggingface_compatibility, get_rosbag_duration


class GetRosbagDurationTests(SimpleTestCase):
    @patch('rosbag_processing.data_utils.Bag')
    def test_returns_duration_and_closes_bag(self, bag_class):
        bag = MagicMock()
        bag.get_start_time.return_value = 100.25
        bag.get_end_time.return_value = 460.75
        bag_class.return_value = bag

        duration = get_rosbag_duration('/tmp/example.bag')

        self.assertEqual(duration, 360.5)
        bag.close.assert_called_once_with()

    @patch('rosbag_processing.data_utils.Bag')
    def test_never_returns_negative_duration(self, bag_class):
        bag = MagicMock()
        bag.get_start_time.return_value = 20
        bag.get_end_time.return_value = 10
        bag_class.return_value = bag

        self.assertEqual(get_rosbag_duration('/tmp/example.bag'), 0.0)
        bag.close.assert_called_once_with()


class HuggingFaceCompatibilityTests(SimpleTestCase):
    @patch('rosbag_processing.data_utils.hf_hub_download')
    def test_maps_legacy_auth_argument_to_token(self, download_mock):
        configure_huggingface_compatibility()

        from pyannote.audio.core import pipeline as pipeline_module
        pipeline_module.hf_hub_download(
            'owner/model', 'config.yaml', use_auth_token='secret-token'
        )

        download_mock.assert_called_once_with(
            'owner/model', 'config.yaml', token='secret-token'
        )


class InspectInputApiTests(SimpleTestCase):
    def setUp(self):
        self.client = APIClient()
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.rosbag_directory_patch = patch(
            'rosbag_processing.views.ROSBAG_DATA_DIR',
            self.temporary_directory.name,
        )
        self.rosbag_directory_patch.start()

    def tearDown(self):
        self.rosbag_directory_patch.stop()
        self.temporary_directory.cleanup()

    def create_bag_file(self, filename='example.bag'):
        path = os.path.join(self.temporary_directory.name, filename)
        with open(path, 'wb'):
            pass
        return path

    @patch('rosbag_processing.views.get_rosbag_duration', return_value=3600.125)
    def test_returns_input_duration(self, get_duration):
        bag_path = self.create_bag_file()

        response = self.client.post(
            '/api/inputs/inspect/',
            {'bag_filename': 'example.bag'},
            format='json',
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, {
            'bag_filename': 'example.bag',
            'duration_seconds': 3600.125,
            'duration_minutes': 60.002,
            'supports_chunking': True,
        })
        get_duration.assert_called_once_with(bag_path)

    def test_rejects_path_traversal(self):
        response = self.client.post(
            '/api/inputs/inspect/',
            {'bag_filename': '../example.bag'},
            format='json',
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn('bag_filename', response.data)

    def test_returns_not_found_for_unknown_bag(self):
        response = self.client.post(
            '/api/inputs/inspect/',
            {'bag_filename': 'missing.bag'},
            format='json',
        )

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.data['error'], 'ROSBag file not found.')

    @patch(
        'rosbag_processing.views.get_rosbag_duration',
        side_effect=RuntimeError('invalid bag'),
    )
    def test_returns_bad_request_for_unreadable_bag(self, _get_duration):
        self.create_bag_file()

        response = self.client.post(
            '/api/inputs/inspect/',
            {'bag_filename': 'example.bag'},
            format='json',
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn('Unable to read ROSBag duration', response.data['error'])


class ChunkManifestTests(SimpleTestCase):
    def test_builds_navigation_and_short_final_chunk(self):
        chunks = build_chunks(610, 300)

        self.assertEqual(len(chunks), 3)
        self.assertEqual(chunks[0]['previous_index'], None)
        self.assertEqual(chunks[0]['next_index'], 1)
        self.assertEqual(chunks[2], {
            'index': 2,
            'start_seconds': 600.0,
            'end_seconds': 610.0,
            'duration_seconds': 10.0,
            'previous_index': 1,
            'next_index': None,
        })

    def test_rejects_invalid_numbers(self):
        for duration, size in ((0, 10), (10, 0), (float('nan'), 10), (True, 10)):
            with self.subTest(duration=duration, size=size):
                with self.assertRaises(ValueError):
                    build_chunks(duration, size)

    def test_persists_and_loads_manifest(self):
        with tempfile.TemporaryDirectory() as directory:
            saved = save_manifest(directory, 'example.bag', 60, 20)
            loaded = load_manifest(directory, saved['id'])

        self.assertEqual(loaded, saved)
        self.assertEqual(loaded['chunk_count'], 3)


class ChunkAnnotationTests(SimpleTestCase):
    def test_filters_clips_and_rebases_annotations(self):
        annotations = [{
            'id': 1,
            'axisType': 'Type-in',
            'axisName': 'Notes',
            'axisBooklistName': '',
            'annotationBlocks': [
                {'start': 290, 'end': 310, 'text': 'crosses start'},
                {'start': 320, 'end': 330, 'text': 'inside'},
                {'start': 590, 'end': 620, 'text': 'crosses end'},
                {'start': 700, 'end': 710, 'text': 'outside'},
            ],
        }]

        result = annotations_for_chunk(annotations, {
            'start_seconds': 300,
            'end_seconds': 600,
        })

        self.assertEqual(result[0]['annotationBlocks'], [
            {'start': 0, 'end': 10, 'text': 'crosses start'},
            {'start': 20, 'end': 30, 'text': 'inside'},
            {'start': 290, 'end': 300, 'text': 'crosses end'},
        ])


class ChunkApiTests(SimpleTestCase):
    def setUp(self):
        self.client = APIClient()
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.rosbag_directory = os.path.join(self.temporary_directory.name, 'bags')
        self.manifest_directory = os.path.join(self.temporary_directory.name, 'manifests')
        os.makedirs(self.rosbag_directory)
        with open(os.path.join(self.rosbag_directory, 'example.bag'), 'wb'):
            pass
        self.settings_patch = self.settings(
            ROSBAG_DATA_DIR=self.rosbag_directory,
            CHUNK_MANIFEST_DIR=self.manifest_directory,
        )
        self.settings_patch.enable()

    def tearDown(self):
        self.settings_patch.disable()
        self.temporary_directory.cleanup()

    @patch('rosbag_processing.chunk_views.read_duration', return_value=610)
    def test_creates_and_retrieves_chunk_manifest(self, _read_duration):
        response = self.client.post('/api/chunks/', {
            'bag_filename': 'example.bag',
            'chunking_enabled': True,
            'chunk_seconds': 300,
        }, format='json')

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data['chunk_count'], 3)
        manifest_id = response.data['id']
        chunk_response = self.client.get(f'/api/chunks/{manifest_id}/2/')
        self.assertEqual(chunk_response.status_code, 200)
        self.assertEqual(chunk_response.data['start_seconds'], 600.0)
        self.assertIsNone(chunk_response.data['next_index'])

    @patch('rosbag_processing.chunk_views.read_duration', return_value=610)
    def test_no_chunking_creates_one_full_input_chunk(self, _read_duration):
        response = self.client.post('/api/chunks/', {
            'bag_filename': 'example.bag',
            'chunking_enabled': False,
        }, format='json')

        self.assertEqual(response.status_code, 201)
        self.assertFalse(response.data['chunking_enabled'])
        self.assertEqual(response.data['chunk_count'], 1)
        self.assertEqual(response.data['chunks'][0]['end_seconds'], 610.0)

    @patch('rosbag_processing.chunk_views.read_duration', return_value=610)
    def test_rejects_chunk_size_equal_to_input(self, _read_duration):
        response = self.client.post('/api/chunks/', {
            'bag_filename': 'example.bag',
            'chunking_enabled': True,
            'chunk_seconds': 610,
        }, format='json')

        self.assertEqual(response.status_code, 400)

    @patch('rosbag_processing.chunk_views.process_chunk')
    def test_processes_selected_chunk(self, process_chunk_mock):
        manifest = save_manifest(
            self.manifest_directory, 'example.bag', 610, 300,
        )
        process_chunk_mock.return_value = {
            **manifest['chunks'][1],
            'video_path': 'chunks/id/0001/output.mp4',
            'status': 'ready',
        }

        response = self.client.post(f"/api/chunks/{manifest['id']}/1/process/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['index'], 1)
        self.assertEqual(response.data['status'], 'ready')
        process_chunk_mock.assert_called_once()

    @patch('rosbag_processing.chunk_views.process_chunk')
    def test_model_certificate_errors_explain_recovery(self, process_chunk_mock):
        import ssl
        from urllib.error import URLError
        from requests.exceptions import SSLError

        manifest = save_manifest(self.manifest_directory, 'example.bag', 610, 300)
        for error in (
            URLError(ssl.SSLCertVerificationError('certificate verify failed')),
            SSLError('certificate verify failed'),
        ):
            with self.subTest(error=type(error).__name__):
                process_chunk_mock.side_effect = error
                response = self.client.post(f"/api/chunks/{manifest['id']}/0/process/")
                self.assertEqual(response.status_code, 503)
                self.assertEqual(response.data['code'], 'model_download_tls_error')
                self.assertIn('CA certificate', response.data['error'])

    @patch('rosbag_processing.chunk_views.process_chunk')
    def test_unrelated_errors_do_not_report_certificate_failure(self, process_chunk_mock):
        manifest = save_manifest(self.manifest_directory, 'example.bag', 610, 300)
        process_chunk_mock.side_effect = ValueError('internal detail')
        response = self.client.post(f"/api/chunks/{manifest['id']}/0/process/")
        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.data, {'error': 'Unable to process chunk.'})

    def test_missing_remote_key_offers_local_without_starting_it(self):
        from . import views

        views.gpt_history = ""
        views.video_frames = ["frame-1"]
        request = self.factory.post(
            "/api/gpt_chat/",
            data=json.dumps(
                {
                    "message": "Add an annotation",
                    "audio_transcript": "Speaker 1: Hello",
                    "Axeinfo": [],
                    "Codebook": [],
                }
            ),
            content_type="application/json",
        )

        with patch.object(views, "openai_api_key", None), patch.object(
            views, "RemoteAPI"
        ) as remote_api, patch.object(views, "create_local_ai") as local_ai:
            response = views.gpt_chat(request)

        self.assertEqual(response.status_code, 503)
        response_data = json.loads(response.content)
        self.assertTrue(response_data["can_fallback_to_local"])
        self.assertEqual(response_data["assistant_mode"], "remote")
        remote_api.assert_not_called()
        local_ai.assert_not_called()

    def test_invalid_remote_key_offers_local_without_starting_it(self):
        from . import views

        views.gpt_history = ""
        views.video_frames = ["frame-1"]
        request = self.factory.post(
            "/api/gpt_chat/",
            data=json.dumps(
                {
                    "message": "Add an annotation",
                    "audio_transcript": "Speaker 1: Hello",
                    "Axeinfo": [],
                    "Codebook": [],
                }
            ),
            content_type="application/json",
        )

        with patch.object(views, "openai_api_key", "invalid-key"), patch.object(
            views, "RemoteAPI"
        ) as remote_api, patch.object(views, "create_local_ai") as local_ai:
            remote_api.return_value.respond.side_effect = RemoteAuthenticationError()
            response = views.gpt_chat(request)

        self.assertEqual(response.status_code, 503)
        response_data = json.loads(response.content)
        self.assertTrue(response_data["can_fallback_to_local"])
        local_ai.assert_not_called()

    def test_consented_remote_to_local_fallback_is_recorded(self):
        from . import views

        views.gpt_history = ""
        views.video_frames = ["frame-1"]
        request = self.factory.post(
            "/api/gpt_chat/",
            data=json.dumps(
                {
                    "message": "Retry locally",
                    "audio_transcript": "Speaker 1: Hello",
                    "Axeinfo": [],
                    "Codebook": [],
                    "assistant_mode": "local",
                    "context_routes": {
                        "transcript": "local",
                        "frames": "local",
                        "codebook": "local",
                        "timeline": "local",
                    },
                    "fallback_consent": {
                        "from": "remote",
                        "to": "local",
                        "user_consented": True,
                    },
                }
            ),
            content_type="application/json",
        )

        with patch.object(views, "RemoteAPI") as remote_api, patch.object(
            views, "create_local_ai"
        ) as local_ai:
            local_ai.return_value.respond.return_value = "local response"
            response = views.gpt_chat(request)

        self.assertEqual(response.status_code, 200)
        response_data = json.loads(response.content)
        self.assertEqual(response_data["assistant_mode"], "local")
        self.assertEqual(
            response_data["ai_record"]["model_selection"]["requested"], "remote"
        )
        self.assertEqual(
            response_data["ai_record"]["model_selection"]["used"], "local"
        )
        local_ai.return_value.respond.assert_called_once_with("Retry locally", "")
        remote_api.assert_not_called()

    def test_consented_local_to_remote_fallback_is_recorded(self):
        from . import views

        views.gpt_history = ""
        views.video_frames = ["frame-1"]
        request = self.factory.post(
            "/api/gpt_chat/",
            data=json.dumps(
                {
                    "message": "Use remote with permission",
                    "audio_transcript": "Speaker 1: Hello",
                    "Axeinfo": [],
                    "Codebook": [],
                    "assistant_mode": "remote",
                    "context_routes": {
                        "transcript": "remote",
                        "frames": "remote",
                        "codebook": "remote",
                        "timeline": "remote",
                    },
                    "fallback_consent": {
                        "from": "local",
                        "to": "remote",
                        "user_consented": True,
                    },
                }
            ),
            content_type="application/json",
        )

        with patch.object(views, "openai_api_key", "test-key"), patch.object(
            views, "RemoteAPI"
        ) as remote_api:
            remote_api.return_value.respond.return_value = "remote response"
            response = views.gpt_chat(request)

        record = json.loads(response.content)["ai_record"]
        self.assertEqual(record["model_selection"]["requested"], "local")
        self.assertEqual(record["model_selection"]["used"], "remote")

    def test_local_mode_never_calls_remote_api(self):
        from . import views

        views.gpt_history = ""
        views.video_frames = ["frame-1"]
        request = self.factory.post(
            "/api/gpt_chat/",
            data=json.dumps(
                {
                    "message": "Keep this local",
                    "audio_transcript": "Sensitive transcript",
                    "Axeinfo": [],
                    "Codebook": [],
                    "assistant_mode": "local",
                    "context_routes": {
                        "transcript": "local",
                        "frames": "local",
                        "codebook": "local",
                        "timeline": "local",
                    },
                }
            ),
            content_type="application/json",
        )

        with patch.object(views, "openai_api_key", "test-key"), patch.object(
            views, "RemoteAPI"
        ) as remote_api, patch.object(views, "create_local_ai") as local_ai:
            local_ai.return_value.respond.side_effect = LocalInferenceError()
            response = views.gpt_chat(request)

        self.assertEqual(response.status_code, 501)
        self.assertIn("local language model is not connected", response.content.decode())
        self.assertTrue(json.loads(response.content)["can_fallback_to_remote"])
        remote_api.assert_not_called()

    def test_local_mode_does_not_offer_remote_without_api_key(self):
        from . import views

        views.gpt_history = ""
        views.video_frames = ["frame-1"]
        request = self.factory.post(
            "/api/gpt_chat/",
            data=json.dumps(
                {
                    "message": "Keep this local",
                    "audio_transcript": "Sensitive transcript",
                    "Axeinfo": [],
                    "Codebook": [],
                    "assistant_mode": "local",
                    "context_routes": {
                        "transcript": "local",
                        "frames": "local",
                        "codebook": "local",
                        "timeline": "local",
                    },
                }
            ),
            content_type="application/json",
        )

        with patch.object(views, "openai_api_key", None), patch.object(
            views, "create_local_ai"
        ) as local_ai:
            local_ai.return_value.respond.side_effect = LocalInferenceError()
            response = views.gpt_chat(request)

        self.assertEqual(response.status_code, 501)
        self.assertFalse(json.loads(response.content)["can_fallback_to_remote"])

    def test_mixed_hybrid_mode_never_calls_remote_until_orchestrator_exists(self):
        from . import views

        views.gpt_history = ""
        views.video_frames = ["frame-1"]
        request = self.factory.post(
            "/api/gpt_chat/",
            data=json.dumps(
                {
                    "message": "Use hybrid routing",
                    "audio_transcript": "Sensitive transcript",
                    "Axeinfo": [],
                    "Codebook": [],
                    "assistant_mode": "hybrid",
                    "context_routes": {
                        "transcript": "local",
                        "frames": "local",
                        "codebook": "remote",
                        "timeline": "remote",
                    },
                }
            ),
            content_type="application/json",
        )

        with patch.object(views, "openai_api_key", "test-key"), patch.object(
            views, "RemoteAPI"
        ) as remote_api:
            response = views.gpt_chat(request)

        self.assertEqual(response.status_code, 501)
        self.assertIn("Mixed Local/Remote", response.content.decode())
        remote_api.assert_not_called()

    def test_mixed_hybrid_routes_explain_empty_remote_api_key(self):
        from . import views

        request = self.factory.post(
            "/api/gpt_chat/",
            data=json.dumps(
                {
                    "message": "Use hybrid routing",
                    "audio_transcript": "Speaker 1: Hello",
                    "assistant_mode": "hybrid",
                    "context_routes": {
                        "transcript": "local",
                        "frames": "local",
                        "codebook": "remote",
                        "timeline": "remote",
                    },
                }
            ),
            content_type="application/json",
        )

        with patch.object(views, "openai_api_key", None):
            response = views.gpt_chat(request)

        self.assertEqual(response.status_code, 503)
        self.assertIn("API key is empty", response.content.decode())

    def test_all_local_hybrid_routes_use_local_model(self):
        from . import views

        views.gpt_history = ""
        views.video_frames = ["frame-1"]
        request = self.factory.post(
            "/api/gpt_chat/",
            data=json.dumps(
                {
                    "message": "Use local routing",
                    "audio_transcript": "Speaker 1: Hello",
                    "Axeinfo": [],
                    "Codebook": [],
                    "assistant_mode": "hybrid",
                    "context_routes": {
                        "transcript": "local",
                        "frames": "local",
                        "codebook": "local",
                        "timeline": "local",
                    },
                }
            ),
            content_type="application/json",
        )

        with patch.object(views, "RemoteAPI") as remote_api, patch.object(
            views, "create_local_ai"
        ) as local_ai:
            local_ai.return_value.respond.return_value = "local response"
            response = views.gpt_chat(request)

        response_data = json.loads(response.content)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response_data["response"], "local response")
        self.assertEqual(response_data["assistant_mode"], "local")
        self.assertEqual(
            response_data["ai_record"]["model_selection"]["requested"], "hybrid"
        )
        self.assertEqual(
            response_data["ai_record"]["model_selection"]["used"], "local"
        )
        remote_api.assert_not_called()
        local_ai.return_value.respond.assert_called_once_with("Use local routing", "")

    def test_all_local_hybrid_routes_explain_local_model_setup_failure(self):
        from . import views

        views.gpt_history = ""
        request = self.factory.post(
            "/api/gpt_chat/",
            data=json.dumps(
                {
                    "message": "Use local routing",
                    "audio_transcript": "Speaker 1: Hello",
                    "assistant_mode": "hybrid",
                    "context_routes": {
                        "transcript": "local",
                        "frames": "local",
                        "codebook": "local",
                        "timeline": "local",
                    },
                }
            ),
            content_type="application/json",
        )

        with patch.object(views, "openai_api_key", None), patch.object(
            views, "create_local_ai"
        ) as local_ai:
            local_ai.return_value.respond.side_effect = LocalInferenceError()
            response = views.gpt_chat(request)

        self.assertEqual(response.status_code, 501)
        self.assertIn("Choose a local model", response.content.decode())
        self.assertIn("models/ directory", response.content.decode())

    def test_all_remote_hybrid_routes_explain_empty_api_key(self):
        from . import views

        views.gpt_history = ""
        request = self.factory.post(
            "/api/gpt_chat/",
            data=json.dumps(
                {
                    "message": "Use remote routing",
                    "audio_transcript": "Speaker 1: Hello",
                    "assistant_mode": "hybrid",
                    "context_routes": {
                        "transcript": "remote",
                        "frames": "remote",
                        "codebook": "remote",
                        "timeline": "remote",
                    },
                }
            ),
            content_type="application/json",
        )

        with patch.object(views, "openai_api_key", None), patch.object(
            views, "RemoteAPI"
        ) as remote_api:
            response = views.gpt_chat(request)

        self.assertEqual(response.status_code, 503)
        self.assertIn("API key is empty", response.content.decode())
        remote_api.assert_not_called()

    def test_all_remote_hybrid_routes_explain_invalid_api_key(self):
        from . import views

        views.gpt_history = ""
        request = self.factory.post(
            "/api/gpt_chat/",
            data=json.dumps(
                {
                    "message": "Use remote routing",
                    "audio_transcript": "Speaker 1: Hello",
                    "assistant_mode": "hybrid",
                    "context_routes": {
                        "transcript": "remote",
                        "frames": "remote",
                        "codebook": "remote",
                        "timeline": "remote",
                    },
                }
            ),
            content_type="application/json",
        )

        with patch.object(views, "openai_api_key", "invalid-key"), patch.object(
            views, "RemoteAPI"
        ) as remote_api:
            remote_api.return_value.respond.side_effect = RemoteAuthenticationError()
            response = views.gpt_chat(request)

        self.assertEqual(response.status_code, 503)
        self.assertIn("API key is invalid", response.content.decode())


class AIRecordPersistenceTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def test_save_annotation_writes_named_ai_records_sidecar(self):
        from . import views

        ai_record = {
            "schema_version": 1,
            "run_id": "run-1",
            "ai_response": "Done",
        }
        request = self.factory.post(
            "/api/save_annotation/",
            data=json.dumps(
                {
                    "annotation_name": "recording.bag+booklist.json",
                    "annotation_data": [],
                    "ai_records": [ai_record],
                }
            ),
            content_type="application/json",
        )

        with TemporaryDirectory() as temp_directory, patch.object(
            views, "ANNOTATION_PATH", temp_directory
        ):
            response = views.save_annotation(request)
            sidecar_path = Path(temp_directory) / (
                "ai_records_recording.bag+booklist.json.json"
            )
            saved_payload = json.loads(sidecar_path.read_text())

        self.assertEqual(response.status_code, 200)
        self.assertEqual(saved_payload["schema_version"], 1)
        self.assertEqual(saved_payload["ai_runs"], [ai_record])

    def test_load_ai_records_is_backward_compatible_without_sidecar(self):
        from . import views

        with TemporaryDirectory() as temp_directory, patch.object(
            views, "ANNOTATION_PATH", temp_directory
        ):
            self.assertEqual(views.load_ai_records("old-annotation.csv"), [])


class LMPipelineAcceptanceTests(SimpleTestCase):
    """Focused acceptance tests for provider routing without real inference."""

    def setUp(self):
        self.factory = RequestFactory()

    def make_request(self, **overrides):
        body = {
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
        from . import views

        views.gpt_history = ""
        views.video_frames = ["private-frame"]
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
        from . import views

        views.gpt_history = "existing history"
        views.video_frames = ["private-frame"]
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
        self.assertEqual(views.gpt_history, "existing history")
        remote_api.assert_not_called()

    def test_remote_timeout_does_not_start_local_automatically(self):
        '''remote API timeout or unreachable shows failure message and offer local fallback; fallback does not start automatically'''
        from . import views

        views.gpt_history = ""
        views.video_frames = ["frame-1"]
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
        self.assertEqual(views.gpt_history, "")

    def test_multiline_unicode_prompt_round_trips_through_request_and_record(self):
        '''multiline prompt or unicode prompt preserves content without breaking request serialization or audit records.'''
        from . import views

        message = "First line\n第二行：café 🤖"
        response_text = "完成\nResult preserved ✅"
        views.gpt_history = ""
        views.video_frames = []
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
        from . import views

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

    def test_invalid_hybrid_routes_call_no_provider(self):
        '''split a batch between local and remote, local only data never appears in remote request'''
        from . import views

        request = self.make_request(
            assistant_mode="hybrid",
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
            json.loads(response.content), {"error": "Invalid hybrid context routes"}
        )
        remote_api.assert_not_called()
        local_ai.assert_not_called()
