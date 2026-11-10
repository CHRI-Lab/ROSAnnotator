import os
import re

from rest_framework import serializers


# Characters Windows forbids in filenames, plus the null byte. The datas
# directory is bind-mounted to a Windows host in normal use, so the stricter
# set applies even though the container is Linux.
_FORBIDDEN_NAME_CHARACTERS = re.compile(r'[\\/:*?"<>|\x00]')

# Windows treats these as device names regardless of extension.
_RESERVED_NAMES = {
    'CON', 'PRN', 'AUX', 'NUL',
    *(f'COM{digit}' for digit in range(1, 10)),
    *(f'LPT{digit}' for digit in range(1, 10)),
}

# ext4 and NTFS both cap a filename at 255 bytes. ".csv" is added by the view.
_MAX_NAME_BYTES = 255 - len('.csv')


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

class AnnotationBlockSerializer(serializers.Serializer):
    """One annotation block. Times are seconds."""

    start = serializers.FloatField()
    end = serializers.FloatField()
    text = serializers.CharField(
        required=False, allow_blank=True, trim_whitespace=False, default='',
    )
    # Absolute bounds of a source block clipped for chunk-local editing. They
    # are transient merge metadata and are not written to the CSV.
    sourceStart = serializers.FloatField(required=False)
    sourceEnd = serializers.FloatField(required=False)

    def validate_start(self, value):
        return _finite(value, 'start')

    def validate_end(self, value):
        return _finite(value, 'end')

    def validate_sourceStart(self, value):
        return _finite(value, 'sourceStart')

    def validate_sourceEnd(self, value):
        return _finite(value, 'sourceEnd')


def _finite(value, field):
    # Python's json module accepts NaN and Infinity even though JSON does not.
    # Either would be written to the CSV and fail to parse on the way back.
    if value != value or value in (float('inf'), float('-inf')):
        raise serializers.ValidationError(f'{field} must be a finite number.')
    return value


class AnnotationAxisSerializer(serializers.Serializer):
    """One time axis and its blocks, as the frontend collects it."""

    id = serializers.IntegerField()
    axisType = serializers.CharField(
        required=False, allow_blank=True, default='',
    )
    axisName = serializers.CharField(
        required=False, allow_blank=True, default='',
    )
    axisBooklistName = serializers.CharField(
        required=False, allow_blank=True, default='',
    )
    annotationBlocks = AnnotationBlockSerializer(many=True)


class SaveAnnotationSerializer(serializers.Serializer):
    """Validates a save request before anything touches the filesystem.

    annotation_name is a stem: the view appends ".csv". Note this differs from
    ChunkRequestSerializer.annotation_filename, which expects a full ".csv"
    filename because it names an existing file rather than one being created.
    """

    annotation_name = serializers.CharField(max_length=255, trim_whitespace=True)
    annotation_data = AnnotationAxisSerializer(many=True)
    confirm_overwrite = serializers.BooleanField(required=False, default=False)
    # Chunk saves merge into the existing file. Both are needed to locate the
    # chunk, so neither is meaningful alone.
    manifest_id = serializers.UUIDField(allow_null=True, default=None)
    chunk_index = serializers.IntegerField(allow_null=True, default=None, min_value=0)
    
    # The recording this annotation set belongs to. Optional: a save that omits
    # it preserves whatever the file already records, rather than clearing it.
    bag_filename = serializers.CharField(
        required=False, allow_blank=True, default='',
        max_length=255, trim_whitespace=True,
    )
    source_duration = serializers.FloatField(
        required=False, allow_null=True, default=None,
    )

    def validate_bag_filename(self, value):
        if not value:
            return ''
        if value != os.path.basename(value) or not value.lower().endswith('.bag'):
            raise serializers.ValidationError('A valid .bag filename is required.')
        return value

    def validate_source_duration(self, value):
        if value is None:
            return None
        value = _finite(value, 'source_duration')
        if value <= 0:
            raise serializers.ValidationError(
                'source_duration must be greater than zero.'
            )
        return value

    def validate(self, values):
        has_manifest = values.get('manifest_id') is not None
        has_index = values.get('chunk_index') is not None
        if has_manifest != has_index:
            raise serializers.ValidationError(
                'manifest_id and chunk_index must be supplied together.'
            )
        return values
    
    def validate_annotation_name(self, value):
        # Accept a name the user pasted with its extension rather than
        # producing "session.csv.csv". Needed once the save dialog is
        # prefilled with a loaded annotation's filename.
        if value.lower().endswith('.csv'):
            value = value[:-4]

        value = value.strip()

        if not value:
            raise serializers.ValidationError('A name is required.')

        if value != os.path.basename(value):
            raise serializers.ValidationError(
                'A name without a path is required.'
            )

        if _FORBIDDEN_NAME_CHARACTERS.search(value):
            raise serializers.ValidationError(
                'A name cannot contain any of: \\ / : * ? " < > |'
            )

        if not value.strip('. '):
            raise serializers.ValidationError(
                'A name cannot consist only of dots or spaces.'
            )

        if value != value.rstrip('. '):
            raise serializers.ValidationError(
                'A name cannot end with a dot or a space.'
            )

        if value.upper() in _RESERVED_NAMES:
            raise serializers.ValidationError(
                f'"{value}" is a reserved filename.'
            )

        if len(value.encode('utf-8')) > _MAX_NAME_BYTES:
            raise serializers.ValidationError('That name is too long.')

        return value
