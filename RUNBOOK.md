# RUNBOOK.md

## Cel

Ten dokument jest krótką instrukcją operatorską dla pracy z `alf-light-tracking` na robocie i przez SSH.

Zakłada:

* Ubuntu 22.04
* ROS 2
* pracę w terminalu
* brak monitora i GUI
* główny workspace w `ros2\_ws/`

\---

## 1\. Najszybszy start

### Build pakietu i uruchomienie nowoczesnego pipeline'u

```bash
cd ros2\_ws
colcon build --packages-select g1\_light\_tracking
source install/setup.bash
ros2 launch g1\_light\_tracking unified\_system.launch.py mode:=modern
```

### Uruchomienie produkcyjnego launchera

```bash
cd ros2\_ws
source install/setup.bash
ros2 launch g1\_light\_tracking prod.launch.py
```

\---

## 2\. Najczęstsze warianty uruchomienia

### Modern

```bash
cd ros2\_ws
source install/setup.bash
ros2 launch g1\_light\_tracking unified\_system.launch.py mode:=modern
```

### Legacy

```bash
cd ros2\_ws
source install/setup.bash
ros2 launch g1\_light\_tracking unified\_system.launch.py mode:=legacy
```

### Hybrid

```bash
cd ros2\_ws
source install/setup.bash
ros2 launch g1\_light\_tracking unified\_system.launch.py mode:=hybrid
```

### Hybrid z legacy kamerą

```bash
cd ros2\_ws
source install/setup.bash
ros2 launch g1\_light\_tracking unified\_system.launch.py mode:=hybrid with\_legacy\_camera:=true
```

### Legacy z bridge'ami Unitree

```bash
cd ros2\_ws
source install/setup.bash
ros2 launch g1\_light\_tracking unified\_system.launch.py mode:=legacy with\_unitree\_bridges:=true
```

\---

## 3\. Uruchamianie pojedynczych node'ów

### Kamera D435i

```bash
cd ros2\_ws
source install/setup.bash
ros2 run g1\_light\_tracking d435i\_node
```

### Percepcja

```bash
cd ros2\_ws
source install/setup.bash
ros2 run g1\_light\_tracking perception\_node --ros-args --params-file src/g1\_light\_tracking/config/perception.yaml
```

### Lokalizacja

```bash
cd ros2\_ws
source install/setup.bash
ros2 run g1\_light\_tracking localization\_node --ros-args --params-file src/g1\_light\_tracking/config/localization.yaml
```

### Tracking

```bash
cd ros2\_ws
source install/setup.bash
ros2 run g1\_light\_tracking tracking\_node --ros-args --params-file src/g1\_light\_tracking/config/tracking.yaml
```

### Misja

```bash
cd ros2\_ws
source install/setup.bash
ros2 run g1\_light\_tracking mission\_node --ros-args --params-file src/g1\_light\_tracking/config/mission.yaml
```

### Sterowanie

```bash
cd ros2\_ws
source install/setup.bash
ros2 run g1\_light\_tracking control\_node --ros-args --params-file src/g1\_light\_tracking/config/control.yaml
```

### Debug node

```bash
cd ros2\_ws
source install/setup.bash
ros2 run g1\_light\_tracking debug\_node
```

### TUI monitor

```bash
cd ros2\_ws
source install/setup.bash
ros2 run g1\_light\_tracking tui\_monitor\_node
```

\---

## 4\. Podstawowa diagnostyka przez terminal

### Lista topiców

```bash
cd ros2\_ws
source install/setup.bash
ros2 topic list
```

### Czy są detekcje

```bash
cd ros2\_ws
source install/setup.bash
ros2 topic echo /perception/detections
```

### Czy są tracki

```bash
cd ros2\_ws
source install/setup.bash
ros2 topic echo /tracking/targets
```

### Czy jest stan misji

```bash
cd ros2\_ws
source install/setup.bash
ros2 topic echo /mission/state
```

### Czy publikowane jest sterowanie

```bash
cd ros2\_ws
source install/setup.bash
ros2 topic echo /cmd\_vel
```

### Czy działa depth hint

```bash
cd ros2\_ws
source install/setup.bash
ros2 topic echo /navigation/depth\_hint
```

### Czy działa kamera

```bash
cd ros2\_ws
source install/setup.bash
ros2 topic echo /camera/image\_raw --once
```

### Czy działa CameraInfo

```bash
cd ros2\_ws
source install/setup.bash
ros2 topic echo /camera/camera\_info --once
```

\---

## 5\. Szybka diagnostyka problemów

### Problem: nic się nie uruchamia po nowym terminalu

Rozwiązanie:

```bash
cd ros2\_ws
source install/setup.bash
```

### Problem: build wywala się po wcześniejszych zmianach CMake / setup.py

Rozwiązanie:

