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

## Status panelu mapy (`MapTab`)
| Tekst UI | Warunek techniczny | Źródło sygnału |
|---|---|---|
| `GOTOWY` | `validate_map_sample` zwraca `DataQuality.VALID` i `reason_code=ok` | Poprawna próbka + aktywny TF + aktywny ROS |
| `OCZEKIWANIE NA DANE` | Każdy inny przypadek degradacji poza ROS/TF (np. `missing_sample`, `MAP_POSE_STALE`, `degraded_input_quality:*`) | Wynik walidacji mapy |
| `BRAK TF` | `reason_code=MAP_TF_MISSING` | Walidacja dostępności TF |
| `ROZŁĄCZONY ROS` | `reason_code=ros_unavailable` | Walidacja połączenia ROS |

## Zasada
- **Lepszy brak wyniku niż błędny wynik**.
- **Brak danych fikcyjnych** w polach statusowych i historycznych.
