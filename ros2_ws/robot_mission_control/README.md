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


<!-- [AI-CHANGE | 2026-04-21 10:19 UTC | v0.168] -->
<!-- CO ZMIENIONO: Dodano instrukcję instalacji zależności z nowego pliku `requirements.txt`. -->
<!-- DLACZEGO: Pakiet wymaga jawnego kroku instalacji bibliotek Python przed uruchomieniem GUI poza buildem ROS2. -->
<!-- JAK TO DZIAŁA: Przed `colcon build` instalujemy zależności pip, co redukuje ryzyko błędów importu runtime. -->
<!-- TODO: Zautomatyzować ten krok w skrypcie bootstrap środowiska developerskiego. -->
<!-- [AI-CHANGE | 2026-04-21 12:10 UTC | v0.167] -->
<!-- CO ZMIENIONO: Zaktualizowano instrukcję uruchamiania po relokacji pakietu do `ros2_ws/robot_mission_control`. -->
<!-- DLACZEGO: Stare polecenia (`cd robot_mission_control`) były niezgodne z nową strukturą workspace ROS2. -->
<!-- JAK TO DZIAŁA: README prowadzi przez `colcon build`, `source install/setup.bash` i uruchomienie przez `ros2 launch`. -->
<!-- TODO: Dodać wariant uruchomienia headless do testów CI bez środowiska graficznego. -->
```bash
pip install -r ros2_ws/robot_mission_control/requirements.txt
cd ros2_ws
colcon build --packages-select robot_mission_control
source install/setup.bash
ros2 launch robot_mission_control mission_control.launch.py
```

## Struktura

- `robot_mission_control/app.py` – entrypoint aplikacji.
- `robot_mission_control/ui/main_window.py` – główne okno i layout.
- `robot_mission_control/ui/tabs/` – zakładki funkcjonalne (placeholdery).


<!-- [AI-CHANGE | 2026-04-21 09:30 UTC | v0.166] -->
<!-- CO ZMIENIONO: Dodano opis nowych modułów core, konfiguracji i launch ROS2 zgodnych z backlogiem. -->
<!-- DLACZEGO: Zespół potrzebuje jasnego mapowania odpowiedzialności oraz instrukcji uruchamiania przez tooling ROS2. -->
<!-- JAK TO DZIAŁA: README opisuje nowe pliki `config/default.yaml`, `launch/mission_control.launch.py` i moduły `core/*`. -->
<!-- TODO: Dodać diagram przepływu zdarzeń operatora z correlation_id po wdrożeniu telemetrycznego traceingu. -->

## Nowe moduły core (backlog)

- `robot_mission_control/core/config_loader.py` – rygorystyczny odczyt i walidacja YAML (bez cichych defaultów).
- `robot_mission_control/core/event_bus.py` – szyna zdarzeń z wymuszeniem `correlation_id` dla zdarzeń operatorskich.
- `robot_mission_control/core/logger.py` – ustrukturyzowane logowanie (timestamp/module/level/correlation_id/session_id).
- `robot_mission_control/core/models.py` – współdzielone modele danych konfiguracji, zdarzeń i błędów.
- `robot_mission_control/core/error_codes.py` – katalog stabilnych kodów błędów i komunikatów.
- `robot_mission_control/core/error_boundary.py` – mapowanie wyjątków i bezpieczna degradacja bez freeze UI.

## Integracja ROS2

- `launch/mission_control.launch.py` uruchamia node Mission Control z parametrami z `config/default.yaml`.
- `package.xml` deklaruje pakiet ROS2 kompatybilny z `ament_python`.
