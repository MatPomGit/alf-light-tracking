<!--
[AI-CHANGE | 2026-04-21 10:24 UTC | v0.169]
CO ZMIENIONO: Dodano dedykowany plik TODO z planem dalszych prac dla pakietu `robot_mission_control`.
DLACZEGO: Po relokacji i bazowej integracji ROS2 potrzebna jest jawna lista kolejnych kroków technicznych i safety.
JAK TO DZIAŁA: Dokument grupuje zadania wg priorytetu, definiuje warunki ukończenia i wskazuje obszary ryzyka.
TODO: Regularnie (co sprint) aktualizować statusy i dopinać linki do ticketów/PR dla każdego punktu.
-->

# TODO — robot_mission_control

## Założenie bezpieczeństwa (nadrzędne)
- **Zasada obowiązkowa:** lepiej zwrócić `UNAVAILABLE`/brak wyniku niż pokazać operatorowi wynik niepewny lub błędny.
- Wszystkie nowe integracje muszą mapować jakość danych do jednego z: `VALID`, `STALE`, `UNAVAILABLE`, `ERROR`.

## P0 — krytyczne przed rolloutem operatorskim

1. **Podłączyć prawdziwy backend ROS Action (zamiast transportu unavailable).**
   - Zakres:
     - zdefiniować endpoint Action i kontrakt Goal/Feedback/Result,
     - wdrożyć klienta Action z timeout/retry/cancel,
     - mapować błędy 1:1 do `reason_code` bez „zgadywania” stanu.
   - Kryterium ukończenia:
     - UI pokazuje wyłącznie statusy pochodzące z backendu,
     - test integracyjny potwierdza brak danych fikcyjnych.

2. **Dodać testy integracyjne launch + install-space.**
   - Zakres:
     - test, że `mission_control.launch.py` ładuje config z `share/robot_mission_control/config/default.yaml`,
     - test, że `ros2 run robot_mission_control robot_mission_control` odnajduje entrypoint.
   - Kryterium ukończenia:
     - testy przechodzą w CI dla środowiska ROS2.

3. **Uzupełnić monitoring jakości danych w UI.**
   - Zakres:
     - pokazywać operatorowi `reason_code` dla stanów `UNAVAILABLE`/`ERROR`,
     - dodać jednoznaczne oznaczenia kolorystyczne dla `VALID/STALE/UNAVAILABLE/ERROR`.
   - Kryterium ukończenia:
     - każdy panel ma jawny status jakości i źródło danych.

## P1 — stabilizacja środowisk i DX

1. **Rozdzielić zależności GUI i headless (`extras`).**
   - Cel:
     - umożliwić uruchamianie testów core/ROS bez bibliotek graficznych.

2. **Dodać skrypt bootstrap środowiska developerskiego.**
   - Cel:
     - jeden skrypt instaluje `requirements.txt`, buduje pakiet i drukuje komendy startowe.

3. **Dodać testy jednostkowe warstwy `ros/__init__.py` i kontraktu publicznego API.**
   - Cel:
     - wykrywać niekompatybilne zmiany eksportów modułów.

## P2 — dokumentacja i operacje

1. **Uzupełnić dokumentację o playbook awarii backendu ROS.**
   - Co opisać:
     - typowe `reason_code`,
     - oczekiwane reakcje operatora,
     - procedury eskalacji.

2. **Dodać macierz kompatybilności ROS2 distro / Python / PySide6.**
   - Cel:
     - przewidywalne wdrożenia na stanowiskach operatorskich.

3. **Wpiąć aktualizację TODO do procesu sprintowego.**
   - Cel:
     - raz na sprint przegląd statusu i zamkniętych pozycji.
