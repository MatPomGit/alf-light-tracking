# g1_light_tracking

Pakiet `g1_light_tracking` to rozwijany szkielet systemu ROS 2 dla robota mobilnego do zadań intra-logistycznych. Pakiet został przygotowany jako praktyczna baza pod robota, który:

- wykrywa człowieka przekazującego paczkę,
- wykrywa kartonową przesyłkę,
- odczytuje QR kod z paczki,
- śledzi obiekty w czasie,
- wiąże QR z konkretnym śledzonym kartonem,
- buduje zagregowany obiekt przesyłki (`ParcelTrack`),
- wykorzystuje regały, płaskie powierzchnie i plamki światła jako wskazówki nawigacyjne,
- przechodzi przez prostą maszynę stanów misji: od wyszukiwania, przez odbiór paczki, po odłożenie.

To nie jest jeszcze system produkcyjny „plug and play”. To uporządkowany, techniczny szkielet, w którym są już przygotowane:
- struktura pakietu,
- własne wiadomości ROS 2,
- pipeline percepcji,
- tracking,
- wiązanie QR do kartonu,
- agregacja danych logistycznych,
- logika misji wysokiego poziomu.

---

## 1. Architektura pakietu

Pakiet jest zorganizowany wokół kilku głównych node’ów:

- `perception_node`  
  Detekcja w obrazie: YOLOv8n, QR, AprilTag, plamka światła, kolor plamki.

- `localization_node`  
  Lokalizacja 3D obiektów na podstawie detekcji 2D. Obsługuje:
  - projekcję plamki światła na podłogę,
  - PnP dla QR i AprilTag,
  - heurystyczną lub wymiarową lokalizację kartonu i innych obiektów.

- `tracking_node`  
  Śledzenie obiektów w czasie. Dla `person`, `parcel_box` i `shelf` używa filtru Kalmana. Dla pozostałych obiektów stosuje lekkie wygładzanie.

- `association_node`  
  Wiąże wykryty i śledzony QR z konkretnym śledzonym kartonem (`parcel_box_track_id`), korzystając z rzeczywistego bbox-a.

- `parcel_track_node`  
  Scala dane z trackingu, wiązania QR i sparsowanego payloadu do jednego obiektu logicznego `ParcelTrack`.

- `mission_node`  
  Realizuje logikę wysokiego poziomu oraz prostą maszynę stanów:
  `search -> approach_person -> receive_parcel -> verify_qr -> navigate -> align -> drop`

- `control_node`  
  Generuje uproszczone komendy `/cmd_vel` na podstawie aktywnego celu misji.

- `debug_node`  
  Loguje stan detekcji, trackingu, wiązania, `ParcelTrack` i maszyny stanów.

---

## 2. Struktura katalogów

```text
g1_light_tracking/
├── CMakeLists.txt
├── package.xml
├── setup.py
├── setup.cfg
├── README.md
├── launch/
│   └── prod.launch.py
├── config/
│   ├── perception.yaml
│   ├── localization.yaml
│   ├── tracking.yaml
│   ├── association.yaml
│   ├── parcel_track.yaml
│   ├── mission.yaml
│   └── control.yaml
├── msg/
│   ├── Detection2D.msg
│   ├── LocalizedTarget.msg
│   ├── TrackedTarget.msg
│   ├── ParcelTrackBinding.msg
│   ├── ParcelTrack.msg
│   ├── ParcelInfo.msg
│   ├── MissionTarget.msg
│   └── MissionState.msg
├── scripts/
│   ├── perception_node
│   ├── localization_node
│   ├── tracking_node
│   ├── association_node
│   ├── parcel_track_node
│   ├── mission_node
│   ├── control_node
│   └── debug_node
└── g1_light_tracking/
    ├── nodes/
    └── utils/
```

---

## 3. Wymagania

### ROS 2
Pakiet został przygotowany pod ROS 2 z budowaniem przez `colcon`.

