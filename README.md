# ROS2 Unitree G1 light tracking PoC

<!--
[AI-CHANGE | 2026-04-27 09:51 UTC | v0.203]
CO ZMIENIONO: Zastąpiono rozbudowaną treść README wersją skróconą zawierającą tylko opis pakietu, szybki start (headless/UI), uruchomienie testu E2E oraz zestaw kluczowych linków do dokumentów operacyjnych.
DLACZEGO: Uproszczenie README skraca czas wejścia do projektu i usuwa nadmiarowe opisy backlogowe oraz długie notatki procesowe, zgodnie z wymaganiem użytkownika.
JAK TO DZIAŁA: README działa jako krótki punkt startowy — użytkownik dostaje minimalny kontekst projektu, dwie ścieżki uruchomienia i bezpośrednie odnośniki do dokumentacji szczegółowej.
TODO: Dodać w README krótki diagram przepływu uruchomienia (detekcja -> decyzja -> sterowanie) jako ściągę dla nowych członków zespołu.
-->

## 1. Czym jest pakiet

`alf-light-tracking` to pakiet ROS2 do śledzenia plamki światła dla robota Unitree G1, z trybami uruchomienia zarówno na robocie, jak i lokalnie (symulacja/testy). Priorytet jakościowy projektu: **lepiej odrzucić niepewną detekcję niż zwrócić wynik błędny**.

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



<!--
[AI-CHANGE | 2026-04-30 14:15 UTC | v0.201]
CO ZMIENIONO: Dodano sekcję statusu funkcji „Mapa” po wdrożeniu aktywnej nawigacji i bezpiecznego renderowania danych mapowych.
DLACZEGO: README miał skrócony start, ale brakowało informacji operacyjnej o nowym zachowaniu zakładki Mapa.
JAK TO DZIAŁA: Sekcja opisuje aktywny przycisk Mapa, zasady walidacji jakości i bezpieczny fallback `BRAK DANYCH`.
TODO: Dodać zrzut ekranu zakładki Mapa z przykładami statusów VALID/UNAVAILABLE po stabilizacji pipeline UI.
-->

## 5. Status funkcji „Mapa” w Mission Control

- Przycisk **Mapa** w lewym panelu GUI jest aktywny i przełącza do zakładki mapy.
- Zakładka renderuje pozycję wyłącznie dla danych `VALID`; dla jakości niepewnej pokazuje `BRAK DANYCH`.
- Dla typowych problemów (`MAP_TF_MISSING`, `MAP_POSE_STALE`, `MAP_FRAME_MISMATCH`) UI prezentuje wskazówki operatorskie.

> Zasada bezpieczeństwa: jeśli dane lokalizacyjne są niepewne, system preferuje brak wyniku zamiast fałszywej pozycji.
