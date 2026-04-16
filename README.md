# alf-light-tracking

`alf-light-tracking` to repozytorium zawierające workspace ROS 2 `ros2_ws/` oraz główny pakiet `g1_light_tracking`. Projekt realizuje warstwowy pipeline do percepcji obrazu, lokalizacji 3D, trackingu, wiązania QR z kartonami, logiki misji i sterowania ruchem robota. Repo zawiera także zachowaną warstwę kompatybilności `legacy`, która pozwala zasilać aktualny pipeline danymi ze starszego toru i wspierać etap migracji.

Docelowym środowiskiem pracy jest robot **Unitree G1 EDU** uruchamiany na **Ubuntu 22.04**, zwykle w trybie **headless przez SSH**. Z tego powodu narzędzia, launchery i moduły diagnostyczne muszą być użyteczne z poziomu terminala. Komunikacja między modułami powinna odbywać się przez **ROS 2**.

---

## 1. Co znajduje się w repozytorium

Najważniejsze ścieżki od katalogu głównego repo:

```text
.
├── README.md
├── AGENTS.md
├── CODE_STYLE_PL.md
├── install_git_hooks.sh
└── ros2_ws/
    ├── README.md
    ├── src/
    │   └── g1_light_tracking/
    │       ├── README.md
    │       ├── CMakeLists.txt
    │       ├── package.xml
    │       ├── setup.py
    │       ├── config/
    │       ├── docs/
    │       ├── g1_light_tracking/
    │       │   ├── nodes/
    │       │   ├── standalone/
    │       │   ├── utils/
    │       │   └── vision/
    │       ├── launch/
    │       ├── msg/
    │       ├── profiles/
    │       ├── scripts/
    │       ├── test/
    │       ├── requirements-ros-python.txt
    │       ├── requirements-standalone.txt
    │       └── requirements-compat.txt
    ├── build/
    ├── install/
    └── log/
```

Znaczenie głównych katalogów:

- `ros2_ws/` — główny workspace ROS 2; to z tego katalogu wykonuje się `colcon build`, `source install/setup.bash` i większość poleceń uruchomieniowych.
- `ros2_ws/src/g1_light_tracking/` — główny pakiet ROS 2 z node’ami, launcherami, konfiguracjami i własnymi wiadomościami.
- `ros2_ws/src/g1_light_tracking/g1_light_tracking/` — kod Pythona: node’y runtime, utils, vision, narzędzia standalone.
- `ros2_ws/src/g1_light_tracking/launch/` — launchery ROS 2 dla wariantów `modern`, `legacy`, `hybrid` i narzędzi pomocniczych.
- `ros2_ws/src/g1_light_tracking/config/` — konfiguracje YAML dla node’ów.
- `ros2_ws/src/g1_light_tracking/msg/` — własne wiadomości ROS 2.
- `ros2_ws/src/g1_light_tracking/docs/` — dokumentacja HTML i opisy architektury.
- `ros2_ws/src/g1_light_tracking/test/` — testy pakietu.

---

## 2. Główna architektura systemu

Docelowy tor pracy to pipeline `modern`:

1. `perception_node` publikuje `Detection2D`.
2. `localization_node` przelicza obserwacje 2D na położenia 3D i publikuje `LocalizedTarget`.
3. `tracking_node` stabilizuje identyfikatory i publikuje `TrackedTarget`.
4. `parcel_track_node` wiąże QR z obiektami logistycznymi i publikuje `ParcelTrack`.
5. `mission_node` wybiera aktywny cel i publikuje `MissionState` oraz `MissionTarget`.
6. `control_node` tłumaczy wynik misji na komendy ruchu, zwykle `geometry_msgs/Twist`.
7. `depth_mapper_node`, `visual_slam_node`, `debug_node`, TUI i inne narzędzia pełnią role pomocnicze, safety i diagnostyczne.

Warstwa `legacy` została zachowana równolegle:

