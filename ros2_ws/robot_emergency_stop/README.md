# robot_emergency_stop

<!--
[AI-CHANGE | 2026-04-19 22:17 UTC | v0.133]
CO ZMIENIONO: Przebudowano README do rozszerzonej wersji operacyjnej: dodano pełny opis kontraktu pakietu E-STOP,
  diagram przepływu, warianty konfiguracji, checklistę bezpieczeństwa, scenariusze testowe oraz instrukcję integracji krok po kroku
  z dowolnym programem ROS2 (bez zależności od `g1_light_tracking`).
DLACZEGO: Potrzebna jest dokumentacja, którą można bezpośrednio wykorzystać jako playbook wdrożeniowy w innych projektach.
  Dotychczasowy opis był poprawny, ale zbyt skrócony do szybkiej i powtarzalnej integracji między zespołami.
JAK TO DZIAŁA: README prowadzi od instalacji i uruchomienia standalone, przez mapowanie topiców, aż po walidację runtime i procedury
  awaryjne. Interfejs jest celowo mały (Twist/Bool/Empty/Trigger), co wspiera przenośność pakietu.
TODO: Dodać sekcję „Hardening dla produkcji” z gotowymi profilami QoS i przykładowymi politykami watchdog dla różnych klas robotów.
-->

Niezależny pakiet ROS2 (Python) do **awaryjnego zatrzymania ruchu robota**.

Priorytet bezpieczeństwa: **lepiej zatrzymać ruch niepotrzebnie, niż przepuścić błędną komendę**.

---

## 1. Co robi ten pakiet

`robot_emergency_stop` działa jako **bramka bezpieczeństwa** na torze `cmd_vel`:

- odbiera komendy wejściowe na `cmd_vel_in`,
- na podstawie sygnałów E-STOP decyduje, czy ruch jest dozwolony,
- publikuje bezpieczny wynik na `cmd_vel_out`.

Jeżeli warunki bezpieczeństwa nie są spełnione, węzeł publikuje zerowy `Twist`.

### Prosty model działania

```text
Controller/Planner ---> /cmd_vel_in --> [EmergencyStopNode] --> /cmd_vel_out ---> Robot bridge/driver
                              ^
                              |--- /estop_signal (Bool)
                              |--- /estop_heartbeat (Empty/Bool, opcjonalnie)
                              |--- /estop_arm (Bool, opcjonalnie)
```

---

## 2. Maszyna stanów

Pakiet używa dwóch stanów:

- `STOPPED` — ruch zablokowany (na wyjściu zero),
- `RUN_ALLOWED` — ruch może przechodzić na wyjście.

### Reguły bezpieczeństwa

1. `estop_signal == true` -> natychmiast `STOPPED`.
2. Jeśli `use_heartbeat=true` i heartbeat nie dotrze na czas -> `STOPPED`.
3. Jeśli `require_arm_to_clear=true` i `estop_arm=false` -> `STOPPED`.
4. Przejście do `RUN_ALLOWED` tylko wtedy, gdy wszystkie aktywne warunki są spełnione.

---

## 3. Interfejs publiczny (kontrakt pakietu)

## Topic wejściowe

- `/cmd_vel_in` (`geometry_msgs/msg/Twist`) — komenda ruchu do filtrowania.
- `/estop_signal` (`std_msgs/msg/Bool`) — główny sygnał E-STOP:
  - `true` = stop,
  - `false` = próba odblokowania.
- `/estop_heartbeat` (`std_msgs/msg/Empty` lub `std_msgs/msg/Bool`) — opcjonalny heartbeat.
- `/estop_arm` (`std_msgs/msg/Bool`) — opcjonalny sygnał arm.

## Topic wyjściowe

- `/cmd_vel_out` (`geometry_msgs/msg/Twist`) — komenda po filtrze bezpieczeństwa.

## Opcjonalne serwisy

- `/emergency_stop/trigger` (`std_srvs/srv/Trigger`) — ręczna aktywacja STOP.
- `/emergency_stop/clear` (`std_srvs/srv/Trigger`) — ręczna próba wyjścia ze STOP.

---

## 4. Parametry

| Parametr | Typ | Domyślnie | Znaczenie |
|---|---:|---:|---|
| `use_heartbeat` | bool | `false` | Czy heartbeat jest wymagany do RUN_ALLOWED |
| `heartbeat_msg_type` | string | `empty` | Typ heartbeat: `empty` albo `bool` |
| `heartbeat_timeout_s` | float | `0.5` | Maksymalny dopuszczalny brak heartbeat |
| `enable_trigger_services` | bool | `true` | Czy wystawiać serwisy trigger/clear |
| `require_arm_to_clear` | bool | `true` | Czy `estop_arm=true` jest wymagane do clear |

---

## 5. Szybki start

### 5.1 Build pakietu

```bash
cd ros2_ws
colcon build --packages-select robot_emergency_stop
source install/setup.bash
```

### 5.2 Uruchomienie node (standalone)

```bash
ros2 run robot_emergency_stop emergency_stop_node
```

### 5.3 Uruchomienie przez launch

```bash
ros2 launch robot_emergency_stop emergency_stop_standalone.launch.py
```

---

## 6. Integracja krok po kroku z innym programem ROS2

Poniższa procedura zakłada, że masz już istniejący system publikujący `/cmd_vel`.

