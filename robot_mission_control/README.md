<!-- [AI-CHANGE | 2026-04-20 14:12 UTC | v0.141] -->
<!-- CO ZMIENIONO: Dodano dokumentację nowego modułu robot_mission_control i instrukcję uruchamiania. -->
<!-- DLACZEGO: Użytkownik i zespół potrzebują jasnego opisu celu, ograniczeń i sposobu startu aplikacji. -->
<!-- JAK TO DZIAŁA: README opisuje strukturę katalogów, punkt wejścia i stan początkowy bez robota. -->
<!-- TODO: Uzupełnić sekcję o architekturę sygnałów Qt oraz macierz kompatybilności ROS2 dystrybucji. -->

# robot_mission_control

Aplikacja desktopowa do nadzoru misji robota (PySide6 + most ROS2).

## Stan tej wersji

- UI jest szkieletem funkcjonalnym.
- Niegotowe sekcje są jawnie oznaczone jako **NIEDOSTĘPNE W TEJ WERSJI** i zablokowane.
- Aplikacja uruchamia się bez podłączonego robota i startuje w stanie:
  - `BRAK DOSTĘPU` (połączenie),
  - `BRAK DANYCH` (telemetria/wideo/diagnoza).

## Uruchomienie lokalne

```bash
cd robot_mission_control
python -m venv .venv
source .venv/bin/activate
pip install -e .
robot-mission-control
```

## Struktura

- `robot_mission_control/app.py` – entrypoint aplikacji.
- `robot_mission_control/ui/main_window.py` – główne okno i layout.
- `robot_mission_control/ui/tabs/` – zakładki funkcjonalne (placeholdery).
