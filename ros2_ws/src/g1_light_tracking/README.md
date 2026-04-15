# g1_light_tracking

`g1_light_tracking` to pakiet ROS 2 łączący percepcję obrazu, lokalizację 3D, tracking, logikę domenową przesyłek i sterowanie. Po ostatnich zmianach zawiera również warstwę kompatybilności legacy oraz zunifikowany launcher przełączający tryby `modern`, `legacy` i `hybrid`.

## Co robi pakiet

Pakiet rozdziela odpowiedzialność na kilka etapów:

1. wykrycie obiektu w obrazie,
2. estymacja jego położenia 3D,
3. utrzymanie tożsamości w czasie,
4. powiązanie danych logistycznych,
5. wybór celu misji,
6. wygenerowanie uproszczonej komendy sterowania.

Taki układ upraszcza debugowanie i integrację. Można podmienić źródło detekcji, zostawiając bez zmian tracking, albo podłączyć inny kontroler, zachowując resztę pipeline'u.

## Struktura pakietu

Od katalogu `ros2_ws/src/g1_light_tracking/`:

```text
.
├── CMakeLists.txt
├── package.xml
├── setup.py
├── VERSION
├── config/
├── docs/
├── g1_light_tracking/
│   ├── nodes/
│   ├── standalone/
│   ├── utils/
│   └── vision/
├── launch/
├── msg/
├── profiles/
├── scripts/
└── test/
```

## Najważniejsze node'y nowoczesnego pipeline'u

### `perception_node`

Wejście:

- `sensor_msgs/Image` z kamery RGB

Wyjście:

- `/perception/detections` jako `Detection2D`

Rola:

- wykrywanie obiektów 2D,
- odczyt QR,
- wykrywanie AprilTagów,
- wykrywanie plamki światła.

### `localization_node`

Wejście:

- `/perception/detections`
- opcjonalnie dane głębi

Wyjście:

- `/localization/targets` jako `LocalizedTarget`

Rola:

- przejście z 2D do 3D,
- estymacja XYZ,
- oznaczenie metody lokalizacji.

### `tracking_node`

Wejście:

- `/localization/targets`
- opcjonalnie źródła debug / kalibracja ruchu

Wyjście:

- `/tracking/targets` jako `TrackedTarget`
- `/tracking/global_motion_debug`

Rola:

- asocjacja między klatkami,
- filtr Kalmana,
- global motion compensation,
- ograniczanie false positives.

### `parcel_track_node`

Wejście:

- `/tracking/targets`

Wyjście:

- `/tracking/parcel_bindings`
- `/tracking/parcel_tracks`

Rola:

- wiązanie QR z kartonami,
- budowa logicznego obiektu przesyłki.

### `mission_node`

Wejście:

- `/tracking/targets`
- `/tracking/parcel_tracks`

Wyjście:

- `/mission/state`
- `/mission/target`
- `/mission/parcel_info`

Rola:

- wybór aktywnego celu,
- zarządzanie stanem zadania,
- publikacja informacji domenowych.

### `control_node`

Wejście:

- `/mission/target`
- opcjonalnie `/navigation/depth_hint`

Wyjście:

- komendy ruchu typu `Twist`

Rola:

- referencyjne sterowanie robota na podstawie celu misji,
- ograniczanie ruchu do przodu przy sygnałach z głębi.

### `depth_mapper_node`

Rola:

- analiza obrazu głębi,
- budowa lokalnych wskazówek bezpieczeństwa,
- publikacja `DepthNavHint`.

### `visual_slam_node`

Rola:

- eksperymentalna estymacja ruchu z obrazu,
- publikacja odometrii i ścieżki dla diagnostyki / top-down.

## Node'y warstwy legacy i kompatybilności

Po scaleniu repozytoriów w pakiecie są też dodatkowe komponenty:

- `d435i_node`
- `light_spot_detector_node`
- `g1_light_follower_node`
- `unitree_cmd_vel_bridge_node`
- `arm_skill_bridge_node`
- `csv_detection_replay_node`
- `turtlesim_cmd_vel_bridge_node`
- `legacy_detection_adapter_node`

