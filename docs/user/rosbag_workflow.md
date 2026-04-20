<!--
[AI-CHANGE | 2026-04-20 20:39 UTC | v0.153]
CO ZMIENIONO: Utworzono nowy dokument specyfikacyjny/architektoniczny/użytkowy dla etapu Stage 0.
DLACZEGO: Uporządkowanie wymagań i procedur operacyjnych projektu oraz formalizacja kryteriów jakości.
JAK TO DZIAŁA: Dokument stanowi źródło referencyjne; definiuje zasady, zakres i wymagane działania dla zespołu.
TODO: Uzupełnić dokument o referencje do konkretnych modułów i artefaktów CI po ich wdrożeniu.
-->

# Workflow użytkownika ROS bag

## Przygotowanie
1. Ustal identyfikator sesji i cel nagrania.
2. Potwierdź konfigurację tematów i częstotliwości.

## Nagranie
- Uruchom `ros2 bag record` dla zestawu tematów referencyjnych.
- Zachowaj metadane: wersja aplikacji, commit, konfiguracja progów.

## Odtwarzanie i analiza
- Odtwarzaj dane w izolowanym środowisku testowym.
- Zbieraj metryki odrzuceń i przyczyny (`REJECTED`).

## Zasady jakości
- Nie traktuj braku detekcji jako błędu bez analizy jakości wejścia.
- **Lepszy brak wyniku niż błędny wynik**.
- **Brak danych fikcyjnych** w raportach z odtworzenia.

