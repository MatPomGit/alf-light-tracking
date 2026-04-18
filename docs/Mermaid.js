flowchart TD

subgraph group_group_sources["Inputs"]
  node_node_d435i["D435i node<br/>camera source<br/>[d435i_node.py]"]
  node_node_csv_replay["CSV replay<br/>offline source"]
end

subgraph group_group_perception["Perception"]
  node_node_detector["Light detector<br/>perception node"]
  node_node_vision_iface["Detector API<br/>vision abstraction"]
  node_node_vision_types["Detection types<br/>vision model<br/>[detection_types.py]"]
  node_node_detector_registry["Registry"]
  node_node_detectors["Detectors<br/>vision impls<br/>[detectors.py]"]
end

subgraph group_group_control["Control"]
  node_node_follower["Follower<br/>control node"]
end

subgraph group_group_actuation["Actuation"]
  node_node_unitree_bridge["Unitree bridge<br/>cmd_vel bridge"]
  node_node_turtlesim_bridge["Turtlesim bridge<br/>cmd_vel bridge"]
end

subgraph group_group_arm["Arm Skills"]
  node_node_arm_bridge["Arm bridge<br/>service bridge"]
  node_node_arm_controller["Arm controller"]
end

subgraph group_group_launch["Launch & Tools"]
  node_node_stack_launch["Robot launch<br/>launch file"]
  node_node_turtle_launch["Turtlesim launch<br/>launch file"]
  node_node_calibrate["Calibration tool<br/>offline tool"]
  node_node_calib_report["Calibration report"]
end

subgraph group_group_config["Configuration"]
  node_node_perception_cfg["Perception cfg<br/>yaml config<br/>[perception.yaml]"]
  node_node_control_cfg["Control cfg<br/>yaml config<br/>[control.yaml]"]
  node_node_bridge_cfg["Bridge cfg<br/>yaml config<br/>[bridge.yaml]"]
end

node_node_d435i -->|"/camera/image_raw"| node_node_detector
node_node_csv_replay -->|"/light_tracking/detection_json"| node_node_follower
node_node_detector -->|"/light_tracking/detection_json"| node_node_follower
node_node_follower -->|"/cmd_vel"| node_node_unitree_bridge
node_node_follower -->|"/cmd_vel"| node_node_turtlesim_bridge
node_node_arm_bridge -->|"services"| node_node_arm_controller
node_node_stack_launch -->|"starts"| node_node_d435i
node_node_stack_launch -->|"starts"| node_node_detector
node_node_stack_launch -->|"starts"| node_node_follower
node_node_stack_launch -->|"starts"| node_node_unitree_bridge
node_node_stack_launch -->|"starts"| node_node_arm_bridge
node_node_turtle_launch -->|"starts"| node_node_csv_replay
node_node_turtle_launch -->|"starts"| node_node_follower
node_node_turtle_launch -->|"starts"| node_node_turtlesim_bridge
node_node_calibrate -->|"writes"| node_node_perception_cfg
node_node_calibrate -->|"produces"| node_node_calib_report
node_node_perception_cfg -->|"configures"| node_node_detector
node_node_control_cfg -->|"configures"| node_node_follower
node_node_bridge_cfg -->|"configures"| node_node_unitree_bridge
node_node_vision_iface -->|"defines"| node_node_detectors
node_node_vision_types -->|"defines"| node_node_detector
node_node_detector_registry -->|"selects"| node_node_detector
node_node_detectors -->|"implements"| node_node_detector
node_node_arm_bridge -.->|"optional"| node_node_stack_launch

