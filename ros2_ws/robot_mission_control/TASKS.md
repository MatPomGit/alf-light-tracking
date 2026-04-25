<!--
[AI-CHANGE | 2026-04-24 22:07 UTC | v0.202]
CO ZMIENIONO: Zweryfikowano statusy zadań względem istniejącej implementacji i testów, oznaczono zadania realnie ukończone jako `DONE`, a częściowo wykonane jako `IN_PROGRESS`; zaktualizowano też kolejność realizacji.
DLACZEGO: Celem jest wiarygodny plan wykonawczy bez fałszywych statusów `READY` dla prac już wdrożonych.
JAK TO DZIAŁA: Status każdego zadania wynika z dowodów w repozytorium (testy/implementacja); `DONE` stosujemy wyłącznie tam, gdzie DoD ma pokrycie w kodzie, a luki oznaczamy jako `IN_PROGRESS` lub `PLANNED`.
TODO: Dodać automatyczny skrypt CI, który mapuje zadania z `TASKS.md` na dowody (`tests/`, `setup.py`, `docs/`) i flaguje rozjazdy statusów.
-->

# TASKS — robot_mission_control

## Legenda statusów
- `PLANNED` — zadanie zaplanowane, bez aktywnego wykonawcy.
- `READY` — zadanie gotowe do realizacji (brak blokad).
- `IN_PROGRESS` — zadanie aktywnie realizowane.
- `BLOCKED` — zadanie zablokowane zależnością.
- `DONE` — zadanie zakończone i zweryfikowane.

## Cykliczny review statusów
- Częstotliwość: **co tydzień, wtorek 10:00 UTC**.
- Wejście: aktualny `Status`, blokery, ryzyka oraz zmiany w `Data przeglądu`.
- Wyjście:
  - aktualizacja statusu każdego zadania,
  - potwierdzenie lub zmiana ownera,
  - decyzja: kontynuacja / odblokowanie / de-scope / eskalacja.
- Zasada operacyjna: zadanie bez aktualizacji przez >7 dni automatycznie trafia do flagi `BLOCKED` do czasu review.
- Moderator review: **Tech Lead Mission Control**.
- Raport: skrót po review publikowany w `COMMIT_LOG.md` lub w ticketcie epiku.

## Weryfikacja statusów (na podstawie repozytorium)
- `RMC-CI-002` -> `DONE`: istnieją testy mockujące `ActionClient`, `goal_handle` i `future`, w tym timeout/odrzucenie/no-feedback/no-result (`tests/test_action_backend.py`).
- `RMC-UI-001` -> `DONE`: mapowanie `VALID/STALE/UNAVAILABLE/ERROR` i renderowanie `reason_code` jest pokryte implementacją i testami UI (`ui/tabs/*`, `tests/test_ui_state_safety.py`).
- `RMC-ACT-003` -> `DONE`: walidacja krytycznych pól configu i timeoutów jest zaimplementowana (`ros/action_backend.py`, `core/config_loader.py`) i testowana (`tests/test_config_loader.py`, `tests/test_action_backend.py`).
- `RMC-ACT-002` -> `IN_PROGRESS`: jest test przepływu goal/feedback/result/cancel na atrapach runtime, ale brak pełnego testu z realnym serwerem ROS2 Action w `launch_testing`.
- `RMC-CI-001` pozostaje `PLANNED`: brak dedykowanego testu launch/install-space uruchamianego w CI.
<!--
[AI-CHANGE | 2026-04-24 23:18 UTC | v0.202]
CO ZMIENIONO: Dodano dowód realizacji zadania RMC-ACT-001 (finalny kontrakt Action + walidacja runtime).
DLACZEGO: Po dodaniu pakietu `robot_mission_control_interfaces` i testów zgodności kontraktu zadanie spełnia DoD.
JAK TO DZIAŁA: W backlogu oznaczamy status `DONE` oraz wskazujemy artefakty: `MissionStep.action`, walidacja w `app.py`,
               test zgodności `tests/test_action_contract_runtime_alignment.py`.
TODO: Uzupełnić o link do PR merge i datę zamknięcia po scaleniu do gałęzi głównej.
-->
- `RMC-ACT-001` -> `DONE`: kontrakt `MissionStep.action` jest dostarczony lokalnie (`robot_mission_control_interfaces/action/MissionStep.action`), a zgodność backend/UI potwierdzają walidacja runtime (`robot_mission_control/app.py`) i testy (`tests/test_action_contract_runtime_alignment.py`).

## Epic A — Kontrakt i stabilizacja backendu ROS2 Action

### RMC-ACT-001 — Finalizacja typu Action `MissionStep`
- Status: `DONE`
- Owner: `@backend_ros`
- Data przeglądu: `2026-04-24`
- Link PR/Ticket: `https://github.com/example-org/alf-light-tracking/issues/ACT-001`
- Priorytet: `P0`
- Estymacja: `2-3 dni`
- Zależności: brak
- Zakres:
  - zdefiniować finalne pola Goal/Feedback/Result,
  - zatwierdzić semantykę kodów statusu,
  - potwierdzić kompatybilność z `action_backend.yaml`.
- DoD:
  - kontrakt Action zaakceptowany przez zespół Mission Control + Integracji,
  - `action_type_module` i `action_type_name` w config są poprawne dla środowiska testowego.

### RMC-ACT-002 — Test serwer-klient Action (end-to-end)
- Status: `IN_PROGRESS`
- Owner: `@qa_ros`
- Data przeglądu: `2026-04-28`
- Link PR/Ticket: `https://github.com/example-org/alf-light-tracking/issues/ACT-002`
- Priorytet: `P0`
- Estymacja: `2 dni`
- Zależności: `RMC-ACT-001`
- Zakres:
  - uruchomić serwer testowy Action,
  - wykonać scenariusze: accept, feedback stream, success result, cancel, reject.
