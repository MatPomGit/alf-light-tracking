import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Image

import pyrealsense2 as rs


class D435iNode(Node):
    """
    Cel: Ta klasa realizuje odpowiedzialność `D435iNode` w aktualnym module.
    Dlaczego tak: Wydzielenie tej jednostki upraszcza debugowanie i chroni krytyczne ścieżki przed niekontrolowanymi zmianami.
    """
    def __init__(self) -> None:
        """
        Cel: Ta metoda realizuje odpowiedzialność `__init__` w aktualnym module.
        Dlaczego tak: Wydzielenie tej jednostki upraszcza debugowanie i chroni krytyczne ścieżki przed niekontrolowanymi zmianami.
        """
        super().__init__('d435i_node')

        self.declare_parameter('width', 640)
        self.declare_parameter('height', 480)
        self.declare_parameter('fps', 30)
        self.declare_parameter('image_topic', '/camera/image_raw')
        self.declare_parameter('legacy_color_topic', '/camera/color/image_raw')
        self.declare_parameter('publish_legacy_color_topic', True)
        self.declare_parameter('frame_id', 'camera_color_optical_frame')

        self.width = int(self.get_parameter('width').value)
        self.height = int(self.get_parameter('height').value)
        self.fps = int(self.get_parameter('fps').value)
        self.image_topic = str(self.get_parameter('image_topic').value)
        self.legacy_color_topic = str(self.get_parameter('legacy_color_topic').value)
        self.publish_legacy_color_topic = bool(
            self.get_parameter('publish_legacy_color_topic').value
        )
        self.frame_id = str(self.get_parameter('frame_id').value)

        self.image_pub = self.create_publisher(Image, self.image_topic, 10)
        self.legacy_pub = None
        if self.publish_legacy_color_topic and self.legacy_color_topic != self.image_topic:
            self.legacy_pub = self.create_publisher(Image, self.legacy_color_topic, 10)

        self.pipeline = rs.pipeline()
        self.config = rs.config()
        self.config.enable_stream(
            rs.stream.color,
            self.width,
            self.height,
            rs.format.bgr8,
            self.fps,
        )

        try:
            self.pipeline.start(self.config)
        except Exception as exc:
            self.get_logger().error(f'Failed to start RealSense D435i: {exc}')
            raise

        timer_period = max(1.0 / float(self.fps), 0.001)
        self.timer = self.create_timer(timer_period, self.publish_frame)

        self.get_logger().info(
            f'Publishing D435i color stream to {self.image_topic} ({self.width}x{self.height}@{self.fps}fps)'
        )
        if self.legacy_pub is not None:
            self.get_logger().info(f'Also publishing legacy color topic: {self.legacy_color_topic}')

    def publish_frame(self) -> None:
        """
        Cel: Ta metoda realizuje odpowiedzialność `publish_frame` w aktualnym module.
        Dlaczego tak: Wydzielenie tej jednostki upraszcza debugowanie i chroni krytyczne ścieżki przed niekontrolowanymi zmianami.
        """
        frames = self.pipeline.poll_for_frames()
        if not frames:
            return

        color_frame = frames.get_color_frame()
        if not color_frame:
            return

        image = Image()
        image.header.stamp = self.get_clock().now().to_msg()
        image.header.frame_id = self.frame_id
        image.height = int(color_frame.get_height())
        image.width = int(color_frame.get_width())
        image.encoding = 'bgr8'
        image.is_bigendian = 0
        image.step = image.width * 3
        image.data = bytes(color_frame.get_data())

        self.image_pub.publish(image)
        if self.legacy_pub is not None:
            self.legacy_pub.publish(image)

    def destroy_node(self) -> bool:
        """
        Cel: Ta metoda realizuje odpowiedzialność `destroy_node` w aktualnym module.
        Dlaczego tak: Wydzielenie tej jednostki upraszcza debugowanie i chroni krytyczne ścieżki przed niekontrolowanymi zmianami.
        """
        try:
            self.pipeline.stop()
        except Exception:
            pass
        return super().destroy_node()


def main(args=None) -> None:
    """
    Cel: Ta funkcja realizuje odpowiedzialność `main` w aktualnym module.
    Dlaczego tak: Wydzielenie tej jednostki upraszcza debugowanie i chroni krytyczne ścieżki przed niekontrolowanymi zmianami.
    """
    rclpy.init(args=args)
    node = D435iNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
