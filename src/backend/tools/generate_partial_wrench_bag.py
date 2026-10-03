"""
Generate a synthetic ROS1 bag where one wrench topic covers only part of the
complete timeline
"""
import math
import sys

import rosbag
from geometry_msgs.msg import WrenchStamped
from std_msgs.msg import String

try:
    from rospy import Time
except ImportError:
    from genpy import Time

OUT = sys.argv[1] if len(sys.argv) > 1 else '/tmp/wrench_partial_test.bag'
START = 1700000000.0
DURATION = 60.0
PARTIAL = (20.0, 40.0)


def wrench_msg(t, seq, scale, frame):
    msg = WrenchStamped()
    msg.header.seq = seq
    msg.header.stamp = Time.from_sec(START + t)
    msg.header.frame_id = frame
    msg.wrench.force.x = scale * 10.0 * math.sin(t / 3.0)
    msg.wrench.force.y = scale * 5.0 * math.cos(t / 3.0)
    msg.wrench.force.z = scale * 2.0
    msg.wrench.torque.x = scale * 1.0 * math.sin(t / 2.0)
    msg.wrench.torque.y = scale * 0.5 * math.cos(t / 2.0)
    msg.wrench.torque.z = scale * 0.2
    return msg


with rosbag.Bag(OUT, 'w') as bag:
    for i in range(int(DURATION * 10) + 1):
        t = i / 10.0
        stamp = Time.from_sec(START + t)
        bag.write('/wrench_full', wrench_msg(t, i, 1.0, 'full_sensor'), t=stamp)
        if PARTIAL[0] <= t <= PARTIAL[1]:
            bag.write('/wrench_partial', wrench_msg(t, i, -1.0, 'partial_sensor'), t=stamp)
        if i % 10 == 0:
            bag.write('/heartbeat', String(data=f'{t:.0f}s'), t=stamp)

print(f'wrote {OUT}: /wrench_full 0-{DURATION:.0f}s, '
      f'/wrench_partial {PARTIAL[0]:.0f}-{PARTIAL[1]:.0f}s, /heartbeat 0-{DURATION:.0f}s')