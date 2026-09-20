"""Generate a small, deterministic ROS1 demo bag without touching existing bags.

Run with the ROS Python interpreter: python tools/generate_spatial_demo.py OUTPUT.bag
"""
import argparse
import math
from pathlib import Path

import genpy
from genpy.dynamic import generate_dynamic
from rosbag import Bag
from nav_msgs.msg import Odometry
from geometry_msgs.msg import WrenchStamped, TransformStamped
from tf2_msgs.msg import TFMessage


PEOPLE_DEFINITION = '''std_msgs/Header header
people_msgs/Person[] people
================================================================================
MSG: std_msgs/Header
uint32 seq
time stamp
string frame_id
================================================================================
MSG: people_msgs/Person
string name
geometry_msgs/Point position
geometry_msgs/Point velocity
float64 reliability
string[] tagnames
string[] tags
================================================================================
MSG: geometry_msgs/Point
float64 x
float64 y
float64 z
'''


def generate(output):
    types = generate_dynamic('people_msgs/People', PEOPLE_DEFINITION)
    People, Person = types['people_msgs/People'], types['people_msgs/Person']
    output = Path(output)
    if output.exists():
        raise FileExistsError(f'Refusing to overwrite {output}')
    output.parent.mkdir(parents=True, exist_ok=True)
    with Bag(str(output), 'w') as bag:
        transform = TransformStamped()
        transform.header.stamp = genpy.Time(1000)
        transform.header.frame_id, transform.child_frame_id = 'map', 'front_camera'
        transform.transform.translation.x = 2
        transform.transform.rotation.w = 1
        bag.write('/tf_static', TFMessage([transform]), genpy.Time(1000))
        for step in range(601):
            time = step/20
            stamp = genpy.Time.from_sec(1000+time)
            for robot in range(2):
                message = Odometry()
                message.header.stamp, message.header.frame_id = stamp, 'map'
                message.child_frame_id = f'robot_{robot}/base_link'
                angle = time*0.15 + robot*math.pi
                radius = 2+robot
                message.pose.pose.position.x = radius*math.cos(angle)
                message.pose.pose.position.y = radius*math.sin(angle)
                message.pose.pose.orientation.z = math.sin((angle+math.pi/2)/2)
                message.pose.pose.orientation.w = math.cos((angle+math.pi/2)/2)
                message.twist.twist.linear.x = radius*0.15
                bag.write(f'/robots/{robot+1}/odom', message, stamp)
                force = WrenchStamped()
                force.header.stamp, force.header.frame_id = stamp, f'robot_{robot}/sensor'
                force.wrench.force.x, force.wrench.force.y, force.wrench.force.z = math.sin(time)*4, math.cos(time)*2, robot+1
                force.wrench.torque.x, force.wrench.torque.y, force.wrench.torque.z = math.sin(time/2), -math.cos(time/2), 0.5*robot
                bag.write(f'/robots/{robot+1}/wrench', force, stamp)
            people = People()
            people.header.stamp, people.header.frame_id = stamp, 'front_camera'
            for name, phase in [('Alice', 0), ('Bob', math.pi)]:
                person = Person()
                person.name, person.reliability = name, 1.0
                person.position.x, person.position.y = time/10-3, math.sin(time/4+phase)
                person.velocity.x, person.velocity.y = 0.1, math.cos(time/4+phase)/4
                people.people.append(person)
            bag.write('/front/people', people, stamp)
    return output


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output')
    print(generate(parser.parse_args().output))
