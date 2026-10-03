"""Integration coverage for real serialized Wrench messages."""
import tempfile
from pathlib import Path
from unittest import skipUnless
from unittest.mock import patch
from django.test import SimpleTestCase
from rest_framework.test import APIClient

try:
    import rosbag
except ImportError:
    rosbag = None


@skipUnless(rosbag, 'Requires the ROS runtime')
class RealSpatialBagTests(SimpleTestCase):
    def test_real_sensor_bag_through_api_with_two_chunks_and_cache(self):
        from tools.generate_spatial_demo import generate
        from rosbag_processing.spatial_processors import WrenchProcessor
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            generate(root / 'demo.bag')
            with self.settings(ROSBAG_DATA_DIR=str(root), CHUNK_MANIFEST_DIR=str(root/'chunks'), PROCESSED_DATA_DIR=str(root/'processed')):
                with patch('rosbag_processing.views.ROSBAG_DATA_DIR', str(root)):
                    client = APIClient()
                    response = client.post('/api/chunks/', {'bag_filename': 'demo.bag', 'chunking_enabled': True,
                        'chunk_seconds': 15}, format='json')
                    self.assertEqual(response.status_code, 201, response.data)
                    manifest = response.data
                    for index in (0, 1):
                        url = f"/api/chunks/{manifest['id']}/{index}/process/"
                        result = client.post(url, {}, format='json')
                        self.assertEqual(result.status_code, 200, result.data)
                        views = result.data['views']
                        self.assertFalse(views['video']['available'])
                        self.assertTrue(views['annotations']['available'])
                        self.assertTrue(views['wrench']['available'])
                        entities = views['wrench']['processed_data']['entities']
                        self.assertEqual(len(entities), 2)
                        for entity in entities:
                            self.assertAlmostEqual(entity['samples'][0]['seconds'], 0)
                            self.assertAlmostEqual(entity['samples'][0]['bag_seconds'], index*15)
                        with patch.object(WrenchProcessor, 'extract', side_effect=AssertionError('must reuse cache')):
                            cached = client.post(url, {'view_ids': ['wrench']}, format='json')
                            self.assertTrue(cached.data['views']['wrench']['available'])
