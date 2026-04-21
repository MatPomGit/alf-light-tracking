"""ROS2 launch file uruchamiający aplikację Mission Control."""

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch_ros.actions import Node


# [AI-CHANGE | 2026-04-21 12:10 UTC | v0.167]
# CO ZMIENIONO: Launch korzysta teraz z katalogu share pakietu zamiast relatywnej ścieżki `config/default.yaml`.
# DLACZEGO: Po relokacji do `ros2_ws/` i instalacji przez colcon relatywna ścieżka mogła wskazywać nieistniejący plik.
# JAK TO DZIAŁA: `get_package_share_directory` wyznacza ścieżkę install-space pakietu,
#                a node dostaje jawny parametr z `share/robot_mission_control/config/default.yaml`.
# TODO: Dodać argument launch do nadpisywania pliku config przez operatora bez edycji kodu.
def generate_launch_description() -> LaunchDescription:
    """Zwraca opis uruchomienia aplikacji Mission Control."""
    package_share_dir = get_package_share_directory("robot_mission_control")
    config_path = f"{package_share_dir}/config/default.yaml"

    return LaunchDescription(
        [
            Node(
                package="robot_mission_control",
                executable="robot_mission_control",
                name="robot_mission_control",
                output="screen",
                parameters=[config_path],
            )
        ]
    )
