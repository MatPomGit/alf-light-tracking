<!--
[AI-CHANGE | 2026-04-20 20:39 UTC | v0.153]
CO ZMIENIONO: Utworzono nowy dokument specyfikacyjny/architektoniczny/użytkowy dla etapu Stage 0.
DLACZEGO: Uporządkowanie wymagań i procedur operacyjnych projektu oraz formalizacja kryteriów jakości.
JAK TO DZIAŁA: Dokument stanowi źródło referencyjne; definiuje zasady, zakres i wymagane działania dla zespołu.
TODO: Uzupełnić dokument o referencje do konkretnych modułów i artefaktów CI po ich wdrożeniu.
-->

# Wersjonowanie i build

## Model wersjonowania
- SemVer dla artefaktów aplikacyjnych.
- Numer build zawiera hash commita i znacznik czasu UTC.

## Wymagania pipeline build
1. Build reprodukowalny z lockfile.
2. Artefakty podpisane i śledzone w rejestrze.
3. Raport kompatybilności kontraktów danych przy każdej zmianie minor/major.

## Polityka jakości
- Wydanie nie może włączać trybu domyślnego, który maskuje błędne detekcje.
- Gdy test jakości nie przechodzi, release jest blokowany: **lepszy brak wyniku niż błędny wynik**.
- **Brak danych fikcyjnych** w testach akceptacyjnych bez oznaczenia `synthetic=true`.