### `legacy_detection_adapter_node`

To kluczowy element łączenia starego i nowego świata. Czyta legacy JSON z topicu:

- `/light_tracking/detection_json`

I publikuje nowe wiadomości na:

- `/perception/detections`
- opcjonalnie `/tracking/targets`

Dzięki temu można uruchomić starą ścieżkę percepcji i zasilać aktualny pipeline misji oraz sterowania bez przepisywania wszystkiego naraz.

## Własne wiadomości ROS 2

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

Pliki znajdują się w katalogu `msg/`.

## Konfiguracje

Najważniejsze pliki w `config/`:

- `perception.yaml`
- `localization.yaml`
- `tracking.yaml`
- `parcel_track.yaml`
- `mission.yaml`
- `control.yaml`
- `depth_mapper.yaml`
- `visual_slam.yaml`
- `camera_calibration.yaml`
- `topdown_odom.yaml`

Pliki legacy:

- `legacy_adapter.yaml`
- `legacy_bridge.yaml`
- `legacy_light_control.yaml`
- `legacy_light_perception.yaml`

## Launchery

Wszystkie ścieżki poniżej są względem katalogu pakietu i odpowiadają rzeczywistym plikom w `launch/`.

### `launch/prod.launch.py`

Pełny nowoczesny pipeline:

```bash
cd ros2_ws
source install/setup.bash
ros2 launch g1_light_tracking prod.launch.py
```

### `launch/unified_system.launch.py`

Główny zunifikowany punkt wejścia:

```bash
cd ros2_ws
source install/setup.bash
ros2 launch g1_light_tracking unified_system.launch.py mode:=modern
```

Przykłady uruchomienia:

```bash
cd ros2_ws
source install/setup.bash
ros2 launch g1_light_tracking unified_system.launch.py mode:=modern
ros2 launch g1_light_tracking unified_system.launch.py mode:=legacy
ros2 launch g1_light_tracking unified_system.launch.py mode:=hybrid
ros2 launch g1_light_tracking unified_system.launch.py mode:=hybrid with_legacy_camera:=true
ros2 launch g1_light_tracking unified_system.launch.py mode:=legacy with_unitree_bridges:=true
```

### `launch/legacy_light_tracking_stack.launch.py`

Pełen zestaw legacy:

```bash
cd ros2_ws
source install/setup.bash
ros2 launch g1_light_tracking legacy_light_tracking_stack.launch.py
```

### `launch/legacy_light_tracking_turtlesim.launch.py`

Wariant demonstracyjny z CSV replay i turtlesim:

```bash
cd ros2_ws
source install/setup.bash
ros2 launch g1_light_tracking legacy_light_tracking_turtlesim.launch.py csv_file:=/pelna/sciezka/do/detekcji.csv
```

Przykład z dodatkowymi parametrami:

```bash
cd ros2_ws
source install/setup.bash
ros2 launch g1_light_tracking legacy_light_tracking_turtlesim.launch.py \
  csv_file:=/pelna/sciezka/do/detekcji.csv \
  playback_rate:=2.0 \
  loop:=false
```

### `launch/legacy_modern_mission_bridge.launch.py`

Minimalne połączenie starej percepcji z nową misją i sterowaniem:

```bash
cd ros2_ws
source install/setup.bash
ros2 launch g1_light_tracking legacy_modern_mission_bridge.launch.py
```

### `launch/topdown_odom.launch.py`

Diagnostyka odometrii i wizualizacja top-down:

```bash
cd ros2_ws
source install/setup.bash
ros2 launch g1_light_tracking topdown_odom.launch.py
```

## Standalone

Polecenia standalone wykonuj z katalogu pakietu `ros2_ws/src/g1_light_tracking/`.

### CLI

```bash
python3 -m g1_light_tracking.standalone.cli_app --camera 0 --model yolov8n.pt --profile full_logistics
```

### GUI

```bash
python3 -m g1_light_tracking.standalone.gui_app --camera 0 --model yolov8n.pt --profile debug_perception
```

