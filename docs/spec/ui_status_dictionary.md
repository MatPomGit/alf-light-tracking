<!--
[AI-CHANGE | 2026-04-20 20:39 UTC | v0.153]
CO ZMIENIONO: Utworzono nowy dokument specyfikacyjny/architektoniczny/użytkowy dla etapu Stage 0.
DLACZEGO: Uporządkowanie wymagań i procedur operacyjnych projektu oraz formalizacja kryteriów jakości.
JAK TO DZIAŁA: Dokument stanowi źródło referencyjne; definiuje zasady, zakres i wymagane działania dla zespołu.
TODO: Uzupełnić dokument o referencje do konkretnych modułów i artefaktów CI po ich wdrożeniu.
-->

# Słownik statusów UI

## Statusy główne
| Kod | Nazwa | Znaczenie | Akcja operatora |
|---|---|---|---|
| `NOMINAL` | Nominalny | Wszystkie walidacje zaliczone | Monitorowanie |
| `DEGRADED` | Ograniczony | Część danych odrzucona | Ograniczyć automatyzację |
| `FAIL_SAFE` | Bezpieczne zatrzymanie | Wyniki detekcji zablokowane | Przejść na procedurę ręczną |
| `DATA_REJECTED` | Dane odrzucone | Naruszenie kontraktu danych | Sprawdzić sensory i czas |

## Notyfikacje
UI nie może „upiększać” braków danych. Zamiast tego pokazuje jawny status odrzucenia.

## Zasada
- **Lepszy brak wyniku niż błędny wynik**.
- **Brak danych fikcyjnych** w polach statusowych i historycznych.

