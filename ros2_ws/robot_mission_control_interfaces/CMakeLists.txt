cmake_minimum_required(VERSION 3.8)
project(robot_mission_control_interfaces)

# [AI-CHANGE | 2026-04-24 23:18 UTC | v0.202]
# CO ZMIENIONO: Dodano konfigurację CMake do generowania interfejsu Action `MissionStep`.
# DLACZEGO: Pakiet interfejsów musi produkować kod Python/C++ dla typu akcji używanego przez backend.
# JAK TO DZIAŁA: `rosidl_generate_interfaces` kompiluje plik `.action`, a zależność `action_msgs`
#                dostarcza standardowe typy statusów używane przez transport Action.
# TODO: Rozszerzyć pakiet o dedykowane wiadomości diagnostyczne, jeśli kontrakt będzie wymagał większego telemetry payload.
find_package(ament_cmake REQUIRED)
find_package(rosidl_default_generators REQUIRED)
find_package(action_msgs REQUIRED)

rosidl_generate_interfaces(${PROJECT_NAME}
  "action/MissionStep.action"
  DEPENDENCIES action_msgs
)

ament_export_dependencies(rosidl_default_runtime)
ament_package()
