# ROS2 Unitree G1 light tracking PoC

## Tryb 1: Robot (Unitree)

```bash
colcon build
source install/setup.bash
ros2 launch g1_light_tracking light_tracking_stack.launch.py
```

## Tryb 2: Test bez robota (CSV + turtlesim)

Masz CSV z detekcjami, wiec pipeline testowy jest:
`CSV -> detection_json -> follower -> /cmd_vel -> /turtle1/cmd_vel`

Uruchom:

```bash
colcon build
source install/setup.bash
ros2 launch g1_light_tracking light_tracking_turtlesim.launch.py csv_file:=/ABS/PATH/to/detections.csv
```

Opcjonalnie:
- `playback_rate:=2.0` (2x szybciej)
- `loop:=false` (jedno przejscie)

## Uwagi

- `light_spot_detector_node` jest placeholderem pod Twoj kod wizyjny.
- W trybie turtlesim nie potrzebujesz robota ani topicu `api/sport/request`.
- Domyslny `k_angular` w `control.yaml` jest ustawiony pod `x` z CSV (wartosci pikselowe).

## Sterowanie ramionami (pick/place)

Node `arm_skill_bridge_node` udostepnia serwisy:
- `/arm_skills/pick_box`
- `/arm_skills/place_box`
- `/arm_skills/stop`

Uruchomienie:

```bash
colcon build
source install/setup.bash
ros2 run g1_light_tracking arm_skill_bridge_node
```

Wywolania:

```bash
ros2 service call /arm_skills/pick_box std_srvs/srv/Trigger {}
ros2 service call /arm_skills/place_box std_srvs/srv/Trigger {}
ros2 service call /arm_skills/stop std_srvs/srv/Trigger {}
```

Opcjonalne parametry:
- `service_prefix` (domyslnie `/arm_skills`)
- `arm_sdk_topic` (domyslnie `/arm_sdk`)
- `lowstate_topic` (domyslnie `/lowstate`)

## Przelaczenie na stary tryb detekcji plamki

W pliku `src/g1_light_tracking/config/perception.yaml` ustaw:

```yaml
legacy_mode: true
```

To uruchamia stary algorytm (sortowanie po polu `area`, bez filtrow confidence/score i bez filtra persistence).