Dostępne profile znajdują się w katalogu `profiles/`:

- `full_logistics.json`
- `debug_perception.json`
- `light_only.json`
- `marker_only.json`
- `qr_only.json`

## Instalacja zależności pythonowych

Z katalogu pakietu:

```bash
python3 -m pip install -r requirements-ros-python.txt
python3 -m pip install -r requirements-standalone.txt
python3 -m pip install -r requirements-compat.txt
```

Dodatkowo:

```bash
sudo apt install libzbar0
```

## Testy

Z katalogu pakietu:

```bash
pytest
```

Przykłady:

```bash
pytest test/test_association.py
pytest test/test_kalman_tracking.py
pytest test/test_legacy_adapter.py
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

## Hook wersjonowania

Wariant lokalny z katalogu pakietu:

```bash
bash scripts/install_git_hooks.sh
```

Skrypt instaluje `pre-commit`, który aktualizuje:

- `VERSION`
- `setup.py`
- `package.xml`

## Gdzie czytać dalej

- `docs/index.html` — dokumentacja HTML,
- `docs/architecture.md` — szerszy opis przepływu danych,
- docstringi w `g1_light_tracking/nodes/`, `g1_light_tracking/utils/` i `g1_light_tracking/vision/`.
## Stan pakietu po ostatnich poprawkach

Pakiet został doprowadzony do stanu, w którym obecny tor `modern` pozostaje bazą docelową, a komponenty legacy działają jako warstwa kompatybilności i etap migracyjny. Ostatnie poprawki objęły głównie:

- korekty wywołań funkcji geometrycznych w `nodes/localization_node.py`,
- poprawne wykorzystanie `Detection2D.image_points` do PnP,
- dopisanie brakującego `track_id` w `nodes/parcel_track_node.py`,
- ujednolicenie precyzji `CameraInfo.k` w `nodes/depth_mapper_node.py`,
- dalsze uporządkowanie dokumentacji i ścieżek uruchomieniowych.

## Przykłady uruchomienia

Wszystkie poniższe polecenia zakładają, że pracujesz z katalogu głównego workspace'u `ros2_ws/`.

### Build i aktywacja środowiska

```bash
cd ros2_ws
colcon build --packages-select g1_light_tracking
source install/setup.bash
```

### Główny launcher zunifikowany

```bash
# tryb nowoczesny
cd ros2_ws
source install/setup.bash
ros2 launch g1_light_tracking unified_system.launch.py mode:=modern

# tryb legacy
cd ros2_ws
source install/setup.bash
ros2 launch g1_light_tracking unified_system.launch.py mode:=legacy

# tryb hybrydowy
cd ros2_ws
source install/setup.bash
ros2 launch g1_light_tracking unified_system.launch.py mode:=hybrid with_legacy_camera:=true
```

### Pozostałe użyteczne launchery

```bash
# klasyczny nowy pipeline
cd ros2_ws
source install/setup.bash
ros2 launch g1_light_tracking prod.launch.py

# pełny zachowany stack legacy
cd ros2_ws
source install/setup.bash
ros2 launch g1_light_tracking legacy_light_tracking_stack.launch.py

# replay CSV w turtlesim
cd ros2_ws
source install/setup.bash
ros2 launch g1_light_tracking legacy_light_tracking_turtlesim.launch.py csv_file:=/pelna/sciezka/do/detekcji.csv playback_rate:=1.0 loop:=true

# most legacy do nowej misji i sterowania
cd ros2_ws
source install/setup.bash
ros2 launch g1_light_tracking legacy_modern_mission_bridge.launch.py
```

## Dalszy kierunek migracji

Docelowy kierunek pozostaje bez zmian: pełne przejście na aktualny pipeline z wiadomościami `Detection2D`, `LocalizedTarget`, `TrackedTarget` i `ParcelTrack`. Warstwa legacy powinna być stopniowo ograniczana do:
- źródeł testowych,
- replayu danych historycznych,
- mostów wymaganych tylko przez specyficzny sprzęt lub środowiska demonstracyjne.
