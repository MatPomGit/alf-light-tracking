<!-- [AI-CHANGE | 2026-04-20 14:12 UTC | v0.141] -->
<!-- CO ZMIENIONO: Dodano dziennik zmian dla nowego modułu robot_mission_control. -->
<!-- DLACZEGO: Potrzebna jest ścieżka audytowa dla kolejnych iteracji i decyzji architektonicznych. -->
<!-- JAK TO DZIAŁA: Sekcja wersji zapisuje zakres zmian i poziom gotowości komponentów. -->
<!-- TODO: Zintegrować changelog z automatycznym generowaniem release notes w CI/CD. -->

# Changelog

## 0.1.0 - 2026-04-20

- Dodano nowy katalog aplikacji `robot_mission_control/`.
- Dodano entrypoint desktopowy `app.py` (PySide6 + bezpieczny most ROS2).
- Dodano główne okno UI z top barem, sidebarem, zakładkami, panelem alarmów i statusem.
- Dodano placeholdery wszystkich wymaganych zakładek oznaczone jako „NIEDOSTĘPNE W TEJ WERSJI”.
- Ustawiono stan startowy bez robota: `BRAK DOSTĘPU / BRAK DANYCH`.
