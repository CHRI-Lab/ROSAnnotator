from django.urls import path
from .views import process_rosbag, list_filenames, transcribe_audio, update_booklist, save_annotation, get_annotation,gpt_chat

urlpatterns = [
    path('process_rosbag/', process_rosbag, name='process_rosbag'),
    path('list_filenames/', list_filenames, name='list_filenames'),
    path('transcribe_audio/', transcribe_audio, name='transcribe_audio'),
    path('update_booklist/', update_booklist, name='update_booklist'),
    path('save_annotation/', save_annotation, name='save_annotation'),
    path('get_annotation/', get_annotation, name='get_annotation'),
    path('gpt_chat/', gpt_chat, name='gpt_chat'),
]