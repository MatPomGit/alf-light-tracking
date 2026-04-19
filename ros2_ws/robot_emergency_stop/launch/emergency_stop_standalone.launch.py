from launch import LaunchDescription
from launch_ros.actions import Node


def generate_launch_description() -> LaunchDescription:
    # [AI-CHANGE | 2026-04-19 22:08 UTC | v0.131]
    # CO ZMIENIONO: Dodano niezależny launch uruchamiający wyłącznie `emergency_stop_node`
    #   z mapowaniem surowych komend na kanał końcowy.
    # DLACZEGO: Pakiet `robot_emergency_stop` ma działać samodzielnie poza stosem `g1_light_tracking`.
    # JAK TO DZIAŁA: Launch mapuje `cmd_vel_in` na `/cmd_vel_raw` i `cmd_vel_out` na `/cmd_vel`,
    #   więc może być użyty jako uniwersalny filtr bezpieczeństwa dla innych źródeł komend.
    # TODO: Dodać argumenty launch (`cmd_vel_in`, `cmd_vel_out`) dla łatwej parametryzacji w różnych robotach.
    return LaunchDescription(
        [
            Node(
                package='robot_emergency_stop',
                executable='emergency_stop_node',
                name='emergency_stop_node',
                output='screen',
                remappings=[
                    ('cmd_vel_in', '/cmd_vel_raw'),
                    ('cmd_vel_out', '/cmd_vel'),
                ],
            )
        ]
    )
