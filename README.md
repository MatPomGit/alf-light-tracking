# alf-light-tracking

`alf-light-tracking` to repozytorium z workspace'em ROS 2 i pakietem `g1_light_tracking`. Projekt realizuje warstwowy pipeline do percepcji, lokalizacji 3D, trackingu obiektów, wiązania QR z kartonami oraz logiki misji i sterowania. Po scaleniu repozytoriów zawiera też zachowaną warstwę kompatybilności ze starszym torem legacy opartym o JSON i mosty sprzętowe.

## Zawartość repozytorium

Najważniejsze katalogi od korzenia repo:

- `ros2_ws/` — workspace ROS 2 budowany przez `colcon`.
- `ros2_ws/src/g1_light_tracking/` — właściwy pakiet ROS 2.
- `ros2_ws/src/g1_light_tracking/g1_light_tracking/` — implementacja pythonowa node'ów, utils i wariantu standalone.
- `ros2_ws/src/g1_light_tracking/launch/` — launchery ROS 2.
- `ros2_ws/src/g1_light_tracking/config/` — konfiguracje YAML.
- `ros2_ws/src/g1_light_tracking/msg/` — własne wiadomości ROS 2.
- `ros2_ws/src/g1_light_tracking/docs/` — dokumentacja HTML i architektura.
- `install_git_hooks.sh` — instalacja hooka wersjonującego z poziomu katalogu głównego repo.

## Architektura w skrócie

Domyślny nowoczesny pipeline działa w następującej kolejności:

1. `perception_node` publikuje `Detection2D` na podstawie obrazu.
2. `localization_node` estymuje pozycję 3D i publikuje `LocalizedTarget`.
3. `tracking_node` stabilizuje tożsamość obiektów i publikuje `TrackedTarget`.
4. `parcel_track_node` wiąże QR z kartonem i buduje `ParcelTrack`.
5. `mission_node` wybiera aktywny cel i publikuje `MissionState` oraz `MissionTarget`.
6. `control_node` zamienia wynik misji na komendy ruchu.
7. `depth_mapper_node` i `visual_slam_node` rozszerzają system o warstwę głębi i VO/SLAM.

W repo pozostaje też tor legacy:

- `light_spot_detector_node` publikuje stare detekcje JSON,
- `legacy_detection_adapter_node` tłumaczy je na nowe wiadomości,
- opcjonalne bridge'e obsługują Unitree i turtlesim,
- `unified_system.launch.py` pozwala uruchomić całość w trybie `modern`, `legacy` albo `hybrid`.

## Wymagania

Minimalnie potrzebujesz:

- ROS 2 z `colcon`,
- Python 3,
- pakiety zależne z `package.xml`,
- biblioteki pythonowe z plików `requirements-ros-python.txt` i opcjonalnie `requirements-standalone.txt`,
- `libzbar0` dla QR,
- opcjonalnie `pyrealsense2` dla kamery D435i,
- opcjonalnie środowisko Unitree dla bridge'y sprzętowych.

## Instalacja i build

Uruchamiaj polecenia od katalogu głównego repozytorium:

```bash
cd ros2_ws
colcon build --packages-select g1_light_tracking
source install/setup.bash
```

Jeżeli chcesz zbudować cały workspace bez ograniczania do jednego pakietu:

```bash
cd ros2_ws
colcon build
source install/setup.bash
```

Instalacja zależności pythonowych dla części standalone i narzędzi pomocniczych:

```bash
cd ros2_ws/src/g1_light_tracking
python3 -m pip install -r requirements-ros-python.txt
python3 -m pip install -r requirements-standalone.txt
sudo apt install libzbar0
```

Dodatkowe zależności kompatybilności legacy:

```bash
cd ros2_ws/src/g1_light_tracking
python3 -m pip install -r requirements-compat.txt
```

## Główne sposoby uruchamiania

Wszystkie poniższe polecenia zakładają, że jesteś w katalogu `ros2_ws/` i wykonałeś wcześniej:

```bash
source install/setup.bash
```

### 1. Domyślny pipeline nowoczesny

```bash
ros2 launch g1_light_tracking prod.launch.py
```

Uruchamia:

- `perception_node`
- `localization_node`
- `visual_slam_node`
- `tracking_node`
- `parcel_track_node`
- `depth_mapper_node`
- `mission_node`
- `control_node`
- `debug_node`

