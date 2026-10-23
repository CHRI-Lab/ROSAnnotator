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
    RemoteResponseError,
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
        response_message = json.dumps({"type": "instruction", "steps": [
            {"action": "addBlock", "parameters": {"axisId": 1, "start": 0, "end": 1, "text": "Greeting"}}
        ]})
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
    def test_remote_rejects_malformed_timeline_json(self, openai_class):
        openai_class.return_value.chat.completions.create.return_value = (
            SimpleNamespace(
                model="gpt-4o",
                choices=[SimpleNamespace(message=SimpleNamespace(content="{bad json"))],
            )
        )
        assistant = RemoteAPI(APIKey="test-key", **self.contexts)

        with self.assertRaisesRegex(RemoteResponseError, "No annotation changes"):
            assistant.respond("Create an annotation axis")

    @patch("rosbag_processing.ai_assistant.OpenAI")
    def test_remote_rejects_unsupported_timeline_action(self, openai_class):
        response_message = json.dumps(
            {
                "type": "instruction",
                "steps": [{"action": "runShell", "parameters": {}}],
            }
        )
        openai_class.return_value.chat.completions.create.return_value = (
            SimpleNamespace(
                model="gpt-4o",
                choices=[
                    SimpleNamespace(message=SimpleNamespace(content=response_message))
                ],
            )
        )
        assistant = RemoteAPI(APIKey="test-key", **self.contexts)

        with self.assertRaisesRegex(RemoteResponseError, "invalid timeline"):
            assistant.respond("Create an annotation axis")

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
    def test_local_manual_block_resolves_named_axis_and_point_time(self, openai_class):
        response_message = json.dumps(
            {
                "type": "instruction",
                "steps": [
                    {
                        "action": "addAxi",
                        "parameters": {
                            "axisId": 99,
                            "axisName": "Topics",
                            "axistype": "Type-in",
                        },
                    },
                    {
                        "action": "addBlock",
                        "parameters": {"axisId": 99},
                    },
                ],
            }
        )
        openai_class.return_value.chat.completions.create.return_value = (
            SimpleNamespace(
                model="qwen2.5-0.5b-instruct-q4_k_m",
                choices=[
                    SimpleNamespace(message=SimpleNamespace(content=response_message))
                ],
            )
        )
        assistant = QwenLocalAI(checkpointPath="/models/local.gguf", **self.contexts)

        result = json.loads(
            assistant.respond("Add a new block at 1s on axis Topics")
        )

        self.assertEqual(len(result["steps"]), 1)
        self.assertEqual(result["steps"][0]["action"], "addBlock")
        self.assertEqual(
            result["steps"][0]["parameters"],
            {
                "axisId": 1,
                "start": 1.0,
                "end": 2.0,
                "text": "New annotation",
            },
        )

    @patch("rosbag_processing.ai_assistant.OpenAI")
    def test_local_delete_block_resolves_named_axis_and_time(self, openai_class):
        response_message = json.dumps(
            {
                "type": "instruction",
                "steps": [
                    {
                        "action": "deleteBlock",
                        "parameters": {"axisId": 99},
                    }
                ],
            }
        )
        openai_class.return_value.chat.completions.create.return_value = (
            SimpleNamespace(
                model="qwen2.5-0.5b-instruct-q4_k_m",
                choices=[
                    SimpleNamespace(message=SimpleNamespace(content=response_message))
                ],
            )
        )
        contexts = {
            **self.contexts,
            "timelineContext": [
                {
                    "id": 7,
                    "axisName": "Participant Requests",
                    "blocks": [
                        {"start": 1.0, "end": 2.0, "text": "New annotation"}
                    ],
                }
            ],
        }
        assistant = QwenLocalAI(checkpointPath="/models/local.gguf", **contexts)

        result = json.loads(
            assistant.respond("Delete block at 1s on axis participant requests")
        )

        self.assertEqual(
            result["steps"],
            [
                {
                    "action": "deleteBlock",
                    "parameters": {"axisId": 7, "blockIndex": 0},
                }
            ],
        )

    @patch("rosbag_processing.ai_assistant.OpenAI")
    def test_local_delete_block_uses_full_index_from_filtered_context(
        self, openai_class
    ):
        response_message = json.dumps(
            {
                "type": "instruction",
                "steps": [
                    {
                        "action": "deleteBlock",
                        "parameters": {"axisId": 99, "blockIndex": 0},
                    }
                ],
            }
        )
        openai_class.return_value.chat.completions.create.return_value = (
            SimpleNamespace(
                model="qwen2.5-0.5b-instruct-q4_k_m",
                choices=[
                    SimpleNamespace(message=SimpleNamespace(content=response_message))
                ],
            )
        )
        contexts = {
            **self.contexts,
            "timelineContext": [
                {
                    "id": 7,
                    "axisName": "Participant Requests",
                    "blocks": [
                        {
                            "start": 12.0,
                            "end": 14.0,
                            "text": "Selected annotation",
                            "blockIndex": 1,
                        }
                    ],
                }
            ],
        }
        assistant = QwenLocalAI(checkpointPath="/models/local.gguf", **contexts)

        result = json.loads(
            assistant.respond("Delete block at 12s on axis participant requests")
        )

        self.assertEqual(result["steps"][0]["parameters"]["blockIndex"], 1)

    def test_repeated_auto_annotation_reuses_axis_and_skips_existing_blocks(self):
        contexts = {
            **self.contexts,
            "timelineContext": [
                {
                    "id": 7,
                    "axisName": "Participant Requests",
                    "blocks": [
                        {"start": 7.0, "end": 9.0, "text": "First request"}
                    ],
                }
            ],
        }
        assistant = QwenLocalAI(checkpointPath="/models/local.gguf", **contexts)
        response = json.dumps(
            {
                "type": "instruction",
                "steps": [
                    {
                        "action": "addAxi",
                        "parameters": {
                            "axisId": 8,
                            "axisName": "Participant Requests",
                            "axistype": "Type-in",
                        },
                    },
                    {
                        "action": "addBlock",
                        "parameters": {
                            "axisId": 8,
                            "start": 7.0,
                            "end": 9.0,
                            "text": "First request",
                        },
                    },
                    {
                        "action": "addBlock",
                        "parameters": {
                            "axisId": 8,
                            "start": 10.0,
                            "end": 11.0,
                            "text": "Another request",
                        },
                    },
                ],
            }
        )

        result = json.loads(
            assistant._normalize_timeline_instruction(
                response,
                "Can you annotate all the request utterances made by participants "
                "in a new time axis?",
                requires_new_axis=True,
            )
        )

        self.assertEqual(
            result["steps"],
            [
                {
                    "action": "addBlock",
                    "parameters": {
                        "axisId": 7,
                        "start": 10.0,
                        "end": 11.0,
                        "text": "Another request",
                    },
                }
            ],
        )

    @patch("rosbag_processing.ai_assistant.OpenAI")
    def test_timestamped_request_annotation_only_adds_requested_segment(
        self, openai_class
    ):
        openai_class.return_value.chat.completions.create.return_value = (
            SimpleNamespace(
                model="qwen2.5-0.5b-instruct-q4_k_m",
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(content='{"annotations": []}')
                    )
                ],
            )
        )
        timeline = [
            {
                "id": 7,
                "axisName": "Participant Requests",
                "blocks": [
                    {"start": 229.0, "end": 236.0, "text": "Existing request"}
                ],
            }
        ]
        cases = (
            (
                "Can you annotate at 239s the request utterances made by "
                "participants in a new time axis?",
                "[03:58] Speaker: Could you pass that to me? [04:01]",
                238.0,
                241.0,
            ),
            (
                "Can you annotate the request utterances made by participants "
                "309s in a new time axis?",
                "[05:08] Speaker: Please rotate the object. [05:10]",
                308.0,
                310.0,
            ),
        )

        for message, target_segment, expected_start, expected_end in cases:
            with self.subTest(message=message):
                contexts = {
                    **self.contexts,
                    "timelineContext": timeline,
                    "transcriptContext": (
                        "[03:49] Speaker: Can you turn it again? [03:56]\n"
                        f"{target_segment}"
                    ),
                }
                assistant = QwenLocalAI(
                    checkpointPath="/models/local.gguf", **contexts
                )

                result = json.loads(assistant.respond(message))

                self.assertEqual(len(result["steps"]), 1)
                self.assertEqual(result["steps"][0]["action"], "addBlock")
                self.assertEqual(result["steps"][0]["parameters"]["axisId"], 7)
                self.assertEqual(
                    result["steps"][0]["parameters"]["start"], expected_start
                )
                self.assertEqual(
                    result["steps"][0]["parameters"]["end"], expected_end
                )

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

    def test_selected_video_frames_are_used_instead_of_global_frames(self):
        from . import views

        views.video_frames = ["unrelated-frame"]
        request = self.factory.post(
            "/api/gpt_chat/",
            data=json.dumps({
                "message": "Describe this chunk",
                "audio_transcript": "Speaker 1: Hello",
                "Axeinfo": [],
                "Codebook": [],
                "video_path": "chunks/selected/0000/output.mp4",
            }),
            content_type="application/json",
        )
        with patch.object(views, "frames_for_video", return_value=["selected-frame"]) as sample, \
             patch.object(views, "openai_api_key", "test-key"), \
             patch.object(views, "RemoteAPI") as remote_api:
            remote_api.return_value.respond.return_value = "description"
            response = views.gpt_chat(request)

        self.assertEqual(response.status_code, 200)
        sample.assert_called_once_with("chunks/selected/0000/output.mp4")
        self.assertEqual(remote_api.call_args.kwargs["frameContext"], ["selected-frame"])

    def test_video_path_cannot_escape_processed_directory(self):
        from . import views

        with self.assertRaisesRegex(ValueError, "Selected video was not found"):
            views.frames_for_video("../secret.mp4")

    def test_clear_history_removes_backend_context(self):
        from . import views

        views.gpt_history = "private prior conversation"
        previous_generation = views.gpt_history_generation
        request = self.factory.post("/api/gpt_chat/clear/")

        response = views.clear_gpt_history(request)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(json.loads(response.content), {"cleared": True})
        self.assertEqual(views.gpt_history, "")
        self.assertEqual(views.gpt_history_generation, previous_generation + 1)

    def test_endpoint_keeps_request_and_response_contract(self):
        from . import views

        views.cache.set('chat:test-context', {'history': "", 'frames': []})
        views.cache.set('chat:test-context', {**views.cache.get('chat:test-context'), 'frames': ["frame-1"]})
        body = {
            "chat_context_id": "test-context",
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
            views.cache.get('chat:test-context')['history'], "Add an annotationunchanged response"
        )
