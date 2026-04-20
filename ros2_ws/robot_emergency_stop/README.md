# robot_emergency_stop

<!--
[AI-CHANGE | 2026-04-20 06:19 UTC | v0.134]
CO ZMIENIONO: Przepisano README na wersję „handover-friendly” dla nowych osób w zespole: dodano sekcję TL;DR,
  słownik pojęć, szybkie scenariusze (minimalny i produkcyjny), checklistę „5 minut przed demo”, oraz prostsze,
  bardziej jednoznaczne kroki integracji z innym programem ROS2.
DLACZEGO: Użytkownik wskazał potrzebę łatwego przekazania modułu innym osobom; poprzednia wersja była poprawna,
  ale zbyt rozbudowana i mniej przystępna dla szybkiego onboardingu.
JAK TO DZIAŁA: Dokument prowadzi czytelnika od „co to jest” -> „jak uruchomić” -> „jak zintegrować” ->
  „jak sprawdzić, że działa bezpiecznie”. Każdy etap ma krótki cel, gotowe komendy i oczekiwany efekt.
TODO: Dodać mini-FAQ z realnymi logami z testów poligonowych (przykłady dobrych i błędnych integracji).
-->

Niezależny pakiet ROS2 (Python) do **awaryjnego zatrzymania ruchu robota**.

> Zasada bezpieczeństwa: **lepiej zatrzymać ruch niepotrzebnie, niż przepuścić błędną komendę**.

---

## TL;DR (dla osoby przejmującej moduł)

- Ten pakiet jest **bramką bezpieczeństwa** pomiędzy kontrolerem a driverem robota.
- Wejście ruchu: `/cmd_vel_in`.
- Wyjście ruchu: `/cmd_vel_out`.
- Gdy E-STOP aktywny lub warunki bezpieczeństwa niespełnione -> na wyjściu idzie **zerowy `Twist`**.
- Integracja z innym systemem ROS2 polega głównie na remappingu:
  - `cmd_vel_in` <- `/cmd_vel_raw`
  - `cmd_vel_out` -> `/cmd_vel`

---

## 1) Co robi moduł i gdzie go wpiąć

Pakiet należy umieścić jako **ostatni element toru sterowania ruchem**:

```text
controller/planner -> /cmd_vel_raw -> [robot_emergency_stop] -> /cmd_vel -> robot_driver
```

### Dlaczego „ostatni element”?

Bo tylko wtedy masz gwarancję, że każda komenda ruchu przechodzi przez filtr bezpieczeństwa.

---

## 2) Krótki słownik pojęć

- **E-STOP** — wymuszenie zatrzymania ruchu.
- **Heartbeat** — sygnał „żyję”, który potwierdza, że nadzorca działa.
- **Arm** — sygnał potwierdzający gotowość/autoryzację do odblokowania ruchu.
- **STOPPED** — stan blokady ruchu.
- **RUN_ALLOWED** — stan, w którym ruch może przejść na wyjście.

---

## 3) Interfejs pakietu (publiczny kontrakt)

## Topic wejściowe

- `/cmd_vel_in` (`geometry_msgs/msg/Twist`) — komenda ruchu do filtrowania.
- `/estop_signal` (`std_msgs/msg/Bool`) — główny sygnał bezpieczeństwa:
  - `true` -> natychmiast STOP,
  - `false` -> próba odblokowania.
- `/estop_heartbeat` (`std_msgs/msg/Empty` lub `std_msgs/msg/Bool`) — opcjonalny heartbeat.
- `/estop_arm` (`std_msgs/msg/Bool`) — opcjonalny sygnał arm.

## Topic wyjściowe

- `/cmd_vel_out` (`geometry_msgs/msg/Twist`) — bezpieczna komenda ruchu po filtrze.

## Opcjonalne serwisy

- `/emergency_stop/trigger` (`std_srvs/srv/Trigger`) — ręczna aktywacja STOP.
- `/emergency_stop/clear` (`std_srvs/srv/Trigger`) — próba wyjścia ze STOP.

---

## 4) Logika bezpieczeństwa w jednym miejscu

Node przechodzi do `RUN_ALLOWED` tylko, gdy:

1. `estop_signal == false`,
2. jeśli heartbeat jest włączony: heartbeat jest świeży,
3. jeśli arm jest wymagany: `estop_arm == true`.

W każdej innej sytuacji: `STOPPED` + publikacja zerowego `Twist`.

---

## 5) Parametry

