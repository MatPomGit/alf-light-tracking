import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch_ros.actions import Node


def generate_launch_description() -> LaunchDescription:
    config_dir = os.path.join(get_package_share_directory('g1_light_tracking'), 'config')
    return LaunchDescription([
        Node(
            package='g1_light_tracking',
            executable='light_spot_detector_node',
            name='light_spot_detector_node',
            output='screen',
            parameters=[os.path.join(config_dir, 'legacy_light_perception.yaml')],
        ),
        Node(
            package='g1_light_tracking',
            executable='legacy_detection_adapter_node',
            name='legacy_detection_adapter_node',
            output='screen',
            parameters=[os.path.join(config_dir, 'legacy_adapter.yaml')],
        ),
        Node(
            package='g1_light_tracking',
            executable='mission_node',
            name='mission_node',
            output='screen',
            parameters=[os.path.join(config_dir, 'mission.yaml')],
        ),
        Node(
            package='g1_light_tracking',
            executable='control_node',
            name='control_node',
            output='screen',
            parameters=[os.path.join(config_dir, 'control.yaml')],
        ),
    ])
