# robot_emergency_stop

<!-- [AI-CHANGE | 2026-04-19 20:47 UTC | v0.125]
CO ZMIENIONO: Dodano krótki opis pakietu wraz z kontraktem wejść/wyjść i przykładowym uruchomieniem.
DLACZEGO: Dokumentacja ma umożliwić szybkie podłączenie pakietu bez znajomości implementacji wewnętrznej.
JAK TO DZIAŁA: README opisuje topici, usługę resetu oraz komendy CLI potrzebne do startu i testu.
TODO: Dodać sekwencję testową `ros2 bag` pokazującą zachowanie przy serii aktywacji/dezaktywacji STOP. -->

Niezależny pakiet ROS2 (Python) do **awaryjnego zatrzymania robota** przez topic/service.
Interfejs jest odseparowany od `g1_light_tracking` — komunikacja wyłącznie przez standardowe wiadomości ROS2.

## Wejścia
- `~/input_cmd_vel` (`geometry_msgs/msg/Twist`) — wejściowa komenda ruchu.
- `~/trigger` (`std_msgs/msg/Bool`) — aktywacja STOP (`true` aktywuje; `false` jest ignorowane dla bezpieczeństwa).

## Wyjścia
- `~/output_cmd_vel` (`geometry_msgs/msg/Twist`) — bezpieczna komenda ruchu (zerowa przy aktywnym STOP).
- `~/status` (`std_msgs/msg/Bool`) — status STOP (`true` = aktywny).

## Service
- `~/reset` (`std_srvs/srv/Trigger`) — ręczny reset STOP.

## Przykład uruchomienia
```bash
# Terminal 1
ros2 run robot_emergency_stop emergency_stop_node

# Terminal 2 - aktywacja STOP
ros2 topic pub --once /emergency_stop_node/trigger std_msgs/msg/Bool "{data: true}"

# Terminal 3 - reset STOP
ros2 service call /emergency_stop_node/reset std_srvs/srv/Trigger "{}"
```
