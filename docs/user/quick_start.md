<!--
[AI-CHANGE | 2026-04-20 20:39 UTC | v0.153]
CO ZMIENIONO: Utworzono nowy dokument specyfikacyjny/architektoniczny/użytkowy dla etapu Stage 0.
DLACZEGO: Uporządkowanie wymagań i procedur operacyjnych projektu oraz formalizacja kryteriów jakości.
JAK TO DZIAŁA: Dokument stanowi źródło referencyjne; definiuje zasady, zakres i wymagane działania dla zespołu.
TODO: Uzupełnić dokument o referencje do konkretnych modułów i artefaktów CI po ich wdrożeniu.
-->

# Quick start użytkownika

## Cel
Szybkie uruchomienie środowiska do obserwacji działania systemu.

## Kroki
1. Uruchom wymagane usługi ROS2.
2. Załaduj konfigurację środowiskową i progi jakości.
3. Włącz dashboard operatora.
4. Sprawdź, czy status startowy to `NOMINAL` lub `DEGRADED`.

## Ważne zasady
- Jeśli system zgłasza odrzucenie danych, nie wymuszaj publikacji wyniku.
- Obowiązuje reguła: **lepszy brak wyniku niż błędny wynik**.
- System nie generuje danych fikcyjnych do wypełniania UI.

