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

