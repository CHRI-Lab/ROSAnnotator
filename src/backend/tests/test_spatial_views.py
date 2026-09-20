import math
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace as NS

from rosbag_processing.rosbag_reader import RosbagReader
from rosbag_processing.view_processor import ViewContext, ViewUnavailable
from rosbag_processing.spatial_processors import MotionProcessor, WrenchProcessor
from rosbag_processing.spatial_transforms import TransformBuffer
from tests.test_data_view_processing import FakeBag, stamp


def vec(x=0, y=0, z=0):
    return NS(x=x, y=y, z=z)


def rotation(yaw=0):
    return NS(x=0, y=0, z=math.sin(yaw/2), w=math.cos(yaw/2))


def header(time=101, frame='map'):
    return NS(stamp=stamp(time), frame_id=frame)


def odom(time=101, x=0, y=0, yaw=0, velocity=None, frame='map'):
    return NS(header=header(time, frame), child_frame_id='base_link',
              pose=NS(pose=NS(position=vec(x, y), orientation=rotation(yaw))),
              twist=NS(twist=NS(linear=velocity or vec(1))))


def person(name='Alice', x=0, velocity=None, **extra):
    return NS(name=name, position=vec(x), velocity=velocity or vec(1), **extra)


def people(time=101, persons=None, frame='map'):
    return NS(header=header(time, frame), people=persons if persons is not None else [person()])


def wrench(time=101, force=None, torque=None, frame='sensor'):
    return NS(header=header(time, frame), wrench=NS(force=force or vec(1, -2, 3), torque=torque or vec(-4, 5, -6)))


