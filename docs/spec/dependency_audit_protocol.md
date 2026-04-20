<!--
[AI-CHANGE | 2026-04-20 20:39 UTC | v0.153]
CO ZMIENIONO: Utworzono nowy dokument specyfikacyjny/architektoniczny/użytkowy dla etapu Stage 0.
DLACZEGO: Uporządkowanie wymagań i procedur operacyjnych projektu oraz formalizacja kryteriów jakości.
JAK TO DZIAŁA: Dokument stanowi źródło referencyjne; definiuje zasady, zakres i wymagane działania dla zespołu.
TODO: Uzupełnić dokument o referencje do konkretnych modułów i artefaktów CI po ich wdrożeniu.
-->

# Protokół audytu zależności

## Cel
Standaryzacja audytu bezpieczeństwa i kompatybilności bibliotek.

## Procedura
1. Snapshot wersji (`pip freeze`, `rosdep`, lockfile).
2. Skan CVE.
3. Weryfikacja licencji.
4. Ocena wpływu na deterministyczność pipeline detekcji.

## Kryteria blokujące
- Krytyczne CVE bez mitigacji.
- Zależność wprowadzająca niejawne fallbacki generujące dane zastępcze.
- Brak pinowania wersji komponentu krytycznego.

## Zasada detekcji
W razie niepewności zachowania po aktualizacji, funkcję detekcji blokujemy do czasu walidacji — **lepszy brak wyniku niż błędny wynik**.

