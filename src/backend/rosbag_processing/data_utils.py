import base64
import json
import os
import subprocess
import cv2
from django.http import JsonResponse
import yaml
import numpy as np
from rosbag.bag import Bag
from cv_bridge import CvBridge
from google.cloud import speech_v1p1beta1 as speech
from datetime import datetime, timedelta
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
import matplotlib.pyplot as plt
from .serializers import BooklistSerializer, TranscriptionRequestSerializer
from pydub import AudioSegment
import whisper


def extract_images_from_rosbag(bag_filename, output_folder):
    bag = Bag(bag_filename, 'r')
    bridge = CvBridge()

    for i, (_, message, t) in enumerate(bag.read_messages(topics='/xtion/rgb/image_raw_throttled')):
        cv2_image = bridge.imgmsg_to_cv2(message, desired_encoding='passthrough')
        cv2_image = cv2.cvtColor(cv2_image, cv2.COLOR_BGR2RGB)
        cv2.imwrite(f'{output_folder}/images/frame{i:04d}.jpg', cv2_image)
        
def extract_video(bag_filename, output_folder):

    def get_fps():
        bag = Bag(bag_filename, 'r')
        bag_info = yaml.load(bag._get_yaml_info(), Loader=yaml.Loader)
        for topic in bag_info['topics']:
            if topic['type'] == 'sensor_msgs/Image':
                return topic['frequency']
        return None
    
    fps = str(get_fps())

    input_images_path = os.path.join(output_folder, 'images/frame%04d.jpg')
    output_video_path = os.path.join(output_folder, 'video.avi')
    subprocess.run(['ffmpeg', '-r', str(fps), '-i', input_images_path, output_video_path])


def extract_audio(bag_filename, output_folder):
    bag = Bag(bag_filename, 'r')
    with open(f'{output_folder}/audio.mp3', 'wb') as f:
        for i, (_, message, t) in enumerate(bag.read_messages(topics='/audio')):
            for byte in message.data:
                # f.write(int.to_bytes(byte))
                f.write(byte.to_bytes(1, 'big'))

def plot_waveform(audio_path, output_filename, start_sec=None, end_sec=None):
    audio = AudioSegment.from_file(audio_path)
    if start_sec is not None and end_sec is not None:
        start_ms = start_sec * 1000 
        end_ms = end_sec * 1000
        audio = audio[start_ms:end_ms]
    if audio.channels > 1:
        audio = audio.set_channels(1)
    samples = np.array(audio.get_array_of_samples())
    plt.figure(figsize=(14, 5))
    plt.plot(samples, color='black', linewidth=0.5)
    plt.axis('off')
    plt.savefig(output_filename, bbox_inches='tight', pad_inches=0)
    plt.close()

def combine_video_audio(output_folder):

    video_path = os.path.join(output_folder, 'video.avi')
    audio_path = os.path.join(output_folder, 'audio.mp3')
    output_path = os.path.join(output_folder, 'output.mp4')

    subprocess.run(['ffmpeg', '-i', video_path, '-i', audio_path, '-c:v', 'copy', '-map', '0:v', '-map', '1:a', '-y', output_path])


def transcribe_audio_to_srt(audio_file_path, output_folder_path):
    model = whisper.load_model("base")
    
    def seconds_to_srt_time(seconds):
        return str(timedelta(seconds=seconds))

    # Transcribe the audio file
    result = model.transcribe(audio_file_path)
    
    # Generate SRT content
    srt_content = ""
    for i, segment in enumerate(result["segments"]):
        start = seconds_to_srt_time(segment["start"])
        end = seconds_to_srt_time(segment["end"])
        text = segment["text"]
        srt_content += f"{i+1}\n{start} --> {end}\n{text}\n\n"

    # Create the SRT file name based on the audio file name
    audio_file_name = os.path.basename(audio_file_path)
    srt_file_name = os.path.splitext(audio_file_name)[0] + ".srt"
    srt_file_path = os.path.join(output_folder_path, srt_file_name)

    # Save the SRT file
    with open(srt_file_path, "w") as srt_file:
        srt_file.write(srt_content)

    return srt_file_path

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