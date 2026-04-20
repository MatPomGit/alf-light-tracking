<!--
[AI-CHANGE | 2026-04-20 20:56 UTC | v0.155]
CO ZMIENIONO: Zaktualizowano politykę jakości danych o obowiązkową regułę "niepewne dane => brak wyniku" oraz dodano mapowanie jakości dla klas danych i każdego panelu MVP.
DLACZEGO: Potrzebna była jawna, testowalna polityka decyzyjna, która eliminuje zgadywanie i wymusza bezpieczną degradację prezentacji danych.
JAK TO DZIAŁA: Każdy panel najpierw czyta `quality` z kontraktu danych, następnie stosuje deterministyczną mapę zachowania UI; stany `UNAVAILABLE` i `ERROR` blokują prezentację wartości domenowej.
TODO: Dodać automatyczne testy kontraktowe UI (snapshot + testy mapowania quality), aby każdy panel MVP był weryfikowany w CI.
-->

# Polityka jakości danych

## Priorytet systemu
**Lepszy brak wyniku niż błędny wynik.**

## Słownik jakości (globalny)
- `VALID` — dane poprawne i świeże, mogą zasilać logikę oraz UI.
- `STALE` — dane formalnie poprawne, ale przeterminowane; mogą być pokazane wyłącznie jako historyczne/opóźnione.
- `UNAVAILABLE` — brak danych lub brak minimalnego kontekstu; brak wartości domenowej.
- `ERROR` — błąd techniczny lub semantyczny; brak wartości domenowej, wymagana diagnostyka.

## Reguła jawna (obowiązkowa)
> **Niepewne dane => brak wyniku (`UNAVAILABLE`/`ERROR`), nigdy zgadywanie.**

Konsekwencje:
1. Nie wolno synthesizować `value` na podstawie heurystyki, jeżeli wejścia są niekompletne lub niespójne.
2. W module detekcji brak pewności wejść skutkuje odrzuceniem próbki (brak publikacji rekordu domenowego).
3. UI nie może maskować stanu jakości (zakaz prezentacji "pozornie poprawnej" wartości).

## Mapowanie `VALID/STALE/UNAVAILABLE/ERROR` dla klas danych

| Klasa danych | VALID | STALE | UNAVAILABLE | ERROR |
|---|---|---|---|---|
| `sensor_measurement` | pomiar świeży i w zakresie | pomiar po TTL | brak ramki/pakietu | błąd odczytu/parsowania |
| `derived_state` | obliczenia na poprawnych wejściach | obliczenia na danych stale | brak minimalnych wejść | błąd algorytmu/inwariantu |
| `system_health` | heartbeat i metryki aktualne | heartbeat opóźniony | brak heartbeat | błąd pipeline monitoringu |

## DoD: mapowanie jakości w każdym panelu MVP

Poniżej zdefiniowano wymagane zachowanie każdego panelu MVP.

### Panel MVP: `Tracking`
Źródła: `derived_state` + wspierająco `sensor_measurement`.
- `VALID`: pokaż `value` (pozycja/stan śledzenia) jako bieżący.
- `STALE`: pokaż ostatni znany stan wyłącznie z etykietą "opóźnione"; bez decyzji autonomicznych.
- `UNAVAILABLE`: ukryj wartość śledzenia, pokaż "brak danych".
- `ERROR`: ukryj wartość śledzenia, pokaż status błędu i `reason_code`.

### Panel MVP: `Sensors`
Źródła: `sensor_measurement`.
- `VALID`: pokaż bieżące wartości sensorów.
- `STALE`: pokaż wartości jako historyczne + znacznik TTL.
- `UNAVAILABLE`: pokaż brak odczytu dla konkretnego `source`.
- `ERROR`: pokaż błąd czujnika/transportu i zablokuj użycie wartości w downstream.

### Panel MVP: `System Health`
Źródła: `system_health`.
- `VALID`: stan systemu zielony, metryki aktywne.
- `STALE`: stan ostrzegawczy, metryki tylko informacyjne.
- `UNAVAILABLE`: brak heartbeat; panel wskazuje utratę telemetrii.
- `ERROR`: jawny alarm pipeline monitoringu, wymagane działania operatora.

### Panel MVP: `Decision/Output`
Źródła: skonsolidowane `derived_state` (oraz reguły bezpieczeństwa).
- `VALID`: można publikować wynik końcowy.
- `STALE`: wynik końcowy nie jest publikowany operacyjnie; tylko podgląd historyczny.
- `UNAVAILABLE`: brak publikacji wyniku końcowego.
- `ERROR`: brak publikacji wyniku końcowego + eskalacja diagnostyczna.

## Kryterium akceptacji polityki
Polityka jest spełniona, gdy:
1. każdy rekord posiada pola `value`, `timestamp`, `source`, `quality` (`reason_code?` zależnie od sytuacji),
2. każda klasa danych używa mapowania `VALID/STALE/UNAVAILABLE/ERROR`,
3. każdy panel MVP implementuje powyższe mapowanie bez wyjątków,
4. żaden komponent nie zgaduje wartości przy niepewności danych.