### 2. Launcher zunifikowany

To jest teraz główny punkt wejścia do przełączania trybów pracy:

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

Znaczenie trybów:

- `modern` — pełny aktualny pipeline ROS 2.
- `legacy` — stary detektor światła + adapter + nowy `mission_node` i `control_node`.
- `hybrid` — nowy pipeline plus legacy źródło detekcji 2D, bez dublowania tracków.

### 3. Legacy stack

Pełna ścieżka legacy z bridge'ami, jeśli środowisko je obsługuje:

```bash
ros2 launch g1_light_tracking legacy_light_tracking_stack.launch.py
```

### 4. Legacy turtlesim / CSV replay

Do demonstracji bez fizycznego robota i bez kamery:

```bash
ros2 launch g1_light_tracking legacy_light_tracking_turtlesim.launch.py csv_file:=/pelna/sciezka/do/detekcji.csv
```

Dodatkowe argumenty:

```bash
ros2 launch g1_light_tracking legacy_light_tracking_turtlesim.launch.py \
  csv_file:=/pelna/sciezka/do/detekcji.csv \
  playback_rate:=1.0 \
  loop:=true
```

### 5. Bridge legacy JSON do nowej warstwy misji

```bash
ros2 launch g1_light_tracking legacy_modern_mission_bridge.launch.py
```

Ten launcher uruchamia tylko minimalną ścieżkę łączącą stary detektor z nowym `mission_node` i `control_node`.

### 6. Diagnostyka top-down

```bash
ros2 launch g1_light_tracking topdown_odom.launch.py
```

## Tryb standalone

Polecenia wykonuj z katalogu pakietu `ros2_ws/src/g1_light_tracking/`.

### Standalone CLI

```bash
python3 -m g1_light_tracking.standalone.cli_app --camera 0 --model yolov8n.pt --profile full_logistics
```

Przykład z limitem klatek:

```bash
python3 -m g1_light_tracking.standalone.cli_app \
  --camera 0 \
  --model yolov8n.pt \
  --profile debug_perception \
  --max-frames 300 \
  --show-every 15
```

### Standalone GUI

```bash
python3 -m g1_light_tracking.standalone.gui_app --camera 0 --model yolov8n.pt --profile debug_perception
```

## Testy

Polecenia wykonuj z katalogu pakietu `ros2_ws/src/g1_light_tracking/`.

```bash
pytest
```

Jeżeli chcesz uruchomić pojedynczy plik testowy:

```bash
pytest test/test_legacy_adapter.py
pytest test/test_tracking_logic.py
```

## Jak repozytoria zostały scalone

Scalenie wykonano tak, aby aktualny pakiet pozostał bazą docelową, a starszy projekt został dołączony jako warstwa kompatybilności. Oznacza to w praktyce:

- nowoczesne node'y i własne wiadomości ROS 2 nie zostały zastąpione,
- komponenty legacy zostały dodane obok jako osobne entrypointy i launchery,
- konfiguracje starszego stosu otrzymały osobne pliki `legacy_*.yaml`,
- adapter `legacy_detection_adapter_node` tłumaczy historyczny JSON na aktualne wiadomości `Detection2D` i opcjonalnie `TrackedTarget`,
- `launch/unified_system.launch.py` spina oba światy w jednym punkcie wejścia.

Taki sposób scalenia minimalizuje ryzyko regresji i pozwala stopniowo wygaszać starszy tor bez utraty działających funkcjonalności.

## Dalsze kroki do pełnej migracji na aktualne repozytorium

1. Zmienić wszystkie nowe integracje tak, aby publikowały bezpośrednio `Detection2D`, `LocalizedTarget` albo inne aktualne wiadomości ROS 2, bez pośredniego JSON.
2. Ograniczyć publikację `/tracking/targets` do `tracking_node`, a legacy traktować tylko jako dodatkowe źródło wejścia 2D.
3. Przenieść potrzebne heurystyki ze starego detektora światła do `perception_node`, tak aby utrzymać jedną warstwę percepcji.
4. Ujednolicić bridge'e sprzętowe tak, aby publikowały dokładnie te topiki i typy wiadomości, których oczekuje obecny pipeline.
5. Dodać testy integracyjne launch oraz smoke-test `colcon build` dla trybów `modern`, `legacy` i `hybrid`.
6. Oznaczyć node'y legacy jako przestarzałe dopiero wtedy, gdy nowy pipeline przejmie ich pełną funkcję operacyjną.

