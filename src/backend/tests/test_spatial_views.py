import tempfile
import unittest
import json
import math
from pathlib import Path
from types import SimpleNamespace as NS

from rosbag_processing.rosbag_reader import RosbagReader
from rosbag_processing.view_processor import ViewContext, ViewUnavailable
from rosbag_processing.spatial_processors import WrenchProcessor
from tests.test_data_view_processing import FakeBag, stamp


def vec(x=0, y=0, z=0):
    return NS(x=x, y=y, z=z)


def header(time=101, frame='map'):
    return NS(stamp=stamp(time), frame_id=frame)


def wrench(time=101, force=None, torque=None, frame='sensor'):
    return NS(header=header(time, frame), wrench=NS(force=force or vec(1, -2, 3), torque=torque or vec(-4, 5, -6)))


class SpatialViewTests(unittest.TestCase):
    def run_processor(self, processor, entries, options=None, chunk=None, extra_types=None):
        types = {}
        records = []
        for topic, kind, msg in entries:
            types[topic] = (kind, types.get(topic, ('', 0))[1]+1)
            records.append((topic, msg, stamp(101)))
        types.update(extra_types or {})
        bag = FakeBag(records, types)
        with tempfile.TemporaryDirectory() as directory:
            with RosbagReader('test', chunk, lambda *_: bag) as reader:
                context = ViewContext(reader, Path(directory), options or {})
                selected = processor.check_availability(context)
                data = processor.preprocess(context, processor.extract(context, selected))
                result = processor.serialize(context, selected, data, reader.warnings)
        self.assertTrue(bag.closed)
        return result

    def test_wrench_six_components_and_multiple_topics(self):
        result = self.run_processor(WrenchProcessor(), [('/a', 'geometry_msgs/WrenchStamped', wrench()),
            ('/b', 'geometry_msgs/WrenchStamped', wrench())])
        entities = result['processed_data']['entities']
        self.assertEqual(len(entities), 2)
        self.assertEqual(entities[0]['samples'][0]['force'], [1, -2, 3])
        self.assertEqual(entities[0]['samples'][0]['torque'], [-4, 5, -6])

    def test_wrench_time_fallback_sort_duplicates_and_frame_change(self):
        result = self.run_processor(WrenchProcessor(), [('/a', 'geometry_msgs/WrenchStamped', wrench(104)),
            ('/a', 'geometry_msgs/WrenchStamped', wrench(0)),
            ('/a', 'geometry_msgs/WrenchStamped', wrench(104, force=vec(8))),
            ('/a', 'geometry_msgs/WrenchStamped', wrench(105, frame='changed'))])
        samples = result['processed_data']['entities'][0]['samples']
        self.assertEqual([s['seconds'] for s in samples], [1, 4])
        self.assertEqual(samples[-1]['force'][0], 8)
        self.assertTrue(result['warnings'])

    def test_empty_unsupported_or_missing_type_is_unavailable(self):
        for processor in [WrenchProcessor()]:
            with self.assertRaises(ViewUnavailable):
                self.run_processor(processor, [], extra_types={'/empty': (processor.supported_message_types[0], 0), '/other': ('std_msgs/String', 4)})

    def test_selected_topics_and_invalid_options(self):
        entries = [('/a', 'geometry_msgs/WrenchStamped', wrench()), ('/b', 'geometry_msgs/WrenchStamped', wrench())]
        result = self.run_processor(WrenchProcessor(), entries, {'topics': ['/b']})
        self.assertEqual(result['selected_topics'], ['/b'])
        for options in [{'topics': ['/missing']}, {'max_samples': 1}, {'sample_tolerance_seconds': -1}]:
            with self.assertRaises(ViewUnavailable):
                self.run_processor(WrenchProcessor(), entries, options)
    def test_only_empty_wrench_topic_makes_view_unavailable(self):
        with self.assertRaises(ViewUnavailable):
            self.run_processor(WrenchProcessor(), [], extra_types={'/empty': ('geometry_msgs/WrenchStamped', 0)})

    def test_empty_topic_rejected_but_view_available_with_another_valid_topic(self):
        result = self.run_processor(WrenchProcessor(), [('/valid', 'geometry_msgs/WrenchStamped', wrench())],
                                    extra_types={'/empty': ('geometry_msgs/WrenchStamped', 0)})
        self.assertEqual(result['selected_topics'], ['/valid'])
        entities = result['processed_data']['entities']
        self.assertEqual(len(entities), 1)
        self.assertEqual(entities[0]['label'], '/valid')
        self.assertEqual(entities[0]['samples'][0]['force'], [1, -2, 3])

    def test_several_empty_topics_and_one_valid_topic(self):
        result = self.run_processor(WrenchProcessor(), [('/valid', 'geometry_msgs/WrenchStamped', wrench())],
                                    extra_types={'/empty_a': ('geometry_msgs/WrenchStamped', 0),
                                                 '/empty_b': ('geometry_msgs/WrenchStamped', 0)})
        self.assertEqual(result['selected_topics'], ['/valid'])
        self.assertEqual([e['label'] for e in result['processed_data']['entities']], ['/valid'])
        
    def test_multiple_topics_distinct_entities_with_consistent_colours(self):
        entries = [('/a', 'geometry_msgs/WrenchStamped', wrench()),
                   ('/b', 'geometry_msgs/WrenchStamped', wrench()),
                   ('/c', 'geometry_msgs/WrenchStamped', wrench())]
        first = self.run_processor(WrenchProcessor(), entries)['processed_data']['entities']
        second = self.run_processor(WrenchProcessor(), entries)['processed_data']['entities']
        reordered = self.run_processor(WrenchProcessor(), list(reversed(entries)))['processed_data']['entities']

        self.assertEqual(len(first), 3)
        self.assertEqual(len({e['id'] for e in first}), 3)
        colours = {e['label']: e['color'] for e in first}
        self.assertEqual({e['label']: e['color'] for e in second}, colours)
        self.assertEqual({e['label']: e['color'] for e in reordered}, colours)
        
    def test_invalid_component_values_skipped_or_flagged_without_breaking_series(self):
        for bad in (float('nan'), float('inf'), float('-inf'), None):
            with self.subTest(bad=bad):
                entries = [('/a', 'geometry_msgs/WrenchStamped', wrench(101)),
                           ('/a', 'geometry_msgs/WrenchStamped', wrench(102, force=vec(bad, 0, 0))),
                           ('/a', 'geometry_msgs/WrenchStamped', wrench(103, torque=vec(0, bad, 0))),
                           ('/a', 'geometry_msgs/WrenchStamped', wrench(104))]
                result = self.run_processor(WrenchProcessor(), entries)
                samples = result['processed_data']['entities'][0]['samples']
                seconds = [s['seconds'] for s in samples]

                self.assertIn(1, seconds)
                self.assertIn(4, seconds)
                self.assertEqual(seconds, sorted(seconds))
                for s in samples:
                    for v in s['force'] + s['torque']:
                        self.assertTrue(isinstance(v, (int, float)) and math.isfinite(v),
                                        f'invalid value {v!r} kept in series at {s["seconds"]}s')
                self.assertTrue(result['warnings'] or {2, 3}.isdisjoint(seconds))
                json.dumps(result, allow_nan=False)