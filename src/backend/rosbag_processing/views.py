from .data_utils import *
import json
import os
from django.http import JsonResponse
from datetime import datetime, timezone
from uuid import uuid4
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
from .serializers import BooklistSerializer, InputInspectionSerializer, TranscriptionRequestSerializer
import csv
from django.views.decorators.csrf import csrf_exempt
from dotenv import load_dotenv
from .ai_assistant import (
    LocalInferenceError,
    RemoteAPI,
    RemoteAuthenticationError,
    create_local_ai,
)

load_dotenv()

gpt_history = ""
video_frames = []

openai_api_key = os.getenv("OPENAI_API_KEY")
ROSBAG_DATA_DIR = '/app/datas/rosbag-data/'


@api_view(['POST'])
def inspect_input(request):
    """Return ROSBag duration before the user chooses a chunking strategy."""
    serializer = InputInspectionSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    bag_filename = serializer.validated_data['bag_filename']
    bag_filepath = os.path.join(ROSBAG_DATA_DIR, bag_filename)
    if not os.path.isfile(bag_filepath):
        return Response(
            {'error': 'ROSBag file not found.'},
            status=status.HTTP_404_NOT_FOUND,
        )

    try:
        duration_seconds = round(get_rosbag_duration(bag_filepath), 3)
    except Exception as exc:
        return Response(
            {'error': f'Unable to read ROSBag duration: {str(exc)}'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    return Response({
        'bag_filename': bag_filename,
        'duration_seconds': duration_seconds,
        'duration_minutes': round(duration_seconds / 60, 3),
        'supports_chunking': duration_seconds > 0,
    })
ANNOTATION_PATH = "/app/datas/annotation/"


class AssistantUnavailableError(RuntimeError):
    """Neither the requested remote provider nor local fallback can respond."""


def respond_with_remote_fallback(common_context, message, chat_history):
    """Use RemoteAI when configured, falling back to LocalAI on auth failure."""
    if openai_api_key:
        remote_assistant = RemoteAPI(
            **common_context,
            APIKey=openai_api_key,
        )
        try:
            return (
                remote_assistant.respond(message, chat_history),
                "remote",
                remote_assistant,
            )
        except RemoteAuthenticationError:
            pass

    local_assistant = create_local_ai(
        **common_context,
        checkpointPath=os.getenv("LOCAL_AI_CHECKPOINT_PATH", ""),
    )
    try:
        return (
            local_assistant.respond(message, chat_history),
            "local",
            local_assistant,
        )
    except LocalInferenceError as error:
        raise AssistantUnavailableError(
            "The remote model is unavailable, and the local language model "
            "is not connected yet. Switch to Remote after adding a valid "
            "OpenAI API key."
        ) from error


def build_ai_record(
    assistant,
    requested_mode,
    actual_mode,
    response_text,
    context_routes,
):
    """Build a secret-free record of one successful model interaction."""
    provider_metadata = assistant.get_run_metadata()
    if not isinstance(provider_metadata, dict):
        provider_metadata = {}

    return {
        "schema_version": 1,
        "run_id": str(uuid4()),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "model_selection": {
            "requested": requested_mode,
            "used": actual_mode,
            "context_routes": context_routes,
        },
        "model": provider_metadata.get("model", {
            "provider": actual_mode,
            "requested": None,
            "resolved": None,
        }),
        "parameters": provider_metadata.get("parameters", {}),
        "prompts": provider_metadata.get("prompts", {}),
        "ai_response": response_text,
    }


def ai_records_file_path(annotation_name):
    return os.path.join(ANNOTATION_PATH, f"ai_records_{annotation_name}.json")


def load_ai_records(annotation_filename):
    annotation_name = (
        annotation_filename[:-4]
        if annotation_filename.endswith(".csv")
        else annotation_filename
    )
    file_path = ai_records_file_path(annotation_name)
    if not os.path.exists(file_path):
        return []

    with open(file_path, "r") as record_file:
        payload = json.load(record_file)
    if isinstance(payload, dict):
        return payload.get("ai_runs", [])
    return payload if isinstance(payload, list) else []


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
    ai_records = []
    if annotation_filename:
        annotation_path = os.path.join('/app/datas/annotation/', annotation_filename)
        if not os.path.exists(annotation_path):
            return Response({'error': 'Invalid annotation filename'}, status=400)
        
        try:
            annotation_data = load_annotation(annotation_filename)
            ai_records = load_ai_records(annotation_filename)
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
            'ai_records': ai_records,
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
            'ai_records': ai_records,
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
        assistant_mode = data.get("assistant_mode", "remote")
        context_routes = data.get("context_routes", {})
        fallback_consent = data.get("fallback_consent")
        requested_mode = assistant_mode
        if (
            isinstance(fallback_consent, dict)
            and fallback_consent.get("from") == "local"
            and fallback_consent.get("to") == "remote"
            and fallback_consent.get("user_consented") is True
        ):
            requested_mode = "local"


        if not message:
            return JsonResponse({"error": "No message provided"}, status=400)
        if not audio_transcript:
            return JsonResponse({"error": "No audio transcript provided"}, status=400)
        if assistant_mode not in {"remote", "local", "hybrid"}:
            return JsonResponse({"error": "Invalid assistant mode"}, status=400)

        if assistant_mode == "hybrid":
            required_contexts = {"transcript", "frames", "codebook", "timeline"}
            if set(context_routes) != required_contexts or any(
                target not in {"remote", "local"}
                for target in context_routes.values()
            ):
                return JsonResponse(
                    {"error": "Invalid hybrid context routes"}, status=400
                )

            # Do not silently send hybrid-selected data to the remote provider.
            # The selection is ready for the future local/hybrid orchestrator.
            return JsonResponse(
                {
                    "error": "Hybrid mode requires an available local model.",
                    "assistant_mode": "hybrid",
                },
                status=501,
            )

        common_context = {
            "transcriptContext": audio_transcript,
            "frameContext": video_frames,
            "codebookContext": Codebook,
            "timelineContext": Axiinfo,
        }
        if assistant_mode == "local":
            assistant = create_local_ai(
                **common_context,
                checkpointPath=os.getenv("LOCAL_AI_CHECKPOINT_PATH", ""),
            )
            try:
                response_text = assistant.respond(message, gpt_history)
            except LocalInferenceError as error:
                remote_configured = bool(openai_api_key)
                error_message = str(error) or "The local language model is not connected."
                return JsonResponse(
                    {
                        "error": (
                            f"{error_message} "
                            + ("Would you like to switch to Remote?" if remote_configured else "")
                        ),
                        "assistant_mode": "local",
                        "can_fallback_to_remote": remote_configured,
                    },
                    status=501,
                )
        else:
            try:
                (
                    response_text,
                    assistant_mode,
                    assistant,
                ) = respond_with_remote_fallback(common_context, message, gpt_history)
            except AssistantUnavailableError as error:
                return JsonResponse(
                    {"error": str(error), "assistant_mode": "local"}, status=503
                )

        gpt_history = gpt_history + message + response_text
        ai_record = build_ai_record(
            assistant=assistant,
            requested_mode=requested_mode,
            actual_mode=assistant_mode,
            response_text=response_text,
            context_routes=context_routes,
        )
        return JsonResponse(
            {
                "response": response_text,
                "assistant_mode": assistant_mode,
                "ai_record": ai_record,
            }
        )
    
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
        ai_records = request.data.get('ai_records', [])

        if not isinstance(ai_records, list):
            return JsonResponse({'error': 'Invalid AI records format'}, status=400)

        try:
            annotation_list_str = json.dumps(annotation_data)
            annotation_list = json.loads(annotation_list_str)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'Invalid JSON format'}, status=400)

        # Save annotation data to a new CSV file
        os.makedirs(ANNOTATION_PATH, exist_ok=True)
        file_path = os.path.join(ANNOTATION_PATH, f'{annotation_name}.csv')

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

            with open(ai_records_file_path(annotation_name), 'w') as record_file:
                json.dump(
                    {
                        'schema_version': 1,
                        'annotation_name': annotation_name,
                        'ai_runs': ai_records,
                    },
                    record_file,
                    indent=2,
                )

            return JsonResponse(
                {'message': 'Annotation data and AI records saved successfully'},
                status=200,
            )
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
