# Wytyczne dla agentów AI w projekcie `alf-light-tracking`

## Cel
Te zasady obowiązują przy każdej zmianie kodu i dokumentacji w tym repozytorium.
Priorytet projektu: **lepiej nie zwrócić wyniku detekcji, niż zwrócić wynik błędny**.

## Zasady obowiązkowe
1. **Oznaczaj każdy zamieniony fragment kodu** specjalnym blokiem komentarza.
2. Do każdego oznaczonego fragmentu dodaj komentarze po polsku:
   - **co** zostało zmienione,
   - **czemu** zostało zmienione,
   - **jak** teraz działa.
3. W każdym zmienianym obszarze dodaj także przynajmniej jedno pole `TODO` opisujące sensowny kierunek dalszych usprawnień.
4. Zasada jakości detekcji:
   - jeśli istnieje ryzyko zwrócenia niepewnej lub błędnej detekcji, preferuj brak wyniku (`None` / pusty rezultat / odrzucenie próbki) zamiast zwrócenia fałszywych danych.

## Format oznaczania zmian w kodzie
Każdy zamieniony fragment musi zaczynać się od nagłówka komentarza w poniższym formacie:

```text
[AI-CHANGE | YYYY-MM-DD HH:MM UTC | v0.<N>]
```

Gdzie:
- `YYYY-MM-DD HH:MM UTC` — dokładna data i czas wprowadzenia zmiany,
- `v0.<N>` — numer wersji proporcjonalny do liczby commitów,
- `<N>` — aktualna liczba commitów w repozytorium (`git rev-list --count HEAD`).

Po nagłówku dodaj sekcje komentarzy (po polsku), np.:

```text
CO ZMIENIONO: ...
DLACZEGO: ...
JAK TO DZIAŁA: ...
TODO: ...
```

## Styl komentarzy i kodu
- Komentarze oraz opisy: **język polski**.
- Kod źródłowy (nazwy zmiennych, funkcji, klas): **język angielski**.
- Komentarze mają być konkretne i techniczne, bez ogólników.

## Minimalna checklista przed commitem
- [ ] Każdy zmieniony fragment ma nagłówek `[AI-CHANGE | ... | v0.<N>]`.
- [ ] Przy każdym fragmencie są sekcje: `CO ZMIENIONO`, `DLACZEGO`, `JAK TO DZIAŁA`.
- [ ] Dodano przynajmniej jedno `TODO` dla zmienianego obszaru.
- [ ] Zasada „brak wyniku lepszy niż błędny wynik” jest zachowana w logice detekcji.