| Parametr | Typ | Domyślnie | Znaczenie |
|---|---:|---:|---|
| `use_heartbeat` | bool | `false` | Czy heartbeat jest wymagany do RUN_ALLOWED |
| `heartbeat_msg_type` | string | `empty` | Typ heartbeat: `empty` albo `bool` |
| `heartbeat_timeout_s` | float | `0.5` | Maksymalny dopuszczalny brak heartbeat |
| `enable_trigger_services` | bool | `true` | Czy wystawiać serwisy trigger/clear |
| `require_arm_to_clear` | bool | `true` | Czy `estop_arm=true` jest wymagane do clear |

---

## 6) Szybki start (3 komendy)

```bash
cd ros2_ws
colcon build --packages-select robot_emergency_stop
source install/setup.bash
```

Uruchomienie node:

```bash
ros2 run robot_emergency_stop emergency_stop_node
```

Uruchomienie przez launch:

```bash
ros2 launch robot_emergency_stop emergency_stop_standalone.launch.py
```

---

## 7) Integracja krok po kroku z innym programem ROS2

To jest rekomendowana procedura do przekazania innym zespołom.

### Krok 1 — Przenieś obecny `/cmd_vel` na `/cmd_vel_raw`

W systemie nadrzędnym (controller/planner):

- było: publikacja na `/cmd_vel`,
- ma być: publikacja na `/cmd_vel_raw`.

### Krok 2 — Uruchom E-STOP z remappingiem

W launchu programu docelowego dodaj:

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
)
```

### Krok 3 — Podłącz źródło `estop_signal`

Minimalnie możesz użyć ręcznej publikacji:

```bash
# STOP
ros2 topic pub --once /estop_signal std_msgs/msg/Bool "{data: true}"

# Próba odblokowania
ros2 topic pub --once /estop_signal std_msgs/msg/Bool "{data: false}"
```

Docelowo podłącz fizyczny przycisk, PLC albo supervisor node.

### Krok 4 — (Opcjonalnie) włącz heartbeat

Jeśli chcesz watchdog:

- ustaw `use_heartbeat=true`,
- publikuj heartbeat cyklicznie częściej niż timeout.

Przykład:

```bash
ros2 topic pub -r 10 /estop_heartbeat std_msgs/msg/Empty "{}"
```

### Krok 5 — (Opcjonalnie) wymagaj `arm` przed clear

Zostaw `require_arm_to_clear=true` i podawaj `estop_arm=true` tylko po świadomej autoryzacji.

```bash
ros2 topic pub --once /estop_arm std_msgs/msg/Bool "{data: true}"
```

### Krok 6 — Weryfikacja po integracji

1. Bez clear: niezerowy `cmd_vel_in` -> na `cmd_vel_out` powinno być zero.
2. Po spełnieniu warunków: `cmd_vel_in` powinno przejść na `cmd_vel_out`.
3. Po wyłączeniu heartbeat (gdy wymagany): system wraca do `STOPPED`.

Komendy pomocnicze:

```bash
ros2 topic echo /cmd_vel_out
ros2 service call /emergency_stop/trigger std_srvs/srv/Trigger "{}"
ros2 service call /emergency_stop/clear std_srvs/srv/Trigger "{}"
```

---

## 8) Dwa gotowe profile wdrożenia

## A) Profil minimalny (szybkie uruchomienie)

- `use_heartbeat=false`
- `require_arm_to_clear=false`

Dobre do lokalnych testów integracyjnych.

## B) Profil produkcyjny (zalecany)

- `use_heartbeat=true`
- `require_arm_to_clear=true`
- `heartbeat_timeout_s` dobrany do cyklu systemu nadrzędnego

Dobre do pracy z realnym robotem i nadzorem operatora.

---

## 9) Checklista „5 minut przed demo”

- [ ] Driver robota czyta wyłącznie `/cmd_vel` z wyjścia E-STOP.
- [ ] Źródło sterowania publikuje na `/cmd_vel_raw`.
- [ ] `estop_signal=true` zatrzymuje robota natychmiast.
- [ ] `clear` bez arm/heartbeat (jeśli wymagane) jest odrzucane.
- [ ] Logi przejść stanu są widoczne i zrozumiałe dla operatora.

---

## 10) Najczęstsze problemy

### „Robot nie rusza mimo estop_signal=false”

Najczęściej przyczyna:
- brak heartbeat (gdy `use_heartbeat=true`),
- brak `estop_arm=true` (gdy `require_arm_to_clear=true`),
- błędny remapping (`cmd_vel_in/cmd_vel_out`).

### „Robot rusza mimo oczekiwanego STOP”

To zwykle oznacza, że driver dostaje komendy z innego topicu niż `/cmd_vel_out`.
Sprawdź, czy E-STOP jest naprawdę ostatnią bramką w torze.

---

## 11) Licencja

Apache-2.0
