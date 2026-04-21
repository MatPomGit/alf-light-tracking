<!--
[AI-CHANGE | 2026-04-21 10:52 UTC | v0.172]
CO ZMIENIONO: Dodano szczegółowy plan dalszych zadań wdrożeniowych dla `robot_mission_control`.
DLACZEGO: Potrzebna jest bardziej operacyjna rozpiska niż ogólny TODO: z identyfikatorami, zależnościami, estymacją i DoD.
JAK TO DZIAŁA: Plik grupuje zadania w epiki, definiuje kolejność realizacji i minimalne kryteria akceptacji/testów.
TODO: Powiązać zadania z realnymi numerami ticketów i automatycznie aktualizować status po merge PR.
-->

# TASKS — robot_mission_control

## Legenda statusów
- `PLANNED` — zadanie zaplanowane, bez aktywnego wykonawcy.
- `READY` — zadanie gotowe do realizacji (brak blokad).
- `IN_PROGRESS` — zadanie aktywnie realizowane.
- `BLOCKED` — zadanie zablokowane zależnością.
- `DONE` — zadanie zakończone i zweryfikowane.

## Epic A — Kontrakt i stabilizacja backendu ROS2 Action

### RMC-ACT-001 — Finalizacja typu Action `MissionStep`
- Status: `READY`
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
- Status: `PLANNED`
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
- Status: `READY`
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
- Status: `READY`
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
- Priorytet: `P0`
- Estymacja: `1 dzień`
- Zależności: brak
- Zakres:
  - test `ros2 launch robot_mission_control mission_control.launch.py`,
  - test obecności `default.yaml` i `action_backend.yaml` w `share/`.
- DoD:
  - testy przechodzą w pipeline CI ROS2.

### RMC-CI-002 — Testy jednostkowe backendu Action (mock rclpy)
- Status: `READY`
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
- Priorytet: `P2`
- Estymacja: `1 dzień`
- Zależności: brak
- Zakres:
  - ROS2 distro vs Python vs PySide6 vs zależności systemowe,
  - wymagania minimalne dla stanowiska operatorskiego.
- DoD:
  - checklista instalacyjna bez niejawnych założeń środowiskowych.

## Kolejność realizacji (proponowana)
1. `RMC-ACT-001`
2. `RMC-ACT-002`
3. `RMC-UI-001`
4. `RMC-CI-001`
5. `RMC-CI-002`
6. `RMC-ACT-003`
7. `RMC-UI-002`
8. `RMC-OPS-001`
9. `RMC-OPS-002`
