"""ROS 2 node generujący uproszczone komendy ruchu.

Node tłumaczy `MissionTarget` oraz opcjonalne wskazówki z mapy głębi (`DepthNavHint`)
na komendy `geometry_msgs/Twist`. Implementacja jest celowo prosta: sterowanie opiera się
głównie na błędzie bocznym w obrazie i odległości do celu, a wskazówki głębi korygują prędkość
oraz skręt w pobliżu przeszkód.

Moduł nie jest pełnym regulatorem ruchu mobilnego. To referencyjny kontroler demonstracyjny,
który ułatwia integrację całego pipeline’u end-to-end.
"""

import rclpy
from rclpy.node import Node
from geometry_msgs.msg import Twist

from g1_light_tracking.msg import MissionTarget, DepthNavHint


class ControlNode(Node):
    def __init__(self):
        super().__init__('control_node')
        self.declare_parameter('mission_topic', '/mission/target')
        self.declare_parameter('depth_hint_topic', '/navigation/depth_hint')
        self.declare_parameter('cmd_vel_topic', '/cmd_vel')
        self.declare_parameter('linear_speed', 0.15)
        self.declare_parameter('angular_speed', 0.50)
        self.declare_parameter('stop_distance_m', 0.60)
        self.declare_parameter('use_depth_navigation', True)
        self.declare_parameter('min_safe_clearance_m', 0.70)
        self.declare_parameter('obstacle_stop_clearance_m', 0.45)
        self.declare_parameter('depth_turn_gain', 0.60)

        self.linear_speed = float(self.get_parameter('linear_speed').value)
        self.angular_speed = float(self.get_parameter('angular_speed').value)
        self.stop_distance = float(self.get_parameter('stop_distance_m').value)
        self.use_depth_navigation = bool(self.get_parameter('use_depth_navigation').value)
        self.min_safe_clearance = float(self.get_parameter('min_safe_clearance_m').value)
        self.obstacle_stop_clearance = float(self.get_parameter('obstacle_stop_clearance_m').value)
        self.depth_turn_gain = float(self.get_parameter('depth_turn_gain').value)

        self.latest_depth_hint = None

        self.pub = self.create_publisher(Twist, self.get_parameter('cmd_vel_topic').value, 20)
        # Control consumes the higher-level mission target instead of raw detections so
        # motion logic stays decoupled from perception-specific heuristics.
        self.create_subscription(MissionTarget, self.get_parameter('mission_topic').value, self.cb, 20)
        self.create_subscription(DepthNavHint, self.get_parameter('depth_hint_topic').value, self.depth_cb, 20)

    def depth_cb(self, msg: DepthNavHint):
        self.latest_depth_hint = msg

    def apply_depth_navigation(self, twist: Twist):
        # Depth hints act as a lightweight safety layer, not as a full path planner. They
        # only scale or veto the command computed from the mission target.
        hint = self.latest_depth_hint
        if not self.use_depth_navigation or hint is None or not hint.depth_available:
            return twist

        if hint.forward_clearance_m <= self.obstacle_stop_clearance:
            twist.linear.x = 0.0
            twist.angular.z += -self.depth_turn_gain if hint.recommended_angular_bias > 0 else self.depth_turn_gain
            return twist

        twist.linear.x *= max(0.0, min(1.0, hint.recommended_linear_scale))
        twist.angular.z += float(hint.recommended_angular_bias) * self.depth_turn_gain
        return twist

    def cb(self, mission: MissionTarget):
        # The reference policy is intentionally simple: align first in image space, then
        # move forward only when the target is still farther than the stop threshold.
        twist = Twist()
        if mission.mode in ('idle', 'handover_ready'):
            self.pub.publish(twist)
            return

        if mission.position.z > self.stop_distance:
            twist.linear.x = self.linear_speed

        if abs(mission.position.x) > 0.1:
            twist.angular.z = -self.angular_speed if mission.position.x > 0 else self.angular_speed

        twist = self.apply_depth_navigation(twist)
        self.pub.publish(twist)

def main(args=None):
    rclpy.init(args=args)
    node = ControlNode()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()