- `light_spot_detector_node` publikuje starszy format detekcji JSON,
- `legacy_detection_adapter_node` tłumaczy go na nowe wiadomości,
- dodatkowe bridge’e wspierają Unitree, turtlesim i replay CSV,
- `unified_system.launch.py` umożliwia przełączanie trybów `modern`, `legacy` i `hybrid`.

### Założenia architektoniczne

Projekt powinien być rozwijany tak, aby:
- robot mógł działać autonomicznie,
- brak narzędzi pomocniczych nie psuł głównej pętli sterowania,
- wszystkie krytyczne zależności runtime były widoczne przez topiki, logi i diagnostykę,
- nowe funkcje mogły być w przyszłości wydzielane do osobnych paczek ROS 2.

---

## 3. Najważniejsze node’y pakietu `g1_light_tracking`

### `perception_node`
Rola:
- wykrywanie obiektów 2D,
- odczyt QR,
- wykrywanie AprilTagów,
- wykrywanie plamki światła,
- publikacja zunifikowanych detekcji do dalszych etapów pipeline’u.

Typowe wyjście:
- `/perception/detections` jako `Detection2D`.

### `localization_node`
Rola:
- przejście z reprezentacji 2D do 3D,
- estymacja pozycji XYZ,
- wykorzystanie geometrii kamery, głębi, PnP i innych metod dostępnych w konfiguracji.

Typowe wyjście:
- `/localization/targets` jako `LocalizedTarget`.

### `tracking_node`
Rola:
- asocjacja między klatkami,
- stabilizacja identyfikatorów,
- filtrowanie krótkotrwałych false positives,
- opcjonalna kompensacja global motion.

Typowe wyjście:
- `/tracking/targets` jako `TrackedTarget`.

### `parcel_track_node`
Rola:
- wiązanie QR z obiektami logistycznymi,
- budowa logicznego obiektu przesyłki,
- publikacja informacji logistycznych wykorzystywanych przez misję.

Typowe wyjścia:
- `/tracking/parcel_bindings`
- `/tracking/parcel_tracks`

### `mission_node`
Rola:
- wybór aktywnego celu,
- zarządzanie stanem zadania,
- publikacja stanu systemu i bieżącego celu.

Typowe wyjścia:
- `/mission/state`
- `/mission/target`
- `/mission/parcel_info`

### `control_node`
Rola:
- generowanie komend ruchu na podstawie stanu misji,
- ograniczanie ruchu przy zagrożeniach zgłaszanych przez depth layer,
- referencyjna logika sterowania dla robota.

Typowe wyjście:
- `/cmd_vel`

### `depth_mapper_node`
Rola:
- analiza mapy głębi,
- budowa lokalnych wskazówek bezpieczeństwa,
- publikacja `DepthNavHint`.

### `visual_slam_node`
Rola:
- eksperymentalna estymacja ruchu i odometrii na podstawie obrazu,
- publikacja danych przydatnych diagnostycznie.

### Ważne komponenty dodatkowe i legacy
Repo zawiera także m.in.:
- `d435i_node`
- `light_spot_detector_node`
- `g1_light_follower_node`
- `unitree_cmd_vel_bridge_node`
- `arm_skill_bridge_node`
- `csv_detection_replay_node`
- `turtlesim_cmd_vel_bridge_node`
- `legacy_detection_adapter_node`
- `camera_calibration_node`
- skrypty i narzędzia offline do kalibracji, monitoringu i eksportu danych

---

## 4. Własne wiadomości ROS 2

Pakiet definiuje między innymi:

- `Detection2D.msg`
- `LocalizedTarget.msg`
- `TrackedTarget.msg`
- `ParcelTrackBinding.msg`
- `ParcelTrack.msg`
- `ParcelInfo.msg`
- `MissionTarget.msg`
- `MissionState.msg`
- `DepthNavHint.msg`

Pliki znajdują się w katalogu:

```text
ros2_ws/src/g1_light_tracking/msg/
```

---

## 5. Wymagania środowiskowe

Minimalne wymagania:

