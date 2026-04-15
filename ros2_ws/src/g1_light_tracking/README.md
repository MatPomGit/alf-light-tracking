# g1_light_tracking

Pakiet ROS 2 dla eksperymentalnego pipeline'u percepcji, trackingu i logiki misji w zadaniach intra-logistycznych.

## Co jest w pakiecie

Pipeline jest zbudowany z następujących node'ów:
- `perception_node` — detekcja 2D i odczyt kodów.
- `localization_node` — estymacja położeń 3D.
- `tracking_node` — śledzenie obiektów w czasie.
- `parcel_track_node` — wiązanie QR z kartonem i agregacja stanu przesyłki.
- `mission_node` — logika misji wysokiego poziomu.
- `control_node` — generowanie uproszczonych komend ruchu.
- `depth_mapper_node` — wskazówki nawigacyjne z głębi.
- `debug_node` — logowanie diagnostyczne.
- `camera_calibration_node` — zapis intrinsics kamery.
- `visual_slam_node` oraz `topdown_odom_viewer_node` — moduły pomocnicze SLAM / diagnostyki.

Najważniejsze custom messages znajdują się w `msg/`.

## Struktura

```text
ros2_ws/src/g1_light_tracking/
├── CMakeLists.txt
├── package.xml
├── setup.py
├── g1_light_tracking/
│   ├── nodes/
│   ├── standalone/
│   └── utils/
├── config/
├── launch/
├── msg/
├── profiles/
├── scripts/
└── test/
```

## Build

```bash
cd ros2_ws
colcon build
source install/setup.bash
```

## Testy jednostkowe

Testy utili można uruchamiać bez pełnego środowiska ROS 2:

```bash
cd ros2_ws/src/g1_light_tracking
pytest
```

## Uruchomienie

```bash
cd ros2_ws
source install/setup.bash
ros2 launch g1_light_tracking prod.launch.py
```

Dodatkowy launcher diagnostyczny:

```bash
ros2 launch g1_light_tracking topdown_odom.launch.py
```

## Zależności Pythona

Tryb standalone:

```bash
pip install -r requirements-standalone.txt
```

Środowisko pomocnicze dla node'ów Pythona:

```bash
pip install -r requirements-ros-python.txt
```

`pyzbar` zwykle wymaga zainstalowanej biblioteki systemowej `zbar`.

## Hook wersjonowania

Z katalogu głównego repo:

```bash
bash install_git_hooks.sh
```

Lub z katalogu `ros2_ws/`:

```bash
bash install_git_hooks.sh
```
