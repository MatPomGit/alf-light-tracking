import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, LogInfo
from launch.conditions import IfCondition
from launch.substitutions import (
    AndSubstitution,
    EqualsSubstitution,
    LaunchConfiguration,
    NotSubstitution,
    OrSubstitution,
)
from launch_ros.actions import Node


def _mode_is(mode_name: str):
    # Mały helper, aby warunki trybu były czytelne i bezpieczne typowo.
    return IfCondition(EqualsSubstitution(LaunchConfiguration('mode'), mode_name))


def _mode_in(*mode_names: str):
    # Wspólny warunek dla kilku trybów bez ręcznego budowania PythonExpression.
    return IfCondition(
        OrSubstitution(*[EqualsSubstitution(LaunchConfiguration('mode'), name) for name in mode_names])
    )


def _arg_is_true(arg_name: str):
    # Launch argumenty są stringami; jawnie akceptujemy najczęstsze warianty bool.
    # Dzięki temu unikamy PythonExpression na surowym LaunchConfiguration i błędów parsera.
    return OrSubstitution(
        EqualsSubstitution(LaunchConfiguration(arg_name), 'true'),
        EqualsSubstitution(LaunchConfiguration(arg_name), 'True'),
        EqualsSubstitution(LaunchConfiguration(arg_name), '1'),
    )


def generate_launch_description() -> LaunchDescription:
    # All launch files resolve YAMLs from the installed package share directory so the
    # same launcher works both from the source tree and after `colcon build`.
    # TODO: Add a single mode-to-topology manifest so launch composition lives in
    # one declarative table instead of being spread across separate node lists.
    # That would make it easier to add future modes such as simulation-only or
    # hardware-in-the-loop without duplicating launch conditions.
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
    profile_arg = DeclareLaunchArgument(
        'profile',
        default_value='',
        description='Optional perception profile name from profiles/*.json (e.g. markers_and_light).',
    )
    rosbag_arg = DeclareLaunchArgument(
        'with_rosbag',
        default_value='false',
        description='Start rosbag_recorder_node for runtime recording.',
    )

    actions = [
        mode_arg,
        legacy_camera_arg,
        unitree_bridge_arg,
        profile_arg,
        rosbag_arg,
        LogInfo(msg=['Launching g1_light_tracking in mode=', LaunchConfiguration('mode')]),
        LogInfo(
            condition=IfCondition(
                NotSubstitution(
                    OrSubstitution(
                        EqualsSubstitution(LaunchConfiguration('mode'), 'modern'),
                        EqualsSubstitution(LaunchConfiguration('mode'), 'legacy'),
                        EqualsSubstitution(LaunchConfiguration('mode'), 'hybrid'),
                    )
                )
            ),
            msg="Unsupported mode requested. Valid values: modern, legacy, hybrid.",
        ),
    ]

    # TODO: Introduce health checks / lifecycle gating before starting dependent nodes.
    # Right now launch ordering is static; a future version could wait for camera,
    # SLAM or adapter readiness before enabling mission and control.
    # Modern stack stays the canonical processing pipeline. In hybrid mode it remains
    # active and legacy is only used as an extra perception source.
    modern_nodes = [
        Node(
            package='g1_light_tracking',
            executable='perception_node',
            output='screen',
            parameters=[
                os.path.join(config_dir, 'perception.yaml'),
                {'profile_name': LaunchConfiguration('profile')},
            ],
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
            executable='safety_stop_node',
            output='screen',
            parameters=[os.path.join(config_dir, 'safety.yaml')],
            condition=_mode_in('modern', 'legacy', 'hybrid'),
        ),
        Node(
            package='g1_light_tracking',
            executable='debug_node',
            output='screen',
            condition=_mode_in('modern', 'legacy', 'hybrid'),
        ),
        Node(
            package='g1_light_tracking',
            executable='head_display_state_node',
            output='screen',
            parameters=[os.path.join(config_dir, 'head_display.yaml')],
            condition=_mode_in('modern', 'legacy', 'hybrid'),
        ),
        Node(
            package='g1_light_tracking',
            executable='rosbag_recorder_node',
            output='screen',
            parameters=[os.path.join(config_dir, 'rosbag_recorder.yaml')],
            condition=IfCondition(_arg_is_true('with_rosbag')),
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
            # Nie używamy PythonExpression na surowym LaunchConfiguration:
            # launch argumenty bool przychodzą jako stringi i muszą być jawnie znormalizowane.
            condition=IfCondition(
                AndSubstitution(
                    _arg_is_true('with_legacy_camera'),
                    OrSubstitution(
                        EqualsSubstitution(LaunchConfiguration('mode'), 'legacy'),
                        EqualsSubstitution(LaunchConfiguration('mode'), 'hybrid'),
                    ),
                )
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
                condition=IfCondition(_arg_is_true('with_unitree_bridges')),
            )
        )
    except ImportError:
        actions.append(
            LogInfo(
                condition=IfCondition(_arg_is_true('with_unitree_bridges')),
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
                condition=IfCondition(_arg_is_true('with_unitree_bridges')),
            )
        )
    except ImportError:
        actions.append(
            LogInfo(
                condition=IfCondition(_arg_is_true('with_unitree_bridges')),
                msg='unitree_hg messages not available, skipping arm_skill_bridge_node',
            )
        )

    return LaunchDescription(actions)
