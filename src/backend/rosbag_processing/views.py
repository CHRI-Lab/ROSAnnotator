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
    """Legacy HTTP adapter for the shared whole-bag session contract."""
    from .processing_sessions import ProcessingError, ProcessingRequest
    from .rosbag_session import RosbagProcessingSession

    global video_frames, video_fps
    bag_filename = request.data.get('bag_filename')
    if not bag_filename:
        return Response({'error': 'bag_filename is required'}, status=400)
    session = RosbagProcessingSession()
    try:
        result = session.process(ProcessingRequest(
            bag_path=os.path.join(ROSBAG_DATA_DIR, bag_filename),
            booklist_filename=request.data.get('booklist_filename'),
            annotation_filename=request.data.get('annotation_filename'),
        ))
    except ProcessingError as exc:
        return Response({'error': str(exc)}, status=exc.status_code)
    except Exception as exc:
        return Response({'error': str(exc)}, status=500)
    result['ai_records'] = load_ai_records(request.data['annotation_filename']) if request.data.get('annotation_filename') else []
    video_frames, video_fps = session.video_frames, session.video_fps
    return Response(result)


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
        hybrid_selection = assistant_mode == "hybrid"
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

            selected_targets = set(context_routes.values())
            if "remote" in selected_targets and not openai_api_key:
                return JsonResponse(
                    {
                        "error": (
                            "Remote AI is unavailable because the OpenAI API key is "
                            "empty. Would you like to switch to Local?"
                        ),
                        "assistant_mode": "hybrid",
                        "can_fallback_to_local": True,
                    },
                    status=503,
                )
            if len(selected_targets) == 1:
                # A homogeneous hybrid selection needs no cross-provider
                # orchestration; run it through the selected provider.
                assistant_mode = selected_targets.pop()
            else:
                # Do not silently send locally routed data to the remote
                # provider until a mixed-context orchestrator is available.
                return JsonResponse(
                    {
                        "error": "Mixed Local/Remote hybrid routing is not implemented yet.",
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
                if hybrid_selection:
                    error_message = (
                        "Local AI is unavailable. Choose a local model before starting "
                        "Docker, and check that its .gguf file is in the models/ directory."
                    )
                else:
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
