<!--
[AI-CHANGE | 2026-04-20 20:39 UTC | v0.153]
CO ZMIENIONO: Utworzono nowy dokument specyfikacyjny/architektoniczny/użytkowy dla etapu Stage 0.
DLACZEGO: Uporządkowanie wymagań i procedur operacyjnych projektu oraz formalizacja kryteriów jakości.
JAK TO DZIAŁA: Dokument stanowi źródło referencyjne; definiuje zasady, zakres i wymagane działania dla zespołu.
TODO: Uzupełnić dokument o referencje do konkretnych modułów i artefaktów CI po ich wdrożeniu.
-->

# Granice modułów

## Moduły
- `sensor_adapter`
- `detector_core`
- `fusion_manager`
- `safety_supervisor`
- `operator_ui`

## Kontrakty między modułami
Każda granica modułu wymaga jawnego kontraktu: schemat + walidacje + kody odrzucenia.

## Reguły odpowiedzialności
- `detector_core` nie publikuje wyniku przy niepewnych danych wejściowych.
- `safety_supervisor` wymusza stan `FAIL_SAFE` przy naruszeniu polityki jakości.
- `operator_ui` prezentuje faktyczny stan bez wartości zastępczych.

## Zasady jakości
**Lepszy brak wyniku niż błędny wynik** oraz **brak danych fikcyjnych** obowiązują na każdej granicy.

