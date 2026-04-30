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

