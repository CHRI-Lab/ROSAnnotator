"""Run inside the ROS image: actual bag files, no mocked ROS reader."""
import tempfile
from pathlib import Path
from unittest import skipUnless
from unittest.mock import patch

from django.test import SimpleTestCase
from rest_framework.test import APIClient

try:
    from rosbag import Bag
    from genpy import Time
    from std_msgs.msg import String
except ImportError:
    Bag = None


@skipUnless(Bag, 'Requires the ROS runtime')
class RealInvalidBagTests(SimpleTestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.client = APIClient()
        override = self.settings(ROSBAG_DATA_DIR=str(self.root),
                                 PROCESSED_DATA_DIR=str(self.root / 'processed'))
        override.enable()
        self.addCleanup(override.disable)
        directory = patch('rosbag_processing.views.ROSBAG_DATA_DIR', str(self.root))
        directory.start()
        self.addCleanup(directory.stop)

    def test_empty_bag_has_zero_available_views(self):
        with Bag(str(self.root / 'empty.bag'), 'w'):
            pass
        inspection = self.client.post('/api/inputs/inspect/', {'bag_filename': 'empty.bag'}, format='json')
        self.assertEqual(inspection.status_code, 200, inspection.data)
        self.assertEqual(inspection.data['duration_seconds'], 0)
        response = self.client.post('/api/process_rosbag/', {'bag_filename': 'empty.bag'}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['error']['code'], 'no_available_views')
        self.assertTrue(response.data['views'])
        self.assertTrue(all(not v['available'] and v['reason'] for v in response.data['views'].values()))

    def assert_bad_bag(self, filename):
        for url in ['/api/inputs/inspect/', '/api/process_rosbag/', '/api/chunks/']:
            response = self.client.post(url, {'bag_filename': filename, 'chunking_enabled': False}, format='json')
            self.assertEqual(response.status_code, 400, (url, response.data))
            self.assertTrue(response.data.get('error'))

    def test_corrupt_bag_is_client_error(self):
        (self.root / 'corrupt.bag').write_bytes(b'not a ROS bag\x00\xff')
        self.assert_bad_bag('corrupt.bag')

    def test_truncated_real_bag_is_client_error(self):
        source = self.root / 'source.bag'
        with Bag(str(source), 'w') as bag:
            for second in range(3):
                bag.write('/test', String(data='sample' * 100), Time(second + 1))
        data = source.read_bytes()
        (self.root / 'truncated.bag').write_bytes(data[:len(data) // 2])
        self.assert_bad_bag('truncated.bag')
