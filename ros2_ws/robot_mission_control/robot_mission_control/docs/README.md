<!--
[AI-CHANGE | 2026-04-27 12:59 UTC | v0.202]
CO ZMIENIONO: Rozbudowano README do centralnego spisu dokumentów z polami: nazwa, cel, owner i source of truth.
DLACZEGO: Potrzebny jest jednoznaczny punkt wejścia, który eliminuje problem „gdzie co jest” i skraca czas szukania informacji.
JAK TO DZIAŁA: README pełni rolę rejestru; każdy nowy dokument musi zostać dopisany do tabeli wraz z właścicielem i wskazaniem źródła prawdy.
TODO: Dodać automatyczny check CI, który wykryje pliki *.md w katalogu docs nieujęte w tabeli rejestru.
-->

# Centralny spis dokumentów — `robot_mission_control/docs`

Ten plik jest **jedynym punktem wejścia** do dokumentacji modułu `robot_mission_control`.
Jeżeli szukasz informacji o architekturze, decyzjach lub procesie — zacznij tutaj.

## Rejestr dokumentów

| Nazwa dokumentu | Cel | Owner | Source of truth |
|---|---|---|---|
| `README.md` | Centralny indeks dokumentacji i zasady utrzymania spisu. | Zespół `robot_mission_control` (maintainer bieżącego release’u) | Ten plik (`docs/README.md`) |

## Zasady utrzymania spisu

1. Każdy nowy dokument w `docs/` musi zostać dopisany do tabeli **w tym samym PR**.
2. Pole **Owner** wskazuje osobę lub zespół odpowiedzialny merytorycznie za aktualność treści.
3. Pole **Source of truth** musi wskazywać jeden, konkretny dokument nadrzędny dla danego tematu.
4. Gdy dokument przestaje być aktualny, nie usuwaj go „po cichu” — oznacz status i wskaż następcę.

## Konwencja wpisów (krótki szablon)

Przy dodawaniu nowego dokumentu użyj wiersza w formacie:

```md
| `ścieżka/do/pliku.md` | Krótki opis celu dokumentu. | Imię/Nick lub nazwa zespołu. | `ścieżka/do/source_of_truth.md` |
```

Dla bieżącej wersji elementy operacyjne oznaczone jako niegotowe pozostają **NIEDOSTĘPNE W TEJ WERSJI**.