```bash
cd ros2\_ws
rm -rf build install log
colcon build --packages-select g1\_light\_tracking
source install/setup.bash
```

### Problem: QR nie działa

Sprawdź:

```bash
python3 -c "from pyzbar.pyzbar import decode; print('pyzbar OK')"
ldconfig -p | grep zbar
```

Jeśli trzeba:

```bash
sudo apt update
sudo apt install -y libzbar0
```

### Problem: AprilTag nie działa

Sprawdź:

```bash
python3 -c "from pupil\_apriltags import Detector; print('apriltag OK')"
```

### Problem: kamera działa, ale pipeline nic nie widzi

Sprawdź kolejno:

```bash
ros2 topic echo /camera/image\_raw --once
ros2 topic echo /perception/detections
ros2 topic echo /tracking/targets
ros2 topic echo /mission/state
```

### Problem: robot nie jedzie

Sprawdź:

```bash
ros2 topic echo /mission/target
ros2 topic echo /navigation/depth\_hint
ros2 topic echo /cmd\_vel
```

Najczęstsze przyczyny:

* brak aktywnego celu,
* brak tracków,
* obstacle ahead z depth layer,
* zbyt mały forward clearance,
* tryb misji idle.

\---

## 6\. Kalibracja kamery

### Kalibracja online przez ROS2 node

```bash
cd ros2\_ws
source install/setup.bash
ros2 run g1\_light\_tracking camera\_calibration\_node --ros-args --params-file src/g1\_light\_tracking/config/camera\_calibration.yaml
```

### Kalibracja offline z folderu zdjęć

```bash
python calibrate\_from\_folder.py   --image-folder calibration/images   --board-cols 9   --board-rows 6   --square-size-m 0.024   --min-samples 20   --output-yaml calibration/camera\_intrinsics.yaml   --output-report calibration/camera\_intrinsics\_report.txt   --save-previews   --preview-output-dir calibration/previews
```

\---

## 7\. TUI i diagnostyka operatorska

Jeżeli dostępny jest aktualny `tui\_monitor\_node`, uruchom:

```bash
cd ros2\_ws
source install/setup.bash
ros2 run g1\_light\_tracking tui\_monitor\_node
```

Najważniejsze skróty:

* `a` dashboard
* `d` detections
* `t` tracks
* `m` mission
* `c` cmd\_vel
* `s` status
* `l` alarm history
* `e` event log
* `h` help
* `q` quit

\---

## 8\. Testy i kontrola importów

### Testy

```bash
cd ros2\_ws
source install/setup.bash
python3 -m pytest src/g1\_light\_tracking/test -v
```

### Szybkie sprawdzenie importów

```bash
cd ros2\_ws
source install/setup.bash
python3 -c "from g1\_light\_tracking.nodes.localization\_node import LocalizationNode; print('localization\_node OK')"
python3 -c "from g1\_light\_tracking.nodes.depth\_mapper\_node import DepthMapperNode; print('depth\_mapper OK')"
python3 -c "from g1\_light\_tracking.utils.geometry import solve\_square\_pnp; print('geometry OK')"
```

\---

## 9\. Praca przez SSH i headless

Na robocie zakładaj brak monitora i brak GUI.
Dlatego:

* preferuj terminal,
* używaj TUI, logów i `ros2 topic echo`,
* nie polegaj na `cv2.imshow`,
* nie zakładaj obecności `DISPLAY`.

Jeżeli moduł próbuje otworzyć GUI i zgłasza błąd `no display`, należy:

* przejść w tryb headless,
* wyłączyć część wizualną,
* zostawić działanie core pipeline'u.

\---

## 10\. Minimalna procedura recovery

Jeżeli nie wiadomo, co jest zepsute, wykonaj:

```bash
cd ros2\_ws
rm -rf build install log
colcon build --packages-select g1\_light\_tracking
source install/setup.bash
ros2 launch g1\_light\_tracking unified\_system.launch.py mode:=modern
```

W drugim terminalu:

```bash
cd ros2\_ws
source install/setup.bash
ros2 topic list
ros2 topic echo /mission/state
ros2 topic echo /cmd\_vel
```

Jeżeli chcesz pełniejszej obserwowalności:

```bash
cd ros2\_ws
source install/setup.bash
ros2 run g1\_light\_tracking debug\_node
```

albo:

```bash
cd ros2\_ws
source install/setup.bash
ros2 run g1\_light\_tracking tui\_monitor\_node
```

\---

## 11\. Najważniejsza zasada operatorska

Robot ma działać autonomicznie, ale operator i programista przez SSH muszą zawsze rozumieć:

* co działa,
* co nie działa,
* co robot widzi,
* jaki ma stan,
* dlaczego publikuje takie komendy,
* czego mu aktualnie brakuje.