Ponieważ pakiet zawiera własne wiadomości (`msg/*.msg`), używa układu mieszanego:
- `ament_cmake`
- Pythonowe node’y w `rclpy`

### Zależności Pythona
Zależności zostały uporządkowane w kilku miejscach:

- `setup.py`
  - podstawowe: `setuptools`, `numpy`, `opencv-python`
  - opcjonalne extras:
    - `standalone`: `ultralytics`, `pyzbar`, `pupil-apriltags`
    - `full`: to samo, dla pełniejszej instalacji
- `requirements-standalone.txt`
- `requirements-ros-python.txt`

Minimalna instalacja dla trybu standalone:
```bash
pip install -r requirements-standalone.txt
```

Pełniejsza instalacja z extras:
```bash
pip install -e .[standalone]
```

Jeżeli uruchamiasz pakiet wewnątrz środowiska ROS 2:
```bash
pip install -r requirements-ros-python.txt
```

### Ważna uwaga o QR / pyzbar
Biblioteka `pyzbar` zwykle wymaga także systemowej biblioteki `zbar`.

Na Ubuntu zwykle trzeba doinstalować:
```bash
sudo apt install libzbar0
```

W praktyce warto też zadbać o:
- poprawnie działające `cv_bridge`,
- działające sterowniki kamery,
- poprawną kalibrację kamery,
- plik/model `yolov8n.pt` dostępny lokalnie.

---

## 4. Główne wiadomości ROS 2

### `Detection2D`
Surowa detekcja 2D z percepcji:
- typ obiektu,
- bbox,
- środek w obrazie,
- payload QR,
- kolor plamki światła,
- punkty do PnP.

### `LocalizedTarget`
Detekcja po wzbogaceniu o pozycję 3D i bbox.

### `TrackedTarget`
Obiekt śledzony w czasie:
- `track_id`,
- pozycja 3D,
- bbox,
- confidence,
- source method,
- status potwierdzenia.

### `ParcelTrackBinding`
Powiązanie:
- `qr_track_id`
- `parcel_box_track_id`

### `ParcelTrack`
Najważniejszy komunikat logistyczny, łączący:
- track kartonu,
- track QR,
- pozycję,
- wymiary,
- sparsowane dane QR,
- stan logistyczny przesyłki.

### `MissionTarget`
Aktywny cel dla warstwy sterowania.

### `MissionState`
Stan maszyny stanów misji.

---

## 5. Logika działania systemu

System działa warstwowo:

1. `perception_node` wykrywa obiekty w obrazie.
2. `localization_node` zamienia wykrycia na cele 3D.
3. `tracking_node` stabilizuje obiekty w czasie.
4. `association_node` przypisuje QR do konkretnego kartonu.
5. `parcel_track_node` scala dane do jednego obiektu przesyłki.
6. `mission_node` decyduje, co robot powinien robić.
7. `control_node` wysyła ruch na `/cmd_vel`.

---

## 6. Stany misji

Aktualnie zaimplementowana jest prosta maszyna stanów:

- `search`  
  Robot szuka człowieka, kartonu, regału albo wskazówek odkładczych.

- `approach_person`  
  Robot zbliża się do człowieka.

- `receive_parcel`  
  Robot wykrył karton, ale nie ma jeszcze potwierdzonego QR.

- `verify_qr`  
  Robot ma karton i próbuje ustalić jego tożsamość na podstawie QR.

- `navigate`  
  Robot ma zidentyfikowaną przesyłkę i jedzie do miejsca docelowego.

- `align`  
  Robot ustawia się precyzyjnie względem miejsca odłożenia.

- `drop`  
  Robot jest w stanie końcowego odkładania.

---

## 7. Przykładowe warianty uruchamiania

Poniżej są różne warianty uruchamiania pakietu, zależnie od etapu prac.

### Wariant A: pełne uruchomienie całego systemu

To podstawowy wariant do codziennego testowania całego pipeline’u.

