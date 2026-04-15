# ros2_ws

`ros2_ws/` jest workspace'em ROS 2 dla pakietu `g1_light_tracking`. To właśnie z tego katalogu należy wykonywać:
- `colcon build`,
- aktywację środowiska przez `source install/setup.bash`,
- uruchamianie launcherów ROS 2.

## Struktura workspace'u

Najważniejsze katalogi w `ros2_ws/`:

- `src/` — źródła pakietów ROS 2,
- `src/g1_light_tracking/` — źródła pakietu `g1_light_tracking`,
- `build/` — artefakty kompilacji generowane przez `colcon`,
- `install/` — wynik instalacji workspace'u,
- `log/` — logi builda i konfiguracji.

Najważniejsze katalogi wewnątrz pakietu:

- `src/g1_light_tracking/launch/`
- `src/g1_light_tracking/config/`
- `src/g1_light_tracking/msg/`
- `src/g1_light_tracking/docs/`
- `src/g1_light_tracking/test/`

## Kanoniczny build

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

## Ważne: czyszczenie artefaktów po konflikcie CMake

W tej wersji repo poprawiono konflikt targetów `ament_cmake_python`, który mógł objawiać się błędami:

- `ament_cmake_python_copy_g1_light_tracking already exists`
- `ament_cmake_python_build_g1_light_tracking_egg already exists`

Jeżeli taki build był wykonywany wcześniej na tej samej kopii repo, przed kolejną próbą wykonaj pełne czyszczenie artefaktów:

```bash
cd ros2_ws
rm -rf build install log
colcon build --packages-select g1_light_tracking
source install/setup.bash
```

## Aktywacja środowiska

Po każdym buildzie i w każdej nowej sesji terminala:

```bash
cd ros2_ws
source install/setup.bash
```

## Launchery

Wszystkie polecenia poniżej wykonuj z katalogu `ros2_ws/` po wcześniejszym `source install/setup.bash`.

### Domyślny launcher nowoczesny

```bash
cd ros2_ws
source install/setup.bash
ros2 launch g1_light_tracking prod.launch.py
```

### Launcher zunifikowany

```bash
cd ros2_ws
source install/setup.bash
ros2 launch g1_light_tracking unified_system.launch.py mode:=modern
```

Najczęstsze warianty:

```bash
cd ros2_ws
source install/setup.bash
ros2 launch g1_light_tracking unified_system.launch.py mode:=modern

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

### Pozostałe launchery

```bash
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

Najbardziej precyzyjna i zalecana forma uruchomienia testów:

```bash
cd ros2_ws
source install/setup.bash
python3 -m pytest src/g1_light_tracking/test -v
```

Wariant skrócony z wejściem do katalogu pakietu także może działać, ale nie jest już traktowany jako kanoniczny opis w tej dokumentacji.

## Dokumentacja

Najważniejsze pliki dokumentacyjne:

- `src/g1_light_tracking/README.md`
- `src/g1_light_tracking/docs/index.html`
- `src/g1_light_tracking/docs/architecture.md`

Jeżeli otwierasz dokumentację HTML bezpośrednio z systemu plików, plik wejściowy to:

- `ros2_ws/src/g1_light_tracking/docs/index.html`
