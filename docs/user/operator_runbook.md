<!--
[AI-CHANGE | 2026-04-23 14:48 UTC | v0.191]
CO ZMIENIONO: Dodano nowy dokument użytkowy opisujący pracę operatora z zakładkami UI, interpretacją DataQuality/reason_code, scenariuszami awarii i checklistą przedmisyjną.
DLACZEGO: Operator potrzebuje jednoznacznych, technicznych procedur operacyjnych i zasad bezpieczeństwa danych, aby unikać publikacji błędnych detekcji.
JAK TO DZIAŁA: Dokument pełni rolę runbooka operacyjnego — prowadzi krok po kroku przez przygotowanie, monitoring, reakcję na awarie i decyzje o odrzuceniu danych.
TODO: Dodać zrzuty ekranu po wdrożeniu UI (widok każdej zakładki + przykładowe alerty jakości).
-->

# Runbook operatora UI

## Cel dokumentu
Ten dokument definiuje **operacyjną procedurę pracy operatora** dla UI systemu `alf-light-tracking`.
Priorytet bezpieczeństwa danych: **nie publikować wyniku, jeśli istnieje niepewność jakości**.

---

## Zakładki UI — opis i zastosowanie

### 1. Zakładka `Overview`
**Cel:** szybka ocena, czy system może pracować w trybie operacyjnym.

**Operator widzi:**
- globalny status pipeline (`NOMINAL`, `DEGRADED`, `FAIL_SAFE`),
- aktualny stan strumieni wejściowych,
- licznik odrzuconych próbek,
- czas ostatniej poprawnej detekcji.

**Działanie operatora:**
- jeśli status to `NOMINAL`: można kontynuować,
- jeśli status to `DEGRADED`: ograniczyć zaufanie do automatyki i przejść do diagnostyki,
- jeśli status to `FAIL_SAFE`: wstrzymać użycie wyników i uruchomić procedurę awaryjną.

### 2. Zakładka `Detections`
**Cel:** podgląd zaakceptowanych detekcji i ich metadanych jakościowych.

**Operator widzi:**
- listę detekcji przekazanych przez walidator jakości,
- znaczniki czasu i identyfikator źródła,
- powiązane wskaźniki jakości (`DataQuality`).

**Działanie operatora:**
- nie traktować pustej listy jako błędu UI,
- potwierdzić, czy pusta lista wynika z odrzucenia danych niskiej jakości,
- eskalować tylko wtedy, gdy brak detekcji współwystępuje z błędami systemowymi.

### 3. Zakładka `Data Quality`
**Cel:** interpretacja jakości wejścia i powodów odrzucenia.

**Operator widzi:**
- bieżący stan `DataQuality` per źródło,
- `reason_code` dla każdej odrzuconej próbki,
- trendy degradacji (np. rosnący odsetek odrzuceń).

**Działanie operatora:**
- identyfikacja dominującego `reason_code`,
- decyzja: kontynuować, przełączyć tryb, czy zatrzymać misję,
- dołączenie kodów przyczyn do zgłoszenia incydentu.

### 4. Zakładka `Diagnostics`
**Cel:** analiza techniczna problemów i korelacja z logami runtime.

**Operator widzi:**
- błędy synchronizacji czasu,
- błędy transportu/telemetrii,
- informacje o restartach komponentów.

**Działanie operatora:**
- potwierdzić, czy problem dotyczy jakości danych czy infrastruktury,
- jeśli infrastruktura niestabilna — wstrzymać zaufanie do detekcji,
- wykonać checklistę awaryjną i zarejestrować incydent.

---

## Znaczenie `DataQuality` i `reason_code`

## `DataQuality` — jak interpretować
`DataQuality` określa, czy próbka może być użyta do bezpiecznej detekcji.

Minimalny model operacyjny:
- `GOOD` — próbka spełnia progi jakości i może być użyta,
- `UNCERTAIN` — próbka częściowo niespełnia kryteriów; **nie publikować wyniku**,
- `BAD` — próbka niespełnia kryteriów krytycznych; odrzucić bezwarunkowo,
- `MISSING` — brak próbki lub brak metadanych jakości; traktować jak odrzucenie.

> Reguła: `UNCERTAIN`, `BAD`, `MISSING` => brak wyniku detekcji (`None` / pusty rezultat).

## `reason_code` — po co jest i jak używać
`reason_code` to techniczny kod przyczyny odrzucenia lub degradacji.

