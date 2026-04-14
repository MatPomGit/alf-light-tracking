import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description() -> LaunchDescription:
    config_dir = os.path.join(get_package_share_directory('g1_light_tracking'), 'config')
    csv_file = LaunchConfiguration('csv_file')
    playback_rate = LaunchConfiguration('playback_rate')
    loop = LaunchConfiguration('loop')

    return LaunchDescription(
        [
            DeclareLaunchArgument('csv_file', description='Path to detection CSV file'),
            DeclareLaunchArgument('playback_rate', default_value='1.0'),
            DeclareLaunchArgument('loop', default_value='true'),
            Node(package='turtlesim', executable='turtlesim_node', name='turtlesim'),
            Node(
                package='g1_light_tracking',
                executable='csv_detection_replay_node',
                name='csv_detection_replay_node',
                parameters=[
                    {
                        'csv_file': csv_file,
                        'detection_topic': '/light_tracking/detection_json',
                        'playback_rate': playback_rate,
                        'loop': loop,
                    }
                ],
                output='screen',
            ),
            Node(
                package='g1_light_tracking',
                executable='g1_light_follower_node',
                name='g1_light_follower_node',
                parameters=[os.path.join(config_dir, 'control.yaml')],
                output='screen',
            ),
            Node(
                package='g1_light_tracking',
                executable='turtlesim_cmd_vel_bridge_node',
                name='turtlesim_cmd_vel_bridge_node',
                output='screen',
            ),
        ]
    )
