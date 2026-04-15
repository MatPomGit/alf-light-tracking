# alf-light-tracking

`alf-light-tracking` to repozytorium zawierające workspace ROS 2 `ros2_ws/` oraz pakiet `g1_light_tracking`. Projekt realizuje warstwowy pipeline do percepcji obrazu, lokalizacji 3D, trackingu, wiązania QR z kartonami, logiki misji i sterowania. Repo zawiera także zachowaną warstwę kompatybilności `legacy`, która pozwala zasilać aktualny pipeline danymi ze starszego toru JSON.

## Układ repozytorium

Najważniejsze ścieżki od katalogu głównego repo:

- `ros2_ws/` — główny workspace ROS 2; to z tego katalogu uruchamia się `colcon build`.
- `ros2_ws/src/g1_light_tracking/` — właściwy pakiet ROS 2.
- `ros2_ws/src/g1_light_tracking/g1_light_tracking/` — kod Pythona: node'y, utils, vision, standalone.
- `ros2_ws/src/g1_light_tracking/launch/` — launchery ROS 2.
- `ros2_ws/src/g1_light_tracking/config/` — konfiguracje YAML.
- `ros2_ws/src/g1_light_tracking/msg/` — własne wiadomości ROS 2.
- `ros2_ws/src/g1_light_tracking/docs/` — dokumentacja HTML i opis architektury.
- `install_git_hooks.sh` — instalacja hooków z poziomu katalogu głównego repo.

## Architektura systemu

Docelowy tor pracy to pipeline `modern`:

1. `perception_node` publikuje `Detection2D`.
2. `localization_node` przelicza 2D na 3D i publikuje `LocalizedTarget`.
3. `tracking_node` stabilizuje identyfikatory i publikuje `TrackedTarget`.
4. `parcel_track_node` wiąże QR z obiektami logistycznymi i publikuje `ParcelTrack`.
5. `mission_node` wybiera aktywny cel i publikuje `MissionState` oraz `MissionTarget`.
6. `control_node` zamienia wynik misji na komendy ruchu.
7. `depth_mapper_node`, `visual_slam_node` i `debug_node` pełnią role pomocnicze i diagnostyczne.

Warstwa `legacy` została zachowana obok niego:

- `light_spot_detector_node` publikuje starszy format detekcji JSON,
- `legacy_detection_adapter_node` tłumaczy go na nowe wiadomości,
- dodatkowe bridge'e obsługują Unitree, turtlesim i replay CSV,
- `unified_system.launch.py` pozwala przełączać tryby `modern`, `legacy` i `hybrid`.

## Wymagania

Minimalne wymagania środowiskowe:

- ROS 2 Humble lub zgodne środowisko z `colcon`,
- Python 3,
- zależności z `package.xml`,
- biblioteki Python z:
  - `ros2_ws/src/g1_light_tracking/requirements-ros-python.txt`,
  - opcjonalnie `ros2_ws/src/g1_light_tracking/requirements-standalone.txt`,
  - opcjonalnie `ros2_ws/src/g1_light_tracking/requirements-compat.txt`,
- `libzbar0` dla odczytu QR,
- opcjonalnie `pyrealsense2` dla kamery D435i,
- opcjonalnie środowisko Unitree dla bridge'y sprzętowych.

## Kanoniczna procedura builda

Wszystkie komendy builda wykonuj z katalogu workspace, czyli `ros2_ws/`.

### Standardowy build pakietu

```bash
cd ros2_ws
colcon build --packages-select g1_light_tracking
source install/setup.bash
```

### Build całego workspace

```bash
cd ros2_ws
colcon build
source install/setup.bash
```

### Ważne po naprawie konfliktu CMake targetów

Jeżeli wcześniej wystąpił błąd w stylu:

- `ament_cmake_python_copy_g1_light_tracking already exists`
- `ament_cmake_python_build_g1_light_tracking_egg already exists`

to przed ponownym buildem wyczyść artefakty konfiguracji:

```bash
cd ros2_ws
rm -rf build install log
colcon build --packages-select g1_light_tracking
source install/setup.bash
```

To jest ważne, ponieważ wcześniejszy konflikt targetów CMake mógł pozostawić nieprawidłowy stan w katalogach builda.

## Instalacja zależności Python

Komendy wykonuj z katalogu pakietu:

```bash
cd ros2_ws/src/g1_light_tracking
python3 -m pip install -r requirements-ros-python.txt
python3 -m pip install -r requirements-standalone.txt
python3 -m pip install -r requirements-compat.txt
sudo apt install libzbar0
```

Jeżeli nie używasz wariantu standalone albo kompatybilności legacy, odpowiednie pliki `requirements-*.txt` można pominąć.

