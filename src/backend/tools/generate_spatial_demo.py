"""Generate a small, deterministic ROS1 demo bag without touching existing bags.

Run with the ROS Python interpreter: python tools/generate_spatial_demo.py OUTPUT.bag
"""
import argparse
import math
from pathlib import Path

import genpy
from rosbag import Bag
from geometry_msgs.msg import WrenchStamped


def generate(output):
    output = Path(output)
    if output.exists():
        raise FileExistsError(f'Refusing to overwrite {output}')
    output.parent.mkdir(parents=True, exist_ok=True)
    with Bag(str(output), 'w') as bag:
        for step in range(601):
            time = step/20
            stamp = genpy.Time.from_sec(1000+time)
            for robot in range(2):
                force = WrenchStamped()
                force.header.stamp, force.header.frame_id = stamp, f'robot_{robot}/sensor'
                force.wrench.force.x, force.wrench.force.y, force.wrench.force.z = math.sin(time)*4, math.cos(time)*2, robot+1
                force.wrench.torque.x, force.wrench.torque.y, force.wrench.torque.z = math.sin(time/2), -math.cos(time/2), 0.5*robot
                bag.write(f'/robots/{robot+1}/wrench', force, stamp)
    return output


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output')
    print(generate(parser.parse_args().output))
