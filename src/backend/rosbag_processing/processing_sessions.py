"""HTTP-independent contracts for whole-bag and chunk processing.

Times are seconds. Chunk bounds are relative to bag start; generated media and
transcripts are chunk-local. Media paths returned to callers are relative to
/app/processed_data. Operational exceptions propagate to the HTTP adapter.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
import math
from typing import Any, List, Optional, TypedDict, final


class SpeakerSegment(TypedDict):
    start_time: float
    end_time: float
    speaker_label: str
    text: str


class ResultMetadata(TypedDict, total=False):
    message: str
    booklist_data: Any
    annotation_data: Any
    index: int
    start_seconds: float
    end_seconds: float
    duration_seconds: float
    previous_index: Optional[int]
    next_index: Optional[int]
    status: str


class ProcessingResult(ResultMetadata):
    video_path: str
    audio_path: Optional[str]
    waveform_image_path: Optional[str]
    audio_transcript: str
    speaker_data: List[SpeakerSegment]


class ChunkMetadata(TypedDict, total=False):
    duration_seconds: float
    previous_index: Optional[int]
    next_index: Optional[int]
    status: str


class ChunkSpec(ChunkMetadata):
    index: int
    start_seconds: float
    end_seconds: float


@dataclass(frozen=True)
class ProcessingRequest:
    bag_path: str
    processed_root: str = '/app/processed_data'
    booklist_filename: Optional[str] = None
    annotation_filename: Optional[str] = None
    manifest_id: Optional[str] = None
    chunk: Optional[ChunkSpec] = None
    view_options: Optional[dict] = None
    view_ids: Optional[List[str]] = None


class ProcessingError(Exception):
    """An expected failure with the legacy API's HTTP status."""

    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.status_code = status_code


class BaseDataProcessingSession(ABC):
    """Subclasses implement hooks, callers use process(request) exclusively.

    Hooks receive the same immutable request. Cached and fresh results obey
    the same contract; extra keys (e.g. chunk bounds) are preserved.
    """

    @final
    def process(self, request: ProcessingRequest) -> ProcessingResult:
        self._validate(request)
        result = self._load_cached(request)
        if result is None:
            result = self._run(request)
        result = self._finalize(request, result)
        self._validate_result(result)
        return result

    def _validate(self, request: ProcessingRequest) -> None:
        """Raise ValueError or ProcessingError before processing invalid input."""
        if not isinstance(request.bag_path, str) or not request.bag_path:
            raise ValueError('bag_path is required')
        if not isinstance(request.processed_root, str) or not request.processed_root:
            raise ValueError('processed_root is required')

    def _load_cached(self, request: ProcessingRequest) -> Optional[ProcessingResult]:
        """Return reusable artifacts, or None when processing is required."""
        return None

    @abstractmethod
    def _run(self, request: ProcessingRequest) -> ProcessingResult:
        """Create artifacts; propagate processing failures to the caller."""
        raise NotImplementedError

    def _finalize(self, request: ProcessingRequest, result: ProcessingResult) -> ProcessingResult:
        """Attach session metadata to either cached or fresh artifacts."""
        return result

    @staticmethod
    def _validate_result(result: ProcessingResult) -> None:
        """Reject a broken subclass contract before it reaches the frontend."""
        if not isinstance(result, dict):
            raise TypeError('ProcessingResult must be a dictionary')
        for field in ('video_path', 'audio_transcript'):
            if not isinstance(result.get(field), str):
                raise TypeError(f'{field} must be a string')
        for field in ('audio_path', 'waveform_image_path'):
            if field not in result or (result[field] is not None and not isinstance(result[field], str)):
                raise TypeError(f'{field} must be a string or None')
        if not isinstance(result.get('speaker_data'), list):
            raise TypeError('speaker_data must be a list')
        for segment in result['speaker_data']:
            if not isinstance(segment, dict):
                raise TypeError('Each speaker segment must be a dictionary')
            for field in ('text', 'speaker_label'):
                if not isinstance(segment.get(field), str):
                    raise TypeError(f'Speaker {field} must be a string')
            for field in ('start_time', 'end_time'):
                value = segment.get(field)
                if type(value) not in (int, float) or not math.isfinite(value):
                    raise TypeError(f'Speaker {field} must be finite seconds')
