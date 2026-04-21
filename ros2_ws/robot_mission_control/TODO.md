<!--
[AI-CHANGE | 2026-04-21 10:44 UTC | v0.171]
CO ZMIENIONO: Rozszerzono TODO o dalsze zadania po wdrożeniu backendu ROS2 Action wraz ze statusami i planem sprintów.
DLACZEGO: Potrzebny jest aktualny, operacyjny backlog pokazujący co już wykonano oraz jakie są kolejne kroki wysokiego priorytetu.
JAK TO DZIAŁA: Dokument zawiera statusy (`DONE/IN_PROGRESS/TODO`), listę zadań technicznych i kryteria akceptacji na kolejne etapy.
TODO: Zintegrować ten backlog z narzędziem issue-tracking i automatycznie synchronizować statusy z PR.
-->

# TODO — robot_mission_control

## Założenie bezpieczeństwa (nadrzędne)
- **Zasada obowiązkowa:** lepiej zwrócić `UNAVAILABLE`/brak wyniku niż pokazać operatorowi wynik niepewny lub błędny.
- Wszystkie nowe integracje muszą mapować jakość danych do jednego z: `VALID`, `STALE`, `UNAVAILABLE`, `ERROR`.

## Status bieżący (snapshot)

- `DONE` — relokacja pakietu do `ros2_ws/robot_mission_control`.
- `DONE` — przygotowanie `ament_python` (`setup.py`, `setup.cfg`, `package.xml`, `resource`, launch).
- `DONE` — wdrożenie backendu ROS2 Action (`Ros2MissionActionBackend`) + konfiguracja `config/action_backend.yaml`.
- `IN_PROGRESS` — integracyjne testy ROS2 (`ros2 launch`, `ros2 run`, testy end-to-end Action).
- `TODO` — playbook operatorski dla awarii backendu i polityki reakcji.

## P0 — krytyczne przed rolloutem operatorskim

1. **Domknąć kontrakt Action po stronie interfejsów ROS2.**
   - Zakres:
     - utworzyć/ustalić finalny pakiet interfejsów (`MissionStep.action`),
     - potwierdzić pola Goal/Feedback/Result i semantykę statusów,
     - dopiąć zgodność `action_backend.yaml` z finalnym kontraktem.
   - Kryterium ukończenia:
     - node klienta łączy się z serwerem Action i wykonuje pełny cykl goal->feedback->result,
     - brak fallbacku `action_backend_unavailable` w scenariuszu nominalnym.

2. **Dodać testy integracyjne launch + install-space + Action.**
   - Zakres:
     - test, że launch ładuje oba pliki config (`default.yaml`, `action_backend.yaml`) z `share/`.
     - test, że `ros2 run robot_mission_control robot_mission_control` uruchamia entrypoint,
     - test przepływu Action z serwerem testowym (goal accept, feedback, result, cancel).
   - Kryterium ukończenia:
     - zielony pipeline CI dla scenariusza ROS2.

3. **Uszczelnić mapowanie jakości danych akcji do UI.**
   - Zakres:
     - jawnie mapować statusy transportu na `VALID/STALE/UNAVAILABLE/ERROR`,
     - zawsze publikować `reason_code` dla stanów nie-`VALID`,
     - dopiąć wizualne oznaczenia jakości na panelu sterowania.
   - Kryterium ukończenia:
     - operator widzi stan jakości + kod przyczyny dla każdej operacji Action.

## P1 — stabilizacja i DX

1. **Rozdzielić zależności GUI i headless (`extras`).**
   - Cel:
     - uruchamianie testów core/ROS bez bibliotek graficznych (`PySide6`).

2. **Dodać skrypt bootstrap środowiska developerskiego.**
   - Cel:
     - pojedyncza komenda instalująca zależności i budująca pakiet.

3. **Dodać testy jednostkowe backendu Action (mock rclpy).**
   - Cel:
     - walidacja ścieżek błędów: brak serwera, odrzucony goal, brak feedback, timeout future.

4. **Dodać walidację konfiguracji YAML backendu Action.**
   - Cel:
     - twardy błąd konfiguracji przy brakujących polach krytycznych i wartościach spoza zakresu.

## P2 — dokumentacja i operacje

1. **Uzupełnić dokumentację o playbook awarii backendu ROS.**
   - Co opisać:
     - typowe `reason_code` (`action_backend_unavailable`, `reconnect_failed`, itp.),
     - oczekiwane reakcje operatora,
     - procedury eskalacji i rollback.

2. **Dodać macierz kompatybilności ROS2 distro / Python / PySide6.**
   - Cel:
     - przewidywalne wdrożenia na stanowiskach operatorskich.

3. **Wpiąć aktualizację TODO do procesu sprintowego.**
   - Cel:
     - przegląd statusu co sprint + zamykanie pozycji z odnośnikiem do PR/ticketu.

## Plan na najbliższe 2 sprinty

### Sprint N+1
- [ ] Domknąć kontrakt `MissionStep.action` i weryfikację połączenia klient-serwer.
- [ ] Dodać test integracyjny akcji (goal->feedback->result).
- [ ] Dodać mapowanie `reason_code` do UI w panelu controls.

### Sprint N+2
- [ ] Dodać testy launch/install-space do CI.
- [ ] Rozdzielić `extras` GUI/headless i uzupełnić dokumentację uruchomień.
- [ ] Zamknąć playbook operatorski i macierz kompatybilności.
