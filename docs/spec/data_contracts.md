# Kontrakty danych

## Cel
Zdefiniować jednolity kontrakt danych dla wszystkich strumieni używanych w MVP, tak aby każdy panel i każdy moduł interpretował rekordy w identyczny sposób.

## Obowiązkowe pola rekordu
Każdy rekord danych **musi** zawierać:

| Pole | Typ | Wymagalność | Opis |
|---|---|---|---|
| `value` | `object` \| `number` \| `string` \| `boolean` | wymagane | Właściwa wartość pomiaru lub struktura domenowa (np. wektor pozycji, stan binarny). |
| `timestamp` | `string` (RFC3339 UTC) | wymagane | Czas powstania pomiaru w źródle, nie czas odbioru. |
| `source` | `string` | wymagane | Jednoznaczny identyfikator pochodzenia danych (sensor/topic/moduł). |
| `quality` | `enum` | wymagane | Jedna z wartości: `VALID`, `STALE`, `UNAVAILABLE`, `ERROR`. |
| `reason_code` | `string` | opcjonalne (`reason_code?`) | Kod przyczyny dla stanów innych niż `VALID`; wymagany operacyjnie dla diagnostyki. |

## Reguły walidacji ogólnej
1. `timestamp` musi być poprawnym UTC RFC3339.
2. `source` nie może być pusty ani anonimowy (np. `unknown`, `default`).
3. `quality` musi należeć do słownika: `VALID | STALE | UNAVAILABLE | ERROR`.
4. Jeżeli `quality != VALID`, rekord **powinien** zawierać `reason_code`.
5. Zabronione jest generowanie danych zastępczych ("zgadywanie" wartości `value`) w ścieżce produkcyjnej.

## Klasy danych i mapowanie jakości

### 1) Klasa: `sensor_measurement`
Dane bezpośrednio z czujników (np. pozycja, natężenie światła, IMU).

| Warunek | quality | reason_code (przykład) |
|---|---|---|
| Odczyt poprawny, świeży (TTL nieprzekroczony), walidacja zakresu OK | `VALID` | *(puste)* |
| Odczyt poprawny formalnie, ale przeterminowany (TTL przekroczony) | `STALE` | `TTL_EXCEEDED` |
| Brak odczytu lub brak połączenia z sensorem | `UNAVAILABLE` | `NO_SENSOR_DATA` |
| Błąd sterownika, CRC, deserializacji lub niespójny format | `ERROR` | `SENSOR_READ_ERROR` |

### 2) Klasa: `derived_state`
Dane wyliczane (np. estymowana pozycja, stan śledzenia, agregaty).

| Warunek | quality | reason_code (przykład) |
|---|---|---|
| Model obliczeń zasilony kompletnymi wejściami o jakości `VALID` | `VALID` | *(puste)* |
| Obliczenie wykonane na danych przeterminowanych (`STALE`) | `STALE` | `INPUT_STALE` |
| Brak minimalnego zestawu wejść do wyliczenia | `UNAVAILABLE` | `INSUFFICIENT_INPUT` |
| Błąd obliczeń (overflow, wyjątek algorytmu, naruszenie inwariantu) | `ERROR` | `DERIVATION_ERROR` |

### 3) Klasa: `system_health`
Dane diagnostyczne i heartbeat (np. opóźnienia, żywotność modułów).

| Warunek | quality | reason_code (przykład) |
|---|---|---|
| Heartbeat i metryki aktualne, kompletne i spójne | `VALID` | *(puste)* |
| Heartbeat spóźniony, ale ostatni znany stan jeszcze dostępny | `STALE` | `HEARTBEAT_DELAYED` |
| Brak heartbeat lub brak kanału health | `UNAVAILABLE` | `HEARTBEAT_MISSING` |
| Niespójny format diagnostyki lub błąd źródła monitoringu | `ERROR` | `HEALTH_PIPELINE_ERROR` |

## Reguła bezpieczeństwa danych
> **Niepewne dane => brak wyniku (`UNAVAILABLE`/`ERROR`), nigdy zgadywanie.**

Interpretacja operacyjna:
- Jeżeli nie można potwierdzić poprawności `value`, rekord nie może być oznaczony jako `VALID`.
- Gdy nie da się odróżnić "braku danych" od "błędu technicznego", preferuj `ERROR` i eskalację diagnostyczną.
- Dla ścieżek detekcyjnych wynik końcowy ma być pominięty (`None`/brak publikacji), jeżeli wejścia nie spełniają kryterium pewności.
