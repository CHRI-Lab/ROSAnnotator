"""Acceptance tests for conversation clearing and durable AI-run records."""

import json
import shutil
import sys
import types
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

# The application deploys on Linux and uses flock. A no-op test shim keeps the
# endpoint tests runnable on Windows, where the fcntl module is unavailable.
if "fcntl" not in sys.modules:
    try:
        import fcntl  # noqa: F401
    except ModuleNotFoundError:
        sys.modules["fcntl"] = types.SimpleNamespace(LOCK_EX=1, flock=lambda *_: None)

from django.test import RequestFactory, SimpleTestCase

from rosbag_processing import views


class ConversationLifecycleAcceptanceTests(SimpleTestCase):
    """Exercise the API boundary used by the frontend conversation lifecycle."""

    def setUp(self):
        self.factory = RequestFactory()
        self.test_directory = Path(__file__).parent / f".conversation-{uuid4()}"
        self.test_directory.mkdir()
        self.annotation_path = f"{self.test_directory}{Path('/')}"
        self.annotation_patch = patch.object(
            views, "ANNOTATION_PATH", self.annotation_path
        )
        self.annotation_patch.start()
        views.gpt_history = ""
        views.gpt_history_generation = 0
        views.video_frames = []

    def tearDown(self):
        self.annotation_patch.stop()
        shutil.rmtree(self.test_directory, ignore_errors=True)
        views.gpt_history = ""
        views.gpt_history_generation = 0

    def clear_history(self):
        request = self.factory.post("/api/gpt_chat/clear/", data={})
        return views.clear_gpt_history(request)

    def complete_record(self, run_id, outcome="replied", **extra):
        record = {
            "schema_version": 1,
            "run_id": run_id,
            "parameters": {"temperature": 0.2},
            "ai_response": f"response for {run_id}",
            **extra,
        }
        request = self.factory.post(
            "/api/ai_records/complete/",
            data=json.dumps(
                {
                    "annotation_name": "session.bag+labels.json",
                    "ai_record": record,
                    "outcome": outcome,
                }
            ),
            content_type="application/json",
        )
        return views.complete_ai_record(request)

    def load_records(self):
        return views.load_ai_records("session.bag+labels.json")

    def local_chat_request(self, message):
        return self.factory.post(
            "/api/gpt_chat/",
            data=json.dumps(
                {
                    "message": message,
                    "audio_transcript": "Speaker 1: hello",
                    "Axeinfo": [{"axisId": 1, "blocks": []}],
                    "Codebook": {"Speech": ["Greeting"]},
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

    def test_clear_removes_existing_backend_history(self):
        views.gpt_history = "user promptassistant reply"

        response = self.clear_history()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(json.loads(response.content), {"cleared": True})
        self.assertEqual(views.gpt_history, "")

    def test_clear_empty_history_is_successful(self):
        views.gpt_history = ""

        response = self.clear_history()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(json.loads(response.content), {"cleared": True})
        self.assertEqual(views.gpt_history, "")

    def test_next_conversation_receives_no_cleared_context(self):
        views.gpt_history = "history that must be forgotten"
        self.clear_history()
        assistant_metadata = {
            "model": {"provider": "local", "requested": "test", "resolved": "test"},
            "parameters": {},
            "prompts": {"user": "new prompt"},
        }

        with patch.object(views, "create_local_ai") as create_local_ai:
            create_local_ai.return_value.respond.return_value = "new reply"
            create_local_ai.return_value.get_run_metadata.return_value = assistant_metadata
            response = views.gpt_chat(self.local_chat_request("new prompt"))

        self.assertEqual(response.status_code, 200)
        create_local_ai.return_value.respond.assert_called_once_with("new prompt", "")
        self.assertNotIn("history that must be forgotten", views.gpt_history)

    def test_failed_ai_conversation_creates_no_completed_record(self):
        with patch.object(views, "create_local_ai") as create_local_ai:
            create_local_ai.return_value.respond.side_effect = views.LocalInferenceError(
                "local failure"
            )
            response = views.gpt_chat(self.local_chat_request("failed prompt"))

        self.assertEqual(response.status_code, 501)
        self.assertNotIn("ai_record", json.loads(response.content))
        self.assertEqual(self.load_records(), [])

    def test_completed_record_is_written_with_parameters_and_outcome(self):
        response = self.complete_record("run-1")

        self.assertEqual(response.status_code, 200)
        records = self.load_records()
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["run_id"], "run-1")
        self.assertEqual(records[0]["parameters"], {"temperature": 0.2})
        self.assertEqual(records[0]["action_outcome"], "replied")
        self.assertIn("completed_at", records[0])

    def test_multiple_completed_records_append_without_overwrite(self):
        first = self.complete_record("run-1")
        second = self.complete_record("run-2", outcome="applied")

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        records = self.load_records()
        self.assertEqual([record["run_id"] for record in records], ["run-1", "run-2"])
        self.assertEqual(records[0]["ai_response"], "response for run-1")
        self.assertEqual(records[1]["action_outcome"], "applied")

    def test_retry_of_same_run_updates_without_duplicate(self):
        self.complete_record("run-1", outcome="replied")
        response = self.complete_record("run-1", outcome="not_applied")

        self.assertEqual(response.status_code, 200)
        records = self.load_records()
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["run_id"], "run-1")
        self.assertEqual(records[0]["action_outcome"], "not_applied")

    def test_clear_history_does_not_delete_saved_ai_records(self):
        self.complete_record("run-1")
        views.gpt_history = "temporary conversation context"

        response = self.clear_history()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(views.gpt_history, "")
        self.assertEqual([record["run_id"] for record in self.load_records()], ["run-1"])

    def test_record_is_durable_without_annotation_save_or_autosave(self):
        response = self.complete_record("run-independent")
        record_path = Path(views.ai_records_file_path("session.bag+labels.json"))

        self.assertEqual(response.status_code, 200)
        self.assertTrue(record_path.is_file())
        payload = json.loads(record_path.read_text(encoding="utf-8"))
        self.assertEqual(payload["annotation_name"], "session.bag+labels.json")
        self.assertEqual(payload["ai_runs"][0]["run_id"], "run-independent")