import os
import tempfile
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase
from rest_framework.test import APIClient

from .chunks import build_chunks, load_manifest, save_manifest
from .view_metadata import annotations_for_chunk
from .data_utils import get_rosbag_duration


class ProcessingSessionApiTests(SimpleTestCase):
    @patch('rosbag_processing.rosbag_session.RosbagProcessingSession')
    def test_whole_bag_adapter_preserves_request_and_response(self, session_class):
        session = session_class.return_value
        session.video_frames = []
        session.video_fps = 25
        result = {
            'video_path': 'sample.bag/output.mp4',
            'audio_path': 'sample.bag/audio.mp3',
            'waveform_image_path': 'sample.bag/output_waveform.png',
            'audio_transcript': '', 'speaker_data': [],
            'booklist_data': {}, 'annotation_data': None,
            'message': 'File already processed',
        }
        session.process.return_value = result
        response = APIClient().post('/api/process_rosbag/', {
            'bag_filename': 'sample.bag', 'booklist_filename': 'codes.json',
            'annotation_filename': 'annotations.csv',
        }, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, result)
        request = session.process.call_args.args[0]
        self.assertEqual(request.bag_path, os.path.join('/app/datas/rosbag-data/', 'sample.bag'))
        self.assertEqual(request.booklist_filename, 'codes.json')
        self.assertEqual(request.annotation_filename, 'annotations.csv')

    @patch('rosbag_processing.rosbag_session.RosbagProcessingSession')
    def test_expected_processing_error_keeps_legacy_http_shape(self, session_class):
        from .processing_sessions import ProcessingError
        session_class.return_value.process.side_effect = ProcessingError('Invalid bag filename')
        response = APIClient().post('/api/process_rosbag/', {'bag_filename': 'missing.bag'}, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data, {'error': 'Invalid bag filename'})

    @patch('rosbag_processing.rosbag_session.RosbagProcessingSession')
    def test_missing_filename_does_not_start_a_session(self, session_class):
        response = APIClient().post('/api/process_rosbag/', {}, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data, {'error': 'bag_filename is required'})
        session_class.assert_not_called()


