from django.urls import path
from .views import process_rosbag, list_filenames, transcribe_audio

urlpatterns = [
    path('process_rosbag/', process_rosbag, name='process_rosbag'),
    path('list_filenames/', list_filenames, name='list_filenames'),
    path('transcribe/', transcribe_audio, name='transcribe_audio'),
]