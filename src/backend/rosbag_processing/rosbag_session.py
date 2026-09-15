"""Whole-bag processing behind the shared session interface."""
import base64
import json
import os
from pathlib import Path
from typing import List, Optional

from .processing_sessions import (
    BaseDataProcessingSession, ProcessingError, ProcessingRequest, ProcessingResult, SpeakerSegment,
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

    def _result(self, request: ProcessingRequest, transcript: str,
                speakers: List[SpeakerSegment], message: str) -> ProcessingResult:
        folder = self._folder(request)

        def relative(filename):
            return os.path.relpath(folder / filename, '/app/processed_data').replace(os.sep, '/')

        return {
            'video_path': relative('output.mp4'),
            'audio_path': relative('audio.mp3'),
            'waveform_image_path': relative('output_waveform.png'),
            'audio_transcript': transcript,
            'speaker_data': speakers,
            'message': message,
        }

    def _load_cached(self, request: ProcessingRequest) -> Optional[ProcessingResult]:
        folder = self._folder(request)
        if not all((folder / name).is_file() for name in (
            'output.mp4', 'audio.mp3', 'output_waveform.png', 'transcript_with_speakers.srt',
        )):
            return None
        # Older caches contain no structured speaker data. Keep them usable.
        speakers_path = folder / 'speaker_data.json'
        speakers = json.loads(speakers_path.read_text(encoding='utf-8')) if speakers_path.is_file() else []
        with (folder / 'transcript_with_speakers.srt').open() as stream:
            transcript = stream.read()
        return self._result(request, transcript, speakers, 'File already processed')

    def _run(self, request: ProcessingRequest) -> ProcessingResult:
        from . import data_utils as media

        folder = self._folder(request)
        (folder / 'images').mkdir(parents=True, exist_ok=True)
        output = str(folder)
        audio = str(folder / 'audio.mp3')
        media.extract_images_from_rosbag(request.bag_path, output)
        media.extract_audio(request.bag_path, output)
        media.plot_waveform(audio, str(folder / 'output_waveform.png'))
        media.extract_video(request.bag_path, output)
        _, transcript, speakers = media.transcribe_audio_to_srt(audio, output)
        media.combine_video_audio(output)
        temporary = folder / 'speaker_data.json.tmp'
        temporary.write_text(json.dumps(speakers, allow_nan=False), encoding='utf-8')
        os.replace(temporary, folder / 'speaker_data.json')
        return self._result(request, transcript, speakers, 'Processing complete')

    def _finalize(self, request: ProcessingRequest, result: ProcessingResult) -> ProcessingResult:
        from . import data_utils as media

        booklist_data = {}
        if request.booklist_filename:
            with (Path('/app/datas/booklist') / request.booklist_filename).open() as stream:
                booklist_data = json.load(stream)
        annotation_data = None
        if request.annotation_filename:
            try:
                annotation_data = media.load_annotation(request.annotation_filename)
            except Exception as exc:
                raise ProcessingError(f'Error loading annotation data: {exc}', 500) from exc

        # Preserve frame filtering used by the existing chat integration.
        cv2 = media.cv2
        video = cv2.VideoCapture(str(self._folder(request) / 'output.mp4'))
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
        finally:
            video.release()
        self.video_frames = frames
        return {**result, 'booklist_data': booklist_data, 'annotation_data': annotation_data}