- Ubuntu 22.04
- ROS 2 Humble lub kompatybilne środowisko z `colcon`
- Python 3
- zależności z `package.xml`
- biblioteki Python z:
  - `ros2_ws/src/g1_light_tracking/requirements-ros-python.txt`
  - opcjonalnie `requirements-standalone.txt`
  - opcjonalnie `requirements-compat.txt`
- `libzbar0` dla odczytu QR
- opcjonalnie `pyrealsense2` dla kamery D435i
- opcjonalnie środowisko Unitree dla bridge’y sprzętowych

Instalacja zależności Python i biblioteki systemowej:

```bash
cd ros2_ws/src/g1_light_tracking
python3 -m pip install -r requirements-ros-python.txt
python3 -m pip install -r requirements-standalone.txt
python3 -m pip install -r requirements-compat.txt
sudo apt update
sudo apt install -y libzbar0
```

Jeśli nie używasz wariantu standalone lub legacy, odpowiednie pliki `requirements-*.txt` można pominąć.

---

## 6. Kanoniczny build

Wszystkie polecenia builda wykonuj z katalogu `ros2_ws/`.

### Build tylko pakietu `g1_light_tracking`

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

### Gdy wcześniej wystąpił konflikt CMake targetów

Jeżeli na tej samej kopii repo wcześniej wystąpił błąd typu:

- `ament_cmake_python_copy_g1_light_tracking already exists`
- `ament_cmake_python_build_g1_light_tracking_egg already exists`

wyczyść artefakty builda i zbuduj od nowa:

```bash
cd ros2_ws
rm -rf build install log
colcon build --packages-select g1_light_tracking
source install/setup.bash
```

### Aktywacja środowiska po buildzie

Po każdym buildzie i w każdej nowej sesji terminala:

```bash
cd ros2_ws
source install/setup.bash
```

---

## 7. Uruchamianie systemu z terminala

Wszystkie poniższe polecenia zakładają, że:
- jesteś w katalogu `ros2_ws/`,
- wykonałeś `source install/setup.bash`.

### 7.1. Główny launcher produkcyjny nowego pipeline’u

```bash
cd ros2_ws
source install/setup.bash
ros2 launch g1_light_tracking prod.launch.py
```

### 7.2. Główny launcher zunifikowany

To jest rekomendowany punkt wejścia do przełączania trybów pracy:

```bash
cd ros2_ws
source install/setup.bash
ros2 launch g1_light_tracking unified_system.launch.py mode:=modern
```

### 7.3. Najczęstsze warianty uruchomienia

#### Wyłącznie nowoczesny pipeline

```bash
cd ros2_ws
source install/setup.bash
ros2 launch g1_light_tracking unified_system.launch.py mode:=modern
```

#### Wyłącznie warstwa legacy

```bash
cd ros2_ws
source install/setup.bash
ros2 launch g1_light_tracking unified_system.launch.py mode:=legacy
```

#### Tryb hybrydowy

```bash
cd ros2_ws
source install/setup.bash
ros2 launch g1_light_tracking unified_system.launch.py mode:=hybrid
```

#### Tryb hybrydowy z legacy kamerą

```bash
cd ros2_ws
source install/setup.bash
ros2 launch g1_light_tracking unified_system.launch.py mode:=hybrid with_legacy_camera:=true
```

#### Tryb legacy z bridge’ami Unitree

```bash
cd ros2_ws
source install/setup.bash
ros2 launch g1_light_tracking unified_system.launch.py mode:=legacy with_unitree_bridges:=true
```

---

## 8. Pozostałe launchery i warianty robocze

### Pełny zachowany stack legacy

```bash
cd ros2_ws
source install/setup.bash
ros2 launch g1_light_tracking legacy_light_tracking_stack.launch.py
```

### Replay CSV i turtlesim

```bash
cd ros2_ws
source install/setup.bash
ros2 launch g1_light_tracking legacy_light_tracking_turtlesim.launch.py   csv_file:=/pelna/sciezka/do/detekcji.csv   playback_rate:=1.0   loop:=true
```

