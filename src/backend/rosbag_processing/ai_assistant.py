from abc import ABC, abstractmethod
import json
import logging
import os
import re

from openai import APIConnectionError, APIStatusError, AuthenticationError, OpenAI


logger = logging.getLogger(__name__)

ALL_DATA_VIEWS = (
    "audio", "video", "transcript", "waveform", "annotations",
    "statistics-annotations", "statistics-tiers", "codebook",
)


class RemoteAuthenticationError(RuntimeError):
    """The remote provider rejected its configured credentials."""


class RemoteResponseError(RuntimeError):
    """The remote provider returned an unsafe timeline response."""


class LocalInferenceError(RuntimeError):
    """The local inference server could not complete a request."""


class AIAssistant(ABC):
    """Common context and I/O contract for an annotation AI assistant.

    Every provider receives the four annotation contexts at construction time.
    Callers then pass a user message and the existing chat history to ``respond``.
    Providers return the same raw response string used by the original GPT flow.
    """

    def __init__(
        self,
        transcriptContext,
        frameContext,
        codebookContext,
        timelineContext,
        timelineScope=None,
        selectedDataViews=None,
        dataViewContexts=None,
    ):
        self.transcriptContext = transcriptContext
        self.frameContext = frameContext
        self.codebookContext = codebookContext
        self.timelineContext = timelineContext
        self.timelineScope = timelineScope
        self.selectedDataViews = tuple(
            ALL_DATA_VIEWS if selectedDataViews is None else selectedDataViews
        )
        self.dataViewContexts = dataViewContexts or {}
        self.last_run_metadata = {}

    def respond(self, message, chatHistory=""):
        """Return raw assistant text using the shared provider contract."""
        diagnostic = self._context_diagnostic_response(message)
        if diagnostic is not None:
            return diagnostic
        missing = self._missing_required_data_views(message)
        if missing:
            missing_text = ", ".join(missing)
            return (
                "INSUFFICIENT_DATA\n"
                f"Missing data views: {missing_text}\n"
                "Reason: The requested analysis requires data that was not supplied.\n"
                f"Request: Please select or provide {missing_text} and try again."
            )
        return self._respond(message, chatHistory)

    def _context_diagnostic_response(self, message):
        """Answer context-audit questions from validated data, never model guesses."""
        normalized = " ".join(str(message or "").casefold().split())
        available = self._available_data_views()
        asks_for_received_transcript = (
            "transcript" in normalized
            and any(word in normalized for word in ("send", "show", "display", "give", "return"))
            and any(word in normalized for word in ("received", "sent", "available", "access"))
        )
        if asks_for_received_transcript:
            if "transcript" in available:
                return str(self.transcriptContext)
            return (
                "INSUFFICIENT_DATA\n"
                "Missing data views: transcript\n"
                "Reason: No transcript content was supplied in this request.\n"
                "Request: Please select or provide transcript and try again."
            )

        asks_for_available_views = (
            ("data view" in normalized or "views" in normalized)
            and any(word in normalized for word in ("access", "available", "received", "sent"))
            and any(word in normalized for word in ("what", "which", "list"))
        )
        if asks_for_available_views:
            labels = {
                "video": "video frames",
                "transcript": "transcript",
                "annotations": "annotations",
                "statistics-annotations": "annotation statistics",
                "statistics-tiers": "tier statistics",
                "codebook": "codebook",
            }
            visible = [labels.get(view, view) for view in available]
            return "Available data views: " + (", ".join(visible) if visible else "none") + "."
        return None

    def get_run_metadata(self):
        """Return safe provider metadata for the most recent response."""
        return self.last_run_metadata

    @staticmethod
    def _requests_timeline_change(message):
        """Return whether a user asks for a machine-applied timeline edit."""
        normalized_message = message.casefold()
        action_words = (
            "annotate", "label", "classify", "categorize", "tag",
            "add", "create", "delete", "remove",
        )
        timeline_words = (
            "timeline", "time axis", "timestamp", "time range",
            "axis", "axi", "block", "annotation",
        )
        return any(word in normalized_message for word in action_words) and any(
            word in normalized_message for word in timeline_words
        )

    @staticmethod
    def _codebook_labels(codebook):
        if isinstance(codebook, dict):
            values = codebook.values()
        elif isinstance(codebook, list):
            values = (codebook,)
        else:
            return []
        return list(
            dict.fromkeys(
                str(label).strip()
                for labels in values
                if isinstance(labels, list)
                for label in labels
                if str(label).strip()
            )
        )

    def _codebook_for_message(self, message):
        """Select the codebook categories named by the user's request."""
        if not isinstance(self.codebookContext, dict):
            return self.codebookContext

        normalized_message = str(message or "").casefold()
        category_terms = ()
        if "attitude" in normalized_message:
            category_terms = ("attitude",)
        elif any(
            term in normalized_message
            for term in ("gesture", "body language", "visual")
        ):
            category_terms = ("gesture", "body language", "visual")
        elif "request" in normalized_message:
            category_terms = ("request",)

        if not category_terms:
            return self.codebookContext

        selected_categories = {
            category: labels
            for category, labels in self.codebookContext.items()
            if any(term in str(category).casefold() for term in category_terms)
        }
        return selected_categories or self.codebookContext

    def _timeline_edits_enabled(self):
        if self.timelineScope is None:
            return True
        return bool(
            self.timelineScope.get("axis_ids")
            or self.timelineScope.get("allow_new")
        )

    def _is_timeline_request(self, message):
        if self._missing_required_data_views(message):
            return False
        if not self._timeline_edits_enabled():
            return False
        if self._requests_timeline_change(message):
            return True
        if self.timelineScope is None:
            return False
        normalized_message = str(message or "").casefold()
        return any(
            word in normalized_message
            for word in (
                "annotate",
                "annotation",
                "label",
                "classify",
                "classification",
                "categorize",
                "tag",
                "delete",
                "remove",
                "clear",
            )
        )

    def _missing_required_data_views(self, message):
        """Return obvious evidence prerequisites omitted by the user."""
        normalized = str(message or "").casefold()
        missing = []
        available = set(self._available_data_views())
        if any(word in normalized for word in (
            "gesture", "body language", "facial expression", "visible", "video",
        )) and "video" not in available:
            missing.append("video")
        if any(word in normalized for word in (
            "transcript", "utterance", "speech", "said", "speaker attitude",
        )) and "transcript" not in available:
            missing.append("transcript")
        if any(phrase in normalized for phrase in (
            "codebook", "according to the codebook", "use the codes",
        )) and "codebook" not in available:
            missing.append("codebook")
        if any(word in normalized for word in (
            "delete", "remove", "rename", "modify existing", "existing axis",
        )) and not (
            isinstance(self.timelineScope, dict)
            and self.timelineScope.get("axis_ids")
        ) and not available.intersection({
            "annotations", "statistics-annotations", "statistics-tiers"
        }):
            missing.append("annotations")
        return list(dict.fromkeys(missing))

    def _available_data_views(self):
        """Return selected views that contain inspectable model evidence."""
        selected = set(self.selectedDataViews)
        available = []
        if "transcript" in selected and bool(str(self.transcriptContext or "").strip()):
            available.append("transcript")
        if "video" in selected and bool(self.frameContext):
            available.append("video")
        if "codebook" in selected and bool(self.codebookContext):
            available.append("codebook")
        if bool(self.timelineContext):
            available.extend(
                view for view in (
                    "annotations", "statistics-annotations", "statistics-tiers",
                )
                if view in selected
            )
        return available

    def _data_view_policy_prompt(self):
        labels = {
            "audio": "audio",
            "transcript": "transcript",
            "video": "video frames",
            "waveform": "waveform",
            "annotations": "annotations",
            "statistics-annotations": "annotation statistics",
            "statistics-tiers": "tier statistics",
            "codebook": "codebook",
        }
        available_views = set(self._available_data_views())
        selected = [labels[view] for view in ALL_DATA_VIEWS if view in available_views]
        selected_without_evidence = [
            labels[view] for view in ALL_DATA_VIEWS
            if view in self.selectedDataViews and view not in available_views
        ]
        omitted = [labels[view] for view in ALL_DATA_VIEWS if view not in self.selectedDataViews]
        available_text = ", ".join(selected) if selected else "none"
        unavailable_text = (
            ", ".join(selected_without_evidence)
            if selected_without_evidence else "none"
        )
        omitted_text = ", ".join(omitted) if omitted else "none"
        scoped_axis_ids = (
            self.timelineScope.get("axis_ids", [])
            if isinstance(self.timelineScope, dict) else []
        )
        axis_scope_text = (
            "Separately selected timeline axes: "
            + ", ".join(str(axis_id) for axis_id in scoped_axis_ids)
            + ". Their supplied axis structure and annotation blocks are available "
              "for actions on those axes, even when the full annotations data view is unselected."
            if scoped_axis_ids else
            "No existing timeline axes were separately selected."
        )
        return f"""AVAILABLE DATA POLICY
Available selected data views: {available_text}.
Selected views without inspectable model evidence: {unavailable_text}.
Unavailable or unselected data views: {omitted_text}.
{axis_scope_text}

Use only the selected data views and any separately selected axes described
above. Do not assume access to omitted data and do not infer, fabricate, or
guess missing evidence. The backend has already validated the available views.
Never claim that a view listed as available above is missing, and never invent
additional required views for an ordinary conversational or diagnostic request.
A selected view is usable only to the extent that its supplied context contains
inspectable evidence. A file path or availability flag alone is not evidence.

Absence of evidence in selected data is not evidence that an event did not occur."""

    def _new_axis_allowed(self):
        return self.timelineScope is None or self.timelineScope.get("allow_new") is True

    def _timeline_scope_prompt(self):
        if self.timelineScope is None:
            return "Timeline scope: unrestricted."
        axis_ids = self.timelineScope.get("axis_ids", [])
        allow_new = self.timelineScope.get("allow_new") is True
        if not axis_ids and not allow_new:
            return (
                "Timeline scope: none. Do not return timeline instructions or change "
                "annotations. Reply conversationally in plain text."
            )
        if allow_new and not axis_ids:
            return (
                "Timeline scope: create one new axis. Return addAxi first, then target "
                "that new axis ID in every addBlock step. Do not target any existing "
                "axis."
            )
        return (
            f"Timeline scope: existing axis IDs {axis_ids}; permission to create a "
            f"new axis: {allow_new}. Only target those existing axes. Only use "
            "addAxi when permission to create a new axis is true."
        )

    @abstractmethod
    def _respond(self, message, chatHistory=""):
        """Execute provider-specific inference and return raw response text."""
        raise NotImplementedError


