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
import openai
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

gpt_history = ""


openai_api_key = os.getenv("OPENAI_API_KEY")


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
    annotation_filename = request.data.get('annotation_filename')
    
    output_folder = os.path.join('/app/processed_data/', os.path.basename(bag_filename))
    images_folder = os.path.join(output_folder, 'images')
    video_path = os.path.join(output_folder, 'output.mp4')
    audio_path = os.path.join(output_folder, 'audio.mp3')
    waveform_image_path = os.path.join(output_folder, 'output_waveform.png')
    srt_file_path = os.path.join(output_folder, 'transcript_with_speakers.srt')

    if booklist_filename:
        booklist_path = os.path.join('/app/datas/booklist/', booklist_filename)
        if not os.path.exists(booklist_path):
            return Response({'error': 'Invalid booklist filename'}, status=400)
        with open(booklist_path, 'r') as booklist_file:
            booklist_data = json.load(booklist_file)
    else:
        booklist_data = {}

    annotation_data = None
    if annotation_filename:
        annotation_path = os.path.join('/app/datas/annotation/', annotation_filename)
        if not os.path.exists(annotation_path):
            return Response({'error': 'Invalid annotation filename'}, status=400)
        
        try:
            annotation_data = load_annotation(annotation_filename)
        except Exception as e:
            return Response({'error': f'Error loading annotation data: {str(e)}'}, status=500)

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
            'annotation_data': annotation_data,
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
        srt_file_path, transcript,speaker_data = transcribe_audio_to_srt(audio_path, output_folder)

        # Combine the video and audio files
        combine_video_audio(output_folder)

        return Response({
            'video_path': get_relative_path(video_path),
            'audio_path': get_relative_path(audio_path),
            'waveform_image_path': get_relative_path(waveform_image_path),
            'audio_transcript': transcript,
            'booklist_data': booklist_data,
            'annotation_data': annotation_data,
            'speaker_data':speaker_data,
            'message': 'Processing complete'
        })
    
    except Exception as e:
        return Response({'error': str(e)}, status=500)


@api_view(['POST'])
def gpt_chat(request):
    global gpt_history
    try:
        # 从请求体中获取用户消息
        data = json.loads(request.body)
        message = data.get("message")
        audio_transcript = data.get("audio_transcript")  # 获取音频转录文本
        Axiinfo = data.get("Axeinfo")  # 获取 Axi 信息

        # 确保消息和音频转录文本都存在
        if not message:
            return JsonResponse({"error": "No message provided"}, status=400)
        if not audio_transcript:
            return JsonResponse({"error": "No audio transcript provided"}, status=400)
        if not Axiinfo:
            return JsonResponse({"error": "No Axi information provided"}, status=400)

        client = OpenAI(api_key=openai_api_key)

        # 将 Axiinfo 转换为格式化字符串，确保格式正确
        Axiinfo_str = json.dumps(Axiinfo, indent=2)

        prompt = f"""
        The following is a transcript of an audio recording. This is not a question, but a reference text.
        You should use the transcript as context to help you answer the user's question.

        Audio transcript: {audio_transcript}
        Consider the end of latest senetence as end of audio.
        Now, based on this transcript, answer the following question:

        {message}
        """

        # 调用 GPT API
        chat_completion = client.chat.completions.create(
            model="gpt-4",
            messages=[
                {
                    "role": "system", 
                    "content": f"""
                    You are an assistant that can manipulate timelines. Based on the audio transcript, here are the actions you can perform:
                    
                    1. Add a new `axi`: Method: `addAxi`, Parameters: `axisId` (integer),'axisName' (string),'axistype' (string).
                    2. Add a new `block`: Method: `addBlock`, Parameters: `axisId` (integer), `start` (float), `end` (float), `text` (string).
                    3. Delete a old 'block':Mthod:'deleteBlock', Parameters: `axisId` (integer), 'blockIndex' (integer).
                    4. Delete a old 'axi':Mthod:'deleteAxi', Parameters: `axisId` (integer).
                    When you need to perform multiple actions to complete the task, return the response in the following format:
                    {{
                      "type": "instruction",
                      "steps": [
                        {{
                          "action": "addAxi",
                          "parameters": 
                          {{
                            "axisId": 1,
                            "axisName": Greeting
                            "axistype": Topic annotate
                            }}
                        }},
                        {{
                          "action": "addBlock",
                          "parameters": {{
                            "axisId": 1,
                            "start": 10,
                            "end": 20,
                            "text": "This is a new block"
                          }}
                        }}
                        {{
                          "action": "deleteBlock",
                          "parameters": {{
                            "axisId": 1,
                            "blockIndex": 0
                          }}
                        }}
                        {{
                          "action": "deleteAxi",
                          "parameters": {{
                            "axisId": 1
                          }}
                        }}
                      ]
                    }}
                    axis Name are normally the topic of this axi.
                    Selet one of the axi type('speaker','topic annotate')
                    Always create steps, even there only one step.
                    When you want to return an instruction, only return the format, no plain text.
                    The newest axi id will be current largest id+1.
                    Overlap with other block in one axi will lead to error.
                    If the response is a normal conversation, return the plain text as usual.
                    Here is the current Axi information, you can consider axiId based on this:

                    {Axiinfo_str}

                    Here is previous chat history between you and user:
                    {gpt_history}
                    User may ask you to undo some previous instruction generate by you.
                    """
                },
                {"role": "user", "content": prompt}
            ],
        )
        
        response_text = chat_completion.choices[0].message.content
        gpt_history = gpt_history + message + response_text
        return JsonResponse({"response": response_text})
    
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)
    
@api_view(['GET'])
def list_filenames(request):
    # Define folder paths
    if request.method == 'GET':
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
                fieldnames = ['id', 'axisType', 'axisName', 'axisBooklistName', 'start', 'end', 'text']
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)

                writer.writeheader()
                for annotation_entry in annotation_list:
                    for block in annotation_entry['annotationBlocks']:
                        writer.writerow({
                            'id': annotation_entry['id'],
                            'axisType': annotation_entry['axisType'],
                            'axisName': annotation_entry['axisName'],
                            'axisBooklistName': annotation_entry.get('axisBooklistName', ''),
                            'start': block['start'],
                            'end': block['end'],
                            'text': block['text']
                        })

            return JsonResponse({'message': 'Annotation data saved successfully'}, status=200)
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)
    else:
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    
# testing the load_annotation function 
@api_view(['GET'])
def get_annotation(request):
    annotation_filename = request.query_params.get('annotation_filename')
    
    if not annotation_filename:
        return Response({'error': 'annotation_filename parameter is required'}, status=400)
    
    try:
        annotation_json = load_annotation(annotation_filename)
        return Response(annotation_json, status=200)
    except FileNotFoundError:
        return Response({'error': 'File not found'}, status=404)
    except Exception as e:
        return Response({'error': str(e)}, status=500)

