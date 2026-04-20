<!--
[AI-CHANGE | 2026-04-20 20:39 UTC | v0.153]
CO ZMIENIONO: Utworzono nowy dokument specyfikacyjny/architektoniczny/użytkowy dla etapu Stage 0.
DLACZEGO: Uporządkowanie wymagań i procedur operacyjnych projektu oraz formalizacja kryteriów jakości.
JAK TO DZIAŁA: Dokument stanowi źródło referencyjne; definiuje zasady, zakres i wymagane działania dla zespołu.
TODO: Uzupełnić dokument o referencje do konkretnych modułów i artefaktów CI po ich wdrożeniu.
-->

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

