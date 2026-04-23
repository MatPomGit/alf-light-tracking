<!--
[AI-CHANGE | 2026-04-23 19:01 UTC | v0.195]
CO ZMIENIONO: Rozszerzono runbook o pełną procedurę dla wszystkich tabów UI, instrukcje pracy na kartach, interpretację jakości danych i reakcje na awarie.
DLACZEGO: Operator ma mieć jedną, kompletną instrukcję działania bez luk i bez rozproszonych notatek.
JAK TO DZIAŁA: Dokument prowadzi operatora kolejno przez zakładki, decyzje jakościowe i scenariusze awaryjne; domyślną decyzją przy niepewności jest odrzucenie wyniku.
TODO: Dodać mapowanie pól UI do konkretnych tematów ROS2 po zamrożeniu kontraktu telemetrycznego.
-->

# Runbook operatora UI

## Zasada nadrzędna
Jeśli jakość próbki jest niepewna, wynik detekcji **nie może** zostać opublikowany (`None` / pusty wynik).

## Procedura pracy operatora (pełny obieg)
1. Wejdź w `Overview` i potwierdź status globalny.
2. Wejdź w `Telemetry` i sprawdź świeżość oraz kompletność strumieni.
3. Wejdź w `Video & Depth` i potwierdź poprawność wejścia wizualnego.
4. Wejdź w `Controls` i sprawdź gotowość akcji (bez uruchamiania ryzykownych komend).
5. Wejdź w `Diagnostics` i zweryfikuj brak aktywnych błędów krytycznych.
6. Wejdź w `Rosbag` i potwierdź gotowość zapisu/odtwarzania dla analizy incydentu.
7. Wejdź w `Extensions` i upewnij się, że rozszerzenia nie są źródłem degradacji.
8. Wejdź w `Debug` tylko gdy wymaga tego diagnostyka, nie do normalnej pracy operacyjnej.

---

## Zakładki i karty — instrukcje operacyjne

### 1) `Overview`
**Cel:** decyzja GO/NO-GO.

**Karty (co sprawdzać):**
- **Pipeline Status**: `NOMINAL` / `DEGRADED` / `FAIL_SAFE`.
- **Input Health**: stan źródeł danych.
- **Rejected Samples**: trend odrzuceń.
- **Last Valid Detection**: czas ostatniej poprawnej detekcji.

**Reakcja operatora:**
- `NOMINAL`: przejdź do dalszych tabów.
- `DEGRADED`: ogranicz zaufanie do automatyki i przejdź do `Diagnostics`.
- `FAIL_SAFE`: natychmiast procedura awaryjna, brak użycia wyników.

### 2) `Telemetry`
**Cel:** kontrola integralności strumieni runtime.

**Karty:**
- **Topics Freshness**: czy dane przychodzą w oknie czasowym.
- **Rate/Latency**: czy opóźnienia nie rosną ponad próg.
- **Source Consistency**: zgodność metryk między źródłami.

**Reakcja operatora:**
- przy spadku świeżości lub rosnącym opóźnieniu oznacz system jako ryzykowny,
- potwierdź, czy problem lokalny czy globalny,
- przy niejednoznaczności zatrzymaj decyzje oparte na detekcjach.

### 3) `Video & Depth`
**Cel:** ocena jakości wejścia percepcji.

**Karty:**
- **RGB Preview**: ekspozycja, ostrość, saturacja.
- **Depth Preview**: stabilność mapy głębi i brak „dziur”.
- **Frame Sync**: zgodność czasowa RGB/Depth.

**Reakcja operatora:**
- przy artefaktach obrazu lub desynchronizacji oznacz próbki jako niepewne,
- nie kompensuj ręcznie braków obrazu,
- zgłoś incydent, jeśli problem utrzymuje się dłużej niż okno kontrolne.

### 4) `Controls`
**Cel:** bezpieczne sterowanie misją.

**Karty:**
- **Mission Actions**: uruchomienie/anulowanie akcji.
- **Quick Actions**: skróty operatorskie.
- **Action Result**: status wykonania i wynik backendu.

**Reakcja operatora:**
- nie wysyłaj kolejnej komendy przy aktywnym goal,
- przy braku pewnego statusu wyniku traktuj wynik jako `BRAK DANYCH`,
- po błędzie backendu przejdź do `Diagnostics` i zabezpiecz logi.

### 5) `Diagnostics`
**Cel:** rozdzielenie problemu jakości danych od awarii infrastruktury.

**Karty:**
- **Errors**: aktywne błędy i ich kody.
- **Time Sync**: alarmy `TIME_DESYNC`.
- **Restarts/Health**: restarty komponentów i heartbeat.

