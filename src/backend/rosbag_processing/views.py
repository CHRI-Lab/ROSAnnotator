import base64
import os
import subprocess
import cv2
import yaml
import numpy as np
from rosbag.bag import Bag
from cv_bridge import CvBridge
from google.cloud import speech_v1p1beta1 as speech
from datetime import datetime
from rest_framework.decorators import api_view
from rest_framework.response import Response
import matplotlib.pyplot as plt
from pydub import AudioSegment

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

def generate_srt(uri, output_folder):
    # Create a Speech client
    client = speech.SpeechClient()

    # Configure the audio source
    audio = speech.RecognitionAudio(uri=uri)

    # Configure the speech recognition request
    config = speech.RecognitionConfig(
        encoding=speech.RecognitionConfig.AudioEncoding.MP3,
        sample_rate_hertz=16000,
        language_code='en-US',
        enable_automatic_punctuation=True,
        enable_word_time_offsets=True,
        enable_speaker_diarization=True,
        diarization_speaker_count=2,
    )

    # Perform the long-running speech recognition
    operation = client.long_running_recognize(config=config, audio=audio)
    print("Waiting for operation to complete...")
    response = operation.result(timeout=90)

    # Generate the name for the SRT file
    srt_file_name = os.path.basename(uri).rsplit(".", 1)[0] + ".srt"
    srt_file_path = os.path.join(output_folder, srt_file_name)

    # Write the transcription to the SRT file
    with open(srt_file_path, 'w') as srt_file:
        counter = 1
        for result in response.results:
            if result.alternatives[0].words:
                start_time = result.alternatives[0].words[0].start_time
                end_time = result.alternatives[0].words[-1].end_time
                speaker_tag = result.alternatives[0].words[0].speaker_tag

                srt_file.write(f"{counter}\n")
                srt_file.write(f"{format_time(start_time)} --> {format_time(end_time)}\n")
                srt_file.write(f"Speaker {speaker_tag}: {result.alternatives[0].transcript}\n\n")
                counter += 1
    print(f"SRT file created: {srt_file_path}")
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

@api_view(['POST'])
def process_rosbag(request):
    if request.method == 'POST':
        bag_filename = "/app/rosbag-data/" + request.data.get('bag_filename')
        if not bag_filename:
            return Response({'error': 'No bag_filename provided'}, status=400)

        # add timestamp to the processed file folder
        finish_time = datetime.now()
        finish_time_str = finish_time.strftime('%Y-%m-%d-%H:%M:%S')

        output_folder = f'/app/processed_data/{os.path.basename(bag_filename)}_{finish_time_str}/'
        os.makedirs(output_folder, exist_ok=True)
        os.makedirs(f'{output_folder}/images', exist_ok=True)

        extract_images_from_rosbag(bag_filename, output_folder)
        extract_video(bag_filename, output_folder)
        extract_audio(bag_filename, output_folder)
        combine_video_audio(output_folder)

        # Construct paths to the processed files
        video_path = os.path.join(output_folder, 'output.mp4')
        audio_path = os.path.join(output_folder, 'audio.mp3')
        output_waveform_path = os.path.join(output_folder, 'output_waveform.png')

        # plot audio wave graph
        plot_waveform(audio_path, output_waveform_path)

        #TODO debug the google cloud speech credential issue
        srt_file_path = generate_srt(audio_path, output_folder)

        # encode the processed files as base64 strings
        video_data = encode_file_base64(video_path)
        audio_data = encode_file_base64(audio_path)
        waveform_image_data = encode_file_base64(output_waveform_path)
        srt_transcript_data = encode_file_base64(srt_file_path)

        return Response({
            'video_data': video_data,
            'audio_data': audio_data,
            'waveform_image_data': waveform_image_data,
            'message': 'Processing complete'
        })
    
    else:
        return Response({'error': 'Invalid request method'}, status=405)