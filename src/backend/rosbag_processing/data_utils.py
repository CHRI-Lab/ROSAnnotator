import base64
import csv
import os
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()


def get_rosbag_duration(bag_filename):
    from .rosbag_reader import RosbagReader
    with RosbagReader(bag_filename) as reader:
        return reader.duration

def plot_waveform(audio_path, output_filename, start_sec=None, end_sec=None):
    import numpy as np
    from matplotlib.figure import Figure
    from pydub import AudioSegment
    audio = AudioSegment.from_file(audio_path)
    if start_sec is not None and end_sec is not None:
        start_ms = start_sec * 1000 
        end_ms = end_sec * 1000
        audio = audio[start_ms:end_ms]
    if audio.channels > 1:
        audio = audio.set_channels(1)
    samples = np.array(audio.get_array_of_samples())
    figure = Figure(figsize=(14, 5))
    axes = figure.subplots()
    axes.plot(samples, color='black', linewidth=0.5)
    axes.axis('off')
    figure.savefig(output_filename, bbox_inches='tight', pad_inches=0)

def transcribe_audio_to_srt(audio_file_path, output_folder_path):
    import whisper
    from pydub import AudioSegment
    from pyannote.audio import Pipeline

    huggingface_auth_token = os.getenv("HUGGINGFACE_AUTH_TOKEN")
    if huggingface_auth_token is None:
        raise ValueError("Huggingface token not found in environment variables.")

    if audio_file_path.endswith(".mp3"):
        audio = AudioSegment.from_mp3(audio_file_path)
        wav_file_path = os.path.join(output_folder_path, "converted_audio.wav")
        # AudioSegment.export returns an open file handle. Close it before the
        # next consumer opens the WAV; otherwise Docker Desktop bind mounts can
        # expose a race (most noticeably on Windows) where pyannote cannot see
        # the newly-created file yet.
        exported_audio = audio.export(wav_file_path, format="wav")
        exported_audio.close()
        if not os.path.isfile(wav_file_path):
            raise RuntimeError(f"Audio conversion did not create {wav_file_path}.")
        audio_file_path = wav_file_path


    model = whisper.load_model("base")
    pipeline = Pipeline.from_pretrained("pyannote/speaker-diarization-3.1", use_auth_token=huggingface_auth_token)
    if huggingface_auth_token is None:
        raise ValueError("Huggingface token not found in environment variables.")
    if model is None or pipeline is None:
        raise RuntimeError("Failed to load models.")
        
    def seconds_to_srt_time(seconds):

        td = timedelta(seconds=seconds)
        total_seconds = int(td.total_seconds())
        minutes = total_seconds // 60
        seconds = total_seconds % 60
        return f"[{minutes:02}:{seconds:02}]"


    result = model.transcribe(audio_file_path)
    diarization = pipeline(audio_file_path)

    srt_content = ""
    segments = []
    tolerance = 0.4
    last_end = 0
    for index, segment in enumerate(result["segments"]):
        start_time = seconds_to_srt_time(segment["start"])
        end_time = seconds_to_srt_time(segment["end"])
        text = segment["text"]

        speaker_label = "Unknown Speaker"
        next_segment_start = result["segments"][index + 1]["start"] if index + 1 < len(result["segments"]) else float("inf")

        for turn, _, speaker in diarization.itertracks(yield_label=True):
            if turn.start + tolerance >= last_end and turn.end - tolerance <= next_segment_start:
                last_end = segment["end"]
                speaker_label = speaker
                break

        srt_content += f"{start_time} Speaker {speaker_label}: {text} {end_time}\n"
        
        segments.append({
            "start_time": segment["start"],
            "end_time": segment["end"],
            "speaker_label": speaker_label,
            "text": text
        })

    srt_file_name = "transcript_with_speakers.srt"
    srt_file_path = os.path.join(output_folder_path, srt_file_name)

    with open(srt_file_path, "w") as srt_file:
        srt_file.write(srt_content)


    return srt_file_path, srt_content, segments

def format_time(duration):
    total_seconds = int(duration.total_seconds())
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    seconds = total_seconds % 60
    microseconds = duration.microseconds
    milliseconds = microseconds // 1000

    return f"{hours:02}:{minutes:02}:{seconds:02},{milliseconds:03}"

def encode_file_base64(file_path):
    with open(file_path, 'rb') as file:
        encoded_string = base64.b64encode(file.read()).decode('utf-8')
    return encoded_string


def get_relative_path(path):
    base_path = "/app/processed_data/"
    relative_path = os.path.relpath(path, base_path)
    return relative_path

def load_annotation(annotation_filename, annotation_path='/app/datas/annotation/'):
    file_path = os.path.join(annotation_path, f'{annotation_filename}')

    if not os.path.exists(file_path):
        raise FileNotFoundError('File not found')

    try:
        with open(file_path, 'r') as csvfile:
            reader = csv.DictReader(csvfile)
            annotations = []

            for row in reader:
                annotation_entry = next((item for item in annotations if item['id'] == int(row['id'])), None)
                if not annotation_entry:
                    annotation_entry = {
                        'id': int(row['id']),
                        'axisType': row['axisType'],
                        'axisName': row['axisName'],
                        'axisBooklistName': row['axisBooklistName'],
                        'annotationBlocks': []
                    }
                    annotations.append(annotation_entry)

                annotation_entry['annotationBlocks'].append({
                    'start': float(row['start']),
                    'end': float(row['end']),
                    'text': row['text']
                })

        return annotations
    except Exception as e:
        raise IOError(f'Error loading annotation data: {str(e)}')
