import os

from rest_framework import serializers

class TranscriptionRequestSerializer(serializers.Serializer):
    audio_file_path = serializers.CharField()
    output_folder_path = serializers.CharField()

class BooklistSerializer(serializers.Serializer):
    name = serializers.CharField()
    data = serializers.DictField()


class InputInspectionSerializer(serializers.Serializer):
    bag_filename = serializers.CharField(max_length=255, trim_whitespace=True)
    view_options = serializers.DictField(child=serializers.DictField(), required=False, default=dict)
    view_ids = serializers.ListField(child=serializers.CharField(), required=False, allow_empty=False)

    def validate_bag_filename(self, value):
        if value != os.path.basename(value) or not value.lower().endswith('.bag'):
            raise serializers.ValidationError('A valid .bag filename is required.')
        return value

    def validate_view_ids(self, values):
        from .view_registry import PROCESSORS
        if not set(values).issubset({processor.view_id for processor in PROCESSORS}):
            raise serializers.ValidationError('Unknown view ID.')
        return values
