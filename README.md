# ROS2 Unitree G1 light tracking PoC

<!--
[AI-CHANGE | 2026-04-17 12:04 UTC | v0.80]
CO ZMIENIONO: Przebudowano README do formatu operacyjnego oraz poprawiono nieaktualne odwołania ścieżek w przykładzie uruchomienia (zamieniono na ścieżki zgodne z układem `ros2_ws/g1_light_tracking`).
DLACZEGO: Dotychczasowy opis był skrócony i utrudniał szybkie wejście nowej osoby do projektu, a pozostawione nieaktualne ścieżki mogły wprowadzać w błąd podczas uruchamiania.
JAK TO DZIAŁA: README prowadzi użytkownika krok po kroku: od przygotowania środowiska, przez budowanie pakietu, po uruchamianie konkretnych node'ów i launchy z parametrami. Wszystkie przykładowe ścieżki są teraz spójne z aktualną strukturą repozytorium.
TODO: Dodać sekcję "Troubleshooting" z typowymi błędami ROS2 (DDS, QoS, uprawnienia urządzeń), oraz tabelę mapującą importy Pythona na wymagane zależności systemowe/pip.
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
    ├── g1_light_tracking/
        ├── config/
        ├── g1_light_tracking/
        ├── launch/
        ├── logs/
        ├── package.xml
        ├── requirements.txt
        └── setup.py
    └── robot_mission_control/
        ├── config/
        ├── launch/
        ├── package.xml
        ├── robot_mission_control/
        └── setup.py
```

### Co gdzie jest

<!--
[AI-CHANGE | 2026-04-21 12:10 UTC | v0.167]
CO ZMIENIONO: Rozszerzono README główne o pakiet operatorski `robot_mission_control` przeniesiony do `ros2_ws/`.
DLACZEGO: Po relokacji pakiet musi być widoczny jako część workspace budowanego przez `colcon`.
JAK TO DZIAŁA: Dokument wskazuje nową lokalizację i komendy uruchomienia `ros2 launch robot_mission_control mission_control.launch.py`.
TODO: Dodać osobny diagram przepływu danych między `g1_light_tracking`, `robot_emergency_stop` i `robot_mission_control`.
-->
- `ros2_ws/g1_light_tracking/g1_light_tracking/` – node'y ROS2 (detekcja, follower, bridge, replay CSV, arm skills).
- `ros2_ws/g1_light_tracking/launch/` – gotowe scenariusze uruchomień (`*.launch.py`).
- `ros2_ws/g1_light_tracking/config/` – konfiguracja percepcji, sterowania i bridge.
- `docs/reference-links/` – uporządkowane linki pomocnicze (RT, tf2, tracing, bag recording).
- `ros2_ws/robot_mission_control/` – desktopowy pakiet operatorski ROS2 do monitorowania stanu robota.

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
  control_config:=ros2_ws/g1_light_tracking/config/control.yaml \
  bridge_config:=ros2_ws/g1_light_tracking/config/bridge.yaml
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


<!--
[AI-CHANGE | 2026-04-17 13:32 UTC | v0.109]
CO ZMIENIONO: Dodano sekcję operacyjną opisującą minimalną integrację narzędzia kalibracji percepcji z nagrania wzorcowego oraz checklistę walidacji po kalibracji.
DLACZEGO: Użytkownik potrzebuje krótkiej i praktycznej instrukcji uruchomienia kalibratora oraz kryteriów oceny jakości wyniku względem konfiguracji bazowej.
JAK TO DZIAŁA: Sekcja podaje gotową komendę CLI, wyjaśnia znaczenie plików `perception.yaml` i raportu Markdown oraz sugeruje wymagania dla materiału referencyjnego. Checklista prowadzi przez walidację na innym fragmencie, aby ograniczyć ryzyko false-positive.
TODO: Dodać tabelę z progami akceptacji (np. max false-positive/min recall) dla różnych scen testowych i warunków oświetlenia.
-->

## Kalibracja percepcji z nagrania wzorcowego

Minimalny przebieg (uruchomienie z katalogu repozytorium):

```bash
python3 ros2_ws/g1_light_tracking/tools/calibrate_perception.py \
  --video ros2_ws/g1_light_tracking/tools/video.mp4 \
  --base-config ros2_ws/g1_light_tracking/config/perception.yaml \
  --output-config ros2_ws/g1_light_tracking/config/perception.yaml \
  --output-report ros2_ws/g1_light_tracking/logs/perception_calibration_report.md
