<!--
[AI-CHANGE | 2026-04-29 13:51 UTC | v0.333]
CO ZMIENIONO: Uporządkowano README do jednego bloku meta i zaktualizowano opis pakietu po przejściu na `ament_cmake`.
DLACZEGO: Dokument miał drugi blok AI w środku treści oraz przestarzałą informację o `ament_python`, co utrudniało szybkie odczytanie aktualnego sposobu budowania ROS2.
JAK TO DZIAŁA: Szczegóły E2E są opisane zwykłą treścią operacyjną, a sekcja integracji ROS2 wskazuje aktualny build `ament_cmake` z lokalnym typem Action.
TODO: Dodać automatyczny lint markdown blokujący więcej niż jeden blok [AI-CHANGE] w README.
-->

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
# Profil headless (core/ROS, testy backendowe)
pip install -r ros2_ws/robot_mission_control/requirements.txt

# Profil desktop UI (PySide6)
pip install -r ros2_ws/robot_mission_control/requirements-ui.txt

cd ros2_ws
colcon build --packages-select robot_mission_control
source install/setup.bash
ros2 launch robot_mission_control mission_control.launch.py
```

## Test E2E (realny flow ROS2 Action, bez mocków klienta)

```bash
cd ros2_ws/robot_mission_control
./scripts/run_e2e_real_flow.sh
```

Skrypt wykonuje:
- `colcon build` pakietu `robot_mission_control`,
- `ros2 run robot_mission_control mission_step_action_test_server`,
- `ros2 launch robot_mission_control mission_control.launch.py`,
- `ros2 action send_goal --feedback` (scenariusz sukcesu),
- `ros2 action send_goal --feedback` + `ros2 action cancel` (scenariusz anulowania).

Logi są zapisywane do katalogu `logs/e2e_real_flow/`.

## Wydzielenie zależności

- `requirements.txt` / `requirements-core.txt` – tylko backend (core/ROS), bez PySide6.
- `requirements-ui.txt` – zależności GUI dla aplikacji desktopowej.
- `pyproject.toml` – extra `ui`, czyli instalacja `pip install .[ui]`.

## Struktura

- `robot_mission_control/app.py` – entrypoint aplikacji.
- `robot_mission_control/ui/main_window.py` – główne okno i layout.
- `robot_mission_control/ui/tabs/` – zakładki funkcjonalne.

## Moduły core

- `robot_mission_control/core/config_loader.py` – rygorystyczny odczyt i walidacja YAML (bez cichych defaultów).
- `robot_mission_control/core/event_bus.py` – szyna zdarzeń z wymuszeniem `correlation_id` dla zdarzeń operatorskich.
- `robot_mission_control/core/logger.py` – ustrukturyzowane logowanie (timestamp/module/level/correlation_id/session_id).
- `robot_mission_control/core/models.py` – współdzielone modele danych konfiguracji, zdarzeń i błędów.
- `robot_mission_control/core/error_codes.py` – katalog stabilnych kodów błędów i komunikatów.
- `robot_mission_control/core/error_boundary.py` – mapowanie wyjątków i bezpieczna degradacja bez freeze UI.

## Integracja ROS2

- `launch/mission_control.launch.py` uruchamia node Mission Control z parametrami z `config/default.yaml`.
- `package.xml` deklaruje pakiet ROS2 budowany przez `ament_cmake`.
- `CMakeLists.txt` generuje lokalny typ `robot_mission_control/action/MissionStep` i instaluje wrappery `ros2 run`.

## Controls — komunikacja i szybkie akcje

- `RosBridgeService` integruje backend `Ros2MissionActionBackend` i klienta `MissionActionClient`.
- Obsługiwane operacje: `send_goal`, `cancel_goal`, `fetch_progress`, `fetch_result`.
- Publikowany stan: `action_goal_id`, `action_status`, `action_progress`, `action_result`.
- Bezpieczny fallback: przy niepewności wynik pozostaje `None`, UI pokazuje `BRAK DANYCH`.
- W zakładce **Controls** dostępne są szybkie akcje: `Rozpocznij patrol`, `Powrót do bazy`, `Wstrzymaj misję`, `Wznów misję`.
- Podczas aktywnego goal szybkie akcje są blokowane, by uniknąć kolizji komend.

## Historia zmian dokumentu

- Szczegółowa historia zmian README jest utrzymywana w `COMMIT_LOG.md`.
- Fakty releasowe pozostają w `CHANGELOG.md`.
