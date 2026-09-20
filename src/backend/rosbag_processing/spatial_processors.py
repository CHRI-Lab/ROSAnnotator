"""Motion and wrench processors; all topics and entities are data-driven."""
import hashlib
import json
import math

from .view_processor import DataViewProcessor, ViewUnavailable
from .spatial_transforms import TransformBuffer, vector, quaternion, multiply, rotate


def identity(topic, name):
    return json.dumps([topic, name], ensure_ascii=False, separators=(',', ':'))


def color(key):
    hue = int(hashlib.sha256(key.encode()).hexdigest()[:8], 16) % 360
    return f'hsl({hue}, 65%, 60%)'


def number_option(context, key, default, minimum, maximum):
    value = context.options.get(key, default)
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not minimum <= value <= maximum:
        raise ViewUnavailable(f'{key} must be between {minimum} and {maximum}.')
    return value


class MultiTopicProcessor(DataViewProcessor):
    def check_availability(self, context):
        candidates = sorted(name for name, info in context.reader.topics.items()
                            if info['message_type'] in self.supported_message_types and info['message_count'] > 0)
        topics = context.options.get('topics', candidates)
        if not isinstance(topics, list) or not topics or any(not isinstance(t, str) or t not in candidates for t in topics):
            raise ViewUnavailable('Select nonempty topics with supported types: ' + ', '.join(self.supported_message_types))
        return sorted(set(topics))

    def preprocess(self, context, data):
        limit = int(number_option(context, 'max_samples', 2000, 2, 20000))
        tolerance = number_option(context, 'sample_tolerance_seconds', 0.5, 0, 60)
        used_hues = set()
        for entity in data['entities']:
            hue = int(hashlib.sha256(entity['id'].encode()).hexdigest()[:8], 16) % 360
            # Resolve collisions deterministically within the sorted entity list.
            while hue in used_hues and len(used_hues) < 360:
                hue = (hue+137) % 360
            used_hues.add(hue)
            entity['color'] = f'hsl({hue}, 65%, 60%)'
            # Last record wins for duplicate normalized timestamps.
            samples = sorted({s['seconds']: s for s in entity['samples']}.values(), key=lambda s: s['seconds'])
            entity['sample_count'] = len(samples)
            if self.view_id == 'motion':
                distance = sum(math.hypot(b['position'][0]-a['position'][0], b['position'][1]-a['position'][1])
                               for a, b in zip(samples, samples[1:]))
                elapsed = samples[-1]['seconds'] - samples[0]['seconds']
                entity['summary'] = {'distance_m': distance, 'elapsed_seconds': elapsed,
                                     'average_speed_mps': distance / elapsed if elapsed > 0 else 0}
            if len(samples) > limit:
                # Preserve endpoints; statistics are calculated before downsampling.
                samples = [samples[round(i*(len(samples)-1)/(limit-1))] for i in range(limit)]
                context.reader.warn(f"{entity['label']}: samples reduced to {limit}; endpoints preserved.")
            entity['samples'] = samples
        data['sample_tolerance_seconds'] = tolerance
        return data


