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