Przykładowa interpretacja operacyjna:
- `LOW_SIGNAL` — zbyt niski poziom sygnału wejściowego,
- `TIME_DESYNC` — niespójność czasowa między źródłami,
- `OUT_OF_RANGE` — parametry poza dopuszczalnym zakresem,
- `SENSOR_TIMEOUT` — brak danych w oknie czasowym,
- `VALIDATION_ERROR` — naruszenie reguł walidatora.

Wymóg operacyjny:
- każdy incydent musi zawierać: timestamp, `DataQuality`, `reason_code`, źródło danych i status systemu.

---

## Niepewne dane = BRAK DANYCH

**Twarda reguła operacyjna (bez wyjątków):**

Jeżeli operator lub system nie może jednoznacznie potwierdzić jakości próbki, wynik detekcji **musi zostać odrzucony**.

Konsekwencje praktyczne:
1. brak „ręcznego dopychania” niepewnej detekcji do UI,
2. brak interpolacji „na oko” w celu utrzymania ciągłości,
3. brak zastępowania odrzuconych danych danymi syntetycznymi,
4. w przypadku wątpliwości — eskalacja i analiza przyczyny, nie publikacja wyniku.

Ta reguła jest nadrzędna wobec presji czasowej i oczekiwania ciągłości strumienia.

---

## Scenariusze awarii: co widzi operator i co robić

### Scenariusz A — brak detekcji przy aktywnych wejściach
**Co widzi operator:**
- pusta lista w `Detections`,
- wzrost odrzuceń w `Data Quality`,
- status `DEGRADED` lub `NOMINAL` z alertami jakości.

**Co robić:**
1. sprawdzić dominujący `reason_code`,
2. potwierdzić, że odrzucenie jest celowe (mechanizm bezpieczeństwa),
3. uruchomić diagnostykę źródła z najwyższą liczbą odrzuceń,
4. nie zgłaszać „awarii detektora” bez potwierdzenia symptomów infrastrukturalnych.

### Scenariusz B — `TIME_DESYNC` i niestabilna oś czasu
**Co widzi operator:**
- alarmy synchronizacji,
- skoki timestampów,
- duży udział `reason_code=TIME_DESYNC`.

**Co robić:**
1. wstrzymać decyzje oparte na automatycznych detekcjach,
2. sprawdzić źródło czasu i opóźnienia transportowe,
3. po stabilizacji odczekać okno kontrolne i potwierdzić spadek odrzuceń,
4. dopiero po potwierdzeniu wrócić do pracy operacyjnej.

### Scenariusz C — `FAIL_SAFE`
**Co widzi operator:**
- czerwony status globalny,
- odcięcie publikacji wyników,
- aktywną informację o pracy w trybie bezpiecznym.

**Co robić:**
1. przejść na procedurę ręczną,
2. zabezpieczyć logi i metryki z okresu poprzedzającego awarię,
3. otworzyć incydent z pełnym kontekstem (`DataQuality`, `reason_code`, komponent),
4. wznowić automatykę tylko po formalnym potwierdzeniu gotowości.

### Scenariusz D — zanik telemetrii (`SENSOR_TIMEOUT`)
**Co widzi operator:**
- brak aktualizacji dla jednego lub wielu źródeł,
- `reason_code=SENSOR_TIMEOUT`,
- możliwe przejście do `DEGRADED`.

**Co robić:**
1. potwierdzić, czy zanik dotyczy sensora czy transportu,
2. sprawdzić, czy problem lokalny czy systemowy,
3. utrzymać blokadę publikacji dla brakujących danych,
4. kontynuować tylko na źródłach, które mają stabilne `DataQuality=GOOD`.

---

## Checklista „przed startem misji”

1. **Status systemu:** `Overview` pokazuje brak aktywnych alarmów krytycznych.
2. **Synchronizacja czasu:** brak bieżących błędów typu `TIME_DESYNC`.
3. **Jakość danych:** dla wszystkich źródeł krytycznych `DataQuality=GOOD`.
4. **Odrzucenia próbek:** brak niekontrolowanego trendu wzrostowego.
5. **Łączność sensorów:** brak `SENSOR_TIMEOUT` w oknie kontrolnym.
6. **Pipeline detekcji:** pojawiają się świeże, poprawne detekcje testowe.
7. **Procedura awaryjna:** operator ma otwartą instrukcję dla `FAIL_SAFE`.
8. **Logowanie incydentów:** dostępny kanał i szablon zgłoszenia z polami `reason_code`.
9. **Reguła bezpieczeństwa:** zespół potwierdził zasadę „Niepewne dane = BRAK DANYCH”.
10. **Decyzja GO/NO-GO:** formalnie podjęta i zapisana z timestampem.

Jeżeli którykolwiek punkt 1–10 nie jest spełniony, decyzja domyślna to **NO-GO**.
