from django.urls import path
from .views import process_rosbag

urlpatterns = [
    path('process_rosbag/', process_rosbag, name='process_rosbag'),
]