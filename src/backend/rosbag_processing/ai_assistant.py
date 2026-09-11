from abc import ABC, abstractmethod
import json
import os
import re

from openai import APIConnectionError, APIStatusError, AuthenticationError, OpenAI


class RemoteAuthenticationError(RuntimeError):
    """The remote provider rejected its configured credentials."""


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
    ):
        self.transcriptContext = transcriptContext
        self.frameContext = frameContext
        self.codebookContext = codebookContext
        self.timelineContext = timelineContext
        self.last_run_metadata = {}

    def respond(self, message, chatHistory=""):
        """Return raw assistant text using the shared provider contract."""
        return self._respond(message, chatHistory)

    def get_run_metadata(self):
        """Return safe provider metadata for the most recent response."""
        return self.last_run_metadata

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
    ):
        super().__init__(
            transcriptContext=transcriptContext,
            frameContext=frameContext,
            codebookContext=codebookContext,
            timelineContext=timelineContext,
        )
        self.APIKey = APIKey

    def _respond(self, message, chatHistory=""):
        try:
            return self._request_completion(message, chatHistory)
        except AuthenticationError as error:
            raise RemoteAuthenticationError from error

    def _request_completion(self, message, chatHistory=""):
        client = OpenAI(api_key=self.APIKey)
        timeline_context = json.dumps(self.timelineContext, indent=2)
        selected_frames = self.frameContext[
            0::max(1, len(self.frameContext) // 50)
        ][:50]

        prompt = f"""
        User want you based on the audio_transcript and video frames answer some qustion 
        Now, based on this transcript and frames, answer the following question:

        {message}
        If the question not relative with audio and video, you dont need to watch the following data.
        Here is the audio transcription:
        {self.transcriptContext}
        Here is the video frames
        """

        system_prompt = f"""
                    You are an assistant that can manipulate timelines. Based on the audio transcript, here are the actions you can perform:
                    
                    1. Add a new `axi`: Method: `addAxi`, Parameters: `axisId` (integer),'axisName' (string),'axistype' (string).
                    2. Add a new `block`: Method: `addBlock`, Parameters: `axisId` (integer), `start` (float), `end` (float), `text` (string).
                    3. Delete a old 'block':Mthod:'deleteBlock', Parameters: `axisId` (integer), 'blockIndex' (integer).
                    4. Delete a old 'axi':Mthod:'deleteAxi', Parameters: `axisId` (integer).
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
                    Remove axi could remove all blocks in the axi.
                    Axi type always equal "Type-in"
                    Always create steps, even there only one step.
                    The newest axi id will be current largest id+1.
                    Overlap with other block in one axi will lead to error.
                    If the response is a normal conversation, return the plain text as usual.
                    Here is the current Axi information, you can consider axiId based on this:

                    {timeline_context}

                    Here is the Codebook predefined by user:

                    {self.codebookContext}
                    
                    Here is previous chat history between you and user:

                    {chatHistory}


                    """
        request_parameters = {"model": "gpt-4o"}
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

    def __init__(
        self,
        transcriptContext,
        frameContext,
        codebookContext,
        timelineContext,
        checkpointPath,
        model=None,
    ):
        super().__init__(
            transcriptContext=transcriptContext,
            frameContext=frameContext,
            codebookContext=codebookContext,
            timelineContext=timelineContext,
        )
        self.checkpointPath = checkpointPath
        self.baseURL = os.getenv("LOCAL_AI_BASE_URL", "http://local-llm:8080/v1")
        self.model = model or self.model_name
        if not self.model:
            raise ValueError("A local model subclass must define model_name.")

    def _respond(self, message, chatHistory=""):
        if (
            not self.supports_visual_annotation
            and self._requests_visual_analysis(message)
        ):
            raise LocalInferenceError(
                f"The selected local model ({self.model}) is text-only and cannot "
                "perform gesture annotation or inspect video frames. Select a "
                "vision-capable model or Remote for video-based annotation."
            )

        is_timeline_request = self._requests_timeline_change(message)
        is_auto_annotation = self._requests_auto_annotation(message)
        if is_auto_annotation and len(str(self.transcriptContext or "")) > 4000:
            return self._respond_chunked_auto_annotation(message)

        system_prompt = self._build_system_prompt(message, chatHistory)
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
                    {"role": "user", "content": message},
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
            response_text = self._normalize_timeline_instruction(response_text)
            if is_auto_annotation:
                instruction = json.loads(response_text)
                if not any(
                    step.get("action") == "addBlock"
                    for step in instruction["steps"]
                    if isinstance(step, dict)
                ):
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

    def _respond_chunked_auto_annotation(self, message):
        """Annotate long transcripts without producing one truncated JSON reply."""
        segments = self._transcript_segments()
        if not segments:
            raise LocalInferenceError(
                "The transcript has no timestamped segments to annotate."
            )

        original_segment_count = len(segments)
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
            self.codebookContext, ensure_ascii=False, indent=2
        )
        chunk_size = 24 if is_request_task else 6
        request_parameters = {
            "model": self.model,
            "temperature": 0,
            "max_tokens": 128,
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
            except (TypeError, json.JSONDecodeError, AttributeError):
                failed_chunks += 1

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
            json.dumps(instruction, ensure_ascii=False)
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
    def _requests_timeline_change(message):
        normalized_message = message.lower()
        action_words = ("annotate", "add", "create", "delete", "remove")
        timeline_words = ("timeline", "axis", "axi", "block", "annotation")
        return any(word in normalized_message for word in action_words) and any(
            word in normalized_message for word in timeline_words
        )

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
        return "annotate" in normalized_message and any(
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

    def _normalize_timeline_instruction(self, response_text):
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
            self.codebookContext, ensure_ascii=False, indent=2
        )
        history = str(chatHistory or "")[-2000:]
        transcript_prompt = f"""TRANSCRIPT:
{self.transcriptContext}

PREVIOUS CHAT HISTORY:
{history}
"""

        if self._requests_timeline_change(message):
            timeline_context = json.dumps(
                self.timelineContext, ensure_ascii=False, indent=2
            )
            next_axis_id = max(self._current_axis_ids(), default=0) + 1
            return f"""You control the qualitative annotation timeline.
Complete the entire requested auto-annotation task. Create exactly one new
axis unless the user explicitly requests more. For a request that only asks
for an axis, return one addAxi step and do not add blocks. Otherwise return the
addAxi step first, followed by one addBlock step for every applicable utterance
or span in the full transcript. Do not stop after the first match.

Use the SRT timestamps as evidence and convert HH:MM:SS,mmm timestamps to
seconds for block start and end. A request utterance asks another participant
to do or provide something. For attitudes, apply the supplied codebook to each
relevant utterance and use its exact label. Never invent codebook labels.

{transcript_prompt}

CODEBOOK:
{codebook_context}

CURRENT TIMELINE:
{timeline_context}

Return only one valid JSON object.
The object must have type "instruction" and a steps array. Allowed steps are:
- addAxi with integer axisId, string axisName, and axistype "Type-in".
- addBlock with integer axisId, numeric start, numeric end, and text set to an
  exact codebook label.
- deleteBlock with integer axisId and integer blockIndex.
- deleteAxi with integer axisId.

The next unused axisId is {next_axis_id}. Use it for the new axis and every block.
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


def create_local_ai(**kwargs):
    """Build the appropriate local-model child from ``LOCAL_AI_MODEL``."""
    model = os.getenv("LOCAL_AI_MODEL", QwenLocalAI.model_name)
    model_class = LlamaLocalAI if "llama" in model.casefold() else QwenLocalAI
    return model_class(model=model, **kwargs)