**Reakcja operatora:**
- potwierdź źródło awarii,
- przy niestabilnej infrastrukturze nie ufaj detekcjom,
- uruchom odpowiedni scenariusz awaryjny.

### 6) `Rosbag`
**Cel:** materiał dowodowy i analiza po incydencie.

**Karty:**
- **Recording**: status i ścieżka zapisu.
- **Integrity**: kompletność i spójność plików.
- **Playback**: kontrola odtwarzania diagnostycznego.

**Reakcja operatora:**
- uruchom zapis przed testami ryzykownymi,
- po awarii zabezpiecz paczkę bag + metadane,
- nie opieraj decyzji operacyjnej wyłącznie na niezweryfikowanym playbacku.

### 7) `Extensions`
**Cel:** kontrola modułów dodatkowych.

**Karty:**
- **Loaded Extensions**: lista załadowanych rozszerzeń.
- **Extension Health**: błędy i wpływ na pipeline.
- **Compatibility**: zgodność wersji.

**Reakcja operatora:**
- jeśli rozszerzenie degraduje system, odłącz je i przejdź na bazową konfigurację,
- dokumentuj wpływ rozszerzenia na jakość i opóźnienia.

### 8) `Debug`
**Cel:** diagnostyka inżynierska (tab nieoperacyjny).

**Karty:**
- **Raw State**: surowy stan store.
- **Event Stream**: zdarzenia i korelacja.
- **Developer Flags**: przełączniki diagnostyczne.

**Reakcja operatora:**
- używaj tylko do potwierdzania hipotez diagnostycznych,
- nie podejmuj decyzji GO/NO-GO wyłącznie na podstawie danych debugowych,
- po zakończeniu analizy wróć do standardowej ścieżki (`Overview` → `Telemetry` → `Diagnostics`).

---

## Interpretacja jakości danych

### `DataQuality`
- `GOOD`: można wykorzystać próbkę.
- `UNCERTAIN`: próbka niepewna, wynik odrzucić.
- `BAD`: próbka niespełnia kryteriów krytycznych, odrzucić.
- `MISSING`: brak danych/metadanych, odrzucić.

**Reguła operacyjna:** `UNCERTAIN | BAD | MISSING` => brak publikacji wyniku.

### `reason_code` (przykłady)
- `LOW_SIGNAL`: zbyt słaby sygnał wejścia.
- `TIME_DESYNC`: niespójna oś czasu źródeł.
- `OUT_OF_RANGE`: parametry poza zakresem walidacji.
- `SENSOR_TIMEOUT`: brak próbki w oknie czasowym.
- `VALIDATION_ERROR`: naruszenie reguł walidatora.

Każde zgłoszenie incydentu musi zawierać: timestamp, `DataQuality`, `reason_code`, źródło i status globalny pipeline.

---

## Reakcja na awarie (skrócone procedury)

### A) Brak detekcji przy aktywnych wejściach
1. Sprawdź `Overview` i `Telemetry`.
2. Potwierdź dominujący `reason_code`.
3. Jeśli odrzucenia są celowe (jakość) — utrzymaj blokadę publikacji.
4. Eskaluj dopiero przy symptomach infrastrukturalnych.

### B) `TIME_DESYNC`
1. Wstrzymaj decyzje oparte na automatyce.
2. Sprawdź źródło czasu i opóźnienia transportowe.
3. Wznów operację dopiero po stabilizacji trendu odrzuceń.

### C) `FAIL_SAFE`
1. Przejdź na procedurę ręczną.
2. Zabezpiecz logi, metryki i bag z okna awarii.
3. Wznowienie automatyki tylko po formalnym potwierdzeniu gotowości.

### D) `SENSOR_TIMEOUT`
1. Rozróżnij awarię sensora od problemu transportu.
2. Utrzymaj blokadę publikacji dla brakujących danych.
3. Kontynuuj wyłącznie na źródłach ze stabilnym `DataQuality=GOOD`.

---

## Checklista końcowa operatora (dla wszystkich tabów)
- `Overview`: brak aktywnego stanu krytycznego.
- `Telemetry`: strumienie świeże i kompletne.
- `Video & Depth`: brak trwałej degradacji obrazu/głębi.
- `Controls`: backend akcji odpowiada poprawnie.
- `Diagnostics`: brak nierozwiązanych błędów krytycznych.
- `Rosbag`: gotowy zapis materiału diagnostycznego.
- `Extensions`: brak degradujących dodatków.
- `Debug`: brak aktywnych flag zaburzających pracę operacyjną.

Jeśli dowolny punkt jest niespełniony, domyślna decyzja to **NO-GO**.