### Minimalny most legacy -> nowa misja / sterowanie

```bash
cd ros2_ws
source install/setup.bash
ros2 launch g1_light_tracking legacy_modern_mission_bridge.launch.py
```

### Diagnostyka top-down i odometrii

```bash
cd ros2_ws
source install/setup.bash
ros2 launch g1_light_tracking topdown_odom.launch.py
```

---

## 9. Uruchamianie pojedynczych node’ów z terminala

### `perception_node`

```bash
cd ros2_ws
source install/setup.bash
ros2 run g1_light_tracking perception_node --ros-args --params-file src/g1_light_tracking/config/perception.yaml
```

### `localization_node`

```bash
cd ros2_ws
source install/setup.bash
ros2 run g1_light_tracking localization_node --ros-args --params-file src/g1_light_tracking/config/localization.yaml
```

### `tracking_node`

```bash
cd ros2_ws
source install/setup.bash
ros2 run g1_light_tracking tracking_node --ros-args --params-file src/g1_light_tracking/config/tracking.yaml
```

### `mission_node`

```bash
cd ros2_ws
source install/setup.bash
ros2 run g1_light_tracking mission_node --ros-args --params-file src/g1_light_tracking/config/mission.yaml
```

### `control_node`

```bash
cd ros2_ws
source install/setup.bash
ros2 run g1_light_tracking control_node --ros-args --params-file src/g1_light_tracking/config/control.yaml
```

### `depth_mapper_node`

```bash
cd ros2_ws
source install/setup.bash
ros2 run g1_light_tracking depth_mapper_node --ros-args --params-file src/g1_light_tracking/config/depth_mapper.yaml
```

### `visual_slam_node`

```bash
cd ros2_ws
source install/setup.bash
ros2 run g1_light_tracking visual_slam_node --ros-args --params-file src/g1_light_tracking/config/visual_slam.yaml
```

### `debug_node`

```bash
cd ros2_ws
source install/setup.bash
ros2 run g1_light_tracking debug_node
```

### `d435i_node`

```bash
cd ros2_ws
source install/setup.bash
ros2 run g1_light_tracking d435i_node
```

### `camera_calibration_node`

```bash
cd ros2_ws
source install/setup.bash
ros2 run g1_light_tracking camera_calibration_node --ros-args --params-file src/g1_light_tracking/config/camera_calibration.yaml
```

---

## 10. Offline tools i narzędzia developerskie

### Kalibracja z folderu zdjęć zwykłym Pythonem

Jeżeli używasz offline skryptu kalibracyjnego:

```bash
python calibrate_from_folder.py   --image-folder calibration/images   --board-cols 9   --board-rows 6   --square-size-m 0.024   --min-samples 20   --output-yaml calibration/camera_intrinsics.yaml   --output-report calibration/camera_intrinsics_report.txt   --save-previews   --preview-output-dir calibration/previews
```

### TUI monitor

Jeżeli w repo znajduje się aktualny `tui_monitor_node`:

```bash
cd ros2_ws
source install/setup.bash
ros2 run g1_light_tracking tui_monitor_node
```

### Skrypty standalone

Przykładowe uruchomienie narzędzia standalone CLI:

```bash
cd ros2_ws
source install/setup.bash
ros2 run g1_light_tracking standalone_cli
```

---

## 11. Testy i szybka weryfikacja

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

### Sprawdzenie topiców po starcie systemu

```bash
cd ros2_ws
source install/setup.bash
ros2 topic list
```

### Podgląd wykryć

```bash
cd ros2_ws
source install/setup.bash
ros2 topic echo /perception/detections
```

### Podgląd tracków

```bash
cd ros2_ws
source install/setup.bash
ros2 topic echo /tracking/targets
```

### Podgląd stanu misji

```bash
cd ros2_ws
source install/setup.bash
ros2 topic echo /mission/state
```

### Podgląd komend ruchu

```bash
cd ros2_ws
source install/setup.bash
ros2 topic echo /cmd_vel
```

