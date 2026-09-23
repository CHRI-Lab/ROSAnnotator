"""Concrete views. ROS extraction and media preprocessing are separate hooks."""
import os
import subprocess
from pathlib import Path

from .view_processor import DataViewProcessor, ViewUnavailable


def run_media(arguments):
    subprocess.run(['ffmpeg', '-y', *arguments], check=True, capture_output=True, text=True)


def public_path(path):
    return os.path.relpath(path, '/app/processed_data').replace(os.sep, '/')


def artifact_data(path, **values):
    return {'path': public_path(path), 'artifacts': [str(path.resolve())], **values}


class AudioProcessor(DataViewProcessor):
    view_id = 'audio'
    supported_message_types = ('audio_common_msgs/AudioData', 'audio_common_msgs/AudioDataStamped')

    def extract(self, context, topics):
        packets = []
        spool = context.directory / 'packets.bin'
        with spool.open('wb') as stream:
            for record in context.reader.records(topics):
                payload = getattr(record.message, 'audio', record.message)
                data = bytes(payload.data)
                if data:
                    packets.append((record.seconds, stream.tell(), len(data), record.frame_id))
                    stream.write(data)
        if not packets:
            raise ViewUnavailable('No usable audio packets in this range.')
        return spool, context.reader.ordered(packets)

    def preprocess(self, context, extracted):
        spool, packets = extracted
        source = context.directory / 'source.mp3'
        with spool.open('rb') as stream, source.open('wb') as output:
            for _, offset, length, _ in packets:
                stream.seek(offset)
                output.write(stream.read(length))
        destination = context.directory / 'audio.mp3'
        delay = round(packets[0][0] * 1000)
        run_media(['-i', str(source), '-af', f'adelay={delay}:all=1,apad',
                   '-t', str(context.reader.duration), str(destination)])
        return artifact_data(destination, frame_ids=sorted({p[3] for p in packets}),
                             first_packet_seconds=packets[0][0])

    def legacy_fields(self, data):
        return {'audio_path': data['path']}


class VideoProcessor(DataViewProcessor):
    view_id = 'video'
    supported_message_types = ('sensor_msgs/Image', 'sensor_msgs/CompressedImage')
    dependencies = ('audio',)  # Optional audio mux; unavailable audio never blocks video.

    def extract(self, context, topics):
        import cv2
        from cv_bridge import CvBridge
        bridge = CvBridge()
        samples = []
        frames = set()
        for record in context.reader.records(topics):
            if record.frame_id:
                frames.add(record.frame_id)
            expected = context.options.get('frame_id')
            if len(frames) > 1 or (expected and record.frame_id != expected):
                raise ViewUnavailable('Incompatible image coordinate frames; select one frame.')
            if context.reader.topics[record.topic]['message_type'] == 'sensor_msgs/CompressedImage':
                frame = bridge.compressed_imgmsg_to_cv2(record.message, desired_encoding='bgr8')
            else:
                frame = bridge.imgmsg_to_cv2(record.message, desired_encoding='bgr8')
            filename = context.directory / f'frame{len(samples):08d}.png'
            if not cv2.imwrite(str(filename), frame):
                raise ViewUnavailable('Unable to decode image data.')
            samples.append((record.seconds, filename.name, record.frame_id))
        if not samples:
            raise ViewUnavailable('No usable images in this range.')
        return context.reader.ordered(samples)

    def preprocess(self, context, extracted):
        # Equal timestamps use the last image; preserve all original frame metadata.
        unique = {sample[0]: sample for sample in extracted}
        samples = list(unique.values())
        concat = context.directory / 'frames.txt'
        lines = []
        for index, sample in enumerate(samples):
            start = sample[0] if index else 0.0
            end = samples[index + 1][0] if index + 1 < len(samples) else context.reader.duration
            lines.extend([f"file '{sample[1]}'", f'duration {max(end - start, 0.001):.9f}'])
        lines.append(f"file '{samples[-1][1]}'")
        concat.write_text('\n'.join(lines), encoding='utf-8')
        silent = context.directory / 'silent.mp4'
        run_media(['-f', 'concat', '-safe', '0', '-i', str(concat), '-vsync', 'vfr',
                   '-vf', 'pad=ceil(iw/2)*2:ceil(ih/2)*2', '-pix_fmt', 'yuv420p',
                   '-c:v', 'libx264', '-preset', 'fast', '-t', str(context.reader.duration), str(silent)])
        destination = silent
        audio = context.results.get('audio', {})
        if audio.get('available'):
            combined = context.directory / 'output.mp4'
            try:
                run_media(['-i', str(silent), '-i', audio['processed_data']['artifacts'][0],
                           '-map', '0:v', '-map', '1:a', '-c:v', 'copy', '-c:a', 'aac', str(combined)])
                destination = combined
            except subprocess.CalledProcessError:
                context.reader.warn('Audio mux failed; video is available without audio.')
        return artifact_data(destination, has_audio=destination != silent,
                             frames=[{'seconds': s[0], 'frame_id': s[2]} for s in extracted])

    def legacy_fields(self, data):
        return {'video_path': data['path']}


class AudioDerivedProcessor(DataViewProcessor):
    supported_message_types = AudioProcessor.supported_message_types
    dependencies = ('audio',)

    def check_availability(self, context):
        audio = context.results.get('audio', {})
        if not audio.get('available'):
            raise ViewUnavailable('Usable audio is required. ' + (audio.get('reason') or ''))
        return audio['selected_topics']

    def extract(self, context, topics):
        return context.results['audio']['processed_data']['artifacts'][0]


class TranscriptProcessor(AudioDerivedProcessor):
    view_id = 'transcript'

    def preprocess(self, context, extracted):
        from .data_utils import transcribe_audio_to_srt
        path, transcript, speakers = transcribe_audio_to_srt(extracted, str(context.directory))
        if not transcript.strip():
            raise ViewUnavailable('No speech was detected in this range.')
        return {'transcript': transcript, 'speaker_data': speakers, 'artifacts': [str(Path(path).resolve())]}

    def legacy_fields(self, data):
        return {'audio_transcript': data['transcript'], 'speaker_data': data['speaker_data']}


class WaveformProcessor(AudioDerivedProcessor):
    view_id = 'waveform'

    def preprocess(self, context, extracted):
        from .data_utils import plot_waveform
        path = context.directory / 'waveform.png'
        plot_waveform(extracted, str(path))
        return artifact_data(path)

    def legacy_fields(self, data):
        return {'waveform_image_path': data['path']}


class AnnotationProcessor(DataViewProcessor):
    """An editable timeline is usable when at least one time-bearing input is usable."""
    view_id = 'annotations'
    dependencies = ('video', 'audio', 'wrench')

    def check_availability(self, context):
        ready = [r for r in context.results.values() if r.get('available')]
        if not ready:
            raise ViewUnavailable('No usable input for the annotation timeline.')
        return sorted({t for r in ready for t in r['selected_topics']})

    def extract(self, context, topics):
        return {'editable': True}

    def preprocess(self, context, extracted):
        return extracted


class AnnotationStatisticsProcessor(AnnotationProcessor):
    view_id = 'statistics-annotations'


class TierStatisticsProcessor(AnnotationProcessor):
    view_id = 'statistics-tiers'
