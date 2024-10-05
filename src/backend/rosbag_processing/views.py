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
    global video_frames
    global video_fps

    def detect_faces(frame, scaleFactor=1.1, minNeighbors=5, minSize=(30, 30)):
        face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        faces = face_cascade.detectMultiScale(gray, scaleFactor=scaleFactor, minNeighbors=minNeighbors, minSize=minSize)
        return len(faces) > 0
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
        video = cv2.VideoCapture(video_path)

        base64Frames = []
        while video.isOpened():
            success, frame = video.read()
            if not success:
                break
            
            # Detect face
            if detect_faces(frame):
                print("Frame with face detected, skipping.")
                continue
            
            _, buffer = cv2.imencode(".jpg", frame)
            base64Frames.append(base64.b64encode(buffer).decode("utf-8"))

        video.release()

        video_frames = base64Frames

        video_fps = int(video.get(cv2.CAP_PROP_FPS))
        if video_fps == 0:
            video_fps = 30
        print(len(base64Frames), "frames read.")
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
        srt_file_path, transcript, speaker_data = transcribe_audio_to_srt(audio_path, output_folder)

        # Combine the video and audio files
        combine_video_audio(output_folder)
        video = cv2.VideoCapture(video_path)

        base64Frames = []
        while video.isOpened():
            success, frame = video.read()
            if not success:
                break
            
            if detect_faces(frame):
                print("Frame with face detected, skipping.")
                continue

            _, buffer = cv2.imencode(".jpg", frame)
            base64Frames.append(base64.b64encode(buffer).decode("utf-8"))

        video.release()

        video_frames = base64Frames

        video_fps = int(video.get(cv2.CAP_PROP_FPS))
        if video_fps == 0:
            video_fps = 30
        print(len(base64Frames), "frames read.")
        return Response({
            'video_path': get_relative_path(video_path),
            'audio_path': get_relative_path(audio_path),
            'waveform_image_path': get_relative_path(waveform_image_path),
            'audio_transcript': transcript,
            'booklist_data': booklist_data,
            'annotation_data': annotation_data,
            'speaker_data': speaker_data,
            'message': 'Processing complete'
        })
    
    except Exception as e:
        return Response({'error': str(e)}, status=500)


@api_view(['POST'])
def gpt_chat(request):
    global gpt_history
    try:
        data = json.loads(request.body)
        message = data.get("message")
        audio_transcript = data.get("audio_transcript")
        Axiinfo = data.get("Axeinfo")
        Codebook = data.get("Codebook")


        if not message:
            return JsonResponse({"error": "No message provided"}, status=400)
        if not audio_transcript:
            return JsonResponse({"error": "No audio transcript provided"}, status=400)

        client = OpenAI(api_key=openai_api_key)

        Axiinfo_str = json.dumps(Axiinfo, indent=2)


        prompt = f"""
        User want you based on the audio_transcript and video frames answer some qustion 
        Now, based on this transcript and frames, answer the following question:

        {message}
        If the question not relative with audio and video, you dont need to watch the following data.
        Here is the audio transcription:
        {audio_transcript}
        Here is the video frames
        """

        chat_completion = client.chat.completions.create(
            model="gpt-4o",
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
                    Remove axi could remove all blocks in the axi.
                    Axi type always equal "Type-in"
                    Always create steps, even there only one step.
                    The newest axi id will be current largest id+1.
                    Overlap with other block in one axi will lead to error.
                    If the response is a normal conversation, return the plain text as usual.
                    Here is the current Axi information, you can consider axiId based on this:

                    {Axiinfo_str}

                    Here is the Codebook predefined by user:

                    {Codebook}
                    
                    Here is previous chat history between you and user:

                    {gpt_history}


                    """,
                    
                },
                {"role": "user", "content": [prompt,*map(lambda x: {"image": x}, video_frames[0::max(1, len(video_frames) // 50)][:50])]}
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
    
    if not os.path.exists(booklist_path):
        os.makedirs(booklist_path)
    
    serializer = BooklistSerializer(data=request.data)
    
    if serializer.is_valid():
        booklist_name = serializer.validated_data['name']
        booklist_data = serializer.validated_data['data']

        print(booklist_data)
        
        booklist_file_path = os.path.join(booklist_path, booklist_name)

        try:
            with open(booklist_file_path, 'w') as f:
                json.dump(booklist_data, f, indent=4)
            
            return Response({"message": "Booklist created/updated successfully", "New BookList": booklist_data}, status=status.HTTP_200_OK)
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

