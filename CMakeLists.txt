\
cmake_minimum_required(VERSION 3.8)
project(g1_light_tracking)

find_package(ament_cmake REQUIRED)
find_package(ament_cmake_python REQUIRED)
find_package(rosidl_default_generators REQUIRED)
find_package(std_msgs REQUIRED)
find_package(geometry_msgs REQUIRED)
find_package(sensor_msgs REQUIRED)
find_package(vision_msgs REQUIRED)
find_package(builtin_interfaces REQUIRED)

rosidl_generate_interfaces(${PROJECT_NAME}
  "msg/Detection2D.msg"
  "msg/LocalizedTarget.msg"
  "msg/MissionTarget.msg"
  "msg/ParcelInfo.msg"
  "msg/TrackedTarget.msg"
  "msg/ParcelTrackBinding.msg"
  DEPENDENCIES builtin_interfaces std_msgs geometry_msgs
)

ament_python_install_package(${PROJECT_NAME})

install(PROGRAMS
  scripts/perception_node
  scripts/localization_node
  scripts/tracking_node
  scripts/association_node
  scripts/mission_node
  scripts/control_node
  scripts/debug_node
  DESTINATION lib/${PROJECT_NAME}
)

install(DIRECTORY launch config
  DESTINATION share/${PROJECT_NAME}
)

install(FILES package.xml README.md
  DESTINATION share/${PROJECT_NAME}
)

ament_export_dependencies(rosidl_default_runtime)
ament_package()
