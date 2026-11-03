"""Acceptance coverage for fine-grained AI request selections in both modes."""

import json
from types import SimpleNamespace
from unittest.mock import patch

from django.core.cache import cache
from django.test import RequestFactory, SimpleTestCase

from rosbag_processing import views


class AssistantSelectionPipelineTests(SimpleTestCase):
    """Verify that request selections reach Local and Remote identically."""

    def setUp(self):
        self.factory = RequestFactory()
        cache.clear()

    def make_request(self, mode, **overrides):
        context_id = f"selection-{mode}"
        cache.set(
            f"chat:{context_id}",
            {"history": "previous private conversation", "frames": ["cached-frame"]},
        )
        body = {
            "chat_context_id": context_id,
            "message": "Annotate the selected content",
            "audio_transcript": (
                "[00:00] Speaker A: Before\n"
                "[00:10] Speaker A: Selected\n"
                "[00:20] Speaker A: After"
            ),
            "video_path": "chunks/selected/output.mp4",
            "Axeinfo": [
                {
                    "id": 1,
                    "axisName": "Selected timeline",
                    "blocks": [
                        {"start": 2, "end": 4, "text": "before"},
                        {"start": 12, "end": 14, "text": "selected"},
                    ],
                },
                {
                    "id": 2,
                    "axisName": "Other timeline",
                    "blocks": [{"start": 12, "end": 13, "text": "private"}],
                },
            ],
            "Codebook": {"Speech": ["Greeting"]},
            "selected_data_views": [
                "transcript", "video", "annotations", "codebook",
            ],
            "data_view_contexts": {
                "transcript": {
                    "transcript": "OUTSIDE_RANGE_SECRET",
                    "speaker_data": [{"text": "OUTSIDE_RANGE_SECRET"}],
                },
                "video": {
                    "frames": [{"seconds": 29, "private": "OUTSIDE_RANGE_SECRET"}],
                },
                "annotations": {
                    "axes": [{"blocks": [{"text": "OUTSIDE_RANGE_SECRET"}]}],
                },
                "statistics-tiers": {"private": "not selected"},
            },
            "timeline_scope": {"axis_ids": [1], "allow_new": False},
            "assistant_mode": mode,
            "context_routes": {
                "transcript": mode,
                "frames": mode,
                "codebook": mode,
                "timeline": mode,
            },
            "context_duration": 30,
            "time_range": {"start": 10, "end": 20},
            "current_chunk": {
                "index": 2,
                "start_seconds": 600,
                "end_seconds": 630,
                "is_chunked": True,
            },
        }
        body.update(overrides)
        return self.factory.post(
            "/api/gpt_chat/",
            data=json.dumps(body),
            content_type="application/json",
        )

    def invoke(self, mode, request, response_text="Completed"):
        """Call gpt_chat with both providers mocked and return the used mock."""
        with patch.object(views, "openai_api_key", "test-key"), patch.object(
            views, "create_local_ai"
        ) as local_ai, patch.object(views, "RemoteAPI") as remote_ai:
            provider = local_ai if mode == "local" else remote_ai
            provider.return_value.respond.return_value = response_text
            provider.return_value.get_run_metadata.return_value = {
                "model": {
                    "provider": mode,
                    "requested": f"test-{mode}",
                    "resolved": f"test-{mode}",
                },
                "parameters": {"temperature": 0},
                "prompts": {"user": "Annotate the selected content"},
            }
            response = views.gpt_chat(request)
            used_call = provider.call_args
            respond_call = provider.return_value.respond.call_args
            unused_called = (remote_ai if mode == "local" else local_ai).called
        return response, used_call, respond_call, unused_called

    def test_valid_time_range_filters_context_and_records_both_references_in_both_modes(self):
        for mode in ("local", "remote"):
            with self.subTest(mode=mode), patch.object(
                views, "frames_for_video", return_value=(
                    ["range-frame"],
                    [{
                        "frame_index": 42,
                        "chunk_relative_seconds": 12.5,
                        "sha256": "frame-hash",
                    }],
                )
            ) as frames:
                response, provider_call, _, unused_called = self.invoke(
                    mode, self.make_request(mode)
                )

            self.assertEqual(response.status_code, 200)
            self.assertFalse(unused_called)
            frames.assert_called_once_with(
                "chunks/selected/output.mp4",
                start_seconds=10.0,
                end_seconds=20.0,
            )
            context = provider_call.kwargs
            self.assertIn("Selected", context["transcriptContext"])
            self.assertNotIn("Before", context["transcriptContext"])
            self.assertNotIn("After", context["transcriptContext"])
            self.assertEqual(context["frameContext"], ["range-frame"])
            self.assertEqual(context["dataViewContexts"], {})
            self.assertNotIn("OUTSIDE_RANGE_SECRET", json.dumps(context))
            self.assertEqual(context["timelineContext"], [{
                "id": 1,
                "axisName": "Selected timeline",
                "blocks": [{
                    "start": 12,
                    "end": 14,
                    "text": "selected",
                    "blockIndex": 1,
                }],
            }, {
                "id": 2,
                "axisName": "Other timeline",
                "blocks": [{
                    "start": 12,
                    "end": 13,
                    "text": "private",
                    "blockIndex": 0,
                }],
            }])

            record = json.loads(response.content)["ai_record"]
            options = record["request_options"]
            self.assertEqual(record["model_selection"]["used"], mode)
            self.assertEqual(options["selected_data_types"], [
                "transcript", "video", "annotations", "codebook",
            ])
            self.assertEqual(options["selected_timelines"], [{
                "axis_id": 1,
                "axis_name": "Selected timeline",
            }])
            self.assertEqual(options["current_chunk"], {
                "index": 2,
                "start_seconds": 600.0,
                "end_seconds": 630.0,
                "is_chunked": True,
            })
            self.assertEqual(options["selected_time_range"], {
                "chunk_relative_seconds": {"start": 10.0, "end": 20.0},
                "whole_video_seconds": {"start": 610.0, "end": 620.0},
            })
            self.assertEqual(options["video_frames"], {
                "count": 1,
                "samples": [{
                    "frame_index": 42,
                    "chunk_relative_seconds": 12.5,
                    "whole_video_seconds": 612.5,
                    "sha256": "frame-hash",
                }],
            })

    def test_time_range_excludes_full_range_duplicates_from_actual_lm_payload(self):
        """Only range-filtered evidence reaches either provider's final request."""
        audio_transcript = (
            "[00:00] OUTSIDE_TRANSCRIPT_BEFORE\n"
            "[00:10] INSIDE_TRANSCRIPT\n"
            "[00:20] OUTSIDE_TRANSCRIPT_AFTER"
        )
        timeline = [{
            "id": 1,
            "axisName": "Range audit",
            "blocks": [
                {"start": 2, "end": 4, "text": "OUTSIDE_TIMELINE_BEFORE"},
                {"start": 12, "end": 14, "text": "INSIDE_TIMELINE"},
                {"start": 22, "end": 24, "text": "OUTSIDE_TIMELINE_AFTER"},
            ],
        }]
        duplicate_contexts = {
            "transcript": {"transcript": "DUPLICATE_FULL_RANGE_SECRET"},
            "annotations": {
                "axes": [{"blocks": [{"text": "DUPLICATE_FULL_RANGE_SECRET"}]}],
            },
        }

        for mode in ("local", "remote"):
            with self.subTest(mode=mode), patch(
                "rosbag_processing.ai_assistant.OpenAI"
            ) as openai_class, patch.object(
                views, "openai_api_key", "test-key"
            ):
                openai_class.return_value.chat.completions.create.return_value = (
                    SimpleNamespace(
                        model=f"test-{mode}-model",
                        choices=[SimpleNamespace(
                            message=SimpleNamespace(content=json.dumps({
                                "type": "instruction",
                                "steps": [{
                                    "action": "deleteBlock",
                                    "parameters": {"axisId": 1, "blockIndex": 1},
                                }],
                            }))
                        )],
                    )
                )
                response = views.gpt_chat(self.make_request(
                    mode,
                    message="Delete annotations in the selected range",
                    audio_transcript=audio_transcript,
                    Axeinfo=timeline,
                    video_path=None,
                    selected_data_views=["transcript", "annotations"],
                    data_view_contexts=duplicate_contexts,
                    timeline_scope={"axis_ids": [1], "allow_new": False},
                ))

            self.assertEqual(response.status_code, 200)
            lm_request = (
                openai_class.return_value.chat.completions.create.call_args.kwargs
            )
            serialized_messages = json.dumps(
                lm_request["messages"], ensure_ascii=False
            )
            self.assertIn("INSIDE_TRANSCRIPT", serialized_messages)
            self.assertIn("INSIDE_TIMELINE", serialized_messages)
            for excluded_marker in (
                "OUTSIDE_TRANSCRIPT_BEFORE",
                "OUTSIDE_TRANSCRIPT_AFTER",
                "OUTSIDE_TIMELINE_BEFORE",
                "OUTSIDE_TIMELINE_AFTER",
                "DUPLICATE_FULL_RANGE_SECRET",
            ):
                self.assertNotIn(excluded_marker, serialized_messages)

    def test_invalid_time_ranges_are_rejected_before_either_provider_runs(self):
        invalid_ranges = (
            {"start": -1, "end": 10},
            {"start": 20, "end": 10},
            {"start": 4, "end": 4},
            {"start": 0, "end": 31},
        )
        for mode in ("local", "remote"):
            for selected_range in invalid_ranges:
                with self.subTest(mode=mode, selected_range=selected_range), patch.object(
                    views, "create_local_ai"
                ) as local_ai, patch.object(views, "RemoteAPI") as remote_ai:
                    response = views.gpt_chat(
                        self.make_request(mode, time_range=selected_range)
                    )

                self.assertEqual(response.status_code, 400)
                local_ai.assert_not_called()
                remote_ai.assert_not_called()

    def test_only_selected_data_view_subset_reaches_each_provider(self):
        for mode in ("local", "remote"):
            with self.subTest(mode=mode):
                response, provider_call, _, unused_called = self.invoke(
                    mode,
                    self.make_request(
                        mode,
                        selected_data_views=["transcript"],
                        data_view_contexts={
                            "transcript": {"visible": "yes"},
                            "video": {"private": "must not pass"},
                        },
                        video_path=None,
                        timeline_scope={"axis_ids": [], "allow_new": False},
                        time_range=None,
                    ),
                )

            self.assertEqual(response.status_code, 200)
            self.assertFalse(unused_called)
            context = provider_call.kwargs
            self.assertEqual(context["transcriptContext"], (
                "[00:00] Speaker A: Before\n"
                "[00:10] Speaker A: Selected\n"
                "[00:20] Speaker A: After"
            ))
            self.assertEqual(context["frameContext"], [])
            self.assertEqual(context["codebookContext"], {})
            self.assertEqual(context["timelineContext"], [])
            self.assertEqual(context["selectedDataViews"], ["transcript"])
            self.assertEqual(context["dataViewContexts"], {})

    def test_unscoped_media_metadata_never_reaches_either_provider(self):
        for mode in ("local", "remote"):
            with self.subTest(mode=mode):
                response, provider_call, _, unused_called = self.invoke(
                    mode,
                    self.make_request(
                        mode,
                        selected_data_views=["audio", "waveform"],
                        data_view_contexts={
                            "audio": {"path": "FULL_CHUNK_AUDIO_SECRET"},
                            "waveform": {"path": "FULL_CHUNK_WAVEFORM_SECRET"},
                        },
                        audio_transcript=None,
                        video_path=None,
                        Axeinfo=None,
                        Codebook=None,
                        timeline_scope={"axis_ids": [], "allow_new": False},
                        time_range=None,
                    ),
                )

            self.assertEqual(response.status_code, 200)
            self.assertFalse(unused_called)
            self.assertEqual(provider_call.kwargs["dataViewContexts"], {})
            self.assertNotIn("FULL_CHUNK", json.dumps(provider_call.kwargs))

    def test_confirmed_empty_selection_is_prompt_only_in_both_modes(self):
        for mode in ("local", "remote"):
            with self.subTest(mode=mode):
                response, provider_call, respond_call, unused_called = self.invoke(
                    mode,
                    self.make_request(
                        mode,
                        selected_data_views=[],
                        data_view_contexts={"video": {"private": "must not pass"}},
                        audio_transcript=None,
                        video_path=None,
                        Axeinfo=None,
                        Codebook=None,
                        timeline_scope={"axis_ids": [], "allow_new": False},
                        time_range=None,
                    ),
                    response_text="INSUFFICIENT_DATA",
                )

            self.assertEqual(response.status_code, 200)
            self.assertFalse(unused_called)
            context = provider_call.kwargs
            self.assertEqual(context["transcriptContext"], "")
            self.assertEqual(context["frameContext"], [])
            self.assertEqual(context["codebookContext"], {})
            self.assertEqual(context["timelineContext"], [])
            self.assertEqual(context["selectedDataViews"], [])
            self.assertEqual(context["dataViewContexts"], {})
            self.assertEqual(
                context["timelineScope"], {"axis_ids": [], "allow_new": False}
            )
            self.assertEqual(
                respond_call.args, ("Annotate the selected content", "")
            )

    def test_no_timeline_scope_allows_conversational_reply_in_both_modes(self):
        for mode in ("local", "remote"):
            with self.subTest(mode=mode):
                response, provider_call, _, unused_called = self.invoke(
                    mode,
                    self.make_request(
                        mode,
                        message="Explain the labels conversationally",
                        selected_data_views=["transcript"],
                        video_path=None,
                        timeline_scope={"axis_ids": [], "allow_new": False},
                        time_range=None,
                    ),
                    response_text="Here is a conversational explanation.",
                )

            self.assertEqual(response.status_code, 200)
            self.assertFalse(unused_called)
            payload = json.loads(response.content)
            self.assertEqual(payload["response"], "Here is a conversational explanation.")
            self.assertEqual(
                provider_call.kwargs["timelineScope"],
                {"axis_ids": [], "allow_new": False},
            )
            self.assertEqual(
                payload["ai_record"]["request_options"]["selected_timelines"], []
            )
            self.assertFalse(
                payload["ai_record"]["request_options"]["allow_new_timeline"]
            )

    def test_new_only_timeline_scope_reaches_both_providers_and_record(self):
        for mode in ("local", "remote"):
            with self.subTest(mode=mode):
                response, provider_call, _, unused_called = self.invoke(
                    mode,
                    self.make_request(
                        mode,
                        selected_data_views=["transcript"],
                        video_path=None,
                        timeline_scope={"axis_ids": [], "allow_new": True},
                        time_range=None,
                    ),
                )

            self.assertEqual(response.status_code, 200)
            self.assertFalse(unused_called)
            self.assertEqual(
                provider_call.kwargs["timelineScope"],
                {"axis_ids": [], "allow_new": True},
            )
            options = json.loads(response.content)["ai_record"]["request_options"]
            self.assertEqual(options["selected_timelines"], [])
            self.assertTrue(options["allow_new_timeline"])
