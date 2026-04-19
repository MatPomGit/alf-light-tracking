# robot_emergency_stop

<!-- [AI-CHANGE | 2026-04-19 22:02 UTC | v0.129]
CO ZMIENIONO: Zaktualizowano kontrakt interfejsu pakietu pod maszynę stanów `STOPPED`/`RUN_ALLOWED`.
  Doprecyzowano `estop_signal` jako główny interfejs produkcyjny oraz opisano opcjonalne serwisy
  `/emergency_stop/trigger` i `/emergency_stop/clear` z ochroną heartbeat/arm.
DLACZEGO: Dokumentacja musi odpowiadać aktualnej implementacji i jasno rozróżniać interfejs podstawowy
  (topic) od pomocniczego (service), aby integracja między projektami była szybka i bezpieczna.
JAK TO DZIAŁA: Integrator publikuje `estop_signal`, a serwisy Trigger może włączyć/wyłączyć parametrem.
  `clear` przechodzi tylko przy spełnieniu reguł bezpieczeństwa; inaczej node pozostaje w STOPPED.
TODO: Dodać diagram sekwencji pokazujący wszystkie powody przejść stanu i oczekiwane logi. -->

Niezależny pakiet ROS2 (Python) do **awaryjnego zatrzymania robota**.

## Prosta maszyna stanów
- `STOPPED` — ruch zablokowany, na `cmd_vel_out` publikowane jest zero.
- `RUN_ALLOWED` — ruch może przechodzić z `cmd_vel_in` na `cmd_vel_out`.

Każde przejście między stanami jest logowane z konkretnym powodem (np. `manual_trigger`, `heartbeat_timeout`, `signal_false`).

## Interfejsy topic
### Wejścia
- `cmd_vel_in` (`geometry_msgs/msg/Twist`) — wejściowa komenda ruchu.
- `estop_signal` (`std_msgs/msg/Bool`) — **główny interfejs produkcyjny**:
  - `true` => natychmiastowy STOP,
  - `false` => próba przejścia do `RUN_ALLOWED` (tylko gdy warunki bezpieczeństwa są spełnione).
- `estop_heartbeat` (`std_msgs/msg/Empty` lub `std_msgs/msg/Bool`) — opcjonalny heartbeat.
- `estop_arm` (`std_msgs/msg/Bool`) — sygnał arm wymagany przy `clear` (gdy `require_arm_to_clear=true`).

### Wyjścia
- `cmd_vel_out` (`geometry_msgs/msg/Twist`) — bezpieczna komenda ruchu.

## Opcjonalne serwisy (`std_srvs/srv/Trigger`)
- `/emergency_stop/trigger` — ręczne wymuszenie stanu `STOPPED`.
- `/emergency_stop/clear` — próba przejścia do `RUN_ALLOWED`.
  - `clear` jest zabezpieczone: jeśli heartbeat/arm nie spełnia warunków, żądanie zostaje odrzucone.

## Parametry
- `use_heartbeat` (bool, domyślnie: `false`)
- `heartbeat_msg_type` (`empty` albo `bool`, domyślnie: `empty`)
- `heartbeat_timeout_s` (float, domyślnie: `0.5`)
- `enable_trigger_services` (bool, domyślnie: `true`)
- `require_arm_to_clear` (bool, domyślnie: `true`)

<!-- [AI-CHANGE | 2026-04-19 22:13 UTC | v0.133]
CO ZMIENIONO: Dodano opis polityki bezpieczeństwa heartbeat = brak heartbeat oznacza STOP.
DLACZEGO: W projekcie obowiązuje zasada „brak ruchu lepszy niż błędny ruch”, więc brak sygnału musi wymuszać blokadę ruchu.
JAK TO DZIAŁA: Jeśli heartbeat nie nadejdzie w `heartbeat_timeout_s`, node przechodzi do `STOPPED` i publikuje zerowe `cmd_vel_out`.
TODO: Dodać tabelę stanów z czasami granicznymi heartbeat oraz przykładowymi logami diagnostycznymi. -->
## Polityka bezpieczeństwa heartbeat
- **Brak sygnału heartbeat = STOP**.
- W konfiguracji konserwatywnej ruch startuje zablokowany (`start_in_stop: true`) i może zostać dopuszczony dopiero po spełnieniu warunku heartbeat.
- Utrata heartbeat (timeout) jest traktowana jako niepewność systemu, dlatego ruch jest natychmiast blokowany.
- Ta polityka realizuje zasadę: **lepiej zatrzymać robota niż dopuścić potencjalnie błędny ruch**.

## Przykład uruchomienia
```bash
# Terminal 1
ros2 run robot_emergency_stop emergency_stop_node

# Terminal 2 - aktywacja STOP przez główny interfejs produkcyjny
ros2 topic pub --once /estop_signal std_msgs/msg/Bool "{data: true}"

# Terminal 3 - próba clear przez serwis
ros2 service call /emergency_stop/clear std_srvs/srv/Trigger "{}"
```
