import numpy as np
from rclpy.node import Node
from geometry_msgs.msg import Twist
from sensor_msgs.msg import Image
from std_msgs.msg import Float32MultiArray, Point
from .pid_controller import PIDController

class SpotFollower:
    def __init__(self, node: Node):
        self.node = node

        # Parametry sterowania (możliwe do zmiany przez ROS2 param)
        self.declare_parameters()
        self.load_parameters()

        # Regulatory
        self.pid_angular = PIDController(
            kp=self.kp_ang, ki=self.ki_ang, kd=self.kd_ang,
            output_limits=(-self.max_angular, self.max_angular), anti_windup=True
        )
        self.pid_linear = PIDController(
            kp=self.kp_lin, ki=self.ki_lin, kd=self.kd_lin,
            output_limits=(0.0, self.max_linear), anti_windup=True
        )

        # Filtry dolnoprzepustowe (exponential moving average)
        self.filter_alpha = self.error_filter_alpha
        self.filtered_angular_error = 0.0
        self.filtered_linear_error = 0.0

        # Zmienne pomocnicze
        self.last_time = None
        self.spot_position = None  # (x, y) w pikselach
        self.depth = None          # głębokość w metrach (jeśli dostępna)

        # Subskrypcje
        self.spot_sub = node.create_subscription(Point, '/spot_position', self.spot_callback, 10)
        # Opcjonalnie: subskrypcja głębi (np. z localization_node)
        self.depth_sub = node.create_subscription(Float32MultiArray, '/spot_depth', self.depth_callback, 10)

        # Publikacja cmd_vel
        self.cmd_pub = node.create_publisher(Twist, '/cmd_vel', 10)

        # Timer sterowania (częstotliwość np. 50 Hz)
        self.control_timer = node.create_timer(0.02, self.control_loop)  # 50 Hz

    def declare_parameters(self):
        self.node.declare_parameter('kp_angular', 0.8)
        self.node.declare_parameter('ki_angular', 0.05)
        self.node.declare_parameter('kd_angular', 0.1)
        self.node.declare_parameter('kp_linear', 0.4)
        self.node.declare_parameter('ki_linear', 0.02)
        self.node.declare_parameter('kd_linear', 0.05)
        self.node.declare_parameter('max_angular_speed', 1.5)   # rad/s
        self.node.declare_parameter('max_linear_speed', 0.5)    # m/s
        self.node.declare_parameter('error_deadzone_angular', 10.0)   # piksele
        self.node.declare_parameter('error_deadzone_linear', 30.0)    # piksele
        self.node.declare_parameter('error_filter_alpha', 0.3)        # 0=brak filtracji, 1=brak opóźnienia
        self.node.declare_parameter('linear_speed_scaling', True)     # skalowanie prędkości liniowej wg głębi
        self.node.declare_parameter('depth_reference', 1.0)           # metry – dla jakiej głębokości prędkość max
        self.node.declare_parameter('image_width', 640)               # do przeliczenia błędu na kąt
        self.node.declare_parameter('camera_hfov', 1.047)             # radiany (ok. 60 stopni)

    def load_parameters(self):
        self.kp_ang = self.node.get_parameter('kp_angular').value
        self.ki_ang = self.node.get_parameter('ki_angular').value
        self.kd_ang = self.node.get_parameter('kd_angular').value
        self.kp_lin = self.node.get_parameter('kp_linear').value
        self.ki_lin = self.node.get_parameter('ki_linear').value
        self.kd_lin = self.node.get_parameter('kd_linear').value
        self.max_angular = self.node.get_parameter('max_angular_speed').value
        self.max_linear = self.node.get_parameter('max_linear_speed').value
        self.deadzone_ang = self.node.get_parameter('error_deadzone_angular').value
        self.deadzone_lin = self.node.get_parameter('error_deadzone_linear').value
        self.error_filter_alpha = self.node.get_parameter('error_filter_alpha').value
        self.linear_scaling = self.node.get_parameter('linear_speed_scaling').value
        self.depth_ref = self.node.get_parameter('depth_reference').value
        self.img_width = self.node.get_parameter('image_width').value
        self.hfov = self.node.get_parameter('camera_hfov').value

    def spot_callback(self, msg: Point):
        self.spot_position = (msg.x, msg.y)
        # Jeśli nie ma depth, to ustaw domyślną (np. 1.0)
        if self.depth is None:
            self.depth = self.depth_ref
        def spot_callback(self, msg: Point):
        self.last_spot_time = self.node.get_clock().now()

    def depth_callback(self, msg: Float32MultiArray):
        # Zakładamy, że pierwsza wartość to głębokość w metrach
        if msg.data:
            self.depth = msg.data[0]

    def compute_angular_error(self, x_px: float) -> float:
        """Przelicza błąd w pikselach na błąd kątowy (radiany) względem środka kamery."""
        center = self.img_width / 2.0
        error_px = x_px - center
        # Przeliczenie: błąd kątowy = (error_px / szerokość) * pole widzenia w poziomie
        angular_error = (error_px / self.img_width) * self.hfov
        return angular_error

    def compute_linear_error(self, y_px: float) -> float:
        """Błąd pionowy (odległość od środka) – im wyżej plamka, tym chcemy jechać do przodu? 
        To zależy od konwencji. Zakładam: im bliżej środka w pionie, tym wolniej; im wyżej (ujemny błąd), tym szybciej do przodu."""
        center = self.img_width / 2.0  # zakładamy kwadratowe piksele, ale można oddzielny parametr height
        error_px = center - y_px   # dodatni gdy plamka powyżej środka -> chcemy jechać do przodu
        return error_px

    def control_loop(self):
        now = self.node.get_clock().now()
        if self.spot_position is None or (self.node.get_clock().now() - self.last_spot_time).nanoseconds > 200_000_000:
        # brak świeżej plamki – zatrzymaj
            self.publish_cmd_vel(0.0, 0.0)
            self.last_time = now
        return
        dt = (now - self.last_time).nanoseconds / 1e9
        if dt <= 0 or dt > 0.1:
            dt = 0.02
    
        if self.spot_position is None:
            # Brak plamki – zatrzymaj robota (opcjonalnie można dodać poszukiwanie)
            self.publish_cmd_vel(0.0, 0.0)
            self.last_time = now
            return

        x, y = self.spot_position

        # Obliczenie błędów surowych
        angular_error_raw = self.compute_angular_error(x)   # radiany
        linear_error_raw = self.compute_linear_error(y)     # piksele

        # Filtracja dolnoprzepustowa błędów
        self.filtered_angular_error = self.filter_alpha * angular_error_raw + (1-self.filter_alpha) * self.filtered_angular_error
        self.filtered_linear_error = self.filter_alpha * linear_error_raw + (1-self.filter_alpha) * self.filtered_linear_error

        # Dead zone – pomijamy małe błędy
        if abs(self.filtered_angular_error) < np.radians(self.deadzone_ang):
            angular_cmd = 0.0
        else:
            angular_cmd = self.pid_angular.update(self.filtered_angular_error, dt)

        # Prędkość liniowa – tylko jeśli plamka jest powyżej środka i błąd pionowy przekracza deadzone
        if abs(self.filtered_linear_error) < self.deadzone_lin:
            linear_cmd = 0.0
        else:
            linear_cmd = self.pid_linear.update(self.filtered_linear_error, dt)

        # Adaptacja prędkości liniowej do głębi (im dalej, tym szybciej)
        if self.linear_scaling and self.depth is not None and self.depth > 0.1:
            scale = min(2.0, self.depth / self.depth_ref)   # np. przy 2m -> skala 2.0
            linear_cmd = linear_cmd * scale

        # Ograniczenia końcowe (bezpieczeństwo)
        angular_cmd = max(-self.max_angular, min(self.max_angular, angular_cmd))
        linear_cmd = max(0.0, min(self.max_linear, linear_cmd))

        self.publish_cmd_vel(linear_cmd, angular_cmd)
        self.last_time = now

    def publish_cmd_vel(self, linear: float, angular: float):
        twist = Twist()
        twist.linear.x = linear
        twist.angular.z = angular
        self.cmd_pub.publish(twist)