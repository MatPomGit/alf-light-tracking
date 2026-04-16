from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from ament_index_python.packages import get_package_share_directory
import os


def generate_launch_description():
    pkg_share = get_package_share_directory('g1_light_tracking')
    mission_scenarios_path = os.path.join(pkg_share, 'config', 'mission_scenarios.yaml')

    return LaunchDescription([
        DeclareLaunchArgument(
            'profile',
            default_value='',
            description='Optional perception profile name from profiles/*.json (e.g. markers_and_light).',
        ),
        DeclareLaunchArgument(
            'scenario_file',
            default_value=mission_scenarios_path,
            description='Ścieżka do pliku YAML z rejestrem scenariuszy mission_node.',
        ),
        DeclareLaunchArgument(
            'scenario_name',
            default_value='',
            description='Nazwa scenariusza mission_node. Puste = pierwszy scenariusz z pliku.',
        ),
        Node(
            package='g1_light_tracking',
            executable='d435i_node',
            name='d435i_node',
            parameters=[{
                'calibration_file': os.path.join(pkg_share, 'calibration', 'camera_intrinsics.yaml'),
                'aligned_image_topic': '/camera/aligned/image_raw',
                'aligned_camera_info_topic': '/camera/aligned/camera_info',
                'aligned_depth_topic': '/camera/aligned/depth/image_raw',
                'aligned_depth_camera_info_topic': '/camera/aligned/depth/camera_info',
                'separate_color_topic': '/camera/color/image_raw',
                'separate_color_camera_info_topic': '/camera/camera_info',
                'separate_depth_topic': '/camera/depth/image_raw',
                'separate_depth_camera_info_topic': '/camera/depth/camera_info',
                'legacy_color_topic': '/camera/image_raw',
                'publish_legacy_color_topic': True,
                'publish_camera_info': True,
                'publish_depth': True,
                'frame_timeout_ms': 100,
            }],
            output='screen'
        ),
        Node(
            package='g1_light_tracking',
            executable='perception_node',
            parameters=[
                os.path.join(pkg_share, 'config', 'perception.yaml'),
                {'profile_name': LaunchConfiguration('profile')},
            ],
            output='screen'
        ),
        Node(
            package='g1_light_tracking',
            executable='localization_node',
            parameters=[
                os.path.join(pkg_share, 'config', 'localization.yaml'),
                {'depth_image_topic': '/camera/aligned/depth/image_raw'},
            ],
            output='screen'
        ),
        Node(
            package='g1_light_tracking',
            executable='visual_slam_node',
            parameters=[
                os.path.join(pkg_share, 'config', 'visual_slam.yaml'),
                {'depth_image_topic': '/camera/aligned/depth/image_raw'},
            ],
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
            executable='parcel_track_node',
            parameters=[os.path.join(pkg_share, 'config', 'parcel_track.yaml')],
            output='screen'
        ),
        Node(
            package='g1_light_tracking',
            executable='depth_mapper_node',
            parameters=[
                os.path.join(pkg_share, 'config', 'depth_mapper.yaml'),
                {'depth_image_topic': '/camera/aligned/depth/image_raw'},
            ],
            output='screen'
        ),
        Node(
            package='g1_light_tracking',
            executable='mission_node',
            parameters=[
                os.path.join(pkg_share, 'config', 'mission.yaml'),
                {
                    'scenario_file': LaunchConfiguration('scenario_file'),
                    'scenario_name': LaunchConfiguration('scenario_name'),
                }
            ],
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
        Node(
            package='g1_light_tracking',
            executable='tui_monitor_node',
            output='screen'
        ),
    ])
