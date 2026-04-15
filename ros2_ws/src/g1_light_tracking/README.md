# g1_light_tracking

Pakiet ROS 2 dla eksperymentalnego pipeline'u percepcji, trackingu i logiki misji w zadaniach intra-logistycznych.

Pakiet jest zaprojektowany jako ciąg kolejnych etapów przetwarzania. Każdy etap ma wąską odpowiedzialność i publikuje jawny typ wiadomości ROS 2. Taki układ upraszcza debugowanie: można niezależnie sprawdzać jakość detekcji, lokalizacji, trackingu albo decyzji misji bez konieczności analizowania całego systemu naraz.

## Główne cele pakietu

- wykrywanie obiektów istotnych dla zadania w obrazie kamery,
- lokalizacja tych obiektów w 3D,
- utrzymywanie stabilnych tożsamości między klatkami,
- powiązanie QR z odpowiadającym mu kartonem,
- publikacja stanu przesyłki i celu misji,
- demonstracyjne sterowanie robota na podstawie celu i głębi.

## Pipeline i odpowiedzialności node'ów

### `perception_node`
Warstwa percepcji 2D. Odpowiada za:
- detekcję obiektów ogólnych przez YOLO,
- odczyt QR,
- wykrywanie AprilTagów,
- wykrywanie plamki światła,
- publikację zunifikowanych obserwacji jako `Detection2D`.

To jedyny etap, który pracuje wyłącznie w układzie obrazu. Nie utrzymuje historii obiektów i nie estymuje jeszcze położenia przestrzennego.

### `localization_node`
Warstwa przejścia z 2D do 3D. Na podstawie kamery, głębi i heurystyk estymuje pozycję celu. Publikuje `LocalizedTarget` z polem `source_method`, które mówi, skąd pochodzi estymacja. To ważne podczas debugowania jakości danych.

### `tracking_node`
Warstwa stabilizacji w czasie. Łączy nowe obserwacje z istniejącymi torami, wygładza ich stan i pilnuje liczników trafień / zgubień. Dla wybranych klas używa filtru Kalmana, a opcjonalnie kompensuje ruch kamery między klatkami. Publikuje `TrackedTarget`.

### `parcel_track_node`
Warstwa domenowa logistyki. Wiąże track QR z trackiem kartonu i tworzy z nich logiczny obiekt przesyłki. Publikuje `ParcelTrack` i `ParcelTrackBinding`, dzięki czemu można śledzić zarówno finalny stan paczki, jak i proces wiązania.

### `mission_node`
Wysokopoziomowa logika zadania. Na podstawie tracków i przesyłek wybiera aktywny cel, określa stan automatu oraz publikuje `MissionState`, `MissionTarget` i `ParcelInfo`.

### `control_node`
Referencyjny kontroler. Przekształca `MissionTarget` na komendy `Twist`. Gdy dostępne są wskazówki z głębi, potrafi ograniczyć ruch do przodu i skorygować skręt.

### `depth_mapper_node`
Lekka analiza obrazu głębi pod kątem reaktywnej nawigacji. Nie planuje ścieżki, ale publikuje prostą sugestię bezpieczeństwa i kierunku omijania (`DepthNavHint`).

### Pozostałe node'y
- `debug_node` — obserwowalność i logowanie komunikatów.
- `camera_calibration_node` — kalibracja intrinsics na podstawie szachownicy.
- `visual_slam_node` — eksperymentalny visual odometry / SLAM.
- `topdown_odom_viewer_node` — diagnostyczna wizualizacja odometrii.

## Najważniejsze wiadomości ROS 2

- `Detection2D` — chwilowa obserwacja w układzie obrazu.
- `LocalizedTarget` — obserwacja z przybliżoną pozycją 3D.
- `TrackedTarget` — stabilny tor obiektu w czasie.
- `ParcelTrackBinding` — wynik przypisania QR do kartonu.
- `ParcelTrack` — ustrukturyzowany stan przesyłki.
- `MissionState` — stan logiki zadania.
- `MissionTarget` — aktualny cel przekazywany do sterowania.
- `DepthNavHint` — pomocnicza wskazówka z mapy głębi.

## Struktura katalogów

```text
ros2_ws/src/g1_light_tracking/
├── CMakeLists.txt              # budowanie wiadomości ROS 2 i instalacja zasobów
├── package.xml                 # zależności pakietu
├── setup.py                    # instalacja części pythonowej
├── g1_light_tracking/
│   ├── nodes/                  # implementacje node'ów ROS 2
│   ├── standalone/             # wariant uruchamiany poza ROS 2
│   └── utils/                  # logika pomocnicza i algorytmy
├── config/                     # parametry YAML dla node'ów
├── launch/                     # launchery ROS 2
├── msg/                        # własne typy wiadomości
├── profiles/                   # profile funkcjonalne trybu standalone
├── scripts/                    # skrypty uruchomieniowe / pomocnicze
└── test/                       # testy jednostkowe
```

## Konfiguracja

Konfiguracja node'ów znajduje się w `config/`. Parametry są rozdzielone per moduł, co ułatwia strojenie:

- `perception.yaml` — progi i przełączniki percepcji,
- `localization.yaml` — parametry estymacji 3D,
- `tracking.yaml` — bramkowanie, potwierdzanie tracków i filtr Kalmana,
- `parcel_track.yaml` — zasady wiązania QR z kartonem,
- `mission.yaml` — logika wyboru celu i stany zadania,
- `control.yaml` — prędkości i zachowanie sterowania,
- `depth_mapper.yaml` — progi bezpieczeństwa oparte o głębię.

## Build

```bash
cd ros2_ws
colcon build
source install/setup.bash
```

## Testy jednostkowe

Testy utili można uruchamiać bez pełnego środowiska ROS 2:

```bash
cd ros2_ws/src/g1_light_tracking
pytest
```

Istniejące testy skupiają się na stabilnej, deterministycznej logice domenowej i geometrycznej. Dobre kolejne rozszerzenie to testy integracyjne topic-to-topic dla kluczowych node'ów.

## Uruchomienie

```bash
cd ros2_ws
source install/setup.bash
ros2 launch g1_light_tracking prod.launch.py
```

Dodatkowy launcher diagnostyczny:

```bash
ros2 launch g1_light_tracking topdown_odom.launch.py
```

## Tryb standalone

Pakiet zawiera też uproszczony tryb poza ROS 2, przydatny do szybkich eksperymentów lokalnych. Kod tego wariantu znajduje się w `g1_light_tracking/standalone/` i może działać z profilami z katalogu `profiles/`.

Zależności dla tego trybu:

```bash
pip install -r requirements-standalone.txt
```

## Zależności Pythona

Środowisko pomocnicze dla node'ów Pythona:

```bash
pip install -r requirements-ros-python.txt
```

`pyzbar` zwykle wymaga zainstalowanej biblioteki systemowej `zbar`.

## Jak czytać kod

Najwygodniejsza kolejność czytania implementacji jest następująca:

1. `msg/` — zobacz kontrakty wiadomości.
2. `launch/prod.launch.py` — zobacz jak node’y są spięte.
3. `g1_light_tracking/nodes/perception_node.py` → `localization_node.py` → `tracking_node.py`.
4. `parcel_track_node.py` i `mission_node.py` — logika domenowa.
5. `control_node.py` — końcowe sterowanie.
6. `utils/` — szczegóły heurystyk i pomocnicze algorytmy.

## Hook wersjonowania

Z katalogu głównego repo:

```bash
bash install_git_hooks.sh
```

Lub z katalogu `ros2_ws/`:

```bash
bash install_git_hooks.sh
```
