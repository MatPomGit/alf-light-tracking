# alf-light-tracking

Repozytorium zawiera workspace ROS 2 z pakietem `g1_light_tracking`, który implementuje eksperymentalny pipeline do percepcji, lokalizacji 3D, trackingu obiektów, wiązania QR z kartonami oraz prostej logiki misji i sterowania robota.

Projekt jest zorganizowany warstwowo. Najpierw obraz jest analizowany w pikselach, potem detekcje są lokalizowane w 3D, następnie utrzymywane jako stabilne tracki, a dopiero na końcu zamieniane na pojęcia domenowe, takie jak „konkretna przesyłka” albo „aktywny cel misji”. Dzięki temu można osobno stroić percepcję, tracking i logikę zadania.

## Co znajduje się w repo

- `ros2_ws/` — workspace ROS 2.
- `ros2_ws/src/g1_light_tracking/` — właściwy pakiet źródłowy.
- `ros2_ws/src/g1_light_tracking/config/` — parametry node’ów.
- `ros2_ws/src/g1_light_tracking/launch/` — gotowe launchery.
- `ros2_ws/src/g1_light_tracking/msg/` — własne typy wiadomości ROS 2.
- `ros2_ws/src/g1_light_tracking/docs/` — dokumentacja statyczna oraz dodatkowe opisy.

## Jak działa pipeline

Najkrótszy opis przepływu danych wygląda tak:

1. `perception_node` wykrywa obiekty 2D, kody QR, AprilTagi i plamkę światła.
2. `localization_node` nadaje tym obserwacjom pozycję 3D.
3. `tracking_node` stabilizuje tożsamość obiektów między klatkami.
4. `parcel_track_node` wiąże QR z kartonem i buduje stan przesyłki.
5. `mission_node` wybiera cel i publikuje stan logiki zadania.
6. `control_node` zamienia cel misji na uproszczone komendy ruchu.
7. `depth_mapper_node` może dodatkowo korygować sterowanie na podstawie głębi.

Szczegółowy opis architektury jest w `ros2_ws/src/g1_light_tracking/docs/architecture.md`.

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

Testy obejmują głównie logikę pomocniczą: tracking, asocjację, reguły wiązania oraz walidację schematów danych. Nie zastępują jeszcze pełnych testów integracyjnych ROS 2.

## Gdzie szukać dokumentacji

- `ros2_ws/README.md` — opis workspace i budowania.
- `ros2_ws/src/g1_light_tracking/README.md` — główny opis pakietu.
- `ros2_ws/src/g1_light_tracking/docs/architecture.md` — architektura, odpowiedzialności modułów i przepływ danych.
- docstringi w `g1_light_tracking/nodes/` oraz `g1_light_tracking/utils/` — opis roli kodu bezpośrednio przy implementacji.

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


## Scalony wariant kompatybilności

Repo zawiera teraz także zachowaną warstwę kompatybilności ze starszym projektem `j2s-light_tracking-ros2-g1-ros2-light-tracking`.
Starszy pipeline nie zastępuje obecnych node’ów. Został dołożony obok nich jako osobny zestaw komponentów:

- legacy launcher: `ros2 launch g1_light_tracking legacy_light_tracking_stack.launch.py`
- turtlesim / CSV replay: `ros2 launch g1_light_tracking legacy_light_tracking_turtlesim.launch.py csv_file:=<plik.csv>`
- legacy node’y: `d435i_node`, `light_spot_detector_node`, `g1_light_follower_node`, `unitree_cmd_vel_bridge_node`, `arm_skill_bridge_node`, `csv_detection_replay_node`, `turtlesim_cmd_vel_bridge_node`
- konfiguracje legacy: `config/legacy_light_perception.yaml`, `config/legacy_light_control.yaml`, `config/legacy_bridge.yaml`

Podejście jest celowo zachowawcze: nowy pipeline ROS 2 pozostaje bazą docelową, a starszy projekt służy jako warstwa integracyjna, adaptery sprzętowe i środowisko demonstracyjne.