class MotionProcessor(MultiTopicProcessor):
    view_id = 'motion'
    supported_message_types = ('nav_msgs/Odometry', 'people_msgs/People')

    def extract(self, context, topics):
        records = sorted(context.reader.records(topics), key=lambda r: (r.seconds, r.topic))
        fixed = context.options.get('fixed_frame')
        if fixed is not None and (not isinstance(fixed, str) or not fixed.strip('/ ')):
            raise ViewUnavailable('fixed_frame must be a nonempty frame name.')
        fixed = fixed.lstrip('/') if fixed else next((r.frame_id.lstrip('/') for r in records if r.frame_id), '')
        if not fixed:
            raise ViewUnavailable('Motion data has no valid header.frame_id.')
        transforms = TransformBuffer(context.reader)
        entities = {}
        tracked_names, invalid_ids = {}, set()
        for record in records:
            msg, frame = record.message, record.frame_id.lstrip('/')
            robot = context.reader.topics[record.topic]['message_type'] == 'nav_msgs/Odometry'
            try:
                if not frame:
                    raise ValueError('Missing frame')
                offset, rotation = transforms.lookup(fixed, frame, context.reader.origin + record.seconds)
            except ValueError:
                context.reader.warn(f'{record.topic}: skipped incompatible frame "{frame}"; no transform to "{fixed}".')
                continue
            seen = set()
            for person in [msg] if robot else getattr(msg, 'people', []):
                name = record.topic if robot else getattr(person, 'name', '')
                if not isinstance(name, str) or not name.strip():
                    context.reader.warn(f'{record.topic}: skipped person with an empty name.')
                    continue
                key = identity(record.topic, name)
                if key in seen:
                    context.reader.warn(f'{record.topic}: duplicate person name "{name}" at one timestamp; first used.')
                    continue
                seen.add(key)
                tracking_id = getattr(person, 'id', None) if not robot else None
                if tracking_id is not None:
                    tracked = identity(record.topic, str(tracking_id))
                    previous = tracked_names.setdefault(tracked, key)
                    if previous != key:
                        invalid_ids.update((previous, key))
                        context.reader.warn(f'{record.topic}: tracked person {tracking_id} changed name; entity rejected.')
                try:
                    if robot:
                        position = vector(msg.pose.pose.position)
                        attitude = quaternion(msg.pose.pose.orientation)
                        # Odometry twist is in child_frame_id; pose orientation maps it to header.frame_id.
                        velocity = rotate(attitude, vector(msg.twist.twist.linear))
                        attitude = multiply(rotation, attitude)
                        x, y, z, w = attitude
                        heading = math.atan2(2*(w*z+x*y), 1-2*(y*y+z*z))
                    else:
                        position, velocity = vector(person.position), vector(person.velocity)
                        heading = None
                    position = [a+b for a, b in zip(rotate(rotation, position), offset)]
                    velocity = rotate(rotation, velocity)
                    if heading is None:
                        heading = math.atan2(velocity[1], velocity[0])
                    entity = entities.setdefault(key, {'id': key, 'topic': record.topic, 'name': name,
                        'label': record.topic if robot else f'{record.topic} · {name}',
                        'kind': 'robot' if robot else 'person', 'color': color(key), 'samples': []})
                    entity['samples'].append({'seconds': record.seconds, 'bag_seconds': record.seconds + context.reader.offset,
                        'position': position, 'velocity': velocity, 'heading': heading, 'source_frame': frame})
                except (ValueError, TypeError, AttributeError):
                    context.reader.warn(f'{record.topic}: skipped invalid position, orientation or velocity.')
        valid = [entity for key, entity in sorted(entities.items()) if key not in invalid_ids and entity['samples']]
        if not valid:
            raise ViewUnavailable('No usable motion entities in a compatible coordinate frame.')
        return {'fixed_frame': fixed, 'entities': valid, 'units': {'position': 'm', 'velocity': 'm/s', 'heading': 'rad'}}


class WrenchProcessor(MultiTopicProcessor):
    view_id = 'wrench'
    supported_message_types = ('geometry_msgs/WrenchStamped',)

    def extract(self, context, topics):
        entities = {}
        for record in context.reader.records(topics):
            try:
                force, torque = vector(record.message.wrench.force), vector(record.message.wrench.torque)
                if not record.frame_id:
                    raise ValueError('Missing frame')
                entity = entities.setdefault(record.topic, {'id': record.topic, 'topic': record.topic,
                    'label': record.topic, 'kind': 'wrench', 'color': color(record.topic),
                    'frame_id': record.frame_id, 'samples': []})
                if entity['frame_id'] != record.frame_id:
                    context.reader.warn(f'{record.topic}: skipped wrench with changed coordinate frame.')
                    continue
                entity['samples'].append({'seconds': record.seconds, 'bag_seconds': record.seconds + context.reader.offset,
                                         'force': force, 'torque': torque})
            except (ValueError, TypeError, AttributeError):
                context.reader.warn(f'{record.topic}: skipped invalid force, torque or frame.')
        if not entities:
            raise ViewUnavailable('No usable force/torque samples in this range.')
        return {'entities': [entities[key] for key in sorted(entities)], 'units': {'force': 'N', 'torque': 'N·m'}}
