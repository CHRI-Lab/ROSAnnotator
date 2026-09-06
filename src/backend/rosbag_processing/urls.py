from django.urls import path
from .chunk_views import create_chunks, get_chunks, process_chunk_view
from .views import inspect_input, process_rosbag, list_filenames, transcribe_audio, update_booklist, save_annotation, get_annotation,gpt_chat

urlpatterns = [
    path('chunks/', create_chunks, name='create_chunks'),
    path('chunks/<uuid:manifest_id>/', get_chunks, name='get_chunks'),
    path('chunks/<uuid:manifest_id>/<int:chunk_index>/', get_chunks, name='get_chunk'),
    path('chunks/<uuid:manifest_id>/<int:chunk_index>/process/', process_chunk_view, name='process_chunk'),
    path('inputs/inspect/', inspect_input, name='inspect_input'),
    path('process_rosbag/', process_rosbag, name='process_rosbag'),
    path('list_filenames/', list_filenames, name='list_filenames'),
    path('transcribe_audio/', transcribe_audio, name='transcribe_audio'),
    path('update_booklist/', update_booklist, name='update_booklist'),
    path('save_annotation/', save_annotation, name='save_annotation'),
    path('get_annotation/', get_annotation, name='get_annotation'),
    path('gpt_chat/', gpt_chat, name='gpt_chat'),
]
