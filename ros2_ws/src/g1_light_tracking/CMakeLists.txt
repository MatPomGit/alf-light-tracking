cmake_minimum_required(VERSION 3.8)
project(g1_light_tracking)

if(CMAKE_COMPILER_IS_GNUCXX OR CMAKE_CXX_COMPILER_ID MATCHES "Clang")
  add_compile_options(-Wall -Wextra -Wpedantic)
endif()

find_package(ament_cmake REQUIRED)
find_package(ament_cmake_python REQUIRED)
find_package(rosidl_default_generators REQUIRED)
find_package(rclpy REQUIRED)
find_package(std_msgs REQUIRED)
find_package(sensor_msgs REQUIRED)
find_package(geometry_msgs REQUIRED)
find_package(nav_msgs REQUIRED)
find_package(builtin_interfaces REQUIRED)
find_package(cv_bridge REQUIRED)
find_package(image_transport REQUIRED)
find_package(tf2_ros REQUIRED)

rosidl_generate_interfaces(${PROJECT_NAME}
  "msg/Detection2D.msg"
  "msg/LocalizedTarget.msg"
  "msg/TrackedTarget.msg"
  "msg/ParcelTrackBinding.msg"
  "msg/ParcelTrack.msg"
  "msg/ParcelInfo.msg"
  "msg/MissionTarget.msg"
  "msg/MissionState.msg"
  "msg/DepthNavHint.msg"
  DEPENDENCIES builtin_interfaces std_msgs geometry_msgs nav_msgs sensor_msgs
)

ament_python_install_package(${PROJECT_NAME})

install(PROGRAMS
  scripts/perception_node
  scripts/localization_node
  scripts/tracking_node
  scripts/parcel_track_node
  scripts/mission_node
  scripts/control_node
  scripts/debug_node
  scripts/camera_calibration_node
  scripts/depth_mapper_node
  scripts/visual_slam_node
  scripts/topdown_odom_viewer_node
  scripts/standalone_cli
  scripts/standalone_gui
  scripts/version_bump.py
  DESTINATION lib/${PROJECT_NAME}
)

install(DIRECTORY launch config profiles calibration docs msg
  DESTINATION share/${PROJECT_NAME}
)

install(FILES
  package.xml
  VERSION
  DESTINATION share/${PROJECT_NAME}
)

ament_export_dependencies(rosidl_default_runtime)
ament_package()