class GetRosbagDurationTests(SimpleTestCase):
    @patch('rosbag_processing.rosbag_reader.RosbagReader')
    def test_returns_duration_through_shared_reader(self, reader_class):
        reader_class.return_value.__enter__.return_value.duration = 360.5
        self.assertEqual(get_rosbag_duration('/tmp/example.bag'), 360.5)
        reader_class.assert_called_once_with('/tmp/example.bag')
        reader_class.return_value.__exit__.assert_called_once()

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

    @patch('rosbag_processing.rosbag_reader.RosbagReader')
    def test_returns_input_duration(self, get_duration):
        get_duration.return_value.__enter__.return_value.duration = 3600.125
        get_duration.return_value.__enter__.return_value.topics = {}
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
            'topics': [],
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
        'rosbag_processing.rosbag_reader.RosbagReader',
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
            {'start': 0, 'end': 10, 'text': 'crosses start',
             'sourceStart': 290, 'sourceEnd': 310},
            {'start': 20, 'end': 30, 'text': 'inside'},
            {'start': 290, 'end': 300, 'text': 'crosses end',
             'sourceStart': 590, 'sourceEnd': 620},
        ])

class ChunkMergeTests(SimpleTestCase):
    """merge_chunk_annotations: chunk-local in, whole-recording time out."""

    chunk = {'index': 1, 'start_seconds': 300, 'end_seconds': 600}

    @staticmethod
    def axis(blocks):
        return [{
            'id': 1,
            'axisType': 'Type-in',
            'axisName': 'Notes',
            'axisBooklistName': '',
            'annotationBlocks': blocks,
        }]

    def merge(self, existing, incoming):
        from .views import merge_chunk_annotations
        return merge_chunk_annotations(
            existing, incoming, self.chunk,
        )[0]['annotationBlocks']

    def test_text_only_edit_is_preserved(self):
        """Editing only a block's text must not be treated as unedited."""
        existing = self.axis([{'start': 320, 'end': 330, 'text': 'before'}])
        incoming = self.axis([{'start': 20, 'end': 30, 'text': 'after'}])

        blocks = self.merge(existing, incoming)

        self.assertEqual(len(blocks), 1)
        self.assertEqual(blocks[0]['text'], 'after')
        self.assertEqual(blocks[0]['start'], 320)
        self.assertEqual(blocks[0]['end'], 330)

    def test_unedited_round_trip_is_exact(self):
        """Loading a chunk and saving it back unchanged must not alter the file."""
        existing = self.axis([
            {'start': 290, 'end': 310, 'text': 'crosses start'},
            {'start': 320, 'end': 330, 'text': 'inside'},
            {'start': 700, 'end': 710, 'text': 'outside'},
        ])
        incoming = self.axis([
            {'start': 0, 'end': 10, 'text': 'crosses start'},
            {'start': 20, 'end': 30, 'text': 'inside'},
        ])

        blocks = self.merge(existing, incoming)

        self.assertEqual(blocks, existing[0]['annotationBlocks'])

    def test_editing_clipped_block_preserves_its_hidden_part(self):
        existing = self.axis([
            {'start': 290, 'end': 310, 'text': 'before'},
            {'start': 590, 'end': 620, 'text': 'before'},
        ])
        incoming = self.axis([
            {'start': 0, 'end': 8, 'text': 'left edited',
             'sourceStart': 290, 'sourceEnd': 310},
            {'start': 292, 'end': 300, 'text': 'right edited',
             'sourceStart': 590, 'sourceEnd': 620},
        ])

        blocks = self.merge(existing, incoming)

        self.assertEqual(blocks, [
            {'start': 290, 'end': 308, 'text': 'left edited'},
            {'start': 592, 'end': 620, 'text': 'right edited'},
        ])

    def test_block_spanning_both_edges_remains_one_block(self):
        existing = self.axis([
            {'start': 290, 'end': 620, 'text': 'before'},
        ])
        incoming = self.axis([
            {'start': 0, 'end': 300, 'text': 'after',
             'sourceStart': 290, 'sourceEnd': 620},
        ])

        blocks = self.merge(existing, incoming)

        self.assertEqual(blocks, [
            {'start': 290, 'end': 620, 'text': 'after'},
        ])

    def test_blocks_outside_the_chunk_are_untouched(self):
        existing = self.axis([
            {'start': 100, 'end': 110, 'text': 'earlier chunk'},
            {'start': 320, 'end': 330, 'text': 'this chunk'},
        ])
        incoming = self.axis([{'start': 20, 'end': 30, 'text': 'edited'}])

        blocks = self.merge(existing, incoming)

        self.assertEqual(
            blocks[0], {'start': 100, 'end': 110, 'text': 'earlier chunk'},
        )
        self.assertEqual(blocks[1]['text'], 'edited')

    def test_deleted_block_does_not_return(self):
        existing = self.axis([{'start': 320, 'end': 330, 'text': 'delete me'}])

        blocks = self.merge(existing, self.axis([]))

        self.assertEqual(blocks, [])


