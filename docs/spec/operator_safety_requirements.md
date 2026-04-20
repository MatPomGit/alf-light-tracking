<!--
[AI-CHANGE | 2026-04-20 20:39 UTC | v0.153]
CO ZMIENIONO: Utworzono nowy dokument specyfikacyjny/architektoniczny/użytkowy dla etapu Stage 0.
DLACZEGO: Uporządkowanie wymagań i procedur operacyjnych projektu oraz formalizacja kryteriów jakości.
JAK TO DZIAŁA: Dokument stanowi źródło referencyjne; definiuje zasady, zakres i wymagane działania dla zespołu.
TODO: Uzupełnić dokument o referencje do konkretnych modułów i artefaktów CI po ich wdrożeniu.
-->

# Wymagania bezpieczeństwa operatora

## Zasady ogólne
1. Operator musi mieć czytelny status systemu (NOMINAL/DEGRADED/FAIL_SAFE).
2. Każda decyzja automatyczna musi być audytowalna.
3. Sterowanie awaryjne ma priorytet nad automatyzacją.

## Wymagania funkcjonalne
- Przycisk STOP aktywny niezależnie od stanu UI.
- Alarm przy spadku jakości danych poniżej progu.
- Blokada komend wykonawczych przy niepewnej detekcji.

## Polityka wyniku
W warstwie operatorskiej obowiązuje zasada: **lepszy brak wyniku niż błędny wynik** oraz **brak danych fikcyjnych** w prezentacji sytuacji.

