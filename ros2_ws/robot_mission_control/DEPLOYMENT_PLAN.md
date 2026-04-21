<!--
[AI-CHANGE | 2026-04-21 11:00 UTC | v0.173]
CO ZMIENIONO: Dodano plan wdrożenia produkcyjnego modułu `robot_mission_control`.
DLACZEGO: Oprócz backlogu zadań potrzebny jest operacyjny plan rolloutu z bramkami jakości, rollbackiem i metrykami.
JAK TO DZIAŁA: Dokument definiuje fazy wdrożenia, kryteria GO/NO-GO, plan monitoringu i działania po-incydentowe.
TODO: Po pierwszym pilotażu uzupełnić plan o rzeczywiste czasy MTTR i listę najczęstszych reason_code.
-->

# DEPLOYMENT PLAN — robot_mission_control

## 1) Cel wdrożenia
Wdrożyć `robot_mission_control` jako stabilny pakiet operatorski ROS2 w `ros2_ws/` z aktywnym backendem Action,
bez prezentowania danych fikcyjnych (priorytet: `UNAVAILABLE` zamiast błędnego wyniku).

## 2) Zakres
- Pakiet: `ros2_ws/robot_mission_control`
- Runtime: ROS2 (`rclpy`, `launch`, `ament_python`)
- Kluczowe ścieżki:
  - `launch/mission_control.launch.py`
  - `config/default.yaml`
  - `config/action_backend.yaml`
  - `robot_mission_control/ros/action_backend.py`

## 3) Fazy rolloutu

### Faza 0 — Pre-flight (środowisko)
- Zweryfikować obecność narzędzi: `colcon`, `ros2`, `python3`, biblioteki GUI.
- Zweryfikować obecność interfejsu Action (`MissionStep.action` lub docelowy odpowiednik).
- Zweryfikować poprawność configów (`default.yaml`, `action_backend.yaml`).

**Gate GO/NO-GO:**
- GO: wszystkie zależności dostępne i config poprawny.
- NO-GO: brak interfejsu Action, brak `ros2` lub błędy walidacji config.

### Faza 1 — Build + install-space smoke
- `colcon build --packages-select robot_mission_control`
- `source install/setup.bash`
- `ros2 launch robot_mission_control mission_control.launch.py`

**Gate GO/NO-GO:**
- GO: launch startuje bez błędów importu i ładuje config z `share/`.
- NO-GO: wyjątki importu, brak plików config w install-space.

### Faza 2 — Integracja Action (test bench)
- Uruchomić serwer testowy Action.
- Zweryfikować scenariusze:
  - send goal (accepted/rejected),
  - feedback progress,
  - result success/aborted,
  - cancel.

**Gate GO/NO-GO:**
- GO: pełny cykl Action działa i jest widoczny w UI/store.
- NO-GO: niestabilne połączenie, brak feedback/result lub niespójny status.

### Faza 3 — Pilotaż operatorski
- Ograniczony rollout na 1 stanowisku operatorskim.
- Monitoring reason codes i zachowania fallbacków jakości.

**Gate GO/NO-GO:**
- GO: brak krytycznych incydentów i akceptowalna jakość telemetryczna.
- NO-GO: częste `ERROR`, długi czas przywrócenia, błędne etykiety UI.

### Faza 4 — Rollout produkcyjny
- Wdrożenie na wszystkie stanowiska operatorskie.
- Aktywny monitoring + plan szybkiego rollbacku.

## 4) Kryteria akceptacji końcowej
1. Backend Action działa na docelowym serwerze i nie korzysta z danych symulowanych.
2. Stany jakości (`VALID/STALE/UNAVAILABLE/ERROR`) są konsekwentnie prezentowane w UI.
3. Każdy błąd krytyczny ma `reason_code` i zdefiniowaną procedurę operatora.
4. Istnieje gotowa procedura rollbacku i została przećwiczona.

## 5) Plan rollbacku
- Krok 1: zatrzymać aplikację operatorską.
- Krok 2: przywrócić poprzednią wersję pakietu z ostatniego stabilnego artefaktu.
- Krok 3: przywrócić poprzedni `action_backend.yaml`.
- Krok 4: ponowić build i launch smoke.
- Krok 5: oznaczyć incydent i zapisać RCA (root cause analysis).

## 6) Monitoring i KPI
- `KPI-1`: procent sesji bez `action_backend_unavailable` w nominalnym oknie testowym.
- `KPI-2`: średni czas od reconnect do pierwszego poprawnego feedbacku Action.
- `KPI-3`: liczba incydentów `ERROR` na zmianę operatorską.
- `KPI-4`: MTTR (czas przywrócenia) po utracie backendu Action.

## 7) Plan po wdrożeniu (30 dni)
- Tydzień 1: codzienny przegląd logów i reason codes.
- Tydzień 2: korekty konfiguracji timeoutów Action.
- Tydzień 3: analiza trendów jakości i decyzja o tuningach UI.
- Tydzień 4: raport stabilności + decyzja o zamknięciu etapu rolloutu.
