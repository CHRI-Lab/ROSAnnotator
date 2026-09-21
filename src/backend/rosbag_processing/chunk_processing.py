"""On-demand processing for one ROSBag time range at a time."""
import json
import os
import subprocess
from pathlib import Path

import cv2
from cv_bridge import CvBridge
from genpy import Time
from rosbag.bag import Bag

from .data_utils import plot_waveform, transcribe_audio_to_srt


VIDEO_TOPIC = '/xtion/rgb/image_raw_throttled'
AUDIO_TOPIC = '/audio'


def _run(command):
    subprocess.run(command, check=True, capture_output=True, text=True)


def _relative_processed_path(path):
    return os.path.relpath(path, '/app/processed_data').replace(os.sep, '/')


def process_chunk(bag_path, manifest_id, chunk, processed_root='/app/processed_data/chunks'):
    """Create and cache media/transcript artifacts for one manifest chunk."""
    chunk_root = Path(processed_root) / str(manifest_id) / f"{chunk['index']:04d}"
    result_path = chunk_root / 'result.json'
    if result_path.is_file():
        with result_path.open(encoding='utf-8') as stream:
            return json.load(stream)

    chunk_root.mkdir(parents=True, exist_ok=True)
    lock_path = chunk_root / '.processing'
    try:
        lock_descriptor = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.close(lock_descriptor)
    except FileExistsError as exc:
        raise RuntimeError('This chunk is already being processed.') from exc

    try:
        images_root = chunk_root / 'images'
        images_root.mkdir(exist_ok=True)
        audio_path = chunk_root / 'audio.mp3'
        video_only_path = chunk_root / 'video.avi'
        output_path = chunk_root / 'output.mp4'
        waveform_path = chunk_root / 'output_waveform.png'

        bridge = CvBridge()
        frame_times = []
        audio_messages = 0
        bag = Bag(str(bag_path), 'r')
        try:
            bag_start = bag.get_start_time()
            start = Time.from_sec(bag_start + chunk['start_seconds'])
            end = Time.from_sec(bag_start + chunk['end_seconds'])
            with audio_path.open('wb') as audio_stream:
                frame_index = 0
                for topic, message, timestamp in bag.read_messages(
                    topics=[VIDEO_TOPIC, AUDIO_TOPIC], start_time=start, end_time=end,
                ):
                    if topic == VIDEO_TOPIC:
                        image = bridge.imgmsg_to_cv2(message, desired_encoding='passthrough')
                        image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
                        frame_path = images_root / f'frame{frame_index:06d}.jpg'
                        if not cv2.imwrite(str(frame_path), image):
                            raise RuntimeError(f'Unable to write video frame {frame_index}.')
                        frame_times.append(timestamp.to_sec())
                        frame_index += 1
                    elif topic == AUDIO_TOPIC:
                        audio_stream.write(message.data)
                        audio_messages += 1
        finally:
            bag.close()

        if not frame_times:
            raise RuntimeError(f'No video messages found on {VIDEO_TOPIC} in this chunk.')

        fps = 25.0
        if len(frame_times) > 1 and frame_times[-1] > frame_times[0]:
            fps = (len(frame_times) - 1) / (frame_times[-1] - frame_times[0])
        _run([
            'ffmpeg', '-y', '-framerate', f'{fps:.6f}',
            '-i', str(images_root / 'frame%06d.jpg'),
            '-c:v', 'mpeg4', str(video_only_path),
        ])

        transcript = ''
        speaker_data = []
        if audio_messages and audio_path.stat().st_size:
            plot_waveform(str(audio_path), str(waveform_path))
            _, transcript, speaker_data = transcribe_audio_to_srt(str(audio_path), str(chunk_root))
            _run([
                'ffmpeg', '-y', '-i', str(video_only_path), '-i', str(audio_path),
                '-c:v', 'libx264', '-preset', 'fast', '-pix_fmt', 'yuv420p',
                '-c:a', 'aac',
                '-map', '0:v', '-map', '1:a', '-shortest',
                '-movflags', '+faststart', str(output_path),
            ])
        else:
            _run([
                'ffmpeg', '-y', '-i', str(video_only_path),
                '-c:v', 'libx264', '-preset', 'fast', '-pix_fmt', 'yuv420p',
                '-movflags', '+faststart', str(output_path),
            ])

        result = {
            **chunk,
            'video_path': _relative_processed_path(output_path),
            'audio_path': _relative_processed_path(audio_path) if audio_messages else None,
            'waveform_image_path': _relative_processed_path(waveform_path) if waveform_path.exists() else None,
            'audio_transcript': transcript,
            'speaker_data': speaker_data,
            'status': 'ready',
        }
        temporary = result_path.with_suffix('.tmp')
        with temporary.open('w', encoding='utf-8') as stream:
            json.dump(result, stream, allow_nan=False, indent=2)
        os.replace(temporary, result_path)
        return result
    finally:
        lock_path.unlink(missing_ok=True)