```bash
cd ~/ros2_ws
colcon build --packages-select g1_light_tracking
source install/setup.bash
ros2 launch g1_light_tracking prod.launch.py
```

Ten wariant uruchamia:
- percepcję,
- lokalizację,
- tracking,
- wiązanie QR,
- `ParcelTrack`,
- logikę misji,
- sterowanie,
- debug.

---

### Wariant B: tylko percepcja

Przydatne, gdy chcesz testować kamerę, YOLO, QR albo detekcję plamki światła.

```bash
source ~/ros2_ws/install/setup.bash
ros2 run g1_light_tracking perception_node --ros-args --params-file ~/ros2_ws/src/g1_light_tracking/config/perception.yaml
```

Przykład obserwacji topików:

```bash
ros2 topic list
ros2 topic echo /perception/detections
```

---

### Wariant C: percepcja + lokalizacja

Dobre do testów `PnP`, projekcji na podłogę i estymacji `XYZ`.

Terminal 1:
```bash
source ~/ros2_ws/install/setup.bash
ros2 run g1_light_tracking perception_node --ros-args --params-file ~/ros2_ws/src/g1_light_tracking/config/perception.yaml
```

Terminal 2:
```bash
source ~/ros2_ws/install/setup.bash
ros2 run g1_light_tracking localization_node --ros-args --params-file ~/ros2_ws/src/g1_light_tracking/config/localization.yaml
```

Podgląd wyników:
```bash
ros2 topic echo /localization/targets
```

---

### Wariant D: tracking i wiązanie QR do kartonu

Przydatne do sprawdzenia stabilności śladów i poprawności przypięcia QR do `parcel_box_track_id`.

Terminal 1:
```bash
source ~/ros2_ws/install/setup.bash
ros2 run g1_light_tracking perception_node --ros-args --params-file ~/ros2_ws/src/g1_light_tracking/config/perception.yaml
```

Terminal 2:
```bash
source ~/ros2_ws/install/setup.bash
ros2 run g1_light_tracking localization_node --ros-args --params-file ~/ros2_ws/src/g1_light_tracking/config/localization.yaml
```

Terminal 3:
```bash
source ~/ros2_ws/install/setup.bash
ros2 run g1_light_tracking tracking_node --ros-args --params-file ~/ros2_ws/src/g1_light_tracking/config/tracking.yaml
```

Terminal 4:
```bash
source ~/ros2_ws/install/setup.bash
ros2 run g1_light_tracking association_node --ros-args --params-file ~/ros2_ws/src/g1_light_tracking/config/association.yaml
```

Podgląd:
```bash
ros2 topic echo /tracking/targets
ros2 topic echo /tracking/parcel_bindings
```

---

### Wariant E: agregacja przesyłek jako `ParcelTrack`

Ten wariant pokazuje już obiekt logistyczny wyższego poziomu.

Terminal 1:
```bash
source ~/ros2_ws/install/setup.bash
ros2 run g1_light_tracking perception_node --ros-args --params-file ~/ros2_ws/src/g1_light_tracking/config/perception.yaml
```

Terminal 2:
```bash
source ~/ros2_ws/install/setup.bash
ros2 run g1_light_tracking localization_node --ros-args --params-file ~/ros2_ws/src/g1_light_tracking/config/localization.yaml
```

Terminal 3:
```bash
source ~/ros2_ws/install/setup.bash
ros2 run g1_light_tracking tracking_node --ros-args --params-file ~/ros2_ws/src/g1_light_tracking/config/tracking.yaml
```

Terminal 4:
```bash
source ~/ros2_ws/install/setup.bash
ros2 run g1_light_tracking association_node --ros-args --params-file ~/ros2_ws/src/g1_light_tracking/config/association.yaml
```

Terminal 5:
```bash
source ~/ros2_ws/install/setup.bash
ros2 run g1_light_tracking parcel_track_node --ros-args --params-file ~/ros2_ws/src/g1_light_tracking/config/parcel_track.yaml
```

Podgląd:
```bash
ros2 topic echo /tracking/parcel_tracks
```

