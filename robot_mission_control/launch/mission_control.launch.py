"""ROS2 launch file uruchamiający aplikację Mission Control."""

from launch import LaunchDescription
from launch_ros.actions import Node


# [AI-CHANGE | 2026-04-21 09:30 UTC | v0.166]
# CO ZMIENIONO: Dodano podstawowy launch ROS2 dla modułu Mission Control wraz z konfiguracją domyślną.
# DLACZEGO: Backlog wymaga uruchamiania przez tooling ROS2 i jawnego przekazania parametrów startowych.
# JAK TO DZIAŁA: Launch uruchamia pojedynczy node `robot_mission_control` z plikiem `config/default.yaml`.
# TODO: Dodać argumenty launch (namespace, log_level, use_sim_time) dla środowisk testowych i produkcyjnych.
def generate_launch_description() -> LaunchDescription:
    """Zwraca opis uruchomienia aplikacji Mission Control."""
    return LaunchDescription(
        [
            Node(
                package="robot_mission_control",
                executable="robot_mission_control",
                name="robot_mission_control",
                output="screen",
                parameters=["config/default.yaml"],
            )
        ]
    )