class RemoteAPI(AIAssistant):
    """Remote OpenAI implementation of the annotation assistant."""

    def __init__(
        self,
        transcriptContext,
        frameContext,
        codebookContext,
        timelineContext,
        APIKey,
        timelineScope=None,
        selectedDataViews=None,
        dataViewContexts=None,
    ):
        super().__init__(
            transcriptContext=transcriptContext,
            frameContext=frameContext,
            codebookContext=codebookContext,
            timelineContext=timelineContext,
            timelineScope=timelineScope,
            selectedDataViews=selectedDataViews,
            dataViewContexts=dataViewContexts,
        )
        self.APIKey = APIKey

    def _respond(self, message, chatHistory=""):
        try:
            response_text = self._request_completion(message, chatHistory)
        except AuthenticationError as error:
            raise RemoteAuthenticationError from error
        if self._is_timeline_request(message):
            response_text = self._repair_new_only_annotation(response_text, message)
            self._validate_timeline_instruction(response_text, message)
        return response_text

    def _repair_new_only_annotation(self, response_text, message):
        """Route model-produced blocks to a new axis when that is the only scope."""
        if not (
            isinstance(self.timelineScope, dict)
            and self.timelineScope.get("allow_new") is True
            and not self.timelineScope.get("axis_ids")
        ):
            return response_text
        try:
            json_start = response_text.find("{")
            json_end = response_text.rfind("}")
            instruction = json.loads(response_text[json_start : json_end + 1])
        except (AttributeError, json.JSONDecodeError):
            return response_text
        steps = instruction.get("steps") if isinstance(instruction, dict) else None
        if not isinstance(steps, list):
            return response_text
        add_blocks = [
            step for step in steps
            if isinstance(step, dict) and step.get("action") == "addBlock"
        ]
        if not add_blocks:
            return response_text

        add_axis = next(
            (
                step for step in steps
                if isinstance(step, dict) and step.get("action") == "addAxi"
                and isinstance(step.get("parameters"), dict)
            ),
            None,
        )
        if add_axis is None:
            new_axis_id = max(
                (
                    int(axis.get("id", axis.get("axisId")))
                    for axis in self.timelineContext or []
                    if isinstance(axis, dict)
                    and isinstance(axis.get("id", axis.get("axisId")), int)
                ),
                default=0,
            ) + 1
            normalized_message = str(message or "").casefold()
            axis_name = (
                "Speaker Attitudes" if "attitude" in normalized_message
                else "AI Annotations"
            )
            add_axis = {
                "action": "addAxi",
                "parameters": {
                    "axisId": new_axis_id,
                    "axisName": axis_name,
                    "axistype": "Type-in",
                },
            }
            steps.insert(0, add_axis)
        new_axis_id = add_axis["parameters"].get("axisId")
        for step in add_blocks:
            parameters = step.get("parameters")
            if isinstance(parameters, dict):
                parameters["axisId"] = new_axis_id
        return json.dumps(instruction, ensure_ascii=False)

    def _validate_timeline_instruction(self, response_text, message=""):
        error_message = (
            "The remote model returned an invalid timeline instruction. "
            "No annotation changes were applied."
        )
        if not isinstance(response_text, str):
            raise RemoteResponseError(error_message)

        json_start = response_text.find("{")
        json_end = response_text.rfind("}")
        if json_start < 0 or json_end <= json_start:
            raise RemoteResponseError(error_message)
        try:
            instruction = json.loads(response_text[json_start : json_end + 1])
        except json.JSONDecodeError as error:
            raise RemoteResponseError(error_message) from error

        steps = instruction.get("steps") if isinstance(instruction, dict) else None
        if not isinstance(instruction, dict) or instruction.get("type") != "instruction" or not steps:
            raise RemoteResponseError(error_message)

        required_parameters = {
            "addAxi": {"axisId": int, "axisName": str, "axistype": str},
            "addBlock": {
                "axisId": int,
                "start": (int, float),
                "end": (int, float),
                "text": str,
            },
            "deleteBlock": {"axisId": int, "blockIndex": int},
            "deleteAxi": {"axisId": int},
        }
        selected_labels = self._codebook_labels(self._codebook_for_message(message))
        normalized_message = str(message or "").casefold()
        is_deletion_request = any(
            word in normalized_message for word in ("delete", "remove", "clear")
        )
        requires_codebook_label = not is_deletion_request and bool(selected_labels) and any(
            phrase in normalized_message
            for phrase in ("according to", "attitude", "codebook")
        )
        add_block_count = 0
        for step in steps:
            if not isinstance(step, dict) or step.get("action") not in required_parameters:
                raise RemoteResponseError(error_message)
            parameters = step.get("parameters")
            if not isinstance(parameters, dict):
                raise RemoteResponseError(error_message)
            for name, expected_type in required_parameters[step["action"]].items():
                value = parameters.get(name)
                if isinstance(value, bool) or not isinstance(value, expected_type):
                    raise RemoteResponseError(error_message)
            if step["action"] == "addBlock" and parameters["end"] < parameters["start"]:
                raise RemoteResponseError(error_message)
            if step["action"] == "addBlock":
                add_block_count += 1
                if requires_codebook_label and parameters["text"] not in selected_labels:
                    raise RemoteResponseError(
                        "The remote model returned an annotation label that is not "
                        "in the selected codebook. No annotation changes were applied."
                    )
        if requires_codebook_label and add_block_count == 0:
            raise RemoteResponseError(
                "The remote model did not return any codebook annotation blocks. "
                "No annotation changes were applied."
            )

    def _request_completion(self, message, chatHistory=""):
        client = OpenAI(api_key=self.APIKey)
        timeline_available = bool(set(self.selectedDataViews).intersection({
            "annotations", "statistics-annotations", "statistics-tiers",
        })) or bool(
            isinstance(self.timelineScope, dict)
            and self.timelineScope.get("axis_ids")
        )
        timeline_context = (
            json.dumps(self.timelineContext, indent=2)
            if timeline_available else "Not selected."
        )
        selected_codebook = self._codebook_for_message(message)
        allowed_labels = self._codebook_labels(selected_codebook)
        scope_prompt = self._timeline_scope_prompt()
        selected_frames = (
            self.frameContext[0::max(1, len(self.frameContext) // 50)][:50]
            if "video" in self.selectedDataViews else []
        )
        transcript_section = (
            f"Here is the audio transcription:\n{self.transcriptContext}"
            if "transcript" in self.selectedDataViews else ""
        )
        codebook_section = (
            f"""Here is the Codebook predefined by user. When the request asks
                    for codebook annotation, every addBlock text must be exactly one
                    of these labels; do not use summaries or explanations:

                    {selected_codebook}

                    Allowed exact labels: {allowed_labels}"""
            if "codebook" in self.selectedDataViews else "Codebook: Not selected."
        )
        data_view_policy = self._data_view_policy_prompt()
        structured_view_context = json.dumps(
            self.dataViewContexts, ensure_ascii=False, indent=2
        )

        prompt = f"""
        Answer the following request using only the selected data views and axes:
        {message}
        {transcript_section}
        """

        system_prompt = f"""
                    You are an assistant that can manipulate timelines. Based on the audio transcript, here are the actions you can perform:

                    {data_view_policy}

                    SELECTED DATA VIEW CONTEXTS:
                    {structured_view_context}
                    
                    1. Add a new `axi`: Method: `addAxi`, Parameters: `axisId` (integer),'axisName' (string),'axistype' (string).
                    2. Add a new `block`: Method: `addBlock`, Parameters: `axisId` (integer), `start` (float), `end` (float), `text` (string).
                    3. Delete a old 'block':Mthod:'deleteBlock', Parameters: `axisId` (integer), 'blockIndex' (integer).
                    4. Delete a old 'axi':Mthod:'deleteAxi', Parameters: `axisId` (integer).
                    When a timeline block includes blockIndex, copy that exact
                    value into deleteBlock. It is the block's position in the
                    full timeline, even if only a selected time range is shown.
                    "Delete annotations" or "delete all annotations" means delete
                    blocks with deleteBlock while preserving their axes. Use deleteAxi
                    only when the user explicitly asks to delete an axis or timeline.
                    When you need to perform multiple actions to complete the task, return the response in the following format:
                    {{
                      "type": "instruction",
                      "steps": [
                        {{
                          "action": "addAxi",
                          "parameters": 
                          {{
                            "axisId": 1,
                            "axisName": Greeting
                            "axistype": Topic annotate
                            }}
                        }},
                        {{
                          "action": "addBlock",
                          "parameters": {{
                            "axisId": 1,
                            "start": 10,
                            "end": 20,
                            "text": "This is a new block"
                          }}
                        }}
                        {{
                          "action": "deleteBlock",
                          "parameters": {{
                            "axisId": 1,
                            "blockIndex": 0
                          }}
                        }}
                        {{
                          "action": "deleteAxi",
                          "parameters": {{
                            "axisId": 1
                          }}
                        }}
                      ]
                    }}

                    axis Name are normally the topic of this axi.
                    Every axis name must be unique. If creating multiple axes with
                    the same topic, number them as "Topic 1", "Topic 2", and so on.
                    Never reuse an existing axis name.
                    Remove axi could remove all blocks in the axi.
                    Axi type always equal "Type-in"
                    Always create steps, even there only one step.
                    For timeline changes, return only one valid JSON object in the specified format.
                    The newest axi id will be current largest id+1.
                    Overlap with other block in one axi will lead to error.
                    For an annotation request, an axis alone is not a completed annotation.
                    Include at least one evidence-backed addBlock step with start and end
                    times in seconds relative to the current video chunk. Use the
                    transcript timestamps for speech-based annotations and the
                    supplied video frames for visible gestures. Do not invent a
                    gesture when the frames do not show it.
                    For attitude annotation, create one block per applicable utterance
                    using that utterance's start and end timestamps. Do not create one
                    large summary block across separate utterances.
                    If the response is a normal conversation, return the plain text as usual.
                    Here is the current Axi information, you can consider axiId based on this:

                    {timeline_context}

                    {scope_prompt}

                    {codebook_section}
                    
                    Here is previous chat history between you and user:

                    {chatHistory}


                    """
        request_parameters = {"model": "gpt-4o"}
        if self._is_timeline_request(message):
            # Timeline edits must be machine-readable for the frontend to apply.
            request_parameters["response_format"] = {"type": "json_object"}
        messages = [
            {
                "role": "system",
                "content": system_prompt,
            },
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    *map(
                        lambda frame: {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{frame}",
                                "detail": "low",
                            },
                        },
                        selected_frames,
                    ),
                ],
            },
        ]

        chat_completion = client.chat.completions.create(
            **request_parameters,
            messages=messages,
        )
        response_text = chat_completion.choices[0].message.content
        self.last_run_metadata = {
            "model": {
                "provider": "openai",
                "requested": request_parameters["model"],
                "resolved": getattr(chat_completion, "model", None),
            },
            "parameters": request_parameters,
            "prompts": {
                "system": system_prompt,
                "user": message,
            },
        }

        return response_text


