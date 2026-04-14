import rclpy
from rclpy.node import Node
from geometry_msgs.msg import Twist

from g1_light_tracking.msg import MissionTarget


class ControlNode(Node):
    def __init__(self):
        super().__init__('control_node')
        self.declare_parameter('mission_topic', '/mission/target')
        self.declare_parameter('cmd_vel_topic', '/cmd_vel')
        self.declare_parameter('linear_speed', 0.15)
        self.declare_parameter('angular_speed', 0.50)
        self.declare_parameter('stop_distance_m', 0.60)

        self.linear_speed = float(self.get_parameter('linear_speed').value)
        self.angular_speed = float(self.get_parameter('angular_speed').value)
        self.stop_distance = float(self.get_parameter('stop_distance_m').value)

        self.pub = self.create_publisher(Twist, self.get_parameter('cmd_vel_topic').value, 20)
        self.create_subscription(MissionTarget, self.get_parameter('mission_topic').value, self.cb, 20)

    def cb(self, mission: MissionTarget):
        twist = Twist()
        if mission.mode in ('idle', 'handover_ready'):
            self.pub.publish(twist)
            return

        if mission.position.z > self.stop_distance:
            twist.linear.x = self.linear_speed

        if abs(mission.position.x) > 0.1:
            twist.angular.z = -self.angular_speed if mission.position.x > 0 else self.angular_speed

        self.pub.publish(twist)

def main(args=None):
    rclpy.init(args=args)
    node = ControlNode()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()
