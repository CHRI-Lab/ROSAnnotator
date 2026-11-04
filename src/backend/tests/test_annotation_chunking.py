import csv
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.test import SimpleTestCase

from rosbag_processing.data_utils import load_annotation


class ChunkConfirmationSplittingTests(SimpleTestCase):
    def setUp(self):
        self.temporary_directory = TemporaryDirectory()
        root = Path(self.temporary_directory.name)
        self.bag_directory = root / 'bags'
        self.annotation_directory = root / 'annotations'
        self.manifest_directory = root / 'manifests'
        self.bag_directory.mkdir()
        self.annotation_directory.mkdir()
        (self.bag_directory / 'example.bag').write_bytes(b'bag')
        self.settings_patch = self.settings(
            ROSBAG_DATA_DIR=str(self.bag_directory),
            ANNOTATION_PATH=str(self.annotation_directory),
            CHUNK_MANIFEST_DIR=str(self.manifest_directory),
        )
        self.settings_patch.enable()

    def tearDown(self):
        self.settings_patch.disable()
        self.temporary_directory.cleanup()

    def write_annotation(self):
        path = self.annotation_directory / 'annotations.csv'
        with path.open('w', newline='', encoding='utf-8') as stream:
            writer = csv.DictWriter(stream, fieldnames=[
                'id', 'axisType', 'axisName', 'axisBooklistName',
                'start', 'end', 'text', 'bagFilename', 'sourceDuration',
            ])
            writer.writeheader()
            writer.writerow({
                'id': 1, 'axisType': 'Type-in', 'axisName': 'Notes',
                'axisBooklistName': '', 'start': 50, 'end': 70,
                'text': 'span', 'bagFilename': 'example.bag',
                'sourceDuration': 120,
            })
        return path

    @patch('rosbag_processing.chunk_views.read_duration', return_value=120)
    def test_confirming_chunks_rewrites_annotation_before_any_processing(
        self, _read_duration,
    ):
        self.write_annotation()

        response = self.client.post('/api/chunks/', {
            'bag_filename': 'example.bag',
            'annotation_filename': 'annotations.csv',
            'chunking_enabled': True,
            'chunk_seconds': 60,
        }, content_type='application/json')

        self.assertEqual(response.status_code, 201)
        self.assertTrue(all(
            chunk['status'] == 'not_processed' for chunk in response.data['chunks']
        ))
        blocks = load_annotation(
            'annotations.csv', str(self.annotation_directory),
        )[0]['annotationBlocks']
        self.assertEqual(blocks, [
            {'start': 50.0, 'end': 60.0, 'text': 'span'},
            {'start': 60.0, 'end': 70.0, 'text': 'span'},
        ])

