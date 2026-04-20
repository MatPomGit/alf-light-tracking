<!--
[AI-CHANGE | 2026-04-20 20:39 UTC | v0.153]
CO ZMIENIONO: Utworzono nowy dokument specyfikacyjny/architektoniczny/użytkowy dla etapu Stage 0.
DLACZEGO: Uporządkowanie wymagań i procedur operacyjnych projektu oraz formalizacja kryteriów jakości.
JAK TO DZIAŁA: Dokument stanowi źródło referencyjne; definiuje zasady, zakres i wymagane działania dla zespołu.
TODO: Uzupełnić dokument o referencje do konkretnych modułów i artefaktów CI po ich wdrożeniu.
-->

# Kontrakty danych

## Cel
Ustalenie jednolitego kontraktu dla danych wejściowych, pośrednich i wyjściowych.

## Reguły kontraktowe
- Każdy rekord musi zawierać `source_id`, `timestamp_utc`, `schema_version` i `quality_flag`.
- Walidacja schematu jest obowiązkowa przed publikacją.
- Gdy walidacja nie przechodzi: zwracamy pusty rezultat (`None` / brak publikacji), bo **lepszy brak wyniku niż błędny wynik**.
- **Brak danych fikcyjnych**: pola wymagane nie mogą być uzupełniane losową lub stałą wartością techniczną.

## Kontrakt minimalny (szablon)
| Pole | Typ | Wymagalność | Zasada walidacji |
|---|---|---|---|
| `timestamp_utc` | RFC3339 | wymagane | różnica czasu < 2 s względem zegara systemowego |
| `confidence` | float | opcjonalne | zakres [0.0, 1.0] |
| `quality_flag` | enum | wymagane | `VALID`, `REJECTED`, `DEGRADED` |

