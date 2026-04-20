<!--
[AI-CHANGE | 2026-04-20 20:39 UTC | v0.153]
CO ZMIENIONO: Utworzono nowy dokument specyfikacyjny/architektoniczny/użytkowy dla etapu Stage 0.
DLACZEGO: Uporządkowanie wymagań i procedur operacyjnych projektu oraz formalizacja kryteriów jakości.
JAK TO DZIAŁA: Dokument stanowi źródło referencyjne; definiuje zasady, zakres i wymagane działania dla zespołu.
TODO: Uzupełnić dokument o referencje do konkretnych modułów i artefaktów CI po ich wdrożeniu.
-->

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

