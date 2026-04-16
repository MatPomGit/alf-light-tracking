# DEPLOYMENT.md

## Cel

Ten dokument opisuje praktyczne wdrożenie `alf-light-tracking` na docelowym środowisku:
- **Unitree G1 EDU**
- **Ubuntu 22.04**
- środowisko **headless**
- praca głównie przez **SSH**
- komunikacja między modułami przez **ROS 2**

Dokument jest checklistą wdrożeniową i operacyjną. Ma pomóc:
- postawić system od zera,
- sprawdzić poprawność środowiska,
- uruchomić pipeline,
- zdiagnozować typowe problemy,
- nie zablokować robota przez brak GUI lub moduł opcjonalny.

---

## 1. Założenia wdrożeniowe

System ma działać tak, aby:
- podstawowa pętla robota nie wymagała monitora,
- wszystkie krytyczne moduły działały przez ROS 2,
- debugowanie było możliwe z terminala,
- brak modułów pomocniczych nie zatrzymywał pracy robota,
- programista mógł łatwo sprawdzić aktualny stan systemu.

Za krytyczne elementy runtime uznajemy przede wszystkim:
- sensory wejściowe,
- percepcję,
- lokalizację,
- tracking,
- logikę misji,
- sterowanie ruchem.

Za elementy pomocnicze uznajemy m.in.:
- TUI,
- debug monitor,
- replay,
- kalibrację offline,
- recorder,
- rosbag,
- eksporty raportów.

---

## 2. Środowisko docelowe

### Sprzęt
- Unitree G1 EDU
- komputer pokładowy klasy Jetson / wbudowany Linux
- sensory zgodne z konfiguracją projektu, np. D435i
- połączenie sieciowe umożliwiające SSH

### System operacyjny
- Ubuntu 22.04

### Tryb pracy
- headless
- brak założenia obecności `DISPLAY`
- brak wymogu GUI do działania podstawowego

### Wymagania programowe
- ROS 2 Humble lub kompatybilne środowisko
- `colcon`
- Python 3
- zależności systemowe i Pythonowe zgodne z repo

---

## 3. Struktura repo na robocie

Preferowany układ na urządzeniu:

```text
~/alf-light-tracking/
├── README.md
├── RUNBOOK.md
├── DEPLOYMENT.md
└── ros2_ws/
    ├── src/
    │   └── g1_light_tracking/
    ├── build/
    ├── install/
    └── log/
```

Najważniejsze katalogi:
- `~/alf-light-tracking/ros2_ws/` — workspace ROS2
- `~/alf-light-tracking/ros2_ws/src/g1_light_tracking/` — główny pakiet
- `~/alf-light-tracking/ros2_ws/install/` — aktywowane środowisko po buildzie

---

## 4. Wstępna konfiguracja systemu

### Aktualizacja pakietów systemowych

```bash
sudo apt update
sudo apt upgrade -y
```

### Podstawowe narzędzia developerskie

```bash
sudo apt install -y git python3-pip python3-venv curl wget
```

### ROS 2 i build tools
Zakłada się, że ROS 2 jest już zainstalowany lub zostanie zainstalowany zgodnie z oficjalną procedurą dla Ubuntu 22.04 i ROS 2 Humble.

Dodatkowe narzędzia:

```bash
sudo apt install -y python3-colcon-common-extensions
```

### Biblioteka do QR

```bash
sudo apt install -y libzbar0
```

### Opcjonalnie: zależności związane z kamerą
Jeśli używana jest D435i i środowisko korzysta z `pyrealsense2`, upewnij się, że sterowniki i biblioteki są poprawnie dostępne.

---

## 5. Pobranie repo i przygotowanie workspace

### Klonowanie repo

```bash
cd ~
git clone <ADRES_REPO_GIT> alf-light-tracking
```

### Wejście do workspace

```bash
cd ~/alf-light-tracking/ros2_ws
```

---

## 6. Instalacja zależności Pythona

