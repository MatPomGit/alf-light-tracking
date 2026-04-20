<!--
[AI-CHANGE | 2026-04-20 20:39 UTC | v0.153]
CO ZMIENIONO: Utworzono nowy dokument specyfikacyjny/architektoniczny/użytkowy dla etapu Stage 0.
DLACZEGO: Uporządkowanie wymagań i procedur operacyjnych projektu oraz formalizacja kryteriów jakości.
JAK TO DZIAŁA: Dokument stanowi źródło referencyjne; definiuje zasady, zakres i wymagane działania dla zespołu.
TODO: Uzupełnić dokument o referencje do konkretnych modułów i artefaktów CI po ich wdrożeniu.
-->

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

