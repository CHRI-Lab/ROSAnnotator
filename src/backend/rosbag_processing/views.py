from .data_utils import *
import json
import os
import base64
from pathlib import Path
import cv2
from django.http import JsonResponse
from datetime import datetime, timezone
from uuid import UUID, uuid4
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
from .serializers import BooklistSerializer, InputInspectionSerializer, TranscriptionRequestSerializer
import csv
import fcntl
import tempfile
from django.views.decorators.csrf import csrf_exempt
from dotenv import load_dotenv
from openai import APIConnectionError, APIStatusError
from .ai_assistant import (
    LocalInferenceError,
    RemoteAPI,
    RemoteAuthenticationError,
    RemoteResponseError,
    create_local_ai,
)

load_dotenv()

gpt_history = ""
gpt_history_generation = 0
video_frames = []

openai_api_key = os.getenv("OPENAI_API_KEY")
ROSBAG_DATA_DIR = '/app/datas/rosbag-data/'
PROCESSED_DATA_DIR = '/app/processed_data'


def frames_for_video(video_path, max_frames=50):
    """Sample the selected processed MP4, never a different request's global frames."""
    if not isinstance(video_path, str) or not video_path or Path(video_path).is_absolute():
        raise ValueError('Invalid video path.')
    root = Path(PROCESSED_DATA_DIR).resolve()
    path = (root / video_path).resolve()
    if root not in path.parents or path.suffix.lower() != '.mp4' or not path.is_file():
        raise ValueError('Selected video was not found.')

    capture = cv2.VideoCapture(str(path))
    try:
        if not capture.isOpened():
            raise ValueError('Selected video could not be opened.')
        frame_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
        if frame_count <= 0:
            raise ValueError('Selected video has no readable frames.')
        count = min(frame_count, max_frames)
        positions = sorted({round(index * (frame_count - 1) / max(count - 1, 1))
                            for index in range(count)})
        frames = []
        for position in positions:
            capture.set(cv2.CAP_PROP_POS_FRAMES, position)
            success, frame = capture.read()
            if not success:
                continue
            encoded, buffer = cv2.imencode('.jpg', frame)
            if encoded:
                frames.append(base64.b64encode(buffer).decode('ascii'))
        if not frames:
            raise ValueError('Selected video has no readable frames.')
        return frames
    finally:
        capture.release()


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


def ai_records_file_path(annotation_name, manifest_id=None):
    suffix = f"_{manifest_id}" if manifest_id else ""
    return os.path.join(ANNOTATION_PATH, f"ai_records_{annotation_name}{suffix}.json")


def load_ai_records(annotation_filename, manifest_id=None, chunk_index=None):
    annotation_name = (
        annotation_filename[:-4]
        if annotation_filename.endswith(".csv")
        else annotation_filename
    )
    file_path = ai_records_file_path(annotation_name, manifest_id)
    if not os.path.exists(file_path):
        return []

    with open(file_path, "r") as record_file:
        payload = json.load(record_file)
    records = payload.get("ai_runs", []) if isinstance(payload, dict) else payload
    if not isinstance(records, list):
        return []
    if chunk_index is not None:
        return [record for record in records if isinstance(record, dict)
                and record.get('chunk_index') == chunk_index]
    return records


@api_view(['POST'])
def complete_ai_record(request):
    """Persist one completed prompt/reply/action outcome independently of annotation saves."""
    annotation_name = request.data.get('annotation_name')
    record = request.data.get('ai_record')
    outcome = request.data.get('outcome')
    manifest_id = request.data.get('manifest_id')
    chunk_index = request.data.get('chunk_index')
    try:
        manifest_id = str(UUID(str(manifest_id))) if manifest_id is not None else None
    except (ValueError, TypeError, AttributeError):
        return JsonResponse({'error': 'Invalid manifest ID'}, status=400)
    if (
        not isinstance(annotation_name, str)
        or not annotation_name.strip()
        or annotation_name != os.path.basename(annotation_name)
        or '/' in annotation_name
        or '\\' in annotation_name
        or not isinstance(record, dict)
        or not isinstance(record.get('run_id'), str)
        or not record['run_id']
        or outcome not in {'replied', 'applied', 'rejected', 'not_applied'}
        or (manifest_id is None and chunk_index is not None)
        or (chunk_index is not None and (type(chunk_index) is not int or chunk_index < 0))
    ):
        return JsonResponse({'error': 'Invalid completed AI record'}, status=400)

    completed_record = {
        **record,
        'action_outcome': outcome,
        'completed_at': datetime.now(timezone.utc).isoformat(),
    }
    if chunk_index is not None:
        completed_record['chunk_index'] = chunk_index
    os.makedirs(ANNOTATION_PATH, exist_ok=True)
    record_path = ai_records_file_path(annotation_name, manifest_id)
    lock_path = f'{record_path}.lock'
    temporary_path = None
    try:
        with open(lock_path, 'a+') as lock_file:
            fcntl.flock(lock_file, fcntl.LOCK_EX)
            existing = load_ai_records(annotation_name, manifest_id)
            if not isinstance(existing, list):
                raise ValueError('Existing AI record file is invalid')
            record_index = next(
                (index for index, item in enumerate(existing)
                 if isinstance(item, dict) and item.get('run_id') == record['run_id']),
                None,
            )
            if record_index is None:
                existing.append(completed_record)
            else:
                # Retries of the same completed request must not duplicate it.
                existing[record_index] = completed_record
            with tempfile.NamedTemporaryFile(
                mode='w', encoding='utf-8', dir=ANNOTATION_PATH,
                prefix='.ai-record-', suffix='.tmp', delete=False,
            ) as temporary_file:
                temporary_path = temporary_file.name
                json.dump({
                    'schema_version': 1,
                    'annotation_name': annotation_name,
                    'ai_runs': existing,
                }, temporary_file, indent=2)
                temporary_file.flush()
                os.fsync(temporary_file.fileno())
            os.replace(temporary_path, record_path)
            temporary_path = None
    except Exception as error:
        return JsonResponse({'error': f'Unable to save AI record: {error}'}, status=500)
    finally:
        if temporary_path and os.path.exists(temporary_path):
            os.unlink(temporary_path)
    return JsonResponse({'saved': True, 'run_id': record['run_id']})


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
def clear_gpt_history(request):
    global gpt_history, gpt_history_generation
    gpt_history = ""
    gpt_history_generation += 1
    return JsonResponse({"cleared": True})