W katalogu pakietu:

```bash
cd ~/alf-light-tracking/ros2_ws/src/g1_light_tracking
python3 -m pip install -r requirements-ros-python.txt
```

Opcjonalnie:

```bash
python3 -m pip install -r requirements-standalone.txt
python3 -m pip install -r requirements-compat.txt
```

Jeśli dany wariant nie jest potrzebny, można go pominąć.

---

## 7. Build systemu

### Build głównego pakietu

```bash
cd ~/alf-light-tracking/ros2_ws
colcon build --packages-select g1_light_tracking
source install/setup.bash
```

### Build całego workspace

```bash
cd ~/alf-light-tracking/ros2_ws
colcon build
source install/setup.bash
```

### Gdy wystąpi konflikt builda
Jeżeli wcześniej wystąpił problem z targetami CMake lub artefaktami konfiguracji:

```bash
cd ~/alf-light-tracking/ros2_ws
rm -rf build install log
colcon build --packages-select g1_light_tracking
source install/setup.bash
```

---

## 8. Aktywacja środowiska po SSH

Po każdej nowej sesji SSH trzeba aktywować środowisko:

```bash
cd ~/alf-light-tracking/ros2_ws
source install/setup.bash
```

W praktyce warto dodać alias do `~/.bashrc`, ale nie należy polegać wyłącznie na nim.
Przed uruchomieniem systemu operator powinien jawnie wykonać `source install/setup.bash`.

---

## 9. Sanity checks przed pierwszym uruchomieniem

### Czy działają importy Pythona

```bash
cd ~/alf-light-tracking/ros2_ws
source install/setup.bash
python3 -c "from g1_light_tracking.nodes.localization_node import LocalizationNode; print('localization_node OK')"
python3 -c "from g1_light_tracking.nodes.depth_mapper_node import DepthMapperNode; print('depth_mapper OK')"
python3 -c "from g1_light_tracking.utils.geometry import solve_square_pnp; print('geometry OK')"
```

### Czy działa backend QR

```bash
python3 -c "from pyzbar.pyzbar import decode; print('pyzbar OK')"
ldconfig -p | grep zbar
```

### Czy działa backend AprilTag

```bash
python3 -c "from pupil_apriltags import Detector; print('apriltag OK')"
```

### Czy kamera jest widoczna
Jeżeli używana jest D435i:

```bash
cd ~/alf-light-tracking/ros2_ws
source install/setup.bash
ros2 run g1_light_tracking d435i_node
```

W drugim terminalu:

```bash
cd ~/alf-light-tracking/ros2_ws
source install/setup.bash
ros2 topic echo /camera/image_raw --once
```

---

## 10. Pierwsze uruchomienie systemu

### Rekomendowany start: unified launcher w trybie modern

```bash
cd ~/alf-light-tracking/ros2_ws
source install/setup.bash
ros2 launch g1_light_tracking unified_system.launch.py mode:=modern
```

### Wariant produkcyjny

```bash
cd ~/alf-light-tracking/ros2_ws
source install/setup.bash
ros2 launch g1_light_tracking prod.launch.py
```

### Warianty alternatywne

#### Legacy

```bash
cd ~/alf-light-tracking/ros2_ws
source install/setup.bash
ros2 launch g1_light_tracking unified_system.launch.py mode:=legacy
```

#### Hybrid

```bash
cd ~/alf-light-tracking/ros2_ws
source install/setup.bash
ros2 launch g1_light_tracking unified_system.launch.py mode:=hybrid
```

#### Hybrid z legacy kamerą

```bash
cd ~/alf-light-tracking/ros2_ws
source install/setup.bash
ros2 launch g1_light_tracking unified_system.launch.py mode:=hybrid with_legacy_camera:=true
```

#### Legacy z bridge’ami Unitree

```bash
cd ~/alf-light-tracking/ros2_ws
source install/setup.bash
ros2 launch g1_light_tracking unified_system.launch.py mode:=legacy with_unitree_bridges:=true
```

