from rest_framework import serializers

class TranscriptionRequestSerializer(serializers.Serializer):
    audio_file_path = serializers.CharField()
    output_folder_path = serializers.CharField()

class BooklistSerializer(serializers.Serializer):
    name = serializers.CharField()
    data = serializers.DictField()