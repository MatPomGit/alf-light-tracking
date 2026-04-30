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

