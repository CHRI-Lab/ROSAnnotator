from .data_utils import *
import json
import os
from django.http import JsonResponse
from datetime import datetime
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
from .serializers import BooklistSerializer, TranscriptionRequestSerializer

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

        # speech transcript from audio file
        srt_file_path = transcribe_audio_to_srt(audio_path, output_folder)

        # encode the processed files as base64 strings
        video_data = encode_file_base64(video_path)
        audio_data = encode_file_base64(audio_path)
        waveform_image_data = encode_file_base64(output_waveform_path)
        srt_transcript_data = encode_file_base64(srt_file_path)

        return Response({
            'video_data': video_data,
            'audio_data': audio_data,
            'waveform_image_data': waveform_image_data,
            'srt_transcript_data': srt_transcript_data,
            'message': 'Processing complete'
        })
    
    else:
        return Response({'error': 'Invalid request method'}, status=405)

@api_view(['GET'])
def list_filenames(request):
    # Define folder paths
    rosbag_file_folder_path = '/app/rosbag-data/rosbag_file/'
    booklist_folder_path = '/app/rosbag-data/booklist/'
    annotation_folder_path = '/app/rosbag-data/annotation/'

    # Validate folder paths
    if not all(map(os.path.isdir, [rosbag_file_folder_path, booklist_folder_path, annotation_folder_path])):
        return JsonResponse({'error': 'Invalid folder paths'}, status=500)

    # List files in the directories
    rosbag_files = [file for file in os.listdir(rosbag_file_folder_path) if file.endswith('.bag')]
    booklist_files = [file for file in os.listdir(booklist_folder_path) if file.endswith('.json')]
    annotation_files = [file for file in os.listdir(annotation_folder_path) if file.endswith('.csv')]

    # Return the list of files as JSON response
    return JsonResponse({'rosbag_files': rosbag_files, 'booklist_files': booklist_files, 'annotation_files': annotation_files})

# For testing if the transcibe_audio is working 
@api_view(['POST'])
def transcribe_audio(request):
    serializer = TranscriptionRequestSerializer(data=request.data)
    if serializer.is_valid():
        audio_file_path = serializer.validated_data['audio_file_path']
        output_folder_path = serializer.validated_data['output_folder_path']
        try:
            srt_file_path = transcribe_audio_to_srt(audio_file_path, output_folder_path)
            return Response({"srt_file_path": srt_file_path}, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


BOOKLISTS_DIR = '/app/rosbag-data/booklist/'
        
@api_view(['POST'])
def update_booklist(request):

    serializer = BooklistSerializer(data=request.data)
    if serializer.is_valid():
        booklist_name = serializer.validated_data['name']
        booklist_data = serializer.validated_data['data']
            
        # Construct file path
        booklist_file_path = os.path.join(BOOKLISTS_DIR, f"{booklist_name}.json")
        try:
            # Write booklist data to file
            with open(booklist_file_path, 'w') as f:
                json.dump(booklist_data, f, indent=4)
            return Response({"message": "Booklist updated successfully"}, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    else:
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
