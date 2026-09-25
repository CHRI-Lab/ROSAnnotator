"""Whole-bag processing behind the shared session interface."""
import base64
from pathlib import Path

from .processing_sessions import (
    BaseDataProcessingSession, ProcessingError, ProcessingRequest, ProcessingResult,
)


class RosbagProcessingSession(BaseDataProcessingSession):
    def __init__(self):
        # Retained for the existing chat adapter; never included in API JSON.
        self.video_frames = []
        self.video_fps = 30

    @staticmethod
    def _folder(request: ProcessingRequest) -> Path:
        return Path(request.processed_root) / Path(request.bag_path).name

    def _validate(self, request: ProcessingRequest) -> None:
        super()._validate(request)
        if request.chunk is not None or request.manifest_id is not None:
            raise ValueError('Whole-bag processing does not accept a chunk')
        if not Path(request.bag_path).is_file():
            raise ProcessingError('Invalid bag filename')
        for filename, directory, label in (
            (request.booklist_filename, '/app/datas/booklist', 'booklist'),
            (request.annotation_filename, '/app/datas/annotation', 'annotation'),
        ):
            if filename and not (Path(directory) / filename).is_file():
                raise ProcessingError(f'Invalid {label} filename')

    def _run(self, request: ProcessingRequest) -> ProcessingResult:
        from .view_workflow import process_views
        return {**process_views(request), 'message': 'Processing complete'}

    def _finalize(self, request: ProcessingRequest, result: ProcessingResult) -> ProcessingResult:
        from .view_metadata import attach_metadata
        result = attach_metadata(result, request.booklist_filename, request.annotation_filename)
        if not result.get('video_path') or (request.view_ids is not None and 'video' not in request.view_ids):
            return result
        # Optional chat frames must not make a playable view fail.
        try:
            import cv2
        except ImportError:
            return result
        video = cv2.VideoCapture(str(Path('/app/processed_data') / result['video_path']))
        frames = []
        try:
            self.video_fps = int(video.get(cv2.CAP_PROP_FPS)) or 30
            cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
            while video.isOpened():
                success, frame = video.read()
                if not success:
                    break
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                if len(cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(30, 30))):
                    continue
                success, buffer = cv2.imencode('.jpg', frame)
                if success:
                    frames.append(base64.b64encode(buffer).decode('utf-8'))
        except Exception:
            frames = []
        finally:
            video.release()
        self.video_frames = frames
        return result
