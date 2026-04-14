# g1_light_tracking

Repozytorium zostało uporządkowane do układu zgodnego z praktyką `ament_cmake` + Python package w workspace ROS 2.

## Główna struktura

- `g1_light_tracking/ros2_ws/`
  - workspace ROS 2
- `g1_light_tracking/ros2_ws/src/g1_light_tracking/`
  - właściwy pakiet ROS 2

## Najważniejsze katalogi pakietu

W pakiecie:
- `g1_light_tracking/ros2_ws/src/g1_light_tracking/g1_light_tracking/` — moduły Pythona
- `g1_light_tracking/ros2_ws/src/g1_light_tracking/launch/`
- `g1_light_tracking/ros2_ws/src/g1_light_tracking/config/`
- `g1_light_tracking/ros2_ws/src/g1_light_tracking/msg/`
- `g1_light_tracking/ros2_ws/src/g1_light_tracking/scripts/`
- `g1_light_tracking/ros2_ws/src/g1_light_tracking/docs/`
- `g1_light_tracking/ros2_ws/src/g1_light_tracking/resource/`

## Budowanie

```bash
cd g1_light_tracking/ros2_ws
colcon build
source install/setup.bash
```

## Uruchomienie

```bash
cd g1_light_tracking/ros2_ws
source install/setup.bash
ros2 launch g1_light_tracking prod.launch.py
```

## Dokumentacja WWW

Plik dokumentacji znajduje się w:
- `g1_light_tracking/ros2_ws/src/g1_light_tracking/docs/index.html`

## Hook wersjonowania

Z poziomu katalogu głównego repozytorium:
```bash
bash install_git_hooks.sh
```

Z poziomu katalogu workspace:
```bash
bash ros2_ws/install_git_hooks.sh
```

Instalator używa:
- `ros2_ws/src/g1_light_tracking/scripts/version_bump.py`

## Dodatkowy moduł

W strukturze `ros2_ws/src/g1_light_tracking/` znajduje się także:
- `config/visual_slam.yaml`
- `g1_light_tracking/nodes/visual_slam_node.py`
- `scripts/visual_slam_node`
