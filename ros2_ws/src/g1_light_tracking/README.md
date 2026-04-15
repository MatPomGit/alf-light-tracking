# g1_light_tracking

`g1_light_tracking` to pakiet ROS 2 łączący percepcję obrazu, lokalizację 3D, tracking, logikę domenową przesyłek i sterowanie. Pakiet zawiera także warstwę kompatybilności legacy oraz zunifikowany launcher przełączający tryby `modern`, `legacy` i `hybrid`.

## Rola pakietu

Pakiet rozdziela odpowiedzialność na kolejne etapy przetwarzania:

1. wykrycie obiektu w obrazie,
2. estymacja jego położenia 3D,
3. utrzymanie tożsamości w czasie,
4. powiązanie danych logistycznych,
5. wybór celu misji,
6. wygenerowanie komendy sterowania.

Taki podział ułatwia:
- debugowanie,
- wymianę pojedynczych modułów,
- integrację źródeł legacy z nowym przepływem danych,
- stopniową migrację bez wyłączania działających komponentów.

## Struktura pakietu

Od katalogu `ros2_ws/src/g1_light_tracking/`:

```text
.
├── CMakeLists.txt
├── package.xml
├── setup.py
├── setup.cfg
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
├── test/
├── requirements-ros-python.txt
├── requirements-standalone.txt
└── requirements-compat.txt
```

## Najważniejsze node'y nowoczesnego pipeline'u

### `perception_node`

Wejście:
- obraz RGB,
- parametry konfiguracji detekcji.

Wyjście:
- `/perception/detections` jako `Detection2D`.

Rola:
- wykrywanie obiektów 2D,
- odczyt QR,
- wykrywanie AprilTagów,
- wykrywanie plamki światła,
- dostarczanie wspólnego kontraktu wejściowego dla dalszych modułów.

### `localization_node`

Wejście:
- `/perception/detections`,
- opcjonalnie dane głębi,
- kalibracja kamery.

Wyjście:
- `/localization/targets` jako `LocalizedTarget`.

Rola:
- przejście z reprezentacji 2D do 3D,
- estymacja XYZ,
- wybór i oznaczenie metody lokalizacji,
- wykorzystanie geometrii kamery, głębi lub PnP.

### `tracking_node`

Wejście:
- `/localization/targets`,
- opcjonalnie źródła debug i kompensacji ruchu.

Wyjście:
- `/tracking/targets` jako `TrackedTarget`,
- `/tracking/global_motion_debug`.

Rola:
- asocjacja między klatkami,
- filtr Kalmana,
- global motion compensation,
- tłumienie false positives i stabilizacja identyfikatorów.

### `parcel_track_node`

Wejście:
- `/tracking/targets`.

Wyjście:
- `/tracking/parcel_bindings`,
- `/tracking/parcel_tracks`.

Rola:
- wiązanie QR z kartonami,
- budowa logicznego obiektu przesyłki,
- publikacja danych domenowych używanych później przez misję.

### `mission_node`

Wejście:
- `/tracking/targets`,
- `/tracking/parcel_tracks`.

Wyjście:
- `/mission/state`,
- `/mission/target`,
- `/mission/parcel_info`.

Rola:
- wybór aktywnego celu,
- zarządzanie stanem zadania,
- publikacja informacji domenowych dla sterowania i nadzoru.

### `control_node`

Wejście:
- `/mission/target`,
- opcjonalnie `/navigation/depth_hint`.

Wyjście:
- komendy ruchu, np. `Twist`.

Rola:
- referencyjne sterowanie ruchem robota na podstawie celu misji,
- ograniczanie ruchu do przodu przy zagrożeniach z warstwy głębi.

### `depth_mapper_node`

Rola:
- analiza mapy głębi,
- budowa lokalnych wskazówek bezpieczeństwa,
- publikacja `DepthNavHint`.

### `visual_slam_node`

Rola:
- eksperymentalna estymacja ruchu z obrazu,
- publikacja odometrii i ścieżki do diagnostyki.

## Node'y warstwy legacy i kompatybilności

