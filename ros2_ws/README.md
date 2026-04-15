# ros2_ws

`ros2_ws/` jest workspace'em ROS 2 dla pakietu `g1_light_tracking`. To z tego katalogu wykonuje się build przez `colcon`, aktywację środowiska i uruchamianie launcherów ROS 2.

## Struktura workspace'u

- `src/g1_light_tracking/` — źródła pakietu,
- `build/` — artefakty kompilacji generowane przez `colcon`,
- `install/` — wynik instalacji workspace'u,
- `log/` — logi builda.

W samym pakiecie najważniejsze katalogi to:

- `src/g1_light_tracking/launch/`
- `src/g1_light_tracking/config/`
- `src/g1_light_tracking/msg/`
- `src/g1_light_tracking/docs/`

## Build

Z katalogu `ros2_ws/`:

```bash
colcon build --packages-select g1_light_tracking
```

Lub cały workspace:

```bash
colcon build
```

## Aktywacja środowiska

Po każdym buildzie i w każdej nowej sesji terminala:

```bash
source install/setup.bash
```

## Najważniejsze launchery

Wszystkie polecenia poniżej wykonuj z katalogu `ros2_ws/` po `source install/setup.bash`.

### Domyślny launcher nowoczesny

```bash
ros2 launch g1_light_tracking prod.launch.py
```

### Launcher zunifikowany

```bash
ros2 launch g1_light_tracking unified_system.launch.py mode:=modern
```

Przykłady:

```bash
ros2 launch g1_light_tracking unified_system.launch.py mode:=modern
ros2 launch g1_light_tracking unified_system.launch.py mode:=legacy
ros2 launch g1_light_tracking unified_system.launch.py mode:=hybrid
ros2 launch g1_light_tracking unified_system.launch.py mode:=hybrid with_legacy_camera:=true
ros2 launch g1_light_tracking unified_system.launch.py mode:=legacy with_unitree_bridges:=true
```

### Launcher legacy

```bash
ros2 launch g1_light_tracking legacy_light_tracking_stack.launch.py
```

### Legacy turtlesim / CSV replay

```bash
ros2 launch g1_light_tracking legacy_light_tracking_turtlesim.launch.py csv_file:=/pelna/sciezka/do/detekcji.csv
```

### Legacy JSON -> nowa misja / sterowanie

```bash
ros2 launch g1_light_tracking legacy_modern_mission_bridge.launch.py
```

### Top-down / odometria

```bash
ros2 launch g1_light_tracking topdown_odom.launch.py
```

## Dokumentacja

Pliki dokumentacyjne znajdują się tutaj:

- `src/g1_light_tracking/README.md`
- `src/g1_light_tracking/docs/index.html`
- `src/g1_light_tracking/docs/architecture.md`

Jeżeli otwierasz dokumentację HTML bezpośrednio z systemu plików, plik wejściowy to:

- `ros2_ws/src/g1_light_tracking/docs/index.html`

## Testy

Aby uruchomić testy, przejdź do katalogu pakietu:

```bash
cd src/g1_light_tracking
pytest
```

