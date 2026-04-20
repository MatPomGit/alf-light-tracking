<!--
[AI-CHANGE | 2026-04-20 20:39 UTC | v0.153]
CO ZMIENIONO: Utworzono nowy dokument specyfikacyjny/architektoniczny/użytkowy dla etapu Stage 0.
DLACZEGO: Uporządkowanie wymagań i procedur operacyjnych projektu oraz formalizacja kryteriów jakości.
JAK TO DZIAŁA: Dokument stanowi źródło referencyjne; definiuje zasady, zakres i wymagane działania dla zespołu.
TODO: Uzupełnić dokument o referencje do konkretnych modułów i artefaktów CI po ich wdrożeniu.
-->

# Inwentaryzacja interfejsów ROS2

## Zakres
Dokument opisuje wszystkie kontrakty komunikacyjne wykorzystywane przez system śledzenia światła: topic, service, action oraz parametry runtime.

## Zasady jakości danych
- Zasada nadrzędna: **lepszy brak wyniku niż błędny wynik**. Jeśli producent danych nie spełnia walidacji, odbiornik ma odrzucić wiadomość.
- **Brak danych fikcyjnych**: niedozwolone jest generowanie wartości zastępczych, które nie pochodzą z pomiaru lub zweryfikowanej estymacji.

## Tabela interfejsów (szablon)
| Interfejs | Typ | Producent | Konsument | Kryterium odrzucenia |
|---|---|---|---|---|
| `/light_tracking/detections` | `DetectionArray` | Detector Node | Fusion Node, UI | `confidence < threshold` lub brak timestamp |
| `/light_tracking/health` | `DiagnosticArray` | Wszystkie moduły | Supervisor | status `ERROR` bez kodu przyczyny |

## Reguły utrzymania
1. Każda zmiana interfejsu wymaga aktualizacji tego dokumentu i changelogu release.
2. Każde pole krytyczne musi mieć opis typu, jednostki i zakresu.
3. Interfejs bez jawnej polityki odrzucania jest niekompletny.

