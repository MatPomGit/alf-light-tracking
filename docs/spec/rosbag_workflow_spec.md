<!--
[AI-CHANGE | 2026-04-20 20:39 UTC | v0.153]
CO ZMIENIONO: Utworzono nowy dokument specyfikacyjny/architektoniczny/użytkowy dla etapu Stage 0.
DLACZEGO: Uporządkowanie wymagań i procedur operacyjnych projektu oraz formalizacja kryteriów jakości.
JAK TO DZIAŁA: Dokument stanowi źródło referencyjne; definiuje zasady, zakres i wymagane działania dla zespołu.
TODO: Uzupełnić dokument o referencje do konkretnych modułów i artefaktów CI po ich wdrożeniu.
-->

# Specyfikacja workflow ROS bag

## Kroki procesu
1. Rejestracja sesji (`record`) z metadanymi wersji i konfiguracji.
2. Walidacja integralności bag (`reindex`, checksum).
3. Odtworzenie (`play`) z kontrolą czasu i kolejności.
4. Ekstrakcja metryk jakości oraz raport odrzuceń.

## Wymagania jakościowe
- Sesja bez metadanych jest odrzucana.
- Przy niespójności czasu odtwarzania raport oznacza próbkę jako niewiarygodną.
- Jeśli detekcja jest niepewna, zapisujemy `REJECTED`, nie generujemy sztucznego wyniku.
- **Brak danych fikcyjnych**: testy porównawcze używają wyłącznie rzeczywistych lub jawnie oznaczonych danych syntetycznych.

