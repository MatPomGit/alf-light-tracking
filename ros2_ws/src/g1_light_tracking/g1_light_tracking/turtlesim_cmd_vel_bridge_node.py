"""Minimal bridge forwarding /cmd_vel commands into turtlesim."""

import rclpy
from geometry_msgs.msg import Twist
from rclpy.node import Node


class TurtlesimCmdVelBridgeNode(Node):
    def __init__(self) -> None:
        super().__init__('turtlesim_cmd_vel_bridge_node')

        self.sub = self.create_subscription(Twist, '/cmd_vel', self.on_cmd, 10)
        self.pub = self.create_publisher(Twist, '/turtle1/cmd_vel', 10)
        self.get_logger().info('Bridge ready: /cmd_vel -> /turtle1/cmd_vel')

    def on_cmd(self, msg: Twist) -> None:
        out = Twist()
        out.linear.x = self._clamp(msg.linear.x, -2.0, 2.0)
        out.angular.z = self._clamp(msg.angular.z, -2.0, 2.0)
        self.pub.publish(out)

    @staticmethod
    def _clamp(value: float, lo: float, hi: float) -> float:
        return max(lo, min(hi, value))


def main(args=None) -> None:
    rclpy.init(args=args)
    node = TurtlesimCmdVelBridgeNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
