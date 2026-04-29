<!--
[AI-CHANGE | 2026-04-29 13:51 UTC | v0.333]
CO ZMIENIONO: Scalono dwa nagłówkowe bloki AI w jeden opis aktualnego zakresu dokumentu.
DLACZEGO: Kolejne bloki meta przed tytułem dublowały historię utworzenia i relokacji pakietu, utrudniając wejście w treść architektury.
JAK TO DZIAŁA: Dokument nadal opisuje granice modułów Stage 0 i aktualne ścieżki `ros2_ws/robot_mission_control/...`.
TODO: Dodać sekcję zależności runtime pomiędzy modułami core a mostem ROS.
-->

# Granice modułów

## Moduły
- `sensor_adapter`
- `detector_core`
- `fusion_manager`
- `safety_supervisor`
- `operator_ui`

## Kontrakty między modułami
Każda granica modułu wymaga jawnego kontraktu: schemat + walidacje + kody odrzucenia.

## Reguły odpowiedzialności
- `detector_core` nie publikuje wyniku przy niepewnych danych wejściowych.
- `safety_supervisor` wymusza stan `FAIL_SAFE` przy naruszeniu polityki jakości.
- `operator_ui` prezentuje faktyczny stan bez wartości zastępczych.

## Zasady jakości
**Lepszy brak wyniku niż błędny wynik** oraz **brak danych fikcyjnych** obowiązują na każdej granicy.



<!--
[AI-CHANGE | 2026-04-21 09:30 UTC | v0.166]
CO ZMIENIONO: Uzupełniono granice modułów o odpowiedzialności komponentów `ros2_ws/robot_mission_control/robot_mission_control/core`.
DLACZEGO: Potrzebujemy jawnego kontraktu odpowiedzialności dla config/event/log/error, aby uniknąć rozmycia granic.
JAK TO DZIAŁA: Dodana sekcja opisuje odpowiedzialność i minimalne wymagania jakościowe każdego nowego modułu.
TODO: Dodać diagram sekwencji dla przepływu wyjątku przez `error_boundary` i propagację do UI.
-->

## Granice modułów `ros2_ws/robot_mission_control/robot_mission_control/core`

- `config_loader`:
  - Jedyna warstwa dopuszczająca odczyt konfiguracji z pliku.
  - Brak cichych defaultów: błąd walidacji zawsze zwraca kod i komunikat.
- `event_bus`:
  - Transport zdarzeń wewnętrznych między komponentami.
  - Dla kategorii operatorskiej obowiązkowy jest `correlation_id`.
- `logger`:
  - Ujednolicony format logów ze stałymi polami korelacyjnymi i sesyjnymi.
- `error_codes`:
  - Centralny słownik kodów błędów używany przez wszystkie granice.
- `error_boundary`:
  - Przechwytuje wyjątki i mapuje je do kodów błędów.
  - Wymusza degradację (`degraded=True`) zamiast propagacji błędu blokującego UI.
- `models`:
  - Jawne kontrakty danych dla konfiguracji, eventów i deskryptorów błędów.