@api_view(['POST'])
def gpt_chat(request):
    global gpt_history
    try:
        history_generation = gpt_history_generation
        data = json.loads(request.body)
        message = data.get("message")
        audio_transcript = data.get("audio_transcript")
        Axiinfo = data.get("Axeinfo")
        Codebook = data.get("Codebook")
        assistant_mode = data.get("assistant_mode", "remote")
        context_routes = data.get("context_routes", {})
        fallback_consent = data.get("fallback_consent")
        requested_mode = assistant_mode
        accepted_local_to_remote = (
            isinstance(fallback_consent, dict)
            and fallback_consent.get("from") == "local"
            and fallback_consent.get("to") == "remote"
            and fallback_consent.get("user_consented") is True
        )
        accepted_remote_to_local = (
            isinstance(fallback_consent, dict)
            and fallback_consent.get("from") == "remote"
            and fallback_consent.get("to") == "local"
            and fallback_consent.get("user_consented") is True
        )
        if accepted_local_to_remote:
            requested_mode = "local"
        elif accepted_remote_to_local:
            requested_mode = "remote"


        if not message:
            return JsonResponse({"error": "No message provided"}, status=400)
        if not audio_transcript:
            return JsonResponse({"error": "No audio transcript provided"}, status=400)
        if assistant_mode not in {"remote", "local"}:
            return JsonResponse({"error": "Invalid assistant mode"}, status=400)
        if not isinstance(context_routes, dict) or any(
            target != assistant_mode for target in context_routes.values()
        ):
            return JsonResponse({"error": "Invalid context routes"}, status=400)

        selected_video_path = data.get('video_path')
        try:
            request_frames = (
                frames_for_video(selected_video_path)
                if selected_video_path is not None else video_frames
            )
        except ValueError as error:
            return JsonResponse({'error': str(error)}, status=400)

        common_context = {
            "transcriptContext": audio_transcript,
            "frameContext": request_frames,
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
            if not openai_api_key:
                return JsonResponse(
                    {
                        "error": (
                            "Remote AI is unavailable because the OpenAI API key is "
                            "empty. Would you like to switch to Local?"
                        ),
                        "assistant_mode": "remote",
                        "can_fallback_to_local": True,
                    },
                    status=503,
                )
            try:
                assistant = RemoteAPI(
                    **common_context,
                    APIKey=openai_api_key,
                )
                response_text = assistant.respond(message, gpt_history)
            except RemoteAuthenticationError:
                return JsonResponse(
                    {
                        "error": (
                            "Remote AI is unavailable because the OpenAI API key is "
                            "invalid. Would you like to switch to Local?"
                        ),
                        "assistant_mode": "remote",
                        "can_fallback_to_local": True,
                    },
                    status=503,
                )
            except RemoteResponseError as error:
                return JsonResponse(
                    {"error": str(error), "assistant_mode": "remote"},
                    status=502,
                )
            except (APIConnectionError, APIStatusError, TimeoutError) as error:
                return JsonResponse(
                    {
                        "error": (
                            f"Remote AI is unavailable: {error}. "
                            "Would you like to switch to Local?"
                        ),
                        "assistant_mode": "remote",
                        "can_fallback_to_local": True,
                    },
                    status=503,
                )

        if history_generation == gpt_history_generation:
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

            return JsonResponse(
                {'message': 'Annotation data saved successfully'},
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
