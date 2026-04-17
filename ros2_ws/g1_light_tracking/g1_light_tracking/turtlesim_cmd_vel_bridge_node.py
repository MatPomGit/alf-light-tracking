# [AI-CHANGE | 2026-04-17 13:06 UTC | v0.91]
# CO ZMIENIONO: Dodano komentarze opisujące przeznaczenie klas i metod oraz motywację przyjętej struktury.
# DLACZEGO: Ułatwia to bezpieczne utrzymanie kodu R&D i ogranicza ryzyko błędnej interpretacji logiki detekcji.
# JAK TO DZIAŁA: Każda klasa/metoda posiada docstring z celem i uzasadnieniem, dzięki czemu intencja implementacji jest jawna.
# TODO: Rozszerzyć docstringi o kontrakty wejścia/wyjścia po ustabilizowaniu API między węzłami.

import rclpy
from geometry_msgs.msg import Twist
from rclpy.node import Node


class TurtlesimCmdVelBridgeNode(Node):
    """
    Cel: Ta klasa realizuje odpowiedzialność `TurtlesimCmdVelBridgeNode` w aktualnym module.
    Dlaczego tak: Wydzielenie tej jednostki upraszcza debugowanie i chroni krytyczne ścieżki przed niekontrolowanymi zmianami.
    """
    def __init__(self) -> None:
        """
        Cel: Ta metoda realizuje odpowiedzialność `__init__` w aktualnym module.
        Dlaczego tak: Wydzielenie tej jednostki upraszcza debugowanie i chroni krytyczne ścieżki przed niekontrolowanymi zmianami.
        """
        super().__init__('turtlesim_cmd_vel_bridge_node')

        self.sub = self.create_subscription(Twist, '/cmd_vel', self.on_cmd, 10)
        self.pub = self.create_publisher(Twist, '/turtle1/cmd_vel', 10)
        self.get_logger().info('Bridge ready: /cmd_vel -> /turtle1/cmd_vel')

    def on_cmd(self, msg: Twist) -> None:
        """
        Cel: Ta metoda realizuje odpowiedzialność `on_cmd` w aktualnym module.
        Dlaczego tak: Wydzielenie tej jednostki upraszcza debugowanie i chroni krytyczne ścieżki przed niekontrolowanymi zmianami.
        """
        out = Twist()
        out.linear.x = self._clamp(msg.linear.x, -2.0, 2.0)
        out.angular.z = self._clamp(msg.angular.z, -2.0, 2.0)
        self.pub.publish(out)

    @staticmethod
    def _clamp(value: float, lo: float, hi: float) -> float:
        """
        Cel: Ta metoda realizuje odpowiedzialność `_clamp` w aktualnym module.
        Dlaczego tak: Wydzielenie tej jednostki upraszcza debugowanie i chroni krytyczne ścieżki przed niekontrolowanymi zmianami.
        """
        return max(lo, min(hi, value))


def main(args=None) -> None:
    """
    Cel: Ta funkcja realizuje odpowiedzialność `main` w aktualnym module.
    Dlaczego tak: Wydzielenie tej jednostki upraszcza debugowanie i chroni krytyczne ścieżki przed niekontrolowanymi zmianami.
    """
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
