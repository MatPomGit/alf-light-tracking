<!-- [AI-CHANGE | 2026-04-21 15:52 UTC | v0.176] -->
<!-- CO ZMIENIONO: Dodano dedykowany dziennik zmian commitowych dla modułu robot_mission_control. -->
<!-- DLACZEGO: Wymaganie projektu mówi o opisie zmian przy każdym commicie w osobnym pliku modułu. -->
<!-- JAK TO DZIAŁA: Każdy kolejny commit dopisuje nową sekcję z datą, SHA i zakresem zmian. -->
<!-- TODO: Zautomatyzować aktualizację tego pliku hookiem commit-msg lub skryptem release. -->

# Commit log — robot_mission_control

## 2026-04-21 | v0.176 | (bieżący commit)

- Rozbudowano moduł `Controls` o szybkie akcje misji (patrol, powrót do bazy, pauza, wznowienie).
- Rozszerzono `RosBridgeService` o obsługę ROS2 Action: send/cancel/progress/result.
- Dodano delegację szybkich akcji przez `MainWindow`.
- Uzupełniono README o opis nowych funkcji operatorskich i zakres komunikacji ROS2.

## Szablon dla kolejnych commitów

```text
## YYYY-MM-DD | v0.<N> | <short_sha>
- Zmiana 1...
- Zmiana 2...
```
