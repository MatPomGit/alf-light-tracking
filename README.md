# ROS2 Unitree G1 light tracking PoC

## 1. Czym jest pakiet

`alf-light-tracking` to pakiet ROS2 do śledzenia plamki światła dla robota Unitree G1, z trybami uruchomienia zarówno na robocie, jak i lokalnie (symulacja/testy).

## 2. Szybki start (headless/UI)

### Headless (CLI)

```bash
cd ros2_ws
colcon build --packages-select g1_light_tracking robot_mission_control
source install/setup.bash
ros2 launch g1_light_tracking light_tracking_stack.launch.py
```

### UI (Mission Control)

```bash
cd ros2_ws
colcon build --packages-select robot_mission_control
source install/setup.bash
ros2 launch robot_mission_control mission_control.launch.py
```

## 3. Jak uruchomić test E2E

```bash
cd ros2_ws
colcon test --packages-select robot_mission_control --event-handlers console_direct+
colcon test-result --verbose
```

## 4. Linki

- Zadania: [`ros2_ws/robot_mission_control/TASKS.md`](ros2_ws/robot_mission_control/TASKS.md)
- Plan wdrożenia: [`ros2_ws/robot_mission_control/DEPLOYMENT_PLAN.md`](ros2_ws/robot_mission_control/DEPLOYMENT_PLAN.md)
- Runbook: [`docs/operator/incident_runbook.md`](docs/operator/incident_runbook.md)
- Macierz środowisk: [`docs/spec/hard_environment_matrix.md`](docs/spec/hard_environment_matrix.md)

## 5. Status funkcji „Mapa” w Mission Control

- Przycisk **Mapa** w lewym panelu GUI jest aktywny i przełącza do zakładki mapy.
- Zakładka renderuje pozycję wyłącznie dla danych `VALID`; dla jakości niepewnej pokazuje `BRAK DANYCH`.
- Dla typowych problemów (`MAP_TF_MISSING`, `MAP_POSE_STALE`, `MAP_FRAME_MISMATCH`) UI prezentuje wskazówki operatorskie.

> Zasada bezpieczeństwa: jeśli dane lokalizacyjne są niepewne, system preferuje brak wyniku zamiast fałszywej pozycji.
