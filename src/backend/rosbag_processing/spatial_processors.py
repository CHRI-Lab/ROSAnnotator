"""Wrench processors; all topics and entities are data-driven."""
import hashlib
import math

from .view_processor import DataViewProcessor, ViewUnavailable


def vector(value):
    result = [float(getattr(value, key)) for key in ('x', 'y', 'z')]
    if not all(math.isfinite(v) for v in result):
        raise ValueError('Nonfinite vector')
    return result


def color(key):
    hue = int(hashlib.sha256(key.encode()).hexdigest()[:8], 16) % 360
    return f'hsl({hue}, 65%, 60%)'


def number_option(context, key, default, minimum, maximum):
    value = context.options.get(key, default)
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not minimum <= value <= maximum:
        raise ViewUnavailable(f'{key} must be between {minimum} and {maximum}.')
    return value


def integer_option(context, key, default, minimum, maximum):
    value = context.options.get(key, default)
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise ViewUnavailable(f'{key} must be an integer between {minimum} and {maximum}.')
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
        limit = integer_option(context, 'max_samples', 2000, 2, 20000)
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
            if len(samples) > limit:
                # Preserve the first and last samples when downsampling.
                samples = [samples[round(i*(len(samples)-1)/(limit-1))] for i in range(limit)]
                context.reader.warn(f"{entity['label']}: samples reduced to {limit}; endpoints preserved.")
            entity['samples'] = samples
        data['sample_tolerance_seconds'] = tolerance
        return data


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