---

### Wariant F: tylko logika misji i debug

Jeżeli masz już źródła danych z innych node’ów lub z rosbag, możesz uruchomić tylko logikę misji.

Terminal 1:
```bash
source ~/ros2_ws/install/setup.bash
ros2 run g1_light_tracking mission_node --ros-args --params-file ~/ros2_ws/src/g1_light_tracking/config/mission.yaml
```

Terminal 2:
```bash
source ~/ros2_ws/install/setup.bash
ros2 run g1_light_tracking debug_node
```

Podgląd:
```bash
ros2 topic echo /mission/target
ros2 topic echo /mission/state
```

---

### Wariant G: uruchamianie z remapowaniem topiku kamery

Jeżeli kamera publikuje np. na `/oak/rgb/image_raw`, możesz zremapować wejście.

```bash
source ~/ros2_ws/install/setup.bash
ros2 run g1_light_tracking perception_node   --ros-args   -p image_topic:=/oak/rgb/image_raw   -p camera_info_topic:=/oak/rgb/camera_info
```

---

### Wariant H: uruchamianie z innym modelem YOLO

Jeżeli masz własny model do wykrywania kartonów, regałów albo stref odkładczych:

```bash
source ~/ros2_ws/install/setup.bash
ros2 run g1_light_tracking perception_node   --ros-args   -p yolo_model_path:=/home/user/models/warehouse_yolov8n.pt   -p yolo_confidence:=0.45
```

---

## 8. Przykładowe fragmenty kodu

### 8.1. Uruchamianie node’a z Pythona przez `main()`

```python
from g1_light_tracking.nodes.perception_node import main

if __name__ == "__main__":
    main()
```

### 8.2. Subskrypcja `ParcelTrack`

```python
import rclpy
from rclpy.node import Node
from g1_light_tracking.msg import ParcelTrack

class ParcelObserver(Node):
    def __init__(self):
        super().__init__("parcel_observer")
        self.create_subscription(
            ParcelTrack,
            "/tracking/parcel_tracks",
            self.cb,
            10
        )

    def cb(self, msg: ParcelTrack):
        self.get_logger().info(
            f"Parcel box={msg.parcel_box_track_id}, "
            f"shipment={msg.shipment_id}, "
            f"state={msg.logistics_state}, "
            f"z={msg.position.z:.2f}"
        )

def main():
    rclpy.init()
    node = ParcelObserver()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()

if __name__ == "__main__":
    main()
```

### 8.3. Subskrypcja `MissionState`

```python
import rclpy
from rclpy.node import Node
from g1_light_tracking.msg import MissionState

class MissionStateObserver(Node):
    def __init__(self):
        super().__init__("mission_state_observer")
        self.create_subscription(
            MissionState,
            "/mission/state",
            self.cb,
            10
        )

    def cb(self, msg: MissionState):
        self.get_logger().info(
            f"state={msg.state}, prev={msg.previous_state}, "
            f"active_box={msg.active_parcel_box_track_id}, "
            f"shipment={msg.active_shipment_id}"
        )

def main():
    rclpy.init()
    node = MissionStateObserver()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()

if __name__ == "__main__":
    main()
```

### 8.4. Minimalny przykład publikacji sztucznego `MissionTarget`

Przydatne do testów sterowania bez percepcji.

```python
import rclpy
from rclpy.node import Node
from geometry_msgs.msg import Point
from g1_light_tracking.msg import MissionTarget

class FakeMissionPublisher(Node):
    def __init__(self):
        super().__init__("fake_mission_publisher")
        self.pub = self.create_publisher(MissionTarget, "/mission/target", 10)
        self.timer = self.create_timer(0.5, self.tick)

    def tick(self):
        msg = MissionTarget()
        msg.mode = "parcel_approach"
        msg.target_type = "parcel_track"
        msg.class_name = "parcel_box"
        msg.position = Point(x=0.1, y=0.0, z=1.2)
        msg.confidence = 0.95
        self.pub.publish(msg)

def main():
    rclpy.init()
    node = FakeMissionPublisher()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()

if __name__ == "__main__":
    main()
```

