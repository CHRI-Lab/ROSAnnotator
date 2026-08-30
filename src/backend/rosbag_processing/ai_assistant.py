from abc import ABC, abstractmethod
import json

from openai import OpenAI


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

    def respond(self, message, chatHistory=""):
        """Return raw assistant text using the shared provider contract."""
        return self._respond(message, chatHistory)

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
        client = OpenAI(api_key=self.APIKey)
        timeline_context = json.dumps(self.timelineContext, indent=2)

        prompt = f"""
        User want you based on the audio_transcript and video frames answer some qustion 
        Now, based on this transcript and frames, answer the following question:

        {message}
        If the question not relative with audio and video, you dont need to watch the following data.
        Here is the audio transcription:
        {self.transcriptContext}
        Here is the video frames
        """

        chat_completion = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {
                    "role": "system",
                    "content": f"""
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


                    """,
                },
                {
                    "role": "user",
                    "content": [
                        prompt,
                        *map(
                            lambda frame: {"image": frame},
                            self.frameContext[
                                0::max(1, len(self.frameContext) // 50)
                            ][:50],
                        ),
                    ],
                },
            ],
        )

        return chat_completion.choices[0].message.content


class LocalAI(AIAssistant):
    """Black-box boundary for a future local annotation model."""

    def __init__(
        self,
        transcriptContext,
        frameContext,
        codebookContext,
        timelineContext,
        checkpointPath,
    ):
        super().__init__(
            transcriptContext=transcriptContext,
            frameContext=frameContext,
            codebookContext=codebookContext,
            timelineContext=timelineContext,
        )
        self.checkpointPath = checkpointPath

    def _respond(self, message, chatHistory=""):
        raise NotImplementedError(
            "LocalAI is a black box until a local model implementation is provided."
        )