class LocalAI(AIAssistant):
    """Base class for local annotation assistants backed by llama.cpp.

    Local models are text-only unless a subclass explicitly declares visual
    support. Keeping the capability check here prevents each model adapter
    from having to implement (and potentially forget) the same guard.
    """

    model_name = None
    supports_visual_annotation = False
    max_visual_frames = 8

    def __init__(
        self,
        transcriptContext,
        frameContext,
        codebookContext,
        timelineContext,
        checkpointPath,
        model=None,
        timelineScope=None,
        selectedDataViews=None,
        dataViewContexts=None,
    ):
        super().__init__(
            transcriptContext=transcriptContext,
            frameContext=frameContext,
            codebookContext=codebookContext,
            timelineContext=timelineContext,
            timelineScope=timelineScope,
            selectedDataViews=selectedDataViews,
            dataViewContexts=dataViewContexts,
        )
        self.checkpointPath = checkpointPath
        self.baseURL = os.getenv("LOCAL_AI_BASE_URL", "http://local-llm:8080/v1")
        self.model = model or self.model_name
        if not self.model:
            raise ValueError("A local model subclass must define model_name.")

    def _respond(self, message, chatHistory=""):
        requests_visual_analysis = self._requests_visual_analysis(message)
        video_selected = "video" in self.selectedDataViews
        if video_selected and not self.supports_visual_annotation and requests_visual_analysis:
            raise LocalInferenceError(
                f"The selected local model ({self.model}) is text-only and cannot "
                "perform gesture annotation or inspect video frames. Select a "
                "vision-capable model or Remote for video-based annotation."
            )
        if video_selected and requests_visual_analysis and not self.frameContext:
            raise LocalInferenceError(
                "No video frames are available for visual annotation. Process "
                "a video before requesting gesture annotation."
            )

        is_timeline_request = self._is_timeline_request(message)
        is_auto_annotation = self._requests_auto_annotation(message)
        if requests_visual_analysis and is_timeline_request and self._new_axis_allowed():
            return self._respond_visual_annotation(message, chatHistory)
        has_timestamped_segments = bool(self._transcript_segments())
        if (
            is_auto_annotation
            and self._new_axis_allowed()
            and not requests_visual_analysis
            and has_timestamped_segments
            and (
                "request" in message.casefold()
                or len(str(self.transcriptContext or "")) > 4000
            )
        ):
            return self._respond_chunked_auto_annotation(message)

        system_prompt = self._build_request_system_prompt(message, chatHistory)
        request_parameters = {
            "model": self.model,
            "temperature": 0,
            "max_tokens": 768 if is_timeline_request else 256,
        }
        if is_timeline_request:
            request_parameters["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": "timeline_instruction",
                    "strict": True,
                    "schema": self._timeline_instruction_schema(
                        min_steps=2 if is_auto_annotation else 1
                    ),
                },
            }
        client = OpenAI(base_url=self.baseURL, api_key="local", timeout=900)

        try:
            completion = client.chat.completions.create(
                **request_parameters,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": self._user_content(message)},
                ],
            )
        except (APIConnectionError, APIStatusError) as error:
            raise LocalInferenceError(
                "The local language model service is unavailable."
            ) from error

        response_text = completion.choices[0].message.content
        if not response_text:
            raise LocalInferenceError("The local language model returned no text.")

        if is_timeline_request:
            try:
                response_text = self._normalize_timeline_instruction(
                    response_text,
                    message,
                    requires_new_axis=is_auto_annotation and self._new_axis_allowed(),
                )
            except LocalInferenceError:
                logger.error(
                    "Invalid local timeline response from model %s: %r",
                    self.model,
                    response_text,
                )
                raise
            if is_auto_annotation:
                instruction = json.loads(response_text)
                if not any(
                    step.get("action") == "addBlock"
                    for step in instruction["steps"]
                    if isinstance(step, dict)
                ):
                    if self._axis_id_by_name(
                        self._auto_annotation_axis_name(message)
                    ) is not None:
                        response_text = (
                            "No new annotations were added because the existing "
                            "axis already contains all matching spans."
                        )
                    else:
                        raise LocalInferenceError(
                            "The local model did not produce any annotation blocks. "
                            "Try a more capable local model or select Remote."
                        )

        self.last_run_metadata = {
            "model": {
                "provider": "local",
                "requested": self.model,
                "resolved": getattr(completion, "model", self.model),
            },
            "parameters": request_parameters,
            "prompts": {
                "system": system_prompt,
                "user": message,
            },
        }
        return response_text

    def _respond_visual_annotation(self, message, chatHistory=""):
        """Classify sampled frames, then build a safe timeline in code."""
        codebook = self._codebook_for_message(message)
        labels = self._codebook_labels(codebook)
        if not labels:
            raise LocalInferenceError(
                "The codebook has no gesture labels for visual annotation."
            )

        frames = list(self.frameContext or [])
        stride = max(1, len(frames) // self.max_visual_frames)
        selected = [
            (index, frames[index])
            for index in range(0, len(frames), stride)
        ][:self.max_visual_frames]
        segments = self._transcript_segments()
        duration = max(
            (float(segment.get("end", 0)) for segment in segments),
            default=float(max(1, len(selected))),
        )
        allowed_labels = [*labels, "NO_GESTURE"]
        schema = {
            "type": "object",
            "properties": {
                "label": {"type": "string", "enum": allowed_labels}
            },
            "required": ["label"],
            "additionalProperties": False,
        }
        request_parameters = {
            "model": self.model,
            "temperature": 0,
            "max_tokens": 32,
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "gesture_classification",
                    "strict": True,
                    "schema": schema,
                },
            },
        }
        system_prompt = (
            "Classify the visible participant gesture in one video frame. "
            "Return exactly one supplied gesture label. Return NO_GESTURE when "
            "no listed gesture is clearly visible. Do not return timeline "
            "actions, explanations, or additional fields.\n\n"
            f"GESTURE LABELS:\n{json.dumps(labels, ensure_ascii=False)}"
        )
        client = OpenAI(base_url=self.baseURL, api_key="local", timeout=900)
        classifications = []
        failed_frames = 0
        resolved_model = self.model
        for source_index, frame in selected:
            raw_response = None
            try:
                completion = client.chat.completions.create(
                    **request_parameters,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "text",
                                    "text": "Classify the gesture in this frame.",
                                },
                                {
                                    "type": "image_url",
                                    "image_url": {
                                        "url": f"data:image/jpeg;base64,{frame}"
                                    },
                                },
                            ],
                        },
                    ],
                )
                resolved_model = getattr(completion, "model", self.model)
                raw_response = completion.choices[0].message.content
                label = json.loads(raw_response).get("label")
                if label not in allowed_labels:
                    raise ValueError("response label is not in the codebook")
                if label != "NO_GESTURE" and not self._is_none_label(label):
                    timestamp = (
                        duration * source_index / max(1, len(frames) - 1)
                    )
                    classifications.append((timestamp, label))
            except (APIConnectionError, APIStatusError) as error:
                raise LocalInferenceError(
                    "The local language model service is unavailable."
                ) from error
            except (TypeError, ValueError, json.JSONDecodeError, AttributeError) as error:
                failed_frames += 1
                logger.error(
                    "Invalid local visual classification from model %s: "
                    "error=%s raw=%r",
                    self.model,
                    error,
                    raw_response,
                )

        if not classifications:
            detail = (
                f" ({failed_frames} frame responses were invalid)"
                if failed_frames
                else ""
            )
            raise LocalInferenceError(
                "The local visual model found no codebook gestures in the "
                f"sampled frames{detail}."
            )

        sample_spacing = duration / max(1, len(selected) - 1)
        half_window = max(0.05, sample_spacing / 2)
        axis_id = max(self._current_axis_ids(), default=0) + 1
        steps = [
            {
                "action": "addAxi",
                "parameters": {
                    "axisId": axis_id,
                    "axisName": self._auto_annotation_axis_name(message),
                    "axistype": "Type-in",
                },
            }
        ]
        for timestamp, label in classifications:
            start = max(0, timestamp - half_window)
            end = min(duration, timestamp + half_window)
            if end <= start:
                end = start + 0.1
            steps.append(
                {
                    "action": "addBlock",
                    "parameters": {
                        "axisId": axis_id,
                        "start": round(start, 3),
                        "end": round(end, 3),
                        "text": label,
                    },
                }
            )

        response_text = self._normalize_timeline_instruction(
            json.dumps({"type": "instruction", "steps": steps}, ensure_ascii=False),
            message,
            requires_new_axis=True,
        )
        if not json.loads(response_text)["steps"]:
            response_text = (
                "No new annotations were added because the existing axis already "
                "contains all matching spans."
            )
        self.last_run_metadata = {
            "model": {
                "provider": "local",
                "requested": self.model,
                "resolved": resolved_model,
            },
            "parameters": {
                **request_parameters,
                "sampled_frame_count": len(selected),
                "failed_frame_count": failed_frames,
                "classification_count": len(classifications),
            },
            "prompts": {"system": system_prompt, "user": message},
        }
        return response_text

    @staticmethod
    def _is_none_label(label):
        normalized_label = str(label).casefold()
        return normalized_label in {"none", "no gesture", "gesture_none"} or (
            normalized_label.endswith("_none")
        )

    def _user_content(self, message):
        """Build text-only or multimodal content from model capabilities."""
        if (
            not self.supports_visual_annotation
            or not self._requests_visual_analysis(message)
        ):
            return message

        frames = list(self.frameContext or [])
        stride = max(1, len(frames) // self.max_visual_frames)
        selected_frames = frames[::stride][:self.max_visual_frames]
        segments = self._transcript_segments()
        duration = max(
            (float(segment.get("end", 0)) for segment in segments),
            default=0,
        )
        content = [
            {
                "type": "text",
                "text": (
                    f"{message}\n\nThe following images are chronological samples "
                    "from the video. Use visible evidence to identify gestures. "
                    "Frame timestamps are approximate."
                ),
            }
        ]
        for index, frame in enumerate(selected_frames):
            approximate_time = (
                duration * index / max(1, len(selected_frames) - 1)
            )
            content.extend(
                [
                    {
                        "type": "text",
                        "text": f"Video sample near {approximate_time:.2f} seconds:",
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{frame}"
                        },
                    },
                ]
            )
        return content

    def _build_request_system_prompt(self, message, chatHistory=""):
        """Add capability-specific guidance to the shared local prompt."""
        prompt = (
            f"{self._data_view_policy_prompt()}\n\n"
            f"SELECTED DATA VIEW CONTEXTS:\n"
            f"{json.dumps(self.dataViewContexts, ensure_ascii=False, indent=2)}\n\n"
            f"{self._build_system_prompt(message, chatHistory)}"
        )
        if (
            not self.supports_visual_annotation
            or not self._requests_visual_analysis(message)
        ):
            return prompt
        return (
            f"{prompt}\n\nUse the supplied chronological video samples as "
            "visual evidence. For gesture annotation, label only gestures that "
            "are visibly supported. Use the approximate sample timestamps for "
            "block times and acknowledge uncertainty in ordinary text answers."
        )

    def _respond_chunked_auto_annotation(self, message):
        """Annotate long transcripts without producing one truncated JSON reply."""
        segments = self._transcript_segments()
        if not segments:
            raise LocalInferenceError(
                "The transcript has no timestamped segments to annotate."
            )

        original_segment_count = len(segments)
        point_time = self._point_time_from_message(message)
        if point_time is not None:
            matching_segments = [
                segment
                for segment in segments
                if float(segment["start"]) <= point_time <= float(segment["end"])
            ]
            if not matching_segments:
                nearest_distance = min(
                    max(
                        float(segment["start"]) - point_time,
                        point_time - float(segment["end"]),
                        0,
                    )
                    for segment in segments
                )
                matching_segments = [
                    segment
                    for segment in segments
                    if max(
                        float(segment["start"]) - point_time,
                        point_time - float(segment["end"]),
                        0,
                    )
                    == nearest_distance
                ]
            segments = matching_segments
        is_request_task = "request" in message.lower()
        if is_request_task:
            request_candidates = [
                segment
                for segment in segments
                if self._is_request_candidate(segment.get("text", ""))
            ]
            if request_candidates:
                segments = request_candidates

        indexed_segments = [
            {"segmentId": index, **segment}
            for index, segment in enumerate(segments)
        ]

        client = OpenAI(base_url=self.baseURL, api_key="local", timeout=900)
        codebook_context = json.dumps(
            self._codebook_for_message(message), ensure_ascii=False, indent=2
        )
        # Keep each classification response small enough for compact local
        # models to finish valid JSON. Request batches used to contain up to
        # 24 items, which regularly exhausted the output budget mid-object.
        chunk_size = 8 if is_request_task else 6
        request_parameters = {
            "model": self.model,
            "temperature": 0,
            "max_tokens": 256,
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "annotation_selections",
                    "strict": True,
                    "schema": self._annotation_selection_schema(
                        max_items=chunk_size
                    ),
                },
            },
        }
        all_blocks = []
        chunks = [
            indexed_segments[index:index + chunk_size]
            for index in range(0, len(indexed_segments), chunk_size)
        ]
        resolved_model = self.model
        failed_chunks = 0

        uses_codebook_labels = any(
            phrase in message.lower()
            for phrase in ("according to", "attitude", "codebook")
        )
        for chunk in chunks:
            chunk_response = None
            chunk_context = json.dumps(chunk, ensure_ascii=False, indent=2)
            system_prompt = f"""Select matching segments from this transcript chunk.
Apply the user's task to every segment, not only the first match. Return one
annotation for each match using only its integer segmentId. For codebook tasks,
label must be one exact codebook label. For other tasks, label may briefly
describe why the segment matches. Do not copy timestamps or transcript text.

USER TASK:
{message}

CODEBOOK:
{codebook_context}

TIMESTAMPED SEGMENTS:
{chunk_context}
"""
            try:
                completion = client.chat.completions.create(
                    **request_parameters,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": message},
                    ],
                )
                resolved_model = getattr(completion, "model", self.model)
                chunk_response = completion.choices[0].message.content
                parsed_response = json.loads(chunk_response)
                annotations = parsed_response.get("annotations", [])
                chunk_by_id = {
                    segment["segmentId"]: segment for segment in chunk
                }
                if isinstance(annotations, list):
                    for annotation in annotations:
                        if not isinstance(annotation, dict):
                            continue
                        segment = chunk_by_id.get(annotation.get("segmentId"))
                        if not segment:
                            continue
                        label = str(annotation.get("label", "")).strip()
                        if uses_codebook_labels:
                            if not label:
                                continue
                            block_text = label
                        else:
                            block_text = re.sub(
                                r"^.*?:\s*", "", segment["text"], count=1
                            ).strip()
                        all_blocks.append(
                            {
                                "start": segment["start"],
                                "end": segment["end"],
                                "text": block_text,
                            }
                        )
            except (APIConnectionError, APIStatusError) as error:
                raise LocalInferenceError(
                    "The local language model service is unavailable."
                ) from error
            except (TypeError, json.JSONDecodeError, AttributeError) as error:
                failed_chunks += 1
                logger.error(
                    "Invalid local annotation chunk from model %s: error=%s raw=%r",
                    self.model,
                    error,
                    chunk_response,
                )

        unique_blocks = []
        seen_blocks = set()
        for block in sorted(all_blocks, key=lambda item: item.get("start", 0)):
            signature = (
                block.get("start"),
                block.get("end"),
                str(block.get("text", "")).strip(),
            )
            if signature not in seen_blocks:
                seen_blocks.add(signature)
                unique_blocks.append(block)

        if not unique_blocks and is_request_task:
            unique_blocks = [
                {
                    "start": segment["start"],
                    "end": segment["end"],
                    "text": re.sub(
                        r"^.*?:\s*", "", segment["text"], count=1
                    ).strip(),
                }
                for segment in indexed_segments
            ]

        if not unique_blocks:
            raise LocalInferenceError(
                "The local model did not produce any annotation blocks. "
                "Try a more capable local model or select Remote."
            )

        axis_id = max(self._current_axis_ids(), default=0) + 1
        instruction = {
            "type": "instruction",
            "steps": [
                {
                    "action": "addAxi",
                    "parameters": {
                        "axisId": axis_id,
                        "axisName": self._auto_annotation_axis_name(message),
                        "axistype": "Type-in",
                    },
                },
                *[
                    {
                        "action": "addBlock",
                        "parameters": {"axisId": axis_id, **block},
                    }
                    for block in unique_blocks
                ],
            ],
        }
        response_text = self._normalize_timeline_instruction(
            json.dumps(instruction, ensure_ascii=False),
            message,
            requires_new_axis=True,
        )
        if not json.loads(response_text)["steps"]:
            response_text = (
                "No new annotations were added because the existing axis already "
                "contains all matching spans."
            )
        self.last_run_metadata = {
            "model": {
                "provider": "local",
                "requested": self.model,
                "resolved": resolved_model,
            },
            "parameters": {
                **request_parameters,
                "chunk_size": chunk_size,
                "chunk_count": len(chunks),
                "failed_chunks": failed_chunks,
                "original_segment_count": original_segment_count,
                "candidate_segment_count": len(segments),
            },
            "prompts": {
                "system": "Chunked transcript auto-annotation",
                "user": message,
            },
        }
        return response_text

    @staticmethod
    def _requests_code_selection(message):
        normalized_message = message.lower()
        code_words = ("code", "codebook", "label", "classify", "categorize")
        selection_words = (
            "applicable",
            "apply",
            "choose",
            "match",
            "return",
            "select",
            "which",
        )
        return any(word in normalized_message for word in code_words) and any(
            word in normalized_message for word in selection_words
        )

    @staticmethod
    def _requests_visual_analysis(message):
        normalized_message = message.lower()
        visual_words = (
            "body language",
            "facial expression",
            "frame",
            "gesture",
            "video",
            "visual",
        )
        return any(word in normalized_message for word in visual_words)

    @staticmethod
    def _requests_auto_annotation(message):
        normalized_message = message.lower()
        if any(word in normalized_message for word in ("delete", "remove", "clear")):
            return False
        annotation_words = ("annotate", "label", "classify", "categorize", "tag")
        return any(word in normalized_message for word in annotation_words) and any(
            phrase in normalized_message
            for phrase in (
                "all ",
                "according to",
                "attitude",
                "participant",
                "request utterance",
                "speech",
            )
        )

    @staticmethod
    def _auto_annotation_axis_name(message):
        normalized_message = message.lower()
        if "request" in normalized_message:
            return "Participant Requests"
        if "attitude" in normalized_message:
            return "Participant Attitudes"
        if any(
            word in normalized_message
            for word in ("gesture", "body language", "visual")
        ):
            return "Participant Gestures"
        return "Auto Annotation"

    @staticmethod
    def _is_request_candidate(text):
        normalized_text = str(text).casefold()
        return "?" in normalized_text or bool(
            re.search(
                r"\b(please|can you|could you|would you|will you|may you|"
                r"do you mind|help me|tell me|show me)\b",
                normalized_text,
            )
        )

    @staticmethod
    def _annotation_selection_schema(max_items=6):
        return {
            "type": "object",
            "properties": {
                "annotations": {
                    "type": "array",
                    "maxItems": max_items,
                    "items": {
                        "type": "object",
                        "properties": {
                            "segmentId": {"type": "integer"},
                            "label": {"type": "string"},
                        },
                        "required": ["segmentId", "label"],
                        "additionalProperties": False,
                    },
                }
            },
            "required": ["annotations"],
            "additionalProperties": False,
        }

    def _current_axis_ids(self):
        axis_ids = set()
        for axis in self.timelineContext or []:
            if not isinstance(axis, dict):
                continue
            raw_axis_id = axis.get("id", axis.get("axisId"))
            try:
                axis_ids.add(int(raw_axis_id))
            except (TypeError, ValueError):
                continue
        return axis_ids

    def _target_axis_id_from_message(self, message):
        normalized_message = str(message or "").casefold()
        matching_axes = []
        for axis in self.timelineContext or []:
            if not isinstance(axis, dict):
                continue
            axis_name = str(axis.get("axisName", "")).strip()
            raw_axis_id = axis.get("id", axis.get("axisId"))
            try:
                axis_id = int(raw_axis_id)
            except (TypeError, ValueError):
                continue
            if axis_name and axis_name.casefold() in normalized_message:
                matching_axes.append((len(axis_name), axis_id))
        return max(matching_axes, default=(0, None))[1]

    def _axis_id_by_name(self, axis_name):
        normalized_name = str(axis_name or "").strip().casefold()
        for axis in self.timelineContext or []:
            if not isinstance(axis, dict):
                continue
            if str(axis.get("axisName", "")).strip().casefold() != normalized_name:
                continue
            try:
                return int(axis.get("id", axis.get("axisId")))
            except (TypeError, ValueError):
                return None
        return None

    def _block_overlaps_existing(self, axis_id, parameters):
        try:
            new_start = float(parameters.get("start"))
            new_end = float(parameters.get("end"))
        except (TypeError, ValueError):
            return False
        for axis in self.timelineContext or []:
            if not isinstance(axis, dict):
                continue
            try:
                matches_axis = int(axis.get("id", axis.get("axisId"))) == axis_id
            except (TypeError, ValueError):
                matches_axis = False
            if not matches_axis:
                continue
            for block in axis.get("blocks", []):
                if not isinstance(block, dict):
                    continue
                try:
                    start = float(block.get("start"))
                    end = float(block.get("end"))
                except (TypeError, ValueError):
                    continue
                if new_start <= end and new_end >= start:
                    return True
        return False

    @staticmethod
    def _point_time_from_message(message):
        message_text = str(message or "")
        match = re.search(
            r"\b(?:at|from)\s+(\d+(?:\.\d+)?)\s*(?:s|sec|second)s?\b",
            message_text,
            re.IGNORECASE,
        )
        if not match:
            match = re.search(
                r"\b(\d+(?:\.\d+)?)\s*(?:s|sec|second)s?\b",
                message_text,
                re.IGNORECASE,
            )
        return float(match.group(1)) if match else None

    def _block_index_at_time(self, axis_id, point_time):
        if point_time is None:
            return None
        for axis in self.timelineContext or []:
            if not isinstance(axis, dict):
                continue
            raw_axis_id = axis.get("id", axis.get("axisId"))
            try:
                matches_axis = int(raw_axis_id) == axis_id
            except (TypeError, ValueError):
                matches_axis = False
            if not matches_axis:
                continue
            block_key = (
                "blocks" if isinstance(axis.get("blocks"), list)
                else "annotationBlocks"
            )
            for block_index, block in enumerate(axis.get(block_key, [])):
                if not isinstance(block, dict):
                    continue
                try:
                    start = float(block.get("start"))
                    end = float(block.get("end"))
                except (TypeError, ValueError):
                    continue
                if start <= point_time <= end:
                    original_index = block.get("blockIndex")
                    return (
                        original_index
                        if type(original_index) is int and original_index >= 0
                        else block_index
                    )
        return None

    @staticmethod
    def _repair_manual_block(parameters, message):
        start_match = re.search(
            r"\b(?:at|from)\s+(\d+(?:\.\d+)?)\s*(?:s|sec|second)s?\b",
            str(message or ""),
            re.IGNORECASE,
        )
        end_match = re.search(
            r"\bto\s+(\d+(?:\.\d+)?)\s*(?:s|sec|second)s?\b",
            str(message or ""),
            re.IGNORECASE,
        )
        try:
            start = float(parameters.get("start"))
        except (TypeError, ValueError):
            start = float(start_match.group(1)) if start_match else None
        if start is None:
            return

        try:
            end = float(parameters.get("end"))
        except (TypeError, ValueError):
            end = float(end_match.group(1)) if end_match else start + 1.0
        if end <= start:
            end = start + 1.0

        parameters["start"] = start
        parameters["end"] = end
        if not str(parameters.get("text", "")).strip():
            parameters["text"] = "New annotation"

    def _normalize_timeline_instruction(
        self, response_text, message="", requires_new_axis=False
    ):
        """Make model-selected IDs safe for the current timeline."""
        try:
            instruction = json.loads(response_text)
        except (TypeError, json.JSONDecodeError) as error:
            raise LocalInferenceError(
                "The local language model returned an invalid timeline instruction."
            ) from error

        if instruction.get("type") != "instruction" or not isinstance(
            instruction.get("steps"), list
        ):
            raise LocalInferenceError(
                "The local language model returned an invalid timeline instruction."
            )

        used_axis_ids = self._current_axis_ids()
        target_axis_id = self._target_axis_id_from_message(message)
        if requires_new_axis and target_axis_id is None:
            target_axis_id = self._axis_id_by_name(
                self._auto_annotation_axis_name(message)
            )
        if target_axis_id is not None:
            instruction["steps"] = [
                step
                for step in instruction["steps"]
                if not isinstance(step, dict) or step.get("action") != "addAxi"
            ]
            for step in instruction["steps"]:
                if not isinstance(step, dict):
                    continue
                parameters = step.get("parameters")
                if not isinstance(parameters, dict):
                    continue
                if step.get("action") == "addBlock":
                    parameters["axisId"] = target_axis_id
                    self._repair_manual_block(parameters, message)
                elif step.get("action") == "deleteBlock":
                    parameters["axisId"] = target_axis_id
                    block_index = self._block_index_at_time(
                        target_axis_id,
                        self._point_time_from_message(message),
                    )
                    if block_index is not None:
                        parameters["blockIndex"] = block_index
        next_axis_id = max(used_axis_ids, default=0) + 1
        remapped_axis_ids = {}
        for step in instruction["steps"]:
            if not isinstance(step, dict) or not isinstance(
                step.get("parameters"), dict
            ):
                continue
            parameters = step["parameters"]
            original_axis_id = parameters.get("axisId")

            if step.get("action") == "addAxi":
                while next_axis_id in used_axis_ids:
                    next_axis_id += 1
                remapped_axis_ids[original_axis_id] = next_axis_id
                parameters["axisId"] = next_axis_id
                used_axis_ids.add(next_axis_id)
                next_axis_id += 1
            elif original_axis_id in remapped_axis_ids:
                parameters["axisId"] = remapped_axis_ids[original_axis_id]

            if step.get("action") == "addBlock":
                self._ground_block_timestamp(parameters)

        available_axis_ids = used_axis_ids | {
            int(step["parameters"]["axisId"])
            for step in instruction["steps"]
            if isinstance(step, dict)
            and step.get("action") == "addAxi"
            and isinstance(step.get("parameters"), dict)
            and isinstance(step["parameters"].get("axisId"), int)
        }
        add_block_steps = [
            step
            for step in instruction["steps"]
            if isinstance(step, dict)
            and step.get("action") == "addBlock"
            and isinstance(step.get("parameters"), dict)
        ]
        has_add_axis = any(
            isinstance(step, dict) and step.get("action") == "addAxi"
            for step in instruction["steps"]
        )
        if (
            requires_new_axis
            and add_block_steps
            and not has_add_axis
            and target_axis_id is None
        ):
            while next_axis_id in available_axis_ids:
                next_axis_id += 1
            repaired_axis_id = next_axis_id
            next_axis_id += 1
            available_axis_ids.add(repaired_axis_id)
            for step in add_block_steps:
                step["parameters"]["axisId"] = repaired_axis_id
            instruction["steps"].insert(
                0,
                {
                    "action": "addAxi",
                    "parameters": {
                        "axisId": repaired_axis_id,
                        "axisName": self._auto_annotation_axis_name(message),
                        "axistype": "Type-in",
                    },
                },
            )

        orphan_axis_ids = []
        for step in instruction["steps"]:
            if not isinstance(step, dict) or step.get("action") != "addBlock":
                continue
            parameters = step.get("parameters")
            if not isinstance(parameters, dict):
                continue
            try:
                axis_id = int(parameters.get("axisId"))
            except (TypeError, ValueError):
                continue
            if axis_id not in available_axis_ids and axis_id not in orphan_axis_ids:
                orphan_axis_ids.append(axis_id)

        for orphan_axis_id in orphan_axis_ids:
            while next_axis_id in available_axis_ids:
                next_axis_id += 1
            repaired_axis_id = next_axis_id
            next_axis_id += 1
            available_axis_ids.add(repaired_axis_id)
            for step in instruction["steps"]:
                parameters = step.get("parameters") if isinstance(step, dict) else None
                if not isinstance(parameters, dict):
                    continue
                try:
                    references_orphan = int(parameters.get("axisId")) == orphan_axis_id
                except (TypeError, ValueError):
                    references_orphan = False
                if references_orphan:
                    parameters["axisId"] = repaired_axis_id
            instruction["steps"].insert(
                0,
                {
                    "action": "addAxi",
                    "parameters": {
                        "axisId": repaired_axis_id,
                        "axisName": self._auto_annotation_axis_name(message),
                        "axistype": "Type-in",
                    },
                },
            )

        if requires_new_axis:
            safe_steps = []
            for step in instruction["steps"]:
                if not isinstance(step, dict):
                    continue
                action = step.get("action")
                parameters = step.get("parameters")
                if not isinstance(parameters, dict):
                    continue
                if action == "addAxi":
                    safe_steps.append(step)
                    continue
                if action != "addBlock":
                    continue
                try:
                    start = float(parameters.get("start"))
                    end = float(parameters.get("end"))
                except (TypeError, ValueError):
                    continue
                if end < start or not str(parameters.get("text", "")).strip():
                    continue
                parameters["start"] = start
                parameters["end"] = end
                if (
                    target_axis_id is not None
                    and self._block_overlaps_existing(target_axis_id, parameters)
                ):
                    continue
                safe_steps.append(step)
            instruction["steps"] = safe_steps

        return json.dumps(instruction, ensure_ascii=False)

    def _ground_block_timestamp(self, parameters):
        try:
            start = float(parameters.get("start"))
            end = float(parameters.get("end"))
            if end > start:
                return
        except (TypeError, ValueError):
            pass

        block_text = str(parameters.get("text", "")).strip().casefold()
        if not block_text:
            return

        for segment in self._transcript_segments():
            segment_text = segment["text"].casefold()
            if block_text in segment_text or segment_text in block_text:
                parameters["start"] = segment["start"]
                parameters["end"] = segment["end"]
                return

    def _transcript_segments(self):
        segments = []
        bracketed_line = re.compile(
            r"^\[(\d+):(\d+(?:\.\d+)?)\]\s*(.*?)\s*"
            r"\[(\d+):(\d+(?:\.\d+)?)\]$"
        )
        for line in str(self.transcriptContext or "").splitlines():
            match = bracketed_line.match(line.strip())
            if match:
                segments.append(
                    {
                        "start": int(match.group(1)) * 60 + float(match.group(2)),
                        "end": int(match.group(4)) * 60 + float(match.group(5)),
                        "text": match.group(3).strip(),
                    }
                )

        if segments:
            return segments

        srt_block = re.compile(
            r"(?:^|\n)\d+\s*\n"
            r"(\d{2}):(\d{2}):(\d{2})[,.](\d{3})\s*-->\s*"
            r"(\d{2}):(\d{2}):(\d{2})[,.](\d{3})\s*\n"
            r"(.*?)(?=\n\n|\Z)",
            re.DOTALL,
        )
        for match in srt_block.finditer(str(self.transcriptContext or "")):
            segments.append(
                {
                    "start": self._srt_time_to_seconds(*match.groups()[0:4]),
                    "end": self._srt_time_to_seconds(*match.groups()[4:8]),
                    "text": match.group(9).strip(),
                }
            )
        return segments

    @staticmethod
    def _srt_time_to_seconds(hours, minutes, seconds, milliseconds):
        return (
            int(hours) * 3600
            + int(minutes) * 60
            + int(seconds)
            + int(milliseconds) / 1000
        )

    @staticmethod
    def _timeline_instruction_schema(min_steps=1):
        return {
            "type": "object",
            "properties": {
                "type": {"type": "string", "const": "instruction"},
                "steps": {
                    "type": "array",
                    "minItems": min_steps,
                    "maxItems": 64,
                    "items": {
                        "type": "object",
                        "properties": {
                            "action": {
                                "type": "string",
                                "enum": [
                                    "addAxi",
                                    "addBlock",
                                    "deleteBlock",
                                    "deleteAxi",
                                ],
                            },
                            "parameters": {
                                "type": "object",
                                "properties": {
                                    "axisId": {"type": "integer"},
                                    "axisName": {"type": "string"},
                                    "axistype": {
                                        "type": "string",
                                        "const": "Type-in",
                                    },
                                    "start": {"type": "number"},
                                    "end": {"type": "number"},
                                    "text": {"type": "string"},
                                    "blockIndex": {"type": "integer"},
                                },
                                "required": ["axisId"],
                                "additionalProperties": False,
                            },
                        },
                        "required": ["action", "parameters"],
                        "additionalProperties": False,
                    },
                },
            },
            "required": ["type", "steps"],
            "additionalProperties": False,
        }

    def _build_system_prompt(self, message, chatHistory=""):
        codebook_context = json.dumps(
            self._codebook_for_message(message), ensure_ascii=False, indent=2
        )
        history = str(chatHistory or "")[-2000:]
        transcript_prompt = f"""TRANSCRIPT:
{self.transcriptContext}

PREVIOUS CHAT HISTORY:
{history}
"""

        if self._is_timeline_request(message):
            timeline_context = json.dumps(
                self.timelineContext, ensure_ascii=False, indent=2
            )
            next_axis_id = max(self._current_axis_ids(), default=0) + 1
            return f"""You control the qualitative annotation timeline.
Complete the entire requested auto-annotation task within the timeline scope below.
When new-axis permission is false, do not return addAxi and put changes only on the
listed existing axis IDs. When new-axis permission is true and no existing axis is
selected, return addAxi first and then addBlock steps for the new axis. Include one
addBlock step for every applicable utterance or span. Do not stop after the first match.

Use the SRT timestamps as evidence and convert HH:MM:SS,mmm timestamps to
seconds for block start and end. A request utterance asks another participant
to do or provide something. For attitudes, apply the supplied codebook to each
relevant utterance and use its exact label. Never invent codebook labels.

{transcript_prompt}

CODEBOOK:
{codebook_context}

CURRENT TIMELINE:
{timeline_context}

{self._timeline_scope_prompt()}

Return only one valid JSON object.
The object must have type "instruction" and a steps array. Allowed steps are:
- addAxi with integer axisId, string axisName, and axistype "Type-in".
- addBlock with integer axisId, numeric start, numeric end, and text set to an
  exact codebook label.
- deleteBlock with integer axisId and integer blockIndex.
- deleteAxi with integer axisId.

When a CURRENT TIMELINE block includes blockIndex, copy that exact value into
deleteBlock. It is the block's position in the full timeline, even when the
current context contains only a selected time range.

"Delete annotations" or "delete all annotations" means return deleteBlock steps
for the matching blocks and preserve the axes. Return deleteAxi only when the user
explicitly asks to delete an axis or timeline.

The next unused axisId is {next_axis_id}. Use it for the new axis and every block.
Every new axis name must be unique. If multiple axes share a topic, number them
as "Topic 1", "Topic 2", and so on. Never reuse a current timeline name.
For addBlock, use an exact codebook label as text when the user asks for
codebook annotation; otherwise use concise transcript-grounded text. Use the same axisId
for its blocks. Do not create overlapping blocks on one axis. Include all
applicable transcript spans, ordered by start time."""

        if self._requests_code_selection(message):
            return f"""Classify the transcript using the qualitative codebook.
Use only exact label values from the codebook and never invent a label.
Return only the matching label or labels. Return None only when no label applies.

CODEBOOK:
{codebook_context}

{transcript_prompt}"""

        return f"""Answer the user's request using the transcript as the primary source.
If asked to summarize, provide a concise factual summary. Do not classify the
transcript and do not answer None unless the user explicitly requests codebook
classification and no code applies. Plain text is required.

{transcript_prompt}"""


class QwenLocalAI(LocalAI):
    """Local Qwen text model."""

    model_name = "qwen2.5-0.5b-instruct-q4_k_m"


class LlamaLocalAI(LocalAI):
    """Local Llama text model."""

    model_name = "llama-3.2-1b-instruct-q4_k_m"


class SmolVLM2LocalAI(LocalAI):
    """Configuration for local SmolVLM2 multimodal inference."""

    model_name = "SmolVLM2-500M-Video-Instruct-Q8_0"
    supports_visual_annotation = True


def create_local_ai(**kwargs):
    """Build the appropriate local-model child from ``LOCAL_AI_MODEL``."""
    model = os.getenv("LOCAL_AI_MODEL", QwenLocalAI.model_name)
    normalized_model = model.casefold()
    if "smolvlm2" in normalized_model:
        model_class = SmolVLM2LocalAI
    elif "llama" in normalized_model:
        model_class = LlamaLocalAI
    else:
        model_class = QwenLocalAI
    return model_class(model=model, **kwargs)