---

## 11. Minimalna checklista po starcie

Po uruchomieniu sprawdź:

### Czy są topiki systemowe

```bash
cd ~/alf-light-tracking/ros2_ws
source install/setup.bash
ros2 topic list
```

### Czy są detekcje

```bash
ros2 topic echo /perception/detections
```

### Czy są tracki

```bash
ros2 topic echo /tracking/targets
```

### Czy jest stan misji

```bash
ros2 topic echo /mission/state
```

### Czy są komendy ruchu

```bash
ros2 topic echo /cmd_vel
```

### Czy działa warstwa głębi

```bash
ros2 topic echo /navigation/depth_hint
```

Jeżeli core topiki nie żyją, najpierw diagnozuj pipeline, a nie narzędzia pomocnicze.

---

## 12. Diagnostyka operatorska

### Debug node

```bash
cd ~/alf-light-tracking/ros2_ws
source install/setup.bash
ros2 run g1_light_tracking debug_node
```

### TUI monitor

```bash
cd ~/alf-light-tracking/ros2_ws
source install/setup.bash
ros2 run g1_light_tracking tui_monitor_node
```

TUI jest preferowanym narzędziem tekstowym przy pracy przez SSH. Nie może jednak być wymagany do pracy systemu.

---

## 13. Headless i no-display

Na robocie zakładaj brak GUI.

### Zasady wdrożeniowe
- nie uruchamiaj narzędzi wymagających okna bez wyraźnej potrzeby,
- unikaj `cv2.imshow`,
- unikaj zależności od `DISPLAY`,
- każda część wizualna ma być opcjonalna.

### Co zrobić przy błędzie `no display`
Jeżeli moduł wywala się przez brak monitora:
1. wyłącz część GUI,
2. przejdź na TUI, logi i topiki diagnostyczne,
3. upewnij się, że błąd nie wpływa na podstawową pętlę robota.

Błąd `no display` nie powinien zatrzymać:
- percepcji,
- trackingu,
- misji,
- sterowania.

---

## 14. Kalibracja kamery

### Kalibracja online przez ROS2

```bash
cd ~/alf-light-tracking/ros2_ws
source install/setup.bash
ros2 run g1_light_tracking camera_calibration_node --ros-args --params-file src/g1_light_tracking/config/camera_calibration.yaml
```

### Kalibracja offline z folderu zdjęć

```bash
python calibrate_from_folder.py   --image-folder calibration/images   --board-cols 9   --board-rows 6   --square-size-m 0.024   --min-samples 20   --output-yaml calibration/camera_intrinsics.yaml   --output-report calibration/camera_intrinsics_report.txt   --save-previews   --preview-output-dir calibration/previews
```

Po kalibracji należy sprawdzić:
- czy powstał plik YAML,
- czy powstał raport,
- czy `CameraInfo` jest zgodne z rozdzielczością obrazu,
- czy runtime korzysta z właściwego pliku/topicu kalibracyjnego.

---

## 15. Unitree-specyficzne uwagi wdrożeniowe

### Bridge’e sprzętowe
Komponenty Unitree powinny być traktowane jako warstwa integracyjna pomiędzy core pipeline a robotem.

Zasady:
- bridge ma być jawnie włączany launch argumentem, jeśli nie jest obowiązkowy,
- błąd bridge’a ma być łatwo wykrywalny z terminala,
- brak bridge’a nie powinien psuć percepcji, trackingu ani logiki misji,
- warstwa ruchu powinna jasno logować, czy komendy są tylko generowane, czy faktycznie wysyłane do platformy.

### Bezpieczny start
Na etapie wdrożenia:
- uruchamiaj najpierw pipeline bez ruchu,
- potem sprawdzaj tylko publikację `cmd_vel`,
- dopiero potem podłączaj realny bridge sprzętowy.

---

## 16. Co uruchamiać automatycznie, a czego nie

