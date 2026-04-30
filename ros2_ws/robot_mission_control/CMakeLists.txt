cmake_minimum_required(VERSION 3.8)
project(robot_mission_control)

# [AI-CHANGE | 2026-04-29 13:15 UTC | v0.332]
# CO ZMIENIONO: Przeniesiono budowanie pakietu z `ament_python` do `ament_cmake` z lokalnym generowaniem `MissionStep.action`.
# DLACZEGO: Pakiet ma być pojedynczy, więc kontrakt Action musi powstawać w `robot_mission_control`, bez osobnego
#           `robot_mission_control_interfaces`, a jednocześnie moduły Pythona muszą nadal trafiać do install-space.
# JAK TO DZIAŁA: `rosidl_generate_interfaces` generuje typ `robot_mission_control/action/MissionStep`,
#                `ament_python_install_package` instaluje aplikację Python, a skrypty w `lib/${PROJECT_NAME}`
#                zachowują zgodność z `ros2 run`.
# TODO: Zweryfikować w CI pełny `colcon build` na ROS2 Jazzy, bo łączenie interfejsów i modułów Pythona w jednym
#       pakiecie wymaga kontroli konfliktów instalacji wygenerowanego modułu `action`.
find_package(ament_cmake REQUIRED)
find_package(ament_cmake_python REQUIRED)
find_package(rosidl_default_generators REQUIRED)
find_package(action_msgs REQUIRED)

rosidl_generate_interfaces(${PROJECT_NAME}
  "action/MissionStep.action"
  DEPENDENCIES action_msgs
)

# [AI-CHANGE | 2026-04-30 10:22 UTC | v0.202]
# CO ZMIENIONO: Zastąpiono `ament_python_install_package(${PROJECT_NAME})` ręczną instalacją katalogu modułu Python.
# DLACZEGO: `rosidl_generator_py` i `ament_python_install_package` tworzyły identyczne cele CMake
#           (`ament_cmake_python_copy_robot_mission_control`), co kończyło konfigurację błędem duplikatu celu.
# JAK TO DZIAŁA: Moduł aplikacji `robot_mission_control` jest instalowany bezpośrednio do `${PYTHON_INSTALL_DIR}`,
#                a interfejs Action nadal jest generowany przez `rosidl_generate_interfaces`.
# TODO: Rozważyć wydzielenie interfejsów Action do osobnego pakietu `*_interfaces`, aby uprościć zależności build-time.
install(DIRECTORY
  ${PROJECT_NAME}
  DESTINATION ${PYTHON_INSTALL_DIR}
)

install(PROGRAMS
  scripts/robot_mission_control
  scripts/mission_step_action_test_server
  DESTINATION lib/${PROJECT_NAME}
)

install(DIRECTORY
  launch
  config
  DESTINATION share/${PROJECT_NAME}
)

install(FILES
  README.md
  requirements.txt
  requirements-core.txt
  requirements-ui.txt
  DESTINATION share/${PROJECT_NAME}
)

ament_export_dependencies(rosidl_default_runtime)
ament_package()