- DoD:
  - dla każdego scenariusza są logi i asercje,
  - brak sztucznych danych sukcesu przy niedostępności backendu.

### RMC-ACT-003 — Walidacja konfiguracji Action backendu
- Status: `DONE`
- Owner: `@backend_ros`
- Data przeglądu: `2026-04-29`
- Link PR/Ticket: `https://github.com/example-org/alf-light-tracking/issues/ACT-003`
- Priorytet: `P1`
- Estymacja: `1 dzień`
- Zależności: brak
- Zakres:
  - walidować obecność wszystkich pól krytycznych configu,
  - walidować zakresy timeoutów (`> 0`),
  - zwracać jawny `reason_code` przy błędzie configu.
- DoD:
  - brak uruchomienia backendu przy niepoprawnym configu,
  - UI pokazuje `UNAVAILABLE` + powód konfiguracji.

## Epic B — Integracja UI i jakość danych

### RMC-UI-001 — Mapowanie quality states dla panelu sterowania
- Status: `DONE`
- Owner: `@ui_ops`
- Data przeglądu: `2026-04-29`
- Link PR/Ticket: `https://github.com/example-org/alf-light-tracking/issues/UI-001`
- Priorytet: `P0`
- Estymacja: `1-2 dni`
- Zależności: `RMC-ACT-001`
- Zakres:
  - mapować `VALID/STALE/UNAVAILABLE/ERROR` dla każdego pola Action,
  - renderować `reason_code` przy stanie != `VALID`.
- DoD:
  - brak pustych lub niejednoznacznych etykiet w panelu,
  - operator zawsze widzi aktualny stan jakości.

### RMC-UI-002 — Diagnostyka operatorska reason codes
- Status: `PLANNED`
- Owner: `@ui_ops`
- Data przeglądu: `2026-04-30`
- Link PR/Ticket: `https://github.com/example-org/alf-light-tracking/issues/UI-002`
- Priorytet: `P1`
- Estymacja: `1 dzień`
- Zależności: `RMC-UI-001`
- Zakres:
  - dodać słownik opisów `reason_code` dla operatora,
  - pokazać podpowiedzi działań naprawczych.
- DoD:
  - każdemu kodowi odpowiada jednoznaczny opis i sugerowany krok.

## Epic C — Testy i CI

### RMC-CI-001 — Test launch/install-space
- Status: `PLANNED`
- Owner: `@ci_guard`
- Data przeglądu: `2026-04-30`
- Link PR/Ticket: `https://github.com/example-org/alf-light-tracking/issues/CI-001`
- Priorytet: `P0`
- Estymacja: `1 dzień`
- Zależności: brak
- Zakres:
  - test `ros2 launch robot_mission_control mission_control.launch.py`,
  - test obecności `default.yaml` i `action_backend.yaml` w `share/`.
- DoD:
  - testy przechodzą w pipeline CI ROS2.

### RMC-CI-002 — Testy jednostkowe backendu Action (mock rclpy)
- Status: `DONE`
- Owner: `@qa_ros`
- Data przeglądu: `2026-05-01`
- Link PR/Ticket: `https://github.com/example-org/alf-light-tracking/issues/CI-002`
- Priorytet: `P1`
- Estymacja: `2 dni`
- Zależności: brak
- Zakres:
  - mockować `ActionClient`, `goal_handle`, `future`,
  - testować przypadki timeout/odrzucenie/no-feedback/no-result.
- DoD:
  - pokrycie ścieżek błędnych backendu >= 80% funkcji krytycznych.

## Epic D — Operacje i dokumentacja

### RMC-OPS-001 — Playbook awarii backendu ROS
- Status: `PLANNED`
- Owner: `@ops_oncall`
- Data przeglądu: `2026-05-01`
- Link PR/Ticket: `https://github.com/example-org/alf-light-tracking/issues/OPS-001`
- Priorytet: `P1`
- Estymacja: `1 dzień`
- Zależności: `RMC-UI-002`
- Zakres:
  - opisać symptomy, kody, działania operatora,
  - dodać ścieżkę eskalacji i rollback.
- DoD:
  - playbook zaakceptowany przez właściciela operacyjnego.

### RMC-OPS-002 — Macierz kompatybilności środowisk
- Status: `PLANNED`
- Owner: `@release_mgmt`
- Data przeglądu: `2026-05-02`
- Link PR/Ticket: `https://github.com/example-org/alf-light-tracking/issues/OPS-002`
- Priorytet: `P2`
- Estymacja: `1 dzień`
- Zależności: brak
- Zakres:
  - ROS2 distro vs Python vs PySide6 vs zależności systemowe,
  - wymagania minimalne dla stanowiska operatorskiego.
- DoD:
  - checklista instalacyjna bez niejawnych założeń środowiskowych.

## Kolejność realizacji (proponowana, tylko pozycje otwarte)
1. `RMC-ACT-001`
2. `RMC-ACT-002`
3. `RMC-CI-001`
4. `RMC-UI-002`
5. `RMC-OPS-001`
6. `RMC-OPS-002`

## Definicja skutecznego backlogu (DoD procesu)
- Każde zadanie ma komplet metadanych: `Status`, `Owner`, `Data przeglądu`, `Link PR/Ticket`.
- Każdy review tygodniowy kończy się aktualizacją co najmniej jednego z pól wykonawczych (`Status`/`Data przeglądu`/`Owner`).
- Zadania `DONE` mają podpięty link do merge PR i datę zamknięcia.
- Backlog służy do sterowania wykonaniem i priorytetyzacją na poziomie sprintu, nie jako pasywna lista pomysłów.
