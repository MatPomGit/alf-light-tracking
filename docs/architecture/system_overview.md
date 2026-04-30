# Przegląd systemu

## Kontekst
System realizuje detekcję i śledzenie sygnałów świetlnych w środowisku ROS2 z naciskiem na bezpieczeństwo operacyjne.

## Warstwy
1. Ingest danych sensorowych.
2. Przetwarzanie i walidacja.
3. Decyzja detekcyjna.
4. Prezentacja i sterowanie operatorskie.

## Zasady architektoniczne
- Fail-safe domyślny dla błędów jakości danych.
- Minimalizacja sprzężeń między modułami.
- **Lepszy brak wyniku niż błędny wynik** na granicy decyzji.
- **Brak danych fikcyjnych** w runtime produkcyjnym.

