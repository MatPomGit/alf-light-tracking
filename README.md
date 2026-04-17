# ROS2 Unitree G1 light tracking PoC

<!--
[AI-CHANGE | 2026-04-17 11:58 UTC | v0.79]
CO ZMIENIONO: Przebudowano README do formatu operacyjnego: dodano opis struktury repozytorium, wymagania, szybki start i zestaw praktycznych wariantów uruchamiania (robot, turtlesim, testy punktowe, serwisy ramion, replay danych, diagnostyka).
DLACZEGO: Dotychczasowy opis był skrócony i utrudniał szybkie wejście nowej osoby do projektu oraz spójne odtwarzanie scenariuszy testowych R&D.
JAK TO DZIAŁA: README prowadzi użytkownika krok po kroku: od przygotowania środowiska, przez budowanie pakietu, po uruchamianie konkretnych node'ów i launchy z parametrami. Dodatkowo opisuje strukturę katalogów i linki referencyjne po porządkowaniu repo.
TODO: Dodać sekcję "Troubleshooting" z typowymi błędami ROS2 (DDS, QoS, uprawnienia urządzeń) i gotowymi komendami diagnostycznymi.
-->

## Cel projektu

PoC służy do śledzenia plamki światła przez robota **Unitree G1** oraz do testów offline/symulacyjnych bez robota.
Priorytet jakościowy: **lepiej odrzucić niepewną detekcję niż zwrócić błędny wynik**.

---

## Struktura repozytorium

```text
.
├── AGENTS.md
├── README.md
├── docs/
│   └── reference-links/
│       ├── bag/
│       ├── core/
│       ├── performance/
│       └── tracing/
└── ros2_ws/
    └── g1_light_tracking/
        ├── config/
        ├── g1_light_tracking/
        ├── launch/
        ├── logs/
        ├── package.xml
        ├── requirements.txt
        └── setup.py
```

### Co gdzie jest

- `ros2_ws/g1_light_tracking/g1_light_tracking/` – node'y ROS2 (detekcja, follower, bridge, replay CSV, arm skills).
- `ros2_ws/g1_light_tracking/launch/` – gotowe scenariusze uruchomień (`*.launch.py`).
- `ros2_ws/g1_light_tracking/config/` – konfiguracja percepcji, sterowania i bridge.
- `docs/reference-links/` – uporządkowane linki pomocnicze (RT, tf2, tracing, bag recording).

---

## Wymagania

- Ubuntu + ROS2 (zalecane uruchamianie z workspace `ros2_ws`).
- Python 3.10+.
- Zainstalowane zależności pakietu:

```bash
cd ros2_ws/g1_light_tracking
python3 -m pip install -r requirements.txt
```

---

## Szybki start (build)

```bash
cd ros2_ws
colcon build --packages-select g1_light_tracking
source install/setup.bash
```

> W każdej nowej zakładce terminala ponownie wykonaj `source install/setup.bash`.

---

## Praktyczne warianty uruchamiania

## 1) Tryb docelowy: robot Unitree G1 (pełny pipeline)

Uruchamia stack śledzenia z mostkiem komend do robota.

```bash
cd ros2_ws
colcon build --packages-select g1_light_tracking
source install/setup.bash
ros2 launch g1_light_tracking light_tracking_stack.launch.py
```

Przykład z nadpisaniem parametrów w locie:

```bash
ros2 launch g1_light_tracking light_tracking_stack.launch.py \
  control_config:=src/g1_light_tracking/config/control.yaml \
  bridge_config:=src/g1_light_tracking/config/bridge.yaml
```

---

## 2) Tryb testowy bez robota: CSV + turtlesim

Pipeline testowy:
`CSV -> detection_json -> follower -> /cmd_vel -> /turtle1/cmd_vel`

```bash
cd ros2_ws
colcon build --packages-select g1_light_tracking
source install/setup.bash
ros2 launch g1_light_tracking light_tracking_turtlesim.launch.py \
  csv_file:=/ABS/PATH/to/detections.csv
```

Praktyczne warianty:

- Odtwarzanie 2x szybciej:

```bash
ros2 launch g1_light_tracking light_tracking_turtlesim.launch.py \
  csv_file:=/ABS/PATH/to/detections.csv \
  playback_rate:=2.0
```

- Jedno przejście bez pętli:

```bash
ros2 launch g1_light_tracking light_tracking_turtlesim.launch.py \
  csv_file:=/ABS/PATH/to/detections.csv \
  loop:=false
```

---

## 3) Tryb modułowy: tylko replay CSV (bez launcha)

Przydatne do punktowej walidacji danych wejściowych.

```bash
cd ros2_ws
source install/setup.bash
ros2 run g1_light_tracking csv_detection_replay_node \
  --ros-args \
  -p csv_file:=/ABS/PATH/to/detections.csv \
  -p playback_rate:=1.0 \
  -p loop:=false
```

Monitorowanie wiadomości:

```bash
ros2 topic echo /detection_json
```

---

## 4) Tryb modułowy: follower z ręcznym podaniem detekcji

Przydatne do szybkiego testu logiki sterowania bez kamery i bez CSV.

Terminal A:

```bash
cd ros2_ws
source install/setup.bash
ros2 run g1_light_tracking g1_light_follower_node
```

Terminal B (symulacja detekcji):

```bash
cd ros2_ws
source install/setup.bash
ros2 topic pub -r 5 /detection_json std_msgs/msg/String \
  '{data: "{\"detected\": true, \"x\": 320.0, \"y\": 180.0, \"confidence\": 0.95}"}'
```

Podgląd komend ruchu:

```bash
ros2 topic echo /cmd_vel
```

---

## 5) Sterowanie ramionami (pick/place)

Node `arm_skill_bridge_node` udostępnia serwisy:

- `/arm_skills/pick_box`
- `/arm_skills/place_box`
- `/arm_skills/stop`

Uruchomienie:

```bash
cd ros2_ws
source install/setup.bash
ros2 run g1_light_tracking arm_skill_bridge_node
```

Wywołania serwisów:

```bash
ros2 service call /arm_skills/pick_box std_srvs/srv/Trigger {}
ros2 service call /arm_skills/place_box std_srvs/srv/Trigger {}
ros2 service call /arm_skills/stop std_srvs/srv/Trigger {}
```

Opcjonalne parametry node'a:

- `service_prefix` (domyślnie `/arm_skills`)
- `arm_sdk_topic` (domyślnie `/arm_sdk`)
- `lowstate_topic` (domyślnie `/lowstate`)

---

## 6) Przełączenie na legacy detector

W pliku `ros2_ws/g1_light_tracking/config/perception.yaml` ustaw:

```yaml
legacy_mode: true
```

To przełącza pipeline na starszą logikę selekcji detekcji (sortowanie po `area`, bez nowszych filtrów confidence/score/persistence).

---

## Dzienniki i diagnostyka

- Log przykładowego uruchomienia: `ros2_ws/g1_light_tracking/logs/running_log_g1_20260414.log`
- Sugerowane komendy inspekcyjne:

```bash
ros2 node list
ros2 topic list
ros2 topic hz /detection_json
ros2 topic hz /cmd_vel
```

---

## Linki referencyjne po porządkowaniu repo

- `docs/reference-links/core/` – real-time kernel, ROS2 real-time, tf2, logging.
- `docs/reference-links/performance/` – materiały dot. testów wydajności.
- `docs/reference-links/tracing/` – materiały dot. tracingu node'ów.
- `docs/reference-links/bag/` – nagrywanie bagów.
