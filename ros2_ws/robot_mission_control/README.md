<!--
[AI-CHANGE | 2026-04-23 19:01 UTC | v0.195]
CO ZMIENIONO: Uporządkowano dokumentację modułu, scalono rozproszone notatki edytorskie i skrócono komentarze AI do jednego bloku.
DLACZEGO: Dokument miał wiele nakładających się komentarzy, co utrudniało utrzymanie i czytelność.
JAK TO DZIAŁA: README zawiera teraz jedną, zwartą sekcję zmian oraz aktualny opis uruchomienia, struktury i funkcji modułu.
TODO: Uzupełnić README o diagram przepływu zdarzeń operatora i mapę kontraktów Action po stabilizacji API.
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

<!--
[AI-CHANGE | 2026-04-24 10:48 UTC | v0.201]
CO ZMIENIONO: Zaktualizowano instrukcję instalacji o dwa profile zależności: headless (core/ROS) i desktop (UI).
DLACZEGO: Backendowe testy i uruchomienia CI mają działać bez PySide6, a UI ma być instalowane wyłącznie tam, gdzie potrzebne.
JAK TO DZIAŁA: Operator/deweloper wybiera odpowiedni plik requirements; profil bazowy nie instaluje bibliotek GUI.
TODO: Dodać w README gotowe komendy CI pokazujące uruchomienie samych testów core/ROS na profilu headless.
-->
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
- `package.xml` deklaruje pakiet ROS2 kompatybilny z `ament_python`.

## Controls — komunikacja i szybkie akcje

- `RosBridgeService` integruje backend `Ros2MissionActionBackend` i klienta `MissionActionClient`.
- Obsługiwane operacje: `send_goal`, `cancel_goal`, `fetch_progress`, `fetch_result`.
- Publikowany stan: `action_goal_id`, `action_status`, `action_progress`, `action_result`.
- Bezpieczny fallback: przy niepewności wynik pozostaje `None`, UI pokazuje `BRAK DANYCH`.
- W zakładce **Controls** dostępne są szybkie akcje: `Rozpocznij patrol`, `Powrót do bazy`, `Wstrzymaj misję`, `Wznów misję`.
- Podczas aktywnego goal szybkie akcje są blokowane, by uniknąć kolizji komend.