---

## 12. Konfiguracje

Najważniejsze pliki w `config/`:

- `perception.yaml`
- `localization.yaml`
- `tracking.yaml`
- `parcel_tracking.yaml`
- `mission.yaml`
- `control.yaml`
- `depth_mapper.yaml`
- `visual_slam.yaml`
- `debug.yaml`
- `legacy_light_perception.yaml`
- `legacy_light_control.yaml`
- `legacy_bridge.yaml`
- `legacy_adapter.yaml`

W praktyce konfigurację najlepiej trzymać w YAML i przekazywać przez `--params-file`.

---

## 13. Diagnostyka i praca przez SSH

Projekt jest rozwijany z myślą o pracy na robocie bez monitora. Oznacza to:

- preferowane są logi terminalowe, TUI i topiki diagnostyczne,
- nie należy zakładać obecności `DISPLAY`,
- moduły GUI muszą być opcjonalne,
- błędy typu `no-display` nie mogą zatrzymywać podstawowej logiki robota.

Przy pracy zdalnej szczególnie ważne są:

- częste, konkretne logi startowe,
- logi przejść stanów,
- jawne sygnały fallbacku,
- topic freshness i heartbeat,
- debug node i monitor TUI.

---

## 14. Dokumentacja

Najważniejsze dokumenty:

- `README.md` — ten dokument, scalający informacje o repo, workspace i pakiecie,
- `AGENTS.md` — zasady architektoniczne dla agentów i programistów,
- `CODE_STYLE_PL.md` — standard komentarzy, docstringów i TODO,
- `ros2_ws/src/g1_light_tracking/docs/index.html` — dokumentacja HTML,
- `ros2_ws/src/g1_light_tracking/docs/architecture.md` — szczegóły architektury.

Jeżeli otwierasz dokumentację HTML bezpośrednio z systemu plików:

```text
ros2_ws/src/g1_light_tracking/docs/index.html
```

---

## 15. Stan repo i kierunek dalszego rozwoju

Aktualny kierunek rozwoju pozostaje bez zmian:

- `modern` jest trybem docelowym,
- `legacy` ma pełnić rolę warstwy kompatybilności i migracji,
- `hybrid` jest trybem przejściowym do integracji starego i nowego przepływu danych.

Docelowo warstwa legacy powinna zostać ograniczona do:
- replayu danych historycznych,
- demonstracji,
- środowisk testowych,
- mostów wymaganych tylko przez wybrane integracje.

Repo powinno być dalej rozwijane tak, aby nowe funkcjonalności, np.:
- rosbag,
- telemetry,
- monitoring,
- symulacja,
- offline analytics,
- narzędzia kalibracyjne,

mogły być dołączane jako **osobne paczki ROS 2**, bez uzależniania od nich podstawowej pętli działania robota.

---

## 16. Szybkie komendy „na start”

### Build i start nowoczesnego pipeline’u

```bash
cd ros2_ws
colcon build --packages-select g1_light_tracking
source install/setup.bash
ros2 launch g1_light_tracking unified_system.launch.py mode:=modern
```

### Start trybu hybrydowego

```bash
cd ros2_ws
source install/setup.bash
ros2 launch g1_light_tracking unified_system.launch.py mode:=hybrid
```

### Start trybu legacy z Unitree bridge

```bash
cd ros2_ws
source install/setup.bash
ros2 launch g1_light_tracking unified_system.launch.py mode:=legacy with_unitree_bridges:=true
```

### Podgląd stanu misji i sterowania

```bash
cd ros2_ws
source install/setup.bash
ros2 topic echo /mission/state
ros2 topic echo /cmd_vel
```

### Start monitora terminalowego

```bash
cd ros2_ws
source install/setup.bash
ros2 run g1_light_tracking tui_monitor_node
```

Najważniejsza zasada operacyjna:
**robot ma działać autonomicznie, ale człowiek przez SSH ma zawsze rozumieć, co robot robi, dlaczego to robi i czego mu brakuje.**
