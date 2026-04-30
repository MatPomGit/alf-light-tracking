# Odporność na błędy

## Strategie
1. Timeout i watchdog dla komponentów krytycznych.
2. Circuit breaker dla źródeł niestabilnych danych.
3. Retry ograniczone z backoffem dla kanałów pomocniczych.

## Tryby reakcji
- Soft failure: przejście do `DEGRADED`.
- Hard failure: wymuszenie `FAIL_SAFE`.

## Wymagania decyzji
Przy dowolnej niepewności klasyfikacji system nie emituje wyniku detekcji. Zasada: **lepszy brak wyniku niż błędny wynik**.

## Zakaz
**Brak danych fikcyjnych** jako mechanizmu ukrywania awarii.

