"""Small ROS-independent rigid-transform buffer (parent <- child).

Dynamic edges interpolate within their recorded interval, never extrapolate.
Static edges apply across the bag, including chunks starting after /tf_static.
"""
import math
from bisect import bisect_left
from collections import deque


def vector(value):
    result = [float(getattr(value, key)) for key in ('x', 'y', 'z')]
    if not all(math.isfinite(v) for v in result):
        raise ValueError('Nonfinite vector')
    return result


def quaternion(value):
    q = vector(value) + [float(value.w)]
    length = math.sqrt(sum(v * v for v in q))
    if not math.isfinite(length) or length < 1e-12:
        raise ValueError('Invalid quaternion')
    return [v / length for v in q]


def multiply(a, b):
    x, y, z, w = a
    X, Y, Z, W = b
    return [w*X+x*W+y*Z-z*Y, w*Y-x*Z+y*W+z*X,
            w*Z+x*Y-y*X+z*W, w*W-x*X-y*Y-z*Z]


def rotate(q, v):
    return multiply(multiply(q, [*v, 0]), [-q[0], -q[1], -q[2], q[3]])[:3]


def compose(a, b):
    offset = rotate(a[1], b[0])
    return ([a[0][i] + offset[i] for i in range(3)], multiply(a[1], b[1]))


def inverse(transform):
    p, q = transform
    q = [-q[0], -q[1], -q[2], q[3]]
    return rotate(q, [-v for v in p]), q


def interpolate(a, b, weight):
    p = [x + weight * (y-x) for x, y in zip(a[0], b[0])]
    qa, qb = a[1], b[1]
    dot = sum(x*y for x, y in zip(qa, qb))
    if dot < 0:
        qb, dot = [-x for x in qb], -dot
    if dot > 0.9995:
        q = [x + weight * (y-x) for x, y in zip(qa, qb)]
        length = math.sqrt(sum(x*x for x in q))
        return p, [x/length for x in q]
    angle = math.acos(max(-1, min(1, dot)))
    return p, [(math.sin((1-weight)*angle)*x + math.sin(weight*angle)*y) / math.sin(angle)
               for x, y in zip(qa, qb)]


class TransformBuffer:
    def __init__(self, reader):
        self.static, self.dynamic = {}, {}
        topics = [name for name, info in reader.topics.items()
                  if info['message_type'] == 'tf2_msgs/TFMessage']
        # Read full-bag TF: transforms bracketing a chunk may live outside it.
        for topic, message, recorded in reader.bag.read_messages(topics=topics) if topics else []:
            for item in getattr(message, 'transforms', []):
                try:
                    parent, child = item.header.frame_id.lstrip('/'), item.child_frame_id.lstrip('/')
                    if not parent or not child or parent == child:
                        raise ValueError('Invalid TF frame')
                    transform = (vector(item.transform.translation), quaternion(item.transform.rotation))
                    if topic.rstrip('/').split('/')[-1] == 'tf_static':
                        self.static[parent, child] = transform
                    else:
                        time = reader.seconds(item.header.stamp)
                        if time is None or time <= 0:
                            time = reader.seconds(recorded)
                            reader.warn('Invalid TF timestamp; used bag-record time.')
                        if time is None:
                            raise ValueError('Invalid TF time')
                        self.dynamic.setdefault((parent, child), {})[time] = transform
                except (ValueError, TypeError, AttributeError):
                    reader.warn('Skipped invalid TF transform.')
        self.dynamic = {edge: (sorted(values), values) for edge, values in self.dynamic.items()}

    def lookup(self, target, source, time):
        if target == source:
            return ([0, 0, 0], [0, 0, 0, 1])
        edges = dict(self.static)
        for edge, (times, values) in self.dynamic.items():
            index = bisect_left(times, time)
            if index < len(times) and abs(times[index] - time) < 1e-9:
                edges[edge] = values[times[index]]
            elif 0 < index < len(times):
                before, after = times[index-1], times[index]
                edges[edge] = interpolate(values[before], values[after], (time-before)/(after-before))
        graph = {}
        for (parent, child), transform in edges.items():
            graph.setdefault(child, []).append((parent, transform))
            graph.setdefault(parent, []).append((child, inverse(transform)))
        queue = deque([(source, ([0, 0, 0], [0, 0, 0, 1]))])
        visited = {source}
        while queue:
            frame, accumulated = queue.popleft()
            for neighbor, transform in graph.get(frame, []):
                if neighbor in visited:
                    continue
                result = compose(transform, accumulated)
                if neighbor == target:
                    return result
                visited.add(neighbor)
                queue.append((neighbor, result))
        raise ValueError('No TF transform at this timestamp')
