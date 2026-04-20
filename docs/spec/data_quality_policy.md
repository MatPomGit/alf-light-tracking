<!--
[AI-CHANGE | 2026-04-20 20:39 UTC | v0.153]
CO ZMIENIONO: Utworzono nowy dokument specyfikacyjny/architektoniczny/użytkowy dla etapu Stage 0.
DLACZEGO: Uporządkowanie wymagań i procedur operacyjnych projektu oraz formalizacja kryteriów jakości.
JAK TO DZIAŁA: Dokument stanowi źródło referencyjne; definiuje zasady, zakres i wymagane działania dla zespołu.
TODO: Uzupełnić dokument o referencje do konkretnych modułów i artefaktów CI po ich wdrożeniu.
-->

# Polityka jakości danych

## Priorytet
System preferuje bezpieczeństwo decyzji: **lepszy brak wyniku niż błędny wynik**.

## Filary polityki
1. Kompletność: wymagane pola nie mogą być puste.
2. Spójność czasowa: odrzucamy dane po czasie TTL.
3. Wiarygodność: confidence poniżej progu skutkuje odrzuceniem.
4. Idempotencja: duplikaty oznaczamy i nie propagujemy dalej.
5. **Brak danych fikcyjnych**: nie wolno symulować pomiaru w ścieżce produkcyjnej.

## Tryby degradacji
- `DEGRADED_PASSIVE`: brak detekcji, tylko telemetria zdrowia.
- `DEGRADED_LIMITED`: publikacja wyłącznie metryk diagnostycznych.
- `FAIL_SAFE`: zatrzymanie publikacji wyników detekcji.

