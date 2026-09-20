"""ROS-only boundary. All timestamps in records use the requested origin."""
import math
from dataclasses import dataclass


class BagReadError(RuntimeError):
    """The input cannot be opened or its metadata cannot be read."""


@dataclass(frozen=True)
class Record:
    topic: str
    message: object
    seconds: float
    frame_id: str


class RosbagReader:
    def __init__(self, path, chunk=None, bag_factory=None):
        self.path, self.chunk, self.bag_factory = path, chunk, bag_factory
        self.bag = None
        self.warnings = []

    def __enter__(self):
        if self.bag_factory is None:
            from rosbag.bag import Bag
            self.bag_factory = Bag
        try:
            self.bag = self.bag_factory(str(self.path), 'r')
            self.topics = {
                name: {'name': name, 'message_type': info.msg_type, 'message_count': info.message_count}
                for name, info in self.bag.get_type_and_topic_info().topics.items()
            }
            has_messages = any(t['message_count'] > 0 for t in self.topics.values())
            # ROS raises "Bag contains no message" for the times of a valid empty bag.
            self.start = float(self.bag.get_start_time()) if has_messages else 0.0
            self.end = float(self.bag.get_end_time()) if has_messages else 0.0
            if not all(math.isfinite(t) for t in (self.start, self.end)) or self.end < self.start:
                raise ValueError('Invalid bag time bounds')
            self.offset = float(self.chunk['start_seconds']) if self.chunk else 0.0
            stop = float(self.chunk['end_seconds']) if self.chunk else self.end - self.start
            self.duration = max(0.0, min(stop, self.end - self.start) - self.offset)
            self.origin = self.start + self.offset
            return self
        except Exception as exc:
            if self.bag is not None:
                self.bag.close()
            raise BagReadError('Unable to read ROSBag: the file may be invalid or truncated.') from exc

    def __exit__(self, *_):
        self.bag.close()

    def warn(self, message):
        if message not in self.warnings:
            self.warnings.append(message)

    @staticmethod
    def seconds(stamp):
        try:
            value = float(stamp.to_sec())
            return value if math.isfinite(value) else None
        except (AttributeError, TypeError, ValueError):
            return None

    def records(self, topics):
        # Do not filter by record time first: valid header times can differ.
        previous = {}
        for topic, message, recorded in self.bag.read_messages(topics=list(topics)):
            header = getattr(message, 'header', None)
            stamp = self.seconds(getattr(header, 'stamp', None))
            if stamp is None or stamp <= 0 or not self.start <= stamp <= self.end:
                stamp = self.seconds(recorded)
                self.warn('Invalid or absent header timestamp; used bag-record time.')
            if stamp is None:
                self.warn('Skipped message with invalid record timestamp.')
                continue
            seconds = stamp - self.origin
            if seconds < 0 or seconds > self.duration:
                continue
            # A chunk's end is exclusive, except for the final bag endpoint.
            if self.chunk and seconds == self.duration and stamp < self.end:
                continue
            if topic in previous and seconds <= previous[topic]:
                self.warn('Out-of-order or duplicate timestamps; stable timestamp order is used.')
            previous[topic] = seconds
            yield Record(topic, message, seconds, getattr(header, 'frame_id', '') or '')

    @staticmethod
    def ordered(samples):
        """Stable sort: preserve duplicate messages in original order."""
        return sorted(samples, key=lambda sample: sample[0])

    @property
    def time_origin(self):
        return {'reference': 'chunk_start' if self.chunk else 'bag_start',
                'bag_offset_seconds': self.offset, 'absolute_seconds': self.origin}
