<!--
[AI-CHANGE | 2026-04-20 20:39 UTC | v0.153]
CO ZMIENIONO: Utworzono nowy dokument specyfikacyjny/architektoniczny/użytkowy dla etapu Stage 0.
DLACZEGO: Uporządkowanie wymagań i procedur operacyjnych projektu oraz formalizacja kryteriów jakości.
JAK TO DZIAŁA: Dokument stanowi źródło referencyjne; definiuje zasady, zakres i wymagane działania dla zespołu.
TODO: Uzupełnić dokument o referencje do konkretnych modułów i artefaktów CI po ich wdrożeniu.
-->

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

