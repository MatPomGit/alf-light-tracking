from launch import LaunchDescription
from launch_ros.actions import Node
from ament_index_python.packages import get_package_share_directory
import os

def generate_launch_description():
    pkg_share = get_package_share_directory('g1_light_tracking')
    return LaunchDescription([
        Node(
            package='g1_light_tracking',
            executable='topdown_odom_viewer_node',
            name='topdown_odom_viewer_node',
            parameters=[os.path.join(pkg_share, 'config', 'topdown_odom.yaml')],
            output='screen'
        ),
    ])
