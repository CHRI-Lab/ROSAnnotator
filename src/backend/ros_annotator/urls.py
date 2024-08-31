"""
URL configuration for ros_annotator project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include
from django.urls import path
from rosbag_processing import views  

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/', include('rosbag_processing.urls')),
]

# urlpatterns = [
#     path('list_filenames/', views.list_filenames, name='list_filenames'),
#     path('process_rosbag/', views.process_rosbag, name='process_rosbag'),
#     path('transcribe_audio/', views.transcribe_audio, name='transcribe_audio'),
#     path('update_booklist/', views.update_booklist, name='update_booklist'),
#     path('save_annotation/', views.save_annotation, name='save_annotation'),
#     path('get_annotation/', views.get_annotation, name='get_annotation'),
# ]