```

Pliki wynikowe:

- `perception.yaml` – końcowa konfiguracja progów detekcji używana przez node detektora.
  Narzędzie zachowuje tryb bezpieczny: gdy kalibracja jest niewiarygodna, utrzymuje wartości bazowe (preferencja odrzucenia próbki zamiast błędnej detekcji).
- raport (`perception_calibration_report.md`) – podsumowanie statystyk próbki, status wiarygodności i uzasadnienie decyzji o zastosowaniu lub odrzuceniu nowych progów.

Zalecenia dla nagrania referencyjnego:

- nagranie powinno zawierać zarówno poprawne trafienia plamki, jak i trudne tło (odbicia, prześwietlenia),
- utrzymaj stabilne parametry kamery (ekspozycja/ISO/balans bieli) zgodne z docelowym deploymentem,
- unikaj zbyt krótkich klipów; materiał musi mieć reprezentatywną liczbę klatek dla stabilnych statystyk kalibracji,
- po każdej istotnej zmianie optyki, pozycji kamery lub oświetlenia wykonaj rekalibrację.

### Checklista walidacji po kalibracji

- [ ] Uruchom detektor na **innym** fragmencie nagrania niż materiał kalibracyjny i potwierdź stabilność wyniku.
- [ ] Porównaj względem konfiguracji bazowej liczbę odrzuceń (`detected=false`/brak publikacji) oraz false-positive.
- [ ] Jeśli false-positive rosną lub wynik jest niestabilny, wróć do konfiguracji bazowej i powtórz kalibrację na lepszej próbce.

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

<!--
[AI-CHANGE | 2026-04-17 15:53 UTC | v0.120]
CO ZMIENIONO: Rozbudowano README o sekcję przepływu danych, tabelę kluczowych node'ów, tabelę parametrów startowych oraz troubleshooting.
DLACZEGO: Brakowało szybkiego kontekstu operacyjnego i mapy zależności runtime, co utrudniało diagnozowanie błędów oraz onboarding.
JAK TO DZIAŁA: Nowe sekcje porządkują uruchomienie od warstwy danych (kamera/CSV) przez detekcję do sterowania oraz podają gotowe kroki naprawcze dla najczęstszych awarii.
TODO: Dodać automatycznie generowaną tabelę parametrów z plików YAML/launch, aby uniknąć ręcznej niespójności dokumentacji.
-->

## Przepływ danych (skrót architektury runtime)

```text
/camera/image_raw (D435i) lub CSV replay
            |
            v
light_spot_detector_node -> /light_tracking/detection_json
            |
            v
g1_light_follower_node -> /cmd_vel
            |
            +--> unitree_cmd_vel_bridge_node -> kanał sterowania robota
            \--> turtlesim_cmd_vel_bridge_node -> /turtle1/cmd_vel (symulacja)
```

To jest pipeline preferowany dla walidacji: najpierw potwierdź poprawność detekcji (`detection_json`), dopiero potem analizuj sterowanie.

## Kluczowe node'y i odpowiedzialności

| Node | Wejście | Wyjście | Zastosowanie |
|---|---|---|---|
| `light_spot_detector_node` | `/camera/image_raw` | `/light_tracking/detection_json` | Wykrywanie plamki i filtrowanie niepewnych detekcji. |
| `g1_light_follower_node` | `/light_tracking/detection_json` | `/cmd_vel` | Zamiana pozycji celu na komendy ruchu. |
| `unitree_cmd_vel_bridge_node` | `/cmd_vel` | interfejs Unitree | Mostek do robota w trybie online. |
| `turtlesim_cmd_vel_bridge_node` | `/cmd_vel` | `/turtle1/cmd_vel` | Symulacyjne testy bez sprzętu. |
| `csv_detection_replay_node` | CSV | `/light_tracking/detection_json` | Odtwarzanie datasetu detekcji offline. |
| `arm_skill_bridge_node` | serwisy Trigger | kanał arm SDK | Proste akcje pick/place/stop dla manipulatora. |

## Najważniejsze parametry startowe

| Parametr | Gdzie | Domyślnie | Uwagi operacyjne |
|---|---|---|---|
| `playback_rate` | `csv_detection_replay_node` | `1.0` | Używaj wartości `> 0`; wartości niepoprawne są korygowane do `1.0`. |
| `loop` | `csv_detection_replay_node` | `true` | `false` kończy replay po ostatnim rekordzie. |
| `control_config` | `light_tracking_stack.launch.py` | `config/control.yaml` | Strojenie followera i ograniczeń prędkości. |
| `bridge_config` | `light_tracking_stack.launch.py` | `config/bridge.yaml` | Parametry transportu komend do Unitree. |
| `legacy_mode` | `config/perception.yaml` | `false` | `true` włącza starszy tryb selekcji detekcji. |

## Troubleshooting (najczęstsze problemy)

1. **Brak publikacji na `/light_tracking/detection_json`**
   - sprawdź, czy działa źródło obrazu: `ros2 topic hz /camera/image_raw`,
   - zweryfikuj konfigurację percepcji i ROI (`config/perception.yaml`),
   - uruchom tryb CSV, aby odseparować problem kamery od problemu detektora.

2. **Follower publikuje zero lub niestabilne `/cmd_vel`**
   - podejrzyj payload: `ros2 topic echo /light_tracking/detection_json`,
   - sprawdź progi confidence/rank oraz deadband w `control.yaml`,
   - przy niestabilnej detekcji najpierw popraw percepcję (zgodnie z zasadą odrzucania niepewnych danych).

3. **CSV replay nie startuje**
   - upewnij się, że parametr `csv_file` wskazuje istniejący plik,
   - sprawdź, czy kolumna `time_sec` zawiera poprawne liczby,
   - uruchom z `loop:=false`, by łatwiej analizować pojedyncze przejście logu.

4. **Brak ruchu robota Unitree mimo `/cmd_vel`**
   - zweryfikuj topic i typ wiadomości mostka (`unitree_cmd_vel_bridge_node`),
   - sprawdź konfigurację połączenia/namespace w `bridge.yaml`,
   - porównaj z trybem turtlesim, aby potwierdzić, że problem dotyczy wyłącznie warstwy bridge.

---

## Linki referencyjne po porządkowaniu repo

- `docs/reference-links/core/` – real-time kernel, ROS2 real-time, tf2, logging.
- `docs/reference-links/performance/` – materiały dot. testów wydajności.
- `docs/reference-links/tracing/` – materiały dot. tracingu node'ów.
- `docs/reference-links/bag/` – nagrywanie bagów.


## 7) Monitorowanie operatora: robot_mission_control

```bash
cd ros2_ws
colcon build --packages-select robot_mission_control
source install/setup.bash
ros2 launch robot_mission_control mission_control.launch.py
```