### Można automatyzować po starcie systemu
- aktywację workspace,
- launcher `modern` lub `prod`,
- wybrane topiki diagnostyczne,
- recorder opcjonalny,
- heartbeat monitor,
- TUI w osobnej sesji terminala.

### Nie wymuszaj jako krytyczne
- GUI,
- recorder,
- rosbag,
- replay,
- kalibracji,
- raportów offline,
- narzędzi deweloperskich.

Te elementy powinny być dodatkami.

---

## 17. Typowe problemy i recovery

### Problem: po restarcie sesji SSH nic nie działa
Rozwiązanie:

```bash
cd ~/alf-light-tracking/ros2_ws
source install/setup.bash
```

### Problem: build nie działa po zmianach w repo
Rozwiązanie:

```bash
cd ~/alf-light-tracking/ros2_ws
rm -rf build install log
colcon build --packages-select g1_light_tracking
source install/setup.bash
```

### Problem: kamera działa, ale brak detekcji
Sprawdź kolejno:

```bash
ros2 topic echo /camera/image_raw --once
ros2 topic echo /perception/detections
ros2 topic echo /tracking/targets
```

### Problem: brak sterowania
Sprawdź:

```bash
ros2 topic echo /mission/target
ros2 topic echo /navigation/depth_hint
ros2 topic echo /cmd_vel
```

Najczęstsze przyczyny:
- brak aktywnego celu,
- brak tracków,
- obstacle ahead,
- zbyt mały clearance,
- misja w stanie idle,
- bridge sprzętowy nie działa poprawnie.

### Problem: QR nie działa
Sprawdź:

```bash
python3 -c "from pyzbar.pyzbar import decode; print('pyzbar OK')"
ldconfig -p | grep zbar
```

### Problem: AprilTag nie działa
Sprawdź:

```bash
python3 -c "from pupil_apriltags import Detector; print('apriltag OK')"
```

---

## 18. Minimalna procedura awaryjna

Jeżeli system jest w nieznanym stanie:

```bash
cd ~/alf-light-tracking/ros2_ws
rm -rf build install log
colcon build --packages-select g1_light_tracking
source install/setup.bash
ros2 launch g1_light_tracking unified_system.launch.py mode:=modern
```

W drugim terminalu:

```bash
cd ~/alf-light-tracking/ros2_ws
source install/setup.bash
ros2 topic list
ros2 topic echo /mission/state
ros2 topic echo /cmd_vel
```

W trzecim terminalu opcjonalnie:

```bash
cd ~/alf-light-tracking/ros2_ws
source install/setup.bash
ros2 run g1_light_tracking debug_node
```

albo:

```bash
cd ~/alf-light-tracking/ros2_ws
source install/setup.bash
ros2 run g1_light_tracking tui_monitor_node
```

---

## 19. Co warto dodać w przyszłości do wdrożenia

W kolejnych etapach wdrożenia warto rozważyć:
- osobną paczkę `rosbag` lub recorder tools,
- osobną paczkę telemetry / diagnostics,
- watchdog dla topic freshness,
- start przez `systemd`,
- osobny deployment profile dla robota i dla środowiska developerskiego,
- eksport snapshotów i alarmów do plików tekstowych/JSON,
- automatyczne testy smoke po starcie pipeline’u.

Te elementy powinny jednak pozostawać opcjonalne względem głównej pętli robota.

---

## 20. Najważniejsza zasada wdrożeniowa

Robot ma działać autonomicznie, ale operator i programista pracujący przez SSH muszą zawsze być w stanie odpowiedzieć:

- czy system wystartował poprawnie,
- które moduły działają,
- które moduły nie działają,
- co robot widzi,
- jaki jest stan misji,
- czy ruch jest blokowany przez safety,
- czy `cmd_vel` jest tylko liczony czy rzeczywiście wysyłany,
- czego systemowi brakuje.

Jeżeli wdrożenie nie daje takiej wiedzy, to wdrożenie jest niepełne.
