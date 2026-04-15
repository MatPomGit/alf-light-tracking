import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, LogInfo
from launch.conditions import IfCondition
from launch.substitutions import LaunchConfiguration, PythonExpression
from launch_ros.actions import Node


def _mode_is(mode_name: str):
    # Small helper to keep mode-specific conditions readable in the node list below.
    return IfCondition(PythonExpression(["'", LaunchConfiguration('mode'), "' == '", mode_name, "'"]))


def _mode_in(*mode_names: str):
    # Used when a node is shared by several runtime modes, e.g. modern and hybrid.
    comparisons = [f"'{name}'" for name in mode_names]
    expr = ["'", LaunchConfiguration('mode'), "' in [", ','.join(comparisons), "]"]
    return IfCondition(PythonExpression(expr))


def generate_launch_description() -> LaunchDescription:
    # All launch files resolve YAMLs from the installed package share directory so the
    # same launcher works both from the source tree and after `colcon build`.
    config_dir = os.path.join(get_package_share_directory('g1_light_tracking'), 'config')

    mode_arg = DeclareLaunchArgument(
        'mode',
        default_value='modern',
        description='Runtime mode: modern, legacy, or hybrid.',
    )
    legacy_camera_arg = DeclareLaunchArgument(
        'with_legacy_camera',
        default_value='false',
        description='Start d435i_node for legacy / hybrid modes.',
    )
    unitree_bridge_arg = DeclareLaunchArgument(
        'with_unitree_bridges',
        default_value='false',
        description='Start optional Unitree bridge nodes when available.',
    )

    actions = [
        mode_arg,
        legacy_camera_arg,
        unitree_bridge_arg,
        LogInfo(msg=['Launching g1_light_tracking in mode=', LaunchConfiguration('mode')]),
        LogInfo(
            condition=IfCondition(
                PythonExpression([
                    "'", LaunchConfiguration('mode'), "' not in ['modern','legacy','hybrid']"
                ])
            ),
            msg="Unsupported mode requested. Valid values: modern, legacy, hybrid.",
        ),
    ]

    # Modern stack stays the canonical processing pipeline. In hybrid mode it remains
    # active and legacy is only used as an extra perception source.
    modern_nodes = [
        Node(
            package='g1_light_tracking',
            executable='perception_node',
            output='screen',
            parameters=[os.path.join(config_dir, 'perception.yaml')],
            condition=_mode_in('modern', 'hybrid'),
        ),
        Node(
            package='g1_light_tracking',
            executable='localization_node',
            output='screen',
            parameters=[os.path.join(config_dir, 'localization.yaml')],
            condition=_mode_in('modern', 'hybrid'),
        ),
        Node(
            package='g1_light_tracking',
            executable='visual_slam_node',
            output='screen',
            parameters=[os.path.join(config_dir, 'visual_slam.yaml')],
            condition=_mode_in('modern', 'hybrid'),
        ),
        Node(
            package='g1_light_tracking',
            executable='tracking_node',
            output='screen',
            parameters=[os.path.join(config_dir, 'tracking.yaml')],
            condition=_mode_in('modern', 'hybrid'),
        ),
        Node(
            package='g1_light_tracking',
            executable='parcel_track_node',
            output='screen',
            parameters=[os.path.join(config_dir, 'parcel_track.yaml')],
            condition=_mode_in('modern', 'hybrid'),
        ),
        Node(
            package='g1_light_tracking',
            executable='depth_mapper_node',
            output='screen',
            parameters=[os.path.join(config_dir, 'depth_mapper.yaml')],
            condition=_mode_in('modern', 'hybrid'),
        ),
    ]

    # Mission and control are shared across all modes so that business logic and robot
    # actuation live in one place, regardless of where detections come from.
    mission_and_control = [
        Node(
            package='g1_light_tracking',
            executable='mission_node',
            output='screen',
            parameters=[os.path.join(config_dir, 'mission.yaml')],
            condition=_mode_in('modern', 'legacy', 'hybrid'),
        ),
        Node(
            package='g1_light_tracking',
            executable='control_node',
            output='screen',
            parameters=[os.path.join(config_dir, 'control.yaml')],
            condition=_mode_in('modern', 'legacy', 'hybrid'),
        ),
        Node(
            package='g1_light_tracking',
            executable='debug_node',
            output='screen',
            condition=_mode_in('modern', 'legacy', 'hybrid'),
        ),
    ]

    # Legacy nodes are additive. They are launched only when explicitly requested and
    # never replace the current stack in place.
    legacy_source_nodes = [
        Node(
            package='g1_light_tracking',
            executable='d435i_node',
            name='d435i_node',
            output='screen',
            condition=IfCondition(
                PythonExpression([
                    LaunchConfiguration('with_legacy_camera'),
                    " and '",
                    LaunchConfiguration('mode'),
                    "' in ['legacy','hybrid']",
                ])
            ),
        ),
        Node(
            package='g1_light_tracking',
            executable='light_spot_detector_node',
            name='light_spot_detector_node',
            output='screen',
            parameters=[os.path.join(config_dir, 'legacy_light_perception.yaml')],
            condition=_mode_in('legacy', 'hybrid'),
        ),
        Node(
            package='g1_light_tracking',
            executable='legacy_detection_adapter_node',
            name='legacy_detection_adapter_node',
            output='screen',
            parameters=[
                os.path.join(config_dir, 'legacy_adapter.yaml'),
                {
                    'publish_detection2d': True,
                    'publish_tracked_target': True,
                },
            ],
            condition=_mode_is('legacy'),
        ),
        Node(
            package='g1_light_tracking',
            executable='legacy_detection_adapter_node',
            name='legacy_detection_adapter_node',
            output='screen',
            parameters=[
                os.path.join(config_dir, 'legacy_adapter.yaml'),
                {
                    'publish_detection2d': True,
                    # In hybrid mode we publish only Detection2D. This avoids creating
                    # a second tracking source with IDs that would race the modern tracker.
                    'publish_tracked_target': False,
                },
            ],
            condition=_mode_is('hybrid'),
        ),
    ]

    actions.extend(modern_nodes)
    actions.extend(mission_and_control)
    actions.extend(legacy_source_nodes)

    # Unitree dependencies are optional. The try/except pattern keeps the repository
    # runnable on developer machines that do not have the vendor SDK installed.
    try:
        from unitree_api.msg import Request  # noqa: F401

        actions.append(
            Node(
                package='g1_light_tracking',
                executable='unitree_cmd_vel_bridge_node',
                name='unitree_cmd_vel_bridge_node',
                output='screen',
                parameters=[os.path.join(config_dir, 'legacy_bridge.yaml')],
                condition=IfCondition(LaunchConfiguration('with_unitree_bridges')),
            )
        )
    except ImportError:
        actions.append(
            LogInfo(
                condition=IfCondition(LaunchConfiguration('with_unitree_bridges')),
                msg='unitree_api not available, skipping unitree_cmd_vel_bridge_node',
            )
        )

    try:
        from unitree_hg.msg import LowCmd, LowState  # noqa: F401

        actions.append(
            Node(
                package='g1_light_tracking',
                executable='arm_skill_bridge_node',
                name='arm_skill_bridge_node',
                output='screen',
                condition=IfCondition(LaunchConfiguration('with_unitree_bridges')),
            )
        )
    except ImportError:
        actions.append(
            LogInfo(
                condition=IfCondition(LaunchConfiguration('with_unitree_bridges')),
                msg='unitree_hg messages not available, skipping arm_skill_bridge_node',
            )
        )

    return LaunchDescription(actions)
