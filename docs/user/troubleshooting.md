# Troubleshooting

## Typowe problemy
### Brak detekcji
- Sprawdź logi walidacji danych (`quality_flag`).
- Zweryfikuj opóźnienia czasowe i synchronizację zegara.

### Status `DEGRADED`
- Sprawdź, które źródło danych zostało odrzucone.
- Ogranicz automatyzację do czasu przywrócenia jakości.

### Status `FAIL_SAFE`
- Użyj procedury ręcznej.
- Otwórz incydent i dołącz logi diagnostyczne.

## Zasady interpretacji
Brak wyniku detekcji może być poprawnym, bezpiecznym zachowaniem. **Lepszy brak wyniku niż błędny wynik**. System nie podstawia danych fikcyjnych.