---

## 9. Przydatne polecenia diagnostyczne

Lista topików:
```bash
ros2 topic list
```

Podgląd typu wiadomości:
```bash
ros2 topic info /tracking/parcel_tracks
ros2 interface show g1_light_tracking/msg/ParcelTrack
```

Podgląd stanu misji:
```bash
ros2 topic echo /mission/state
```

Podgląd przesyłek:
```bash
ros2 topic echo /tracking/parcel_tracks
```

Podgląd tracków:
```bash
ros2 topic echo /tracking/targets
```

Podgląd wiązań QR -> karton:
```bash
ros2 topic echo /tracking/parcel_bindings
```

---

## 10. Typowe miejsca do dalszego rozwoju

Najbardziej naturalne kolejne kroki rozwoju tego pakietu to:

1. Doprecyzowanie sterowania w `control_node` zależnie od stanu:
   - osobne zachowanie dla `approach_person`,
   - osobne dla `navigate`,
   - osobne dla `align`,
   - osobne dla `drop`.

2. Lepszy tracker wieloobiektowy:
   - lepsze bramkowanie,
   - Hungarian assignment,
   - osobne modele ruchu dla różnych klas.

3. Lepsza lokalizacja 3D kartonu:
   - keypointy narożników,
   - pełne PnP,
   - wykorzystanie depth/stereo.

4. Pełne wiązanie logistyczne:
   - aktualny stan przesyłki,
   - stan „odebrana / wieziona / odłożona”,
   - lepsza obsługa znikania QR.

5. Integracja z manipulatorem lub mechanizmem odbioru paczki.

---

## 11. Uwagi praktyczne

- QR na kartonie powinien być dobrze widoczny i możliwie stabilny w kadrze.
- Dla prawidłowego `PnP` potrzebna jest poprawna kalibracja kamery.
- Przy własnym modelu YOLO warto mieć osobne klasy dla:
  - `parcel_box`
  - `shelf`
  - `drop_surface`
  - `person`
- Dla środowisk magazynowych bardzo szybko przydaje się nagrywanie danych do rosbag i testy offline.

---

## 12. Podsumowanie

Pakiet `g1_light_tracking` jest obecnie sensownym szkieletem badawczo-wdrożeniowym dla robota mobilnego do intra-logistyki. Najważniejszą cechą tej wersji jest to, że logika systemu nie opiera się już wyłącznie na pojedynczych detekcjach, ale na coraz bogatszych poziomach reprezentacji:

`Detection2D -> LocalizedTarget -> TrackedTarget -> ParcelTrack -> MissionState`

Dzięki temu pakiet nadaje się zarówno do:
- eksperymentów badawczych,
- budowy demonstratora,
- jak i dalszego rozwijania w kierunku bardziej kompletnego systemu robota logistycznego.

## 13. Payload markerów: QR i AprilTag

W tej wersji przyjmujemy spójne założenie:
- **QR kod** przekazuje zdekodowaną treść w polu `payload`,
- **AprilTag** również przekazuje zdekodowaną treść w polu `payload`.

W praktyce dla QR:
- `payload` zawiera pełną treść odczytaną z kodu.

W praktyce dla AprilTaga:
- jeżeli detektor zwraca tylko `tag_id`, to `payload` zawiera co najmniej tekstową reprezentację identyfikatora, np. `tag_id=17`,
- jeżeli w przyszłości dodasz własną mapę semantyczną tagów, możesz w tym samym polu przekazywać rozszerzoną treść, np. `tag_id=17;zone=A3;shelf=2`.

To założenie obowiązuje w całym pipeline:
`Detection2D -> LocalizedTarget -> TrackedTarget -> ParcelTrack / MissionTarget`.



## Aktualizacja architektury: scalony `association_node` i `parcel_track_node`

