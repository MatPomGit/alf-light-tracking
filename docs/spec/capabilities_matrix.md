# Macierz możliwości systemu

## Założenia
Macierz wskazuje, które funkcje są dostępne w zależności od stanu platformy i jakości danych.

| Funkcja | Nominalny | Degraded | Fail-safe |
|---|---|---|---|
| Detekcja obiektów świetlnych | TAK | OGRANICZONA | NIE |
| Publikacja danych do UI | TAK | TAK (diagnostyka) | TAK (alarm) |
| Sterowanie półautomatyczne | TAK | NIE | NIE |

## Warunek jakości
Każda komórka „TAK” obowiązuje tylko przy danych spełniających politykę jakości. W przeciwnym razie zwracamy brak wyniku.

## Zasada danych
- **Lepszy brak wyniku niż błędny wynik**.
- **Brak danych fikcyjnych** w tabelach statusu i telemetrii operatora.