Po scaleniu repozytoriów pakiet zawiera także dodatkowe komponenty:

- `d435i_node`
- `light_spot_detector_node`
- `g1_light_follower_node`
- `unitree_cmd_vel_bridge_node`
- `arm_skill_bridge_node`
- `csv_detection_replay_node`
- `turtlesim_cmd_vel_bridge_node`
- `legacy_detection_adapter_node`

### `legacy_detection_adapter_node`

To kluczowy element łączenia starego i nowego świata.

Wejście:
- `/light_tracking/detection_json`

Wyjście:
- `/perception/detections`
- opcjonalnie `/tracking/targets`

Rola:
- translacja legacy JSON do aktualnego kontraktu wiadomości,
- umożliwienie wykorzystania nowej warstwy misji i sterowania bez natychmiastowego przepisywania całej percepcji legacy.

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

## Build i aktywacja środowiska

Build wykonuj z katalogu `ros2_ws/`, nie z katalogu pakietu.

```bash
cd ros2_ws
colcon build --packages-select g1_light_tracking
source install/setup.bash
```

Jeżeli wcześniej pojawił się konflikt targetów CMake, wykonaj pełne czyszczenie:

```bash
cd ros2_ws
rm -rf build install log
colcon build --packages-select g1_light_tracking
source install/setup.bash
```

## Przykłady uruchomienia

### Główny launcher zunifikowany

```bash
cd ros2_ws
source install/setup.bash
ros2 launch g1_light_tracking unified_system.launch.py mode:=modern
```

### Pozostałe tryby launchera unified

```bash
cd ros2_ws
source install/setup.bash
ros2 launch g1_light_tracking unified_system.launch.py mode:=legacy

cd ros2_ws
source install/setup.bash
ros2 launch g1_light_tracking unified_system.launch.py mode:=hybrid

cd ros2_ws
source install/setup.bash
ros2 launch g1_light_tracking unified_system.launch.py mode:=hybrid with_legacy_camera:=true

cd ros2_ws
source install/setup.bash
ros2 launch g1_light_tracking unified_system.launch.py mode:=legacy with_unitree_bridges:=true
```

### Inne launchery

```bash
cd ros2_ws
source install/setup.bash
ros2 launch g1_light_tracking prod.launch.py

cd ros2_ws
source install/setup.bash
ros2 launch g1_light_tracking legacy_light_tracking_stack.launch.py

cd ros2_ws
source install/setup.bash
ros2 launch g1_light_tracking legacy_light_tracking_turtlesim.launch.py csv_file:=/pelna/sciezka/do/detekcji.csv playback_rate:=1.0 loop:=true

cd ros2_ws
source install/setup.bash
ros2 launch g1_light_tracking legacy_modern_mission_bridge.launch.py

cd ros2_ws
source install/setup.bash
ros2 launch g1_light_tracking topdown_odom.launch.py
```

## Testy

Zalecana forma uruchomienia:

```bash
cd ros2_ws
source install/setup.bash
python3 -m pytest src/g1_light_tracking/test -v
```

## Stan pakietu po ostatnich poprawkach

Pakiet został doprowadzony do stanu, w którym:
- tor `modern` pozostaje bazą docelową,
- komponenty `legacy` działają jako warstwa kompatybilności,
- poprawiono wywołania funkcji geometrycznych w `localization_node`,
- poprawiono mapowanie `Detection2D.image_points`,
- dopisano brakujący `track_id` w `parcel_track_node`,
- ujednolicono precyzję `CameraInfo.k` w `depth_mapper_node`,
- usunięto konflikt builda CMake dla pakietu łączącego interfejsy ROS i kod Pythona.

## Dalszy kierunek migracji

Docelowy kierunek pozostaje bez zmian: pełne przejście na aktualny pipeline z wiadomościami:
- `Detection2D`,
- `LocalizedTarget`,
- `TrackedTarget`,
- `ParcelTrack`.

Warstwa legacy powinna być stopniowo ograniczana do:
- źródeł testowych,
- replayu danych historycznych,
- mostów wymaganych tylko przez wybrane środowiska demonstracyjne lub sprzętowe.