W tej wersji:
- osobny `association_node` został usunięty,
- jego logika została włączona bezpośrednio do `parcel_track_node`.

Nowy `parcel_track_node` robi teraz dwa zadania:
1. kojarzy `QR -> parcel_box_track_id`,
2. publikuje gotowy `ParcelTrack`.

Zysk:
- mniej node’ów w launchu,
- prostszy przepływ danych,
- mniej konfiguracji do utrzymania.


## 14. Tryb standalone bez komunikacji ROS 2

W tej wersji dodano dwa warianty pracy bez topiców ROS 2.  
Cały pipeline działa wtedy lokalnie, w jednym procesie:

- odczyt obrazu z kamery,
- detekcja,
- prosty tracking,
- wiązanie QR do kartonu,
- budowa prostego widoku przesyłki.

### 14.1. Tryb CLI

Uruchomienie z wiersza poleceń:

```bash
python3 -m g1_light_tracking.standalone.cli_app --camera 0 --model yolov8n.pt
```

albo po instalacji przez skrypt:

```bash
standalone_cli --camera 0 --model yolov8n.pt
```

Przykład z limitem klatek:

```bash
standalone_cli --camera 0 --model yolov8n.pt --max-frames 300 --show-every 5
```

Co robi tryb CLI:
- nie używa ROS 2 topiców,
- wypisuje wykrycia, tracki i przesyłki w terminalu,
- nadaje się do szybkiego testowania bez uruchamiania całego grafu ROS.

### 14.2. Tryb GUI

Uruchomienie z prostym oknem podglądu:

```bash
python3 -m g1_light_tracking.standalone.gui_app --camera 0 --model yolov8n.pt
```

albo:

```bash
standalone_gui --camera 0 --model yolov8n.pt
```

Sterowanie:
- `q` — wyjście,
- `s` — zapis aktualnej klatki do pliku PNG.

Co pokazuje GUI:
- bbox-y obiektów,
- track ID,
- payload QR / AprilTag,
- kolor plamki światła,
- skrócony stan przesyłki.

### 14.3. Kiedy używać trybu standalone

Tryb standalone jest przydatny, gdy chcesz:
- szybko sprawdzić kamerę i model YOLO,
- przetestować QR i AprilTag bez ROS 2,
- debugować środowisko lokalnie,
- przygotować demonstrator działający jako pojedyncza aplikacja.

### 14.4. Ograniczenia trybu standalone

Ten tryb nie zastępuje w pełni wersji ROS 2:
- nie korzysta z własnych wiadomości ROS,
- nie korzysta z pełnej maszyny stanów ROS,
- ma lżejszy tracking niż wersja ROS,
- nie publikuje `/cmd_vel`.

To jest celowy tryb uproszczony do uruchamiania lokalnego, a nie pełny zamiennik całej architektury ROS 2.


## 15. Informowanie użytkownika o aktywnych funkcjach w CLI i GUI

Moduły standalone zostały rozszerzone tak, aby wyraźnie pokazywały, które funkcje są aktualnie uruchomione.

### CLI
Po starcie CLI wypisuje:
- status kamery,
- status YOLO,
- status QR,
- status AprilTag,
- status wykrywania plamki światła,
- status trackingu,
- status wiązania QR do kartonu,
- aktywny tryb pracy.

Dodatkowo cyklicznie pokazuje:
- liczbę detekcji,
- liczbę tracków,
- liczbę aktywnych obiektów `ParcelTrack`,
- typy obiektów widoczne w bieżącej klatce.

### GUI
GUI wyświetla panel statusu w oknie obrazu:
- aktywne funkcje,
- liczbę detekcji,
- liczbę tracków,
- liczbę aktywnych przesyłek,
- typy wykrytych obiektów.

Dodatkowy skrót klawiaturowy:
- `h` — pokazuje lub ukrywa panel statusu.


## 16. Menu włączania i wyłączania funkcji w runtime

Tryby standalone zostały rozszerzone o dynamiczne przełączanie funkcji bez restartu programu.