class AnnotationBoundsTests(SimpleTestCase):
    def test_rejects_blocks_outside_timeline(self):
        from .views import annotation_bounds_error

        axis = lambda block: [{'annotationBlocks': [block]}]
        self.assertIsNotNone(annotation_bounds_error(
            axis({'start': -1, 'end': 2}), 10,
        ))
        self.assertIsNotNone(annotation_bounds_error(
            axis({'start': 8, 'end': 7}), 10,
        ))
        self.assertIsNotNone(annotation_bounds_error(
            axis({'start': 8, 'end': 11}), 10,
        ))

    def test_accepts_blocks_on_timeline_edges(self):
        from .views import annotation_bounds_error

        self.assertIsNone(annotation_bounds_error([{
            'annotationBlocks': [
                {'start': 0, 'end': 0},
                {'start': 8, 'end': 10},
            ],
        }], 10))


class ManifestIdentityTests(SimpleTestCase):
    """The manifest records the source fingerprint process_chunk_view checks."""

    def test_source_identity_is_stored_and_reloaded(self):
        from tempfile import TemporaryDirectory
        from .chunks import load_manifest, save_manifest

        with TemporaryDirectory() as directory:
            manifest = save_manifest(
                directory, 'sample.bag', 600.0, 300.0,
                source_size=1234, source_mtime_ns=5678,
            )
            reloaded = load_manifest(directory, manifest['id'])

        self.assertEqual(manifest['source_size'], 1234)
        self.assertEqual(manifest['source_mtime_ns'], 5678)
        self.assertEqual(reloaded['source_size'], 1234)
        self.assertEqual(reloaded['source_mtime_ns'], 5678)

    def test_same_inputs_give_the_same_id(self):
        from .chunks import manifest_id

        first = manifest_id('sample.bag', 300.0, True, 1234, 5678)
        second = manifest_id('sample.bag', 300, True, 1234, 5678)
        different_size = manifest_id('sample.bag', 60.0, True, 1234, 5678)

        self.assertEqual(first, second)
        self.assertNotEqual(first, different_size)

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

class AssistantRoutingEndpointTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def test_missing_remote_key_offers_local_without_starting_it(self):
        from . import views

        views.cache.set('chat:test-context', {'history': "", 'frames': []})
        views.cache.set('chat:test-context', {**views.cache.get('chat:test-context'), 'frames': ["frame-1"]})
        request = self.factory.post(
            "/api/gpt_chat/",
            data=json.dumps(
                {
                    "chat_context_id": "test-context",
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

        views.cache.set('chat:test-context', {'history': "", 'frames': []})
        views.cache.set('chat:test-context', {**views.cache.get('chat:test-context'), 'frames': ["frame-1"]})
        request = self.factory.post(
            "/api/gpt_chat/",
            data=json.dumps(
                {
                    "chat_context_id": "test-context",
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

    def test_invalid_remote_timeline_response_is_rejected_without_changes(self):
        from . import views

        views.cache.set('chat:test-context', {'history': "existing history", 'frames': []})
        request = self.factory.post(
            "/api/gpt_chat/",
            data=json.dumps(
                {
                    "chat_context_id": "test-context",
                    "message": "Create an annotation axis",
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
                }
            ),
            content_type="application/json",
        )

        with patch.object(views, "openai_api_key", "test-key"), patch.object(
            views, "RemoteAPI"
        ) as remote_api, patch.object(views, "create_local_ai") as local_ai:
            remote_api.return_value.respond.side_effect = RemoteResponseError(
                "The remote model returned an invalid timeline instruction. "
                "No annotation changes were applied."
            )
            response = views.gpt_chat(request)

        response_data = json.loads(response.content)
        self.assertEqual(response.status_code, 502)
        self.assertIn("No annotation changes were applied", response_data["error"])
        self.assertNotIn("can_fallback_to_local", response_data)
        self.assertEqual(views.cache.get('chat:test-context')['history'], "existing history")
        local_ai.assert_not_called()

    def test_consented_remote_to_local_fallback_is_recorded(self):
        from . import views

        views.cache.set('chat:test-context', {'history': "", 'frames': []})
        views.cache.set('chat:test-context', {**views.cache.get('chat:test-context'), 'frames': ["frame-1"]})
        request = self.factory.post(
            "/api/gpt_chat/",
            data=json.dumps(
                {
                    "chat_context_id": "test-context",
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

        views.cache.set('chat:test-context', {'history': "", 'frames': []})
        views.cache.set('chat:test-context', {**views.cache.get('chat:test-context'), 'frames': ["frame-1"]})
        request = self.factory.post(
            "/api/gpt_chat/",
            data=json.dumps(
                {
                    "chat_context_id": "test-context",
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

        views.cache.set('chat:test-context', {'history': "", 'frames': []})
        views.cache.set('chat:test-context', {**views.cache.get('chat:test-context'), 'frames': ["frame-1"]})
        request = self.factory.post(
            "/api/gpt_chat/",
            data=json.dumps(
                {
                    "chat_context_id": "test-context",
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

        views.cache.set('chat:test-context', {'history': "", 'frames': []})
        views.cache.set('chat:test-context', {**views.cache.get('chat:test-context'), 'frames': ["frame-1"]})
        request = self.factory.post(
            "/api/gpt_chat/",
            data=json.dumps(
                {
                    "chat_context_id": "test-context",
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

    def test_hybrid_mode_is_rejected_without_calling_a_provider(self):
        from . import views

        views.cache.set('chat:test-context', {'history': "", 'frames': []})
        views.cache.set('chat:test-context', {**views.cache.get('chat:test-context'), 'frames': ["frame-1"]})
        request = self.factory.post(
            "/api/gpt_chat/",
            data=json.dumps(
                {
                    "chat_context_id": "test-context",
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

        self.assertEqual(response.status_code, 400)
        self.assertEqual(json.loads(response.content), {"error": "Invalid assistant mode"})
        remote_api.assert_not_called()


class AIRecordPersistenceTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def test_completed_records_append_and_manual_save_does_not_overwrite_them(self):
        from . import views

        ai_record = {
            "schema_version": 1,
            "run_id": "run-1",
            "ai_response": "Done",
        }
        with TemporaryDirectory() as temp_directory, patch.object(
            views, "ANNOTATION_PATH", temp_directory
        ):
            completion = self.factory.post(
                "/api/ai_records/complete/",
                data=json.dumps({
                    "annotation_name": "recording.bag+booklist.json",
                    "ai_record": ai_record,
                    "outcome": "applied",
                }),
                content_type="application/json",
            )
            response = views.complete_ai_record(completion)
            retry_response = views.complete_ai_record(self.factory.post(
                "/api/ai_records/complete/",
                data=json.dumps({
                    "annotation_name": "recording.bag+booklist.json",
                    "ai_record": ai_record,
                    "outcome": "applied",
                }),
                content_type="application/json",
            ))
            manual_save = self.factory.post(
                "/api/save_annotation/",
                data=json.dumps({
                    "annotation_name": "recording.bag+booklist.json",
                    "annotation_data": [],
                    "ai_records": [],
                }),
                content_type="application/json",
            )
            save_response = views.save_annotation(manual_save)
            sidecar_path = Path(temp_directory) / (
                "ai_records_recording.bag+booklist.json.json"
            )
            saved_payload = json.loads(sidecar_path.read_text())

        self.assertEqual(response.status_code, 200)
        self.assertEqual(retry_response.status_code, 200)
        self.assertEqual(save_response.status_code, 200)
        self.assertEqual(saved_payload["schema_version"], 1)
        self.assertEqual(len(saved_payload["ai_runs"]), 1)
        self.assertEqual(saved_payload["ai_runs"][0]["run_id"], "run-1")
        self.assertEqual(saved_payload["ai_runs"][0]["action_outcome"], "applied")

    def test_rejected_action_is_saved_with_rejected_outcome(self):
        from . import views

        with TemporaryDirectory() as temp_directory, patch.object(
            views, "ANNOTATION_PATH", temp_directory
        ):
            request = self.factory.post(
                "/api/ai_records/complete/",
                data=json.dumps({
                    "annotation_name": "recording.bag+noBookList",
                    "ai_record": {"run_id": "rejected-run", "ai_response": "instruction"},
                    "outcome": "rejected",
                }),
                content_type="application/json",
            )
            response = views.complete_ai_record(request)
            records = views.load_ai_records("recording.bag+noBookList.csv")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(records[0]["action_outcome"], "rejected")

    def test_load_ai_records_is_backward_compatible_without_sidecar(self):
        from . import views

        with TemporaryDirectory() as temp_directory, patch.object(
            views, "ANNOTATION_PATH", temp_directory
        ):
            self.assertEqual(views.load_ai_records("old-annotation.csv"), [])

    def test_manifest_records_accumulate_and_keep_chunks_separate(self):
        from . import views

        manifest_id = "550e8400-e29b-41d4-a716-446655440000"
        other_manifest_id = "550e8400-e29b-41d4-a716-446655440001"
        with TemporaryDirectory() as temp_directory, patch.object(
            views, "ANNOTATION_PATH", temp_directory
        ):
            for run_id, chunk_index, identifier in (
                ("first", 0, manifest_id),
                ("second", 0, manifest_id),
                ("other-chunk", 1, manifest_id),
                ("other-manifest", 0, other_manifest_id),
            ):
                request = self.factory.post(
                    "/api/ai_records/complete/",
                    data=json.dumps({
                        "annotation_name": "recording.bag+noBookList",
                        "manifest_id": identifier,
                        "chunk_index": chunk_index,
                        "ai_record": {"run_id": run_id},
                        "outcome": "replied",
                    }),
                    content_type="application/json",
                )
                self.assertEqual(views.complete_ai_record(request).status_code, 200)

            path = Path(temp_directory) / f"ai_records_recording.bag+noBookList_{manifest_id}.json"
            self.assertTrue(path.is_file())
            self.assertEqual(
                [record["run_id"] for record in views.load_ai_records(
                    "recording.bag+noBookList", manifest_id, 0
                )],
                ["first", "second"],
            )
            self.assertEqual(len(views.load_ai_records("recording.bag+noBookList", manifest_id)), 3)
            self.assertEqual(len(views.load_ai_records("recording.bag+noBookList", other_manifest_id)), 1)
