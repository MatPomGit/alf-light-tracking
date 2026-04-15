# alf-light-tracking

Repozytorium zawiera workspace ROS 2 z pakietem `g1_light_tracking`.

## Układ repozytorium

- `ros2_ws/` — workspace ROS 2
- `ros2_ws/src/g1_light_tracking/` — właściwy pakiet

## Szybki start

```bash
cd ros2_ws
colcon build
source install/setup.bash
ros2 launch g1_light_tracking prod.launch.py
```

## Testy

```bash
cd ros2_ws/src/g1_light_tracking
pytest
```

## Hook wersjonowania

Z katalogu głównego repozytorium:

```bash
bash install_git_hooks.sh
```

Z katalogu `ros2_ws/`:

```bash
bash install_git_hooks.sh
```

Szczegóły pakietu są opisane w `ros2_ws/src/g1_light_tracking/README.md`.