### Funkcje przełączalne
Można włączać i wyłączać:
- YOLO
- QR
- AprilTag
- wykrywanie plamki światła
- tracking
- wiązanie QR do kartonu

### GUI
W trybie GUI działają skróty:
- `q` — wyjście
- `s` — zapis klatki
- `h` — pokaż / ukryj panel statusu
- `1` — przełącz YOLO
- `2` — przełącz QR
- `3` — przełącz AprilTag
- `4` — przełącz plamkę światła
- `5` — przełącz tracking
- `6` — przełącz wiązanie QR do kartonu
- `m` — pokaż / ukryj legendę skrótów

### CLI
W trybie CLI działa wejście poleceń z osobnego wątku. Dostępne komendy:
- `status`
- `yolo on`
- `yolo off`
- `qr on`
- `qr off`
- `apriltag on`
- `apriltag off`
- `light on`
- `light off`
- `tracking on`
- `tracking off`
- `binding on`
- `binding off`
- `help`
- `quit`

Przykład:
```text
qr off
tracking off
status
```


## 17. Weryfikacja zależności

W tej wersji zależności zostały sprawdzone i uporządkowane dla wszystkich głównych sposobów uruchamiania.

### ROS 2
Node’y ROS 2 opierają się na:
- `rclpy`
- `cv_bridge`
- `geometry_msgs`
- `sensor_msgs`
- `builtin_interfaces`
- własnych wiadomościach pakietu

To jest definiowane przez:
- `package.xml`
- `CMakeLists.txt`

### Python / percepcja
Funkcje percepcyjne używają:
- `numpy`
- `opencv-python`
- `ultralytics`
- `pyzbar`
- `pupil-apriltags`

To jest teraz opisane w:
- `setup.py`
- `requirements-standalone.txt`
- `requirements-ros-python.txt`

### Zależności systemowe
Dla `pyzbar` potrzebna jest zwykle systemowa biblioteka:
- `libzbar0`

Na Ubuntu:
```bash
sudo apt install libzbar0
```

### Uwaga praktyczna
Nie wszystkie środowiska ROS 2 dobrze znoszą automatyczne dociąganie ciężkich zależności ML przez `install_requires`. Dlatego poza `setup.py` zostawiłem też jawne pliki `requirements-*.txt`, żeby instalacja była przewidywalna i łatwa do odtworzenia.


## 19. Strona dokumentacyjna repozytorium

Dodano statyczną stronę internetową:
- `doc/index.html`

Strona opisuje:
- cel repozytorium,
- architekturę modułów,
- przepływ danych,
- tryby uruchamiania,
- profile runtime,
- sterowanie CLI/GUI,
- zależności.

Możesz ją otworzyć lokalnie bez serwera:
```bash
xdg-open doc/index.html
```
albo po prostu otwierając plik w przeglądarce.


## 20. Automatyczna zmiana wersji przy commicie

Dodano:
- `VERSION`
- `scripts/version_bump.py`
- `scripts/install_git_hooks.sh`

Jak to działa:
1. instalujesz hook:
   ```bash
   bash scripts/install_git_hooks.sh
   ```
2. przy każdym `git commit` hook `pre-commit`:
   - zwiększa patch wersji,
   - aktualizuje `VERSION`,
   - aktualizuje `setup.py`,
   - aktualizuje `package.xml`,
   - dodaje te pliki do commita.

## 21. Rozbudowana strona `doc/index.html`

Strona została przebudowana i teraz zawiera:
- zakładki,
- przyciski pokazujące sekwencje uruchamiania,
- interaktywny diagram przepływu modułów,
- sekcję zależności,
- sekcję wersjonowania.

## 22. Własne profile użytkownika

Standalone CLI:
- zapis profilu:
  ```text
  saveprofile moja_konfiguracja
  ```

Standalone GUI:
- klawisz `w` zapisuje aktualny stan funkcji do:
  - `profiles/custom_last.json`