## Uruchamianie systemu

Wszystkie poniższe komendy zakładają, że:
- jesteś w katalogu `ros2_ws/`,
- wykonałeś `source install/setup.bash`.

### Główny launcher produkcyjny nowego pipeline'u

```bash
cd ros2_ws
source install/setup.bash
ros2 launch g1_light_tracking prod.launch.py
```

### Główny launcher zunifikowany

To jest rekomendowany punkt wejścia do przełączania trybów pracy.

```bash
cd ros2_ws
source install/setup.bash
ros2 launch g1_light_tracking unified_system.launch.py mode:=modern
```

Przykłady:

```bash
# wyłącznie nowoczesny pipeline
cd ros2_ws
source install/setup.bash
ros2 launch g1_light_tracking unified_system.launch.py mode:=modern

# legacy detector + adapter + nowa misja / sterowanie
cd ros2_ws
source install/setup.bash
ros2 launch g1_light_tracking unified_system.launch.py mode:=legacy

# tryb hybrydowy do migracji
cd ros2_ws
source install/setup.bash
ros2 launch g1_light_tracking unified_system.launch.py mode:=hybrid

# tryb hybrydowy z legacy kamerą
cd ros2_ws
source install/setup.bash
ros2 launch g1_light_tracking unified_system.launch.py mode:=hybrid with_legacy_camera:=true

# tryb legacy z mostami Unitree
cd ros2_ws
source install/setup.bash
ros2 launch g1_light_tracking unified_system.launch.py mode:=legacy with_unitree_bridges:=true
```

### Pozostałe launchery

```bash
# pełny zachowany stack legacy
cd ros2_ws
source install/setup.bash
ros2 launch g1_light_tracking legacy_light_tracking_stack.launch.py

# replay CSV i turtlesim
cd ros2_ws
source install/setup.bash
ros2 launch g1_light_tracking legacy_light_tracking_turtlesim.launch.py csv_file:=/pelna/sciezka/do/detekcji.csv playback_rate:=1.0 loop:=true

# minimalny most legacy -> nowa misja / sterowanie
cd ros2_ws
source install/setup.bash
ros2 launch g1_light_tracking legacy_modern_mission_bridge.launch.py

# diagnostyka top-down i odometrii
cd ros2_ws
source install/setup.bash
ros2 launch g1_light_tracking topdown_odom.launch.py
```

## Testy i szybka weryfikacja

### Testy pakietu

```bash
cd ros2_ws
source install/setup.bash
python3 -m pytest src/g1_light_tracking/test -v
```

### Weryfikacja importów Pythona

```bash
cd ros2_ws
source install/setup.bash
python3 -c "from g1_light_tracking.utils.geometry import solve_square_pnp, pixel_to_floor_plane, estimate_depth_from_known_width; print('geometry OK')"
python3 -c "from g1_light_tracking.nodes.localization_node import LocalizationNode; print('localization_node OK')"
python3 -c "from g1_light_tracking.nodes.depth_mapper_node import DepthMapperNode; print('depth_mapper OK')"
```

Pełna weryfikacja runtime ROS 2 nadal wymaga środowiska z zainstalowanym `rclpy`, zależnościami ROS i właściwym sprzętem lub źródłami danych.

## Dokumentacja

Najważniejsze dokumenty:

- `README.md` — przegląd całego repo,
- `ros2_ws/README.md` — opis workspace,
- `ros2_ws/src/g1_light_tracking/README.md` — opis pakietu,
- `ros2_ws/src/g1_light_tracking/docs/index.html` — dokumentacja HTML,
- `ros2_ws/src/g1_light_tracking/docs/architecture.md` — szczegóły architektury.

## Stan repo po ostatnich poprawkach

Aktualna wersja repo uwzględnia między innymi:

- poprawki wywołań helperów geometrycznych w `localization_node`,
- poprawne mapowanie `Detection2D.image_points`,
- spójne ustawianie `track_id` w `ParcelTrack`,
- ujednolicenie typu macierzy kamery w `depth_mapper_node`,
- poprawkę builda CMake dla pakietu łączącego ROS messages i kod Pythona.

## Kierunek dalszej migracji

Repo jest przygotowane do pracy w trzech trybach:
- `modern` — tryb docelowy,
- `legacy` — tryb kompatybilności,
- `hybrid` — tryb przejściowy.

Docelowo warstwa legacy powinna pozostać tylko tam, gdzie jest potrzebna do:
- replayu danych historycznych,
- demonstracji,
- integracji z wybranym sprzętem lub starszym środowiskiem wykonawczym.
