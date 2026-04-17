import os

from ament_index_python.packages import get_package_share_directory
from launch.actions import LogInfo
from launch import LaunchDescription
from launch_ros.actions import Node


def generate_launch_description() -> LaunchDescription:
    config_dir = os.path.join(get_package_share_directory('g1_light_tracking'), 'config')
    actions = [
        Node(
            package='g1_light_tracking',
            executable='d435i_node',
            name='d435i_node',
            output='screen',
        ),
        Node(
            package='g1_light_tracking',
            executable='light_spot_detector_node',
            name='light_spot_detector_node',
            output='screen',
            parameters=[os.path.join(config_dir, 'perception.yaml')],
        ),
        Node(
            package='g1_light_tracking',
            executable='g1_light_follower_node',
            name='g1_light_follower_node',
            output='screen',
            parameters=[os.path.join(config_dir, 'control.yaml')],
        ),
    ]

    try:
        from unitree_api.msg import Request  # noqa: F401

        actions.append(
            Node(
                package='g1_light_tracking',
                executable='unitree_cmd_vel_bridge_node',
                name='unitree_cmd_vel_bridge_node',
                output='screen',
                parameters=[os.path.join(config_dir, 'bridge.yaml')],
            )
        )
    except ImportError:
        actions.append(
            LogInfo(msg='unitree_api not available, skipping unitree_cmd_vel_bridge_node')
        )

    try:
        from unitree_hg.msg import LowCmd, LowState  # noqa: F401

        actions.append(
            Node(
                package='g1_light_tracking',
                executable='arm_skill_bridge_node',
                name='arm_skill_bridge_node',
                output='screen',
            )
        )
    except ImportError:
        actions.append(
            LogInfo(msg='unitree_hg messages not available, skipping arm_skill_bridge_node')
        )

    return LaunchDescription(actions)
