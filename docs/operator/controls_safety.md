<!--
[AI-CHANGE | 2026-04-20 20:39 UTC | v0.153]
CO ZMIENIONO: Utworzono nowy dokument specyfikacyjny/architektoniczny/użytkowy dla etapu Stage 0.
DLACZEGO: Uporządkowanie wymagań i procedur operacyjnych projektu oraz formalizacja kryteriów jakości.
JAK TO DZIAŁA: Dokument stanowi źródło referencyjne; definiuje zasady, zakres i wymagane działania dla zespołu.
TODO: Uzupełnić dokument o referencje do konkretnych modułów i artefaktów CI po ich wdrożeniu.
-->

# Sterowanie i bezpieczeństwo operatora

## Pulpit sterowania
- `START/STOP` pipeline.
- Przełącznik trybu `AUTO/MANUAL`.
- Potwierdzenie alarmów krytycznych.

## Procedury bezpieczeństwa
1. Przy statusie `FAIL_SAFE` natychmiast przejdź na tryb ręczny.
2. Przy `DATA_REJECTED` zweryfikuj sensory i synchronizację czasu.
3. Nie wyłączaj walidacji jakości w produkcji.

## Reguła decyzji
W przypadku niepewności dane są odrzucane. **Lepszy brak wyniku niż błędny wynik** oraz **brak danych fikcyjnych** są obowiązkowe.

