from .data_utils import *
import json
import os
from django.http import JsonResponse
from datetime import datetime
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
from .serializers import BooklistSerializer, TranscriptionRequestSerializer
import csv
from django.views.decorators.csrf import csrf_exempt

@api_view(['POST'])
def process_rosbag(request):
    if request.method != 'POST':
        return Response({'error': 'Invalid request method'}, status=405)
    
    bag_filename = request.data.get('bag_filename')
    if not bag_filename:
        return Response({'error': 'bag_filename is required'}, status=400)

    bag_filepath = os.path.join('/app/datas/rosbag-data/', bag_filename)
    if not os.path.exists(bag_filepath):
        return Response({'error': 'Invalid bag filename'}, status=400)
    
    booklist_filename = request.data.get('booklist_filename')
    # annotation_filename = request.data.get('annotation_filename')
    
    output_folder = os.path.join('/app/processed_data/', os.path.basename(bag_filename))
    images_folder = os.path.join(output_folder, 'images')
    video_path = os.path.join(output_folder, 'output.mp4')
    audio_path = os.path.join(output_folder, 'audio.mp3')
    waveform_image_path = os.path.join(output_folder, 'output_waveform.png')
    srt_file_path = os.path.join(output_folder, 'transcript.srt')

    if booklist_filename:
        booklist_path = os.path.join('/app/datas/booklist/', booklist_filename)
        if not os.path.exists(booklist_path):
            return Response({'error': 'Invalid booklist filename'}, status=400)
        with open(booklist_path, 'r') as booklist_file:
            booklist_data = json.load(booklist_file)
    else:
        booklist_data = {}

    # Check if the bag file has already been processed
    if all(os.path.exists(path) for path in [video_path, audio_path, waveform_image_path, srt_file_path]):
        with open(srt_file_path, 'r') as transcript_file:
            transcript = transcript_file.read()
        return Response({
            'video_path': get_relative_path(video_path),
            'audio_path': get_relative_path(audio_path),
            'waveform_image_path': get_relative_path(waveform_image_path),
            'audio_transcript': transcript,
            'booklist_data': booklist_data,
            'message': 'File already processed'
        })
    
    os.makedirs(images_folder, exist_ok=True)

    try:
        # Extract images, video, and audio from the rosbag file
        extract_images_from_rosbag(bag_filepath, output_folder)
        extract_audio(bag_filepath, output_folder)
        # Plot the audio waveform
        plot_waveform(audio_path, waveform_image_path)
        extract_video(bag_filepath, output_folder)

        # Transcribe the audio to an SRT file
        srt_file_path, transcript = transcribe_audio_to_srt(audio_path, output_folder)

        # Combine the video and audio files
        combine_video_audio(output_folder)

        return Response({
            'video_path': get_relative_path(video_path),
            'audio_path': get_relative_path(audio_path),
            'waveform_image_path': get_relative_path(waveform_image_path),
            'audio_transcript': transcript,
            'booklist_data': booklist_data,
            'message': 'Processing complete'
        })
    
    except Exception as e:
        return Response({'error': str(e)}, status=500)

@api_view(['GET'])
def list_filenames(request):
    # Define folder paths
    rosbag_file_folder_path = '/app/datas/rosbag-data/'
    booklist_folder_path = '/app/datas/booklist/'
    annotation_folder_path = '/app/datas/annotation/'

    # Validate folder paths
    if not all(map(os.path.isdir, [rosbag_file_folder_path, booklist_folder_path, annotation_folder_path])):
        return JsonResponse({'error': 'Invalid folder paths'}, status=500)

    # List files in the directories
    rosbag_files = [file for file in os.listdir(rosbag_file_folder_path) if file.endswith('.bag')]
    booklist_files = [file for file in os.listdir(booklist_folder_path) if file.endswith('.json')]
    annotation_files = [file for file in os.listdir(annotation_folder_path) if file.endswith('.csv')]

    # Return the list of files as JSON response
    return Response({
        'rosbag_files': rosbag_files,
        'booklist_files': booklist_files,
        'annotation_files': annotation_files
    })


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

        
@api_view(['POST'])
def update_booklist(request):
    booklist_path = '/app/datas/booklist/'
    serializer = BooklistSerializer(data=request.data)
    if serializer.is_valid():
        booklist_name = serializer.validated_data['name']
        booklist_data = serializer.validated_data['data']

        print(booklist_data)
            
        # Construct file path
        booklist_file_path = os.path.join(booklist_path, booklist_name)

        if not os.path.exists(booklist_file_path):
            return Response({"error": "Booklist file does not exist"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            # Write booklist data to file
            with open(booklist_file_path, 'w') as f:
                json.dump(booklist_data, f, indent=4)
            return Response({"message": "Booklist updated successfully", "New BookList": booklist_data}, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    else:
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    

import os
import csv
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt

@csrf_exempt
@api_view(['POST'])
def save_annotation(request):
    if request.method == 'POST':
        annotation_name = request.data.get('annotation_name')
        annotation_data = request.data.get('annotation_data')

        try:
            annotation_list_str = json.dumps(annotation_data)
            annotation_list = json.loads(annotation_list_str)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'Invalid JSON format'}, status=400)

        # Save annotation data to a new CSV file
        annotation_path = '/app/datas/annotation/'
        file_path = os.path.join(annotation_path, f'{annotation_name}.csv')

        try:
            with open(file_path, 'w', newline='') as csvfile:
                fieldnames = ['id', 'axisType', 'axisName', 'axisBooklisteName', 'start', 'end', 'text']
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)

                writer.writeheader()
                for annotation_entry in annotation_list:
                    for block in annotation_entry['annotationBlocks']:
                        writer.writerow({
                            'id': annotation_entry['id'],
                            'axisType': annotation_entry['axisType'],
                            'axisName': annotation_entry['axisName'],
                            'axisBooklisteName': annotation_entry.get('axisBooklisteName', ''),  # Handle the case where axisBooklisteName is missing
                            'start': block['start'],
                            'end': block['end'],
                            'text': block['text']
                        })

            return JsonResponse({'message': 'Annotation data saved successfully'}, status=200)
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)
    else:
        return JsonResponse({'error': 'Method not allowed'}, status=405)

