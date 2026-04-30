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

