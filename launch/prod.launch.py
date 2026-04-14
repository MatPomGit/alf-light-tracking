from launch import LaunchDescription
from launch_ros.actions import Node
from ament_index_python.packages import get_package_share_directory
import os

def generate_launch_description():
    pkg_share = get_package_share_directory('g1_light_tracking')
    return LaunchDescription([
        Node(
            package='g1_light_tracking',
            executable='perception_node',
            parameters=[os.path.join(pkg_share, 'config', 'perception.yaml')],
            output='screen'
        ),
        Node(
            package='g1_light_tracking',
            executable='localization_node',
            parameters=[os.path.join(pkg_share, 'config', 'localization.yaml')],
            output='screen'
        ),
        Node(
            package='g1_light_tracking',
            executable='tracking_node',
            parameters=[os.path.join(pkg_share, 'config', 'tracking.yaml')],
            output='screen'
        ),
        Node(
            package='g1_light_tracking',
            executable='association_node',
            parameters=[os.path.join(pkg_share, 'config', 'association.yaml')],
            output='screen'
        ),
        Node(
            package='g1_light_tracking',
            executable='mission_node',
            parameters=[os.path.join(pkg_share, 'config', 'mission.yaml')],
            output='screen'
        ),
        Node(
            package='g1_light_tracking',
            executable='control_node',
            parameters=[os.path.join(pkg_share, 'config', 'control.yaml')],
            output='screen'
        ),
        Node(
            package='g1_light_tracking',
            executable='debug_node',
            output='screen'
        ),
    ])
