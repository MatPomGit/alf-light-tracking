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
ros2 launch g1_light_tracking prod.launch.py
```


```bash
bash g1_light_tracking/install_git_hooks.sh
```


## Hook wersjonowania

Możesz zainstalować hook z poziomu repo:
```bash
bash g1_light_tracking/install_git_hooks.sh
```

albo z poziomu workspace:
```bash
bash g1_light_tracking/ros2_ws/install_git_hooks.sh
```

Instalator sam wykrywa właściwą ścieżkę do:
- `ros2_ws/src/g1_light_tracking/scripts/version_bump.py`