def tf(time=100, parent='map', child='camera', x=10, yaw=math.pi/2):
    return NS(transforms=[NS(header=header(time, parent), child_frame_id=child,
                            transform=NS(translation=vec(x), rotation=rotation(yaw)))])


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

    def test_robot_position_yaw_and_child_frame_velocity(self):
        result = self.run_processor(MotionProcessor(), [('/odom', 'nav_msgs/Odometry', odom(x=2, y=3, yaw=math.pi/2))])
        entity = result['processed_data']['entities'][0]
        sample = entity['samples'][0]
        self.assertEqual(sample['position'], [2, 3, 0])
        self.assertAlmostEqual(sample['heading'], math.pi/2)
        self.assertAlmostEqual(sample['velocity'][0], 0)
        self.assertAlmostEqual(sample['velocity'][1], 1)
        self.assertEqual(entity['kind'], 'robot')

    def test_people_only_multiple_topics_names_and_blank_names(self):
        result = self.run_processor(MotionProcessor(), [
            ('/front', 'people_msgs/People', people(persons=[person(), person('Bob'), person(' ')])),
            ('/rear', 'people_msgs/People', people()),
        ])
        entities = result['processed_data']['entities']
        self.assertEqual(len(entities), 3)
        self.assertEqual(len({e['id'] for e in entities}), 3)
        self.assertTrue(all(e['kind'] == 'person' for e in entities))
        self.assertTrue(any('empty name' in w for w in result['warnings']))

    def test_multiple_robot_topics_and_colors_are_repeatable(self):
        entries = [('/a', 'nav_msgs/Odometry', odom()), ('/b', 'nav_msgs/Odometry', odom(x=3))]
        first = self.run_processor(MotionProcessor(), entries)['processed_data']['entities']
        second = self.run_processor(MotionProcessor(), entries)['processed_data']['entities']
        self.assertEqual(first, second)
        self.assertEqual(len({e['color'] for e in first}), 2)

    def test_known_tracked_id_changing_name_is_rejected(self):
        result = self.run_processor(MotionProcessor(), [('/people', 'people_msgs/People', people(persons=[person(id=7), person('Bob')])),
            ('/people', 'people_msgs/People', people(time=102, persons=[person('Other', id=7)]))])
        self.assertEqual([e['name'] for e in result['processed_data']['entities']], ['Bob'])
        self.assertTrue(any('changed name' in w for w in result['warnings']))

    def test_invalid_numeric_samples_do_not_remove_valid_entities(self):
        result = self.run_processor(MotionProcessor(), [('/people', 'people_msgs/People', people(persons=[person(x=float('nan')), person('Bob')]))])
        self.assertEqual(len(result['processed_data']['entities']), 1)

    def test_incompatible_frame_is_skipped_and_total_mismatch_unavailable(self):
        entries = [('/a', 'nav_msgs/Odometry', odom()), ('/b', 'nav_msgs/Odometry', odom(frame='other'))]
        result = self.run_processor(MotionProcessor(), entries, {'fixed_frame': 'map'})
        self.assertEqual(len(result['processed_data']['entities']), 1)
        self.assertTrue(any('incompatible' in w for w in result['warnings']))
        with self.assertRaises(ViewUnavailable):
            self.run_processor(MotionProcessor(), entries, {'fixed_frame': 'unknown'})

    def test_static_tf_before_chunk_transforms_position_velocity_and_heading(self):
        result = self.run_processor(MotionProcessor(), [('/tf_static', 'tf2_msgs/TFMessage', tf()),
            ('/odom', 'nav_msgs/Odometry', odom(time=103, x=1, frame='camera'))],
            {'fixed_frame': 'map'}, {'start_seconds': 2, 'end_seconds': 5})
        s = result['processed_data']['entities'][0]['samples'][0]
        self.assertAlmostEqual(s['position'][0], 10)
        self.assertAlmostEqual(s['position'][1], 1)
        self.assertAlmostEqual(s['heading'], math.pi/2)
        self.assertAlmostEqual(s['velocity'][1], 1)
        self.assertEqual((s['seconds'], s['bag_seconds']), (1, 3))

    def test_dynamic_tf_interpolation_and_inverse_no_extrapolation(self):
        entries = [('/tf', tf(100, x=0, yaw=0), stamp(100)), ('/tf', tf(110, x=10, yaw=math.pi), stamp(110))]
        bag = FakeBag(entries, {'/tf': ('tf2_msgs/TFMessage', 2)})
        with RosbagReader('test', bag_factory=lambda *_: bag) as reader:
            buffer = TransformBuffer(reader)
            p, q = buffer.lookup('map', 'camera', 105)
            self.assertAlmostEqual(p[0], 5)
            self.assertAlmostEqual(q[2], math.sin(math.pi/4))
            self.assertAlmostEqual(buffer.lookup('camera', 'map', 105)[0][1], 5)
            with self.assertRaises(ValueError):
                buffer.lookup('map', 'camera', 111)

    def test_summary_statistics_before_downsampling_and_endpoints(self):
        entries = [('/odom', 'nav_msgs/Odometry', odom(time=100+i, x=x, y=y))
                   for i, (x, y) in enumerate([(0, 0), (3, 0), (3, 4)])]
        entity = self.run_processor(MotionProcessor(), entries, {'max_samples': 2})['processed_data']['entities'][0]
        self.assertEqual(entity['summary']['distance_m'], 7)
        self.assertEqual(entity['summary']['average_speed_mps'], 3.5)
        self.assertEqual([s['seconds'] for s in entity['samples']], [0, 2])
        self.assertEqual(entity['sample_count'], 3)

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
        for processor in [MotionProcessor(), WrenchProcessor()]:
            with self.assertRaises(ViewUnavailable):
                self.run_processor(processor, [], extra_types={'/empty': (processor.supported_message_types[0], 0), '/other': ('std_msgs/String', 4)})

    def test_selected_topics_and_invalid_options(self):
        entries = [('/a', 'nav_msgs/Odometry', odom()), ('/b', 'nav_msgs/Odometry', odom())]
        result = self.run_processor(MotionProcessor(), entries, {'topics': ['/b']})
        self.assertEqual(result['selected_topics'], ['/b'])
        for options in [{'topics': ['/missing']}, {'max_samples': 1}, {'fixed_frame': ''}, {'sample_tolerance_seconds': -1}]:
            with self.assertRaises(ViewUnavailable):
                self.run_processor(MotionProcessor(), entries, options)