### Krok 1 — Zidentyfikuj źródło komend ruchu

Sprawdź, który node publikuje aktualnie `/cmd_vel`:

```bash
ros2 topic info /cmd_vel
```

Jeśli jest wielu publisherów, ustal jeden „główny” tor sterowania lub wprowadź multiplexer **przed** E-STOP.

### Krok 2 — Wydziel tor „raw”

Źródło komend ruchu przełącz na topic pośredni, np. `/cmd_vel_raw`.

- wcześniej: `controller -> /cmd_vel`
- po zmianie: `controller -> /cmd_vel_raw`

To jest kluczowe, bo E-STOP ma być **ostatnią bramką** przed sterownikiem robota.

### Krok 3 — Dodaj `robot_emergency_stop` do launcha projektu

W swoim launchu uruchom node E-STOP i zrób remapping:

- `cmd_vel_in` -> `/cmd_vel_raw`
- `cmd_vel_out` -> `/cmd_vel`

Przykład fragmentu launch (`Python launch API`):

```python
Node(
    package='robot_emergency_stop',
    executable='emergency_stop_node',
    name='emergency_stop_node',
    output='screen',
    remappings=[
        ('cmd_vel_in', '/cmd_vel_raw'),
        ('cmd_vel_out', '/cmd_vel'),
    ],
    parameters=[{
        'use_heartbeat': True,
        'heartbeat_msg_type': 'empty',
        'heartbeat_timeout_s': 0.5,
        'enable_trigger_services': True,
        'require_arm_to_clear': True,
    }],
)
```

### Krok 4 — Podłącz sygnał E-STOP

Wybierz źródło `estop_signal`:

- fizyczny przycisk bezpieczeństwa,
- safety PLC,
- supervisor node,
- panel operatorski.

Wariant minimalny (manualny):

```bash
# STOP
ros2 topic pub --once /estop_signal std_msgs/msg/Bool "{data: true}"

# Próba odblokowania
ros2 topic pub --once /estop_signal std_msgs/msg/Bool "{data: false}"
```

### Krok 5 — (Opcjonalnie) Włącz watchdog heartbeat

Jeżeli system nadrzędny ma watchdog, włącz heartbeat:

- ustaw `use_heartbeat=true`,
- publikuj `/estop_heartbeat` cyklicznie częściej niż `heartbeat_timeout_s`.

Przykład heartbeat 10 Hz:

```bash
ros2 topic pub -r 10 /estop_heartbeat std_msgs/msg/Empty "{}"
```

### Krok 6 — (Opcjonalnie) Wymuś arm przed clear

Jeżeli chcesz uniknąć przypadkowego wznowienia ruchu:

- zostaw `require_arm_to_clear=true`,
- publikuj `estop_arm=true` dopiero po świadomej autoryzacji operatora.

Przykład:

```bash
ros2 topic pub --once /estop_arm std_msgs/msg/Bool "{data: true}"
```

### Krok 7 — Zweryfikuj zachowanie runtime

1. Podaj niezerowy `cmd_vel_in` i sprawdź, czy bez clear wyjście jest zerowane.
2. Aktywuj `RUN_ALLOWED` i sprawdź, czy `cmd_vel_in` przechodzi na `cmd_vel_out`.
3. Zasymuluj timeout heartbeat (wyłącz publisher heartbeat) i potwierdź powrót do `STOPPED`.

Komendy pomocnicze:

```bash
ros2 topic echo /cmd_vel_out
ros2 service call /emergency_stop/trigger std_srvs/srv/Trigger "{}"
ros2 service call /emergency_stop/clear std_srvs/srv/Trigger "{}"
```

---

## 7. Przykładowy scenariusz integracji „controller + driver”

```text
[controller_node] --/cmd_vel_raw--> [robot_emergency_stop] --/cmd_vel--> [robot_driver_bridge]
                                   ^
                                   +-- /estop_signal  (z safety panelu)
                                   +-- /estop_heartbeat (z supervisora)
                                   +-- /estop_arm (z HMI)
```

### Zalecenie architektoniczne

Nie podłączaj drivera robota bezpośrednio pod `/cmd_vel_raw`.
Jedyny topic podawany do drivera to `cmd_vel_out` z E-STOP.

---

## 8. Diagnostyka i najczęstsze problemy

### Problem: robot nie rusza mimo `estop_signal=false`

Sprawdź kolejno:

1. Czy node działa i publikuje logi przejść stanu.
2. Czy nie ma timeout heartbeat (`use_heartbeat=true`).
3. Czy przy `require_arm_to_clear=true` masz `estop_arm=true`.
4. Czy inne nody nie nadpisują `/cmd_vel` poza E-STOP.

### Problem: clear przez serwis zawsze odrzucany

Najczęściej przyczyna to aktywny warunek bezpieczeństwa (brak arm/heartbeat).
Sprawdź parametry i aktualne topici wejściowe.

---

## 9. Minimalna checklista produkcyjna

- [ ] E-STOP jest ostatnią bramką na torze ruchu.
- [ ] Driver robota czyta wyłącznie `cmd_vel_out`.
- [ ] Timeout heartbeat przetestowany (wymuszony brak heartbeat).
- [ ] Operator ma jednoznaczny mechanizm `trigger` i kontrolowany `clear`.
- [ ] Logi przejść stanów są zbierane i archiwizowane.

---

## 10. Licencja

Apache-2.0