click node_node_d435i "https://github.com/matpomgit/alf-light-tracking/blob/main/ros2_ws/g1_light_tracking/g1_light_tracking/d435i_node.py"
click node_node_csv_replay "https://github.com/matpomgit/alf-light-tracking/blob/main/ros2_ws/g1_light_tracking/g1_light_tracking/csv_detection_replay_node.py"
click node_node_detector "https://github.com/matpomgit/alf-light-tracking/blob/main/ros2_ws/g1_light_tracking/g1_light_tracking/light_spot_detector_node.py"
click node_node_vision_iface "https://github.com/matpomgit/alf-light-tracking/blob/main/ros2_ws/g1_light_tracking/g1_light_tracking/vision/detector_interfaces.py"
click node_node_vision_types "https://github.com/matpomgit/alf-light-tracking/blob/main/ros2_ws/g1_light_tracking/g1_light_tracking/vision/detection_types.py"
click node_node_detector_registry "https://github.com/matpomgit/alf-light-tracking/blob/main/ros2_ws/g1_light_tracking/g1_light_tracking/vision/detector_registry.py"
click node_node_detectors "https://github.com/matpomgit/alf-light-tracking/blob/main/ros2_ws/g1_light_tracking/g1_light_tracking/vision/detectors.py"
click node_node_follower "https://github.com/matpomgit/alf-light-tracking/blob/main/ros2_ws/g1_light_tracking/g1_light_tracking/g1_light_follower_node.py"
click node_node_unitree_bridge "https://github.com/matpomgit/alf-light-tracking/blob/main/ros2_ws/g1_light_tracking/g1_light_tracking/unitree_cmd_vel_bridge_node.py"
click node_node_turtlesim_bridge "https://github.com/matpomgit/alf-light-tracking/blob/main/ros2_ws/g1_light_tracking/g1_light_tracking/turtlesim_cmd_vel_bridge_node.py"
click node_node_arm_bridge "https://github.com/matpomgit/alf-light-tracking/blob/main/ros2_ws/g1_light_tracking/g1_light_tracking/arm_skill_bridge_node.py"
click node_node_arm_controller "https://github.com/matpomgit/alf-light-tracking/blob/main/ros2_ws/g1_light_tracking/g1_light_tracking/arm_skill_controller.py"
click node_node_stack_launch "https://github.com/matpomgit/alf-light-tracking/blob/main/ros2_ws/g1_light_tracking/launch/light_tracking_stack.launch.py"
click node_node_turtle_launch "https://github.com/matpomgit/alf-light-tracking/blob/main/ros2_ws/g1_light_tracking/launch/light_tracking_turtlesim.launch.py"
click node_node_calibrate "https://github.com/matpomgit/alf-light-tracking/blob/main/ros2_ws/g1_light_tracking/tools/calibrate_perception.py"
click node_node_perception_cfg "https://github.com/matpomgit/alf-light-tracking/blob/main/ros2_ws/g1_light_tracking/config/perception.yaml"
click node_node_control_cfg "https://github.com/matpomgit/alf-light-tracking/blob/main/ros2_ws/g1_light_tracking/config/control.yaml"
click node_node_bridge_cfg "https://github.com/matpomgit/alf-light-tracking/blob/main/ros2_ws/g1_light_tracking/config/bridge.yaml"
click node_node_calib_report "https://github.com/matpomgit/alf-light-tracking/blob/main/ros2_ws/g1_light_tracking/config/perception_calibration_report.md"

classDef toneNeutral fill:#f8fafc,stroke:#334155,stroke-width:1.5px,color:#0f172a
classDef toneBlue fill:#dbeafe,stroke:#2563eb,stroke-width:1.5px,color:#172554
classDef toneAmber fill:#fef3c7,stroke:#d97706,stroke-width:1.5px,color:#78350f
classDef toneMint fill:#dcfce7,stroke:#16a34a,stroke-width:1.5px,color:#14532d
classDef toneRose fill:#ffe4e6,stroke:#e11d48,stroke-width:1.5px,color:#881337
classDef toneIndigo fill:#e0e7ff,stroke:#4f46e5,stroke-width:1.5px,color:#312e81
classDef toneTeal fill:#ccfbf1,stroke:#0f766e,stroke-width:1.5px,color:#134e4a
class node_node_d435i,node_node_csv_replay,node_node_perception_cfg,node_node_control_cfg,node_node_bridge_cfg toneBlue
class node_node_detector,node_node_vision_iface,node_node_vision_types,node_node_detector_registry,node_node_detectors toneAmber
class node_node_follower toneMint
class node_node_unitree_bridge,node_node_turtlesim_bridge toneRose
class node_node_arm_bridge,node_node_arm_controller toneIndigo
class node_node_stack_launch,node_node_turtle_launch,node_node_calibrate,node_node_calib_report toneTeal