## Dokumentacja

Najważniejsze pliki dokumentacyjne:

- `ros2_ws/README.md` — build i uruchamianie workspace'u,
- `ros2_ws/src/g1_light_tracking/README.md` — szczegółowy opis pakietu,
- `ros2_ws/src/g1_light_tracking/docs/index.html` — dokumentacja HTML,
- `ros2_ws/src/g1_light_tracking/docs/architecture.md` — dokładniejszy opis architektury.

## Hook wersjonowania

Z katalogu głównego repozytorium:

```bash
bash install_git_hooks.sh
```

Alternatywnie z katalogu `ros2_ws/`:

```bash
bash install_git_hooks.sh
```

Alternatywnie z katalogu pakietu:

```bash
bash scripts/install_git_hooks.sh
```

Każdy z tych wariantów instaluje hook `pre-commit`, który uruchamia `scripts/version_bump.py` i aktualizuje pliki:

- `VERSION`
- `setup.py`
- `package.xml`

## Gdzie szukać czego

- node'y ROS 2: `ros2_ws/src/g1_light_tracking/g1_light_tracking/nodes/`
- node'y legacy / bridge: `ros2_ws/src/g1_light_tracking/g1_light_tracking/`
- utils i logika algorytmiczna: `ros2_ws/src/g1_light_tracking/g1_light_tracking/utils/`
- vision / detektory: `ros2_ws/src/g1_light_tracking/g1_light_tracking/vision/`
- launchery: `ros2_ws/src/g1_light_tracking/launch/`
- konfiguracje: `ros2_ws/src/g1_light_tracking/config/`
- profile standalone: `ros2_ws/src/g1_light_tracking/profiles/`
## Stan repo po ostatnich poprawkach

Aktualna wersja repo zawiera już poprawki po przeglądzie błędów zgłoszonych dla warstwy lokalizacji i integracji legacy/modern. W praktyce oznacza to między innymi:

- poprawione wywołania helperów geometrycznych w `localization_node`,
- poprawne mapowanie narożników z `Detection2D.image_points`,
- spójne ustawianie `track_id` w `ParcelTrack`,
- ujednolicony typ macierzy kamery w `depth_mapper_node`,
- uporządkowaną dokumentację uruchomienia i integracji warstwy legacy.

Repo jest obecnie przygotowane tak, aby:
- uruchamiać nowoczesny pipeline bez warstwy legacy,
- uruchamiać tor legacy z adapterem do nowych wiadomości,
- pracować w trybie hybrydowym podczas migracji.

## Najczęściej używane polecenia

Polecenia uruchamiaj od katalogu głównego repozytorium:

```bash
cd ros2_ws
colcon build --packages-select g1_light_tracking
source install/setup.bash
```

Uruchomienie głównych wariantów systemu:

```bash
# nowoczesny pipeline
cd ros2_ws
source install/setup.bash
ros2 launch g1_light_tracking unified_system.launch.py mode:=modern

# legacy z nową misją i sterowaniem
cd ros2_ws
source install/setup.bash
ros2 launch g1_light_tracking unified_system.launch.py mode:=legacy

# tryb hybrydowy do migracji
cd ros2_ws
source install/setup.bash
ros2 launch g1_light_tracking unified_system.launch.py mode:=hybrid with_legacy_camera:=true
```

Dodatkowe launchery pomocnicze:

```bash
# oryginalny launcher produkcyjny nowego pipeline'u
cd ros2_ws
source install/setup.bash
ros2 launch g1_light_tracking prod.launch.py

# zachowany pełny stack legacy
cd ros2_ws
source install/setup.bash
ros2 launch g1_light_tracking legacy_light_tracking_stack.launch.py

# minimalny most legacy -> mission/control
cd ros2_ws
source install/setup.bash
ros2 launch g1_light_tracking legacy_modern_mission_bridge.launch.py
```

## Szybka weryfikacja po zmianach

```bash
cd ros2_ws
source install/setup.bash
python3 -m pytest src/g1_light_tracking/test -v
```

Jeżeli środowisko zawiera pełną instalację ROS 2 i zależności pakietu, można dodatkowo wykonać:

```bash
cd ros2_ws
colcon build --packages-select g1_light_tracking
source install/setup.bash
ros2 launch g1_light_tracking unified_system.launch.py mode:=modern
```
