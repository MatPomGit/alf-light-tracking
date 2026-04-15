# ros2_ws

`ros2_ws` jest workspace’em ROS 2 używanym do budowania i uruchamiania pakietu `g1_light_tracking`.

W praktyce jest to cienka warstwa organizacyjna nad samym pakietem. Zawiera standardowy układ katalogów dla `colcon`, umożliwia budowanie wiadomości ROS 2 i instalację skryptów wykonywalnych, a po `source install/setup.bash` udostępnia launchery oraz node’y jako normalne elementy środowiska ROS.

## Struktura

- `src/g1_light_tracking/` — kod źródłowy pakietu.
- `install/`, `build/`, `log/` — katalogi generowane po budowaniu workspace, niewersjonowane.

## Budowanie

```bash
cd ros2_ws
colcon build
```

Jeżeli budujesz tylko ten pakiet w większym środowisku, możesz ograniczyć build do niego:

```bash
colcon build --packages-select g1_light_tracking
```

## Aktywacja środowiska

```bash
cd ros2_ws
source install/setup.bash
```

To polecenie musi zostać wykonane w każdej nowej sesji terminala przed uruchamianiem `ros2 launch` albo `ros2 run`.

## Uruchomienie

Standardowy launcher produkcyjno-demonstracyjny:

```bash
ros2 launch g1_light_tracking prod.launch.py
```

Launcher diagnostyczny dla podglądu odometrii z góry:

```bash
ros2 launch g1_light_tracking topdown_odom.launch.py
```

## Dokumentacja

Dokumentacja HTML znajduje się w:
- `src/g1_light_tracking/docs/index.html`

Dodatkowo opis architektury i modułów znajdziesz w:
- `src/g1_light_tracking/docs/architecture.md`
- `src/g1_light_tracking/README.md`
