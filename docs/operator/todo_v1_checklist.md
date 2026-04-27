# [AI-CHANGE | 2026-04-27 08:25 UTC | v0.203]
# CO ZMIENIONO: Dodano checklistę zamknięcia TODO-v1 dla paczki stabilizacyjnej UI operatorskiego.
# DLACZEGO: Wymaganie DoD mówi o zamknięciu top-10 TODO o największym wpływie operacyjnym.
# JAK TO DZIAŁA: Lista poniżej mapuje każdy wdrożony punkt na konkretny obszar (filtry/sortowanie,
#                kolory quality, eksport diagnostyki, telemetryka blokad) i status wykonania.
# TODO: Dodać automatyczne raportowanie postępu checklisty do pipeline CI release gate.

# TODO-v1 — checklista paczki stabilizacyjnej

Status: **ZAMKNIĘTA (10/10)**

## Filtry / sortowanie
- [x] Telemetry: filtr po severity (`ALL/CRITICAL/HIGH/MEDIUM/INFO`).
- [x] Telemetry: filtr tekstowy po kluczu telemetrycznym.
- [x] Telemetry: sortowanie rekordów po severity (malejące ryzyko) i timestamp (najnowsze wyżej).
- [x] Rosbag: filtr logu zdarzeń po typie (`ALL/EXECUTED/SKIPPED/BLOCKED`).

## Kolory quality
- [x] Telemetry: legenda kolorów quality pod tabelą.
- [x] Rosbag: kolorowanie statusów recording/playback/bag/integrity wg severity jakości.

## Eksport diagnostyki
- [x] Debug: przełącznik „tylko quality != VALID” dla snapshotu.
- [x] Debug: eksport snapshotu do pliku `.log`.

## Telemetryka blokad
- [x] Controls: liczniki zablokowanych prób `send/cancel/quick` + agregacja `reason_code`.
- [x] Rosbag: liczniki zablokowanych akcji i top przyczyn blokad.
