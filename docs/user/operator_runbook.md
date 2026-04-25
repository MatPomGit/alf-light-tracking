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

<!--
[AI-CHANGE | 2026-04-24 12:17 UTC | v0.204]
CO ZMIENIONO: Dodano gotowe do użycia scenariusze incydentowe z jasną sekwencją: detekcja, reakcja operatora, kryteria eskalacji oraz procedury rollback.
DLACZEGO: Stanowisko operatorskie wymaga szybkiej, jednoznacznej instrukcji działania pod presją czasu, bez potrzeby interpretacji kilku dokumentów naraz.
JAK TO DZIAŁA: Operator wybiera scenariusz z tabeli, wykonuje kroki w podanej kolejności i kończy incydent dopiero po spełnieniu kryteriów wyjścia; rollback przywraca stan bezpieczny zamiast wymuszać niepewne detekcje.
TODO: Dodać identyfikatory zgłoszeń (np. INC-001..INC-00N) zsynchronizowane z systemem ticketowym i automatyczny generator checklisty dla zmiany dyżuru.
-->

## Scenariusze incydentowe — reakcja, eskalacja, rollback (wersja stanowiskowa)

> **Instrukcja użycia:** znajdź pierwszy pasujący symptom, wykonaj kroki „Reakcja operatora”, a następnie „Eskalacja” i „Rollback”.
> Jeśli występuje kilka symptomów jednocześnie, realizuj scenariusz o **wyższym ryzyku** (`FAIL_SAFE` > `TIME_DESYNC` > `SENSOR_TIMEOUT` > degradacja jakości).

### Macierz decyzyjna (skrót 60-sekundowy)

| Scenariusz | Symptomy wejściowe | Reakcja operatora (0–2 min) | Eskalacja | Rollback do stanu bezpiecznego | Kryterium zamknięcia |
|---|---|---|---|---|---|
| **INC-01: Brak detekcji mimo aktywnych wejść** | Brak nowych wyników, wejścia `RGB/Depth` aktywne, rosnący licznik odrzuceń | 1) Potwierdź `DataQuality` i `reason_code`.<br>2) Jeśli `UNCERTAIN/BAD/MISSING` — utrzymaj blokadę publikacji.<br>3) Zapisz snapshot z `Overview`, `Telemetry`, `Diagnostics`. | Eskaluj do L2 po **10 min** ciągłej niedostępności wyniku lub gdy `reason_code` zmienia się niestabilnie między próbkami. | 1) Przełącz pipeline na tryb bazowy (bez rozszerzeń).<br>2) Restart tylko warstwy percepcji, bez resetu całego stosu.<br>3) Zweryfikuj pierwsze 20 próbek; publikuj tylko `GOOD`. | 20 kolejnych próbek z `DataQuality=GOOD` i stabilna świeżość tematów. |
| **INC-02: `TIME_DESYNC`** | Alarm desynchronizacji czasu, niespójne znaczniki między sensorami | 1) Natychmiast oznacz system `NO-GO` dla automatyki.<br>2) Wstrzymaj akcje zależne od percepcji.<br>3) Uruchom zapis bag z oknem incydentu. | Eskaluj natychmiast do L2 (infrastruktura czasu); do L3 po **15 min**, jeśli offset nie wraca do progu operacyjnego. | 1) Przywróć źródło czasu referencyjnego (NTP/PTP wg konfiguracji).<br>2) Wznów strumienie i odczekaj okno stabilizacji.<br>3) Zweryfikuj trend odrzuceń przed zdjęciem `NO-GO`. | Brak alarmów `TIME_DESYNC` przez minimum 5 min + brak skoków opóźnień. |
| **INC-03: `FAIL_SAFE`** | Globalny status `FAIL_SAFE`, odcięcie automatyki, krytyczne błędy | 1) Przejdź na sterowanie ręczne/procedurę awaryjną.<br>2) Zablokuj publikację wszystkich wyników detekcji.<br>3) Zabezpiecz artefakty: logi, metryki, bag. | Eskaluj **natychmiast** do Incident Commander + L2/L3; wymagaj potwierdzenia przyjęcia zgłoszenia. | 1) Przywróć ostatnią znaną stabilną konfigurację (`golden config`).<br>2) Wykonaj kontrolowany restart komponentów wg kolejności zależności.<br>3) Przeprowadź testy sanity przed odblokowaniem automatyki. | Formalny `GO` od dyżuru technicznego + pozytywny sanity check całego pipeline. |
| **INC-04: `SENSOR_TIMEOUT`** | Brak próbek z jednego sensora, heartbeat niestabilny | 1) Potwierdź, czy problem dotyczy sensora czy transportu.<br>2) Odrzuć próbki zależne od brakującego źródła.<br>3) Oznacz obszar obserwacji jako niepewny. | Eskaluj do L2 po **5 min** timeoutu lub natychmiast, jeśli timeout dotyczy sensora krytycznego dla bezpieczeństwa. | 1) Przełącz na redundancję (jeśli dostępna).<br>2) Restart pojedynczego drivera sensora.<br>3) Powrót do pełnej fuzji dopiero po stabilnym heartbeat. | Stabilny heartbeat i kompletność ramek przez 3 kolejne okna kontrolne. |
| **INC-05: Degradacja jakości obrazu/głębi** | Artefakty, prześwietlenie, „dziury” w depth, spadek ostrości | 1) Oznacz próbki jako `UNCERTAIN`.<br>2) Wyklucz automatyczne decyzje na tych próbkach.<br>3) Sprawdź czy degradacja lokalna czy globalna. | Eskaluj do L2, gdy degradacja trwa > 10 min lub wpływa na >30% próbek w oknie kontrolnym. | 1) Powrót do zapisanych parametrów kamery/sensora.<br>2) Wyłączenie niestabilnych rozszerzeń obrazu.<br>3) Weryfikacja jakości na referencyjnej planszy/test pattern. | Udział odrzuceń spada poniżej progu operacyjnego i utrzymuje trend malejący. |

### Drabina eskalacji (role i SLA)

1. **L1 Operator (stanowisko):** triage, zabezpieczenie dowodów, uruchomienie rollbacku lokalnego.
2. **L2 Inżynier dyżurny:** diagnostyka przyczynowa, decyzja o zmianie konfiguracji runtime.
3. **L3 Owner komponentu/architekt:** zmiany strukturalne, hotfix, decyzja o czasowym ograniczeniu funkcji.
4. **Incident Commander:** koordynacja komunikacji i decyzja o wznowieniu automatyki po `FAIL_SAFE`.

**SLA potwierdzenia eskalacji:**
- Krytyczne (`FAIL_SAFE`, bezpieczeństwo): potwierdzenie w ciągu **5 min**.
- Wysokie (`TIME_DESYNC`, krytyczny timeout): **10 min**.
- Średnie (degradacja jakości bez ryzyka bezpieczeństwa): **30 min**.

### Standard rollback — checklista wykonawcza

1. Ustaw status operacyjny na `NO-GO`.
2. Zatrzymaj publikację detekcji (priorytet: brak błędnych danych).
3. Zabezpiecz artefakty incydentu: logi + metryki + rosbag + znacznik czasu UTC.
4. Przywróć ostatnią stabilną konfigurację (`golden config` / profil bazowy).
5. Restartuj tylko wymagane komponenty, od najniższej warstwy zależności.
6. Uruchom test sanity (wejścia, synchronizacja czasu, status backendu akcji).
7. Odblokuj publikację dopiero przy spełnionym kryterium zamknięcia scenariusza.
8. Zaktualizuj wpis incydentu i przekaż status na zmianę/dyżur.

### Minimalny format wpisu incydentu (do dziennika operatora)

- `timestamp_utc`: `YYYY-MM-DD HH:MM:SS`
- `incident_id`: identyfikator lokalny zmiany
- `scenario`: `INC-01..INC-05`
- `data_quality`: `GOOD/UNCERTAIN/BAD/MISSING`
- `reason_code`: np. `TIME_DESYNC`, `SENSOR_TIMEOUT`
- `actions_taken`: lista wykonanych kroków
- `escalation_level`: `L1/L2/L3/IC`
- `rollback_status`: `NOT_REQUIRED/IN_PROGRESS/DONE`
- `closure_decision`: `GO/NO-GO`

> **Reguła końcowa:** jeżeli po rollbacku pozostaje niepewność diagnostyczna, utrzymaj `NO-GO` i brak publikacji detekcji do czasu decyzji L2/L3.

<!--
[AI-CHANGE | 2026-04-25 11:18 UTC | v0.202]
CO ZMIENIONO: Dodano sekcję „Runbook incydentów (tryb operacyjny L1→L3)” z twardymi krokami czasowymi, kryteriami eskalacji, warunkami wznowienia i formatem handover między zmianami.
DLACZEGO: Potrzebny był jednoznaczny, powtarzalny przebieg obsługi incydentu, który skraca czas reakcji i eliminuje decyzje ad-hoc pod presją.
JAK TO DZIAŁA: Operator wykonuje kolejno fazy T0/T+5/T+15/T+30, a automatyka wraca tylko po spełnieniu kryteriów „exit criteria”; przy niepewności pozostaje NO-GO i brak publikacji detekcji.
TODO: Dodać gotowe szablony zgłoszeń do Jira/ServiceNow z automatycznym wypełnieniem pól reason_code i metryk SLA.
-->

## Runbook incydentów (tryb operacyjny L1→L3)

### Cel i zakres
Ta sekcja definiuje **twardy** przebieg obsługi incydentów dla stanowiska operatorskiego i dyżuru technicznego.
Zakres: awarie percepcji, desynchronizacja czasu, awarie backendu akcji, degradacja infrastruktury ROS2/UI.

### Zegar incydentu (obowiązkowa oś czasu)
- **T0 (0–2 min):** detekcja, klasyfikacja, ustawienie statusu `NO-GO`, uruchomienie zabezpieczenia artefaktów.
- **T+5 min:** potwierdzenie eskalacji wg klasy incydentu i przypisanie właściciela.
- **T+15 min:** decyzja o rollbacku technicznym lub ograniczeniu funkcjonalnym.
- **T+30 min:** checkpoint managerski: kontynuacja prac naprawczych albo formalne zatrzymanie automatyki do końca zmiany.

> Reguła bezwzględna: brak kompletnej diagnozy = brak wznowienia publikacji detekcji.

### Klasy incydentów i SLO reakcji

| Klasa | Definicja | Przykłady | Maks. czas do reakcji L1 | Maks. czas do potwierdzenia L2/L3 |
|---|---|---|---|---|
| `SEV-1` | Ryzyko bezpieczeństwa lub aktywny `FAIL_SAFE` | Utrata sterowania automatycznego, krytyczne błędy backendu | 2 min | 5 min |
| `SEV-2` | Utrata kluczowej funkcji bez bezpośredniego ryzyka bezpieczeństwa | `TIME_DESYNC`, długotrwały `SENSOR_TIMEOUT` | 5 min | 10 min |
| `SEV-3` | Degradacja jakości z obejściem operacyjnym | wzrost odrzuceń, niestabilna jakość obrazu | 10 min | 30 min |

### Procedura wykonawcza (checklista twarda)
1. **Zatrzymanie ryzyka:** ustaw `NO-GO`, zablokuj publikację detekcji, potwierdź status w `Overview`.
2. **Zabezpieczenie danych:** uruchom/utrzymaj `rosbag`, zachowaj logi i metryki z okna `T-5..T+10` min.
3. **Korelacja przyczyny:** sprawdź `reason_code`, `DataQuality`, alarmy `Diagnostics`, świeżość `Telemetry`.
4. **Decyzja o ścieżce:**
   - ścieżka A: rollback konfiguracji (`golden config`),
   - ścieżka B: izolacja komponentu (driver/extension),
   - ścieżka C: pełne utrzymanie `NO-GO` do zakończenia zmiany.
5. **Walidacja po akcji:** min. 20 kolejnych próbek `DataQuality=GOOD` i brak alarmów krytycznych.
6. **Zamknięcie incydentu:** wpis do dziennika + handover (jeżeli zmiana się kończy).

### Kryteria wznowienia automatyki (exit criteria)
Automatyka może zostać wznowiona wyłącznie, gdy **wszystkie** warunki są spełnione:
1. Brak aktywnego `FAIL_SAFE` i brak alarmu `TIME_DESYNC`.
2. Stabilna świeżość krytycznych topiców (bez timeoutów w oknie kontrolnym).
3. Trend odrzuceń malejący i poniżej progu operacyjnego.
4. Potwierdzenie L2 dla `SEV-1/SEV-2` (pisemne w dzienniku incydentu).

Jeżeli choć jeden warunek jest niespełniony, decyzja pozostaje **NO-GO**.

### Handover między zmianami (przekazanie dyżuru)
Minimalny pakiet przekazania:
- numer incydentu i klasa (`SEV-1/2/3`),
- ostatni stabilny timestamp UTC,
- aktualny status (`NO-GO` / ograniczony GO),
- wykonane kroki rollbacku i ich wynik,
- lista ryzyk otwartych + właściciele L2/L3.

Brak pełnego handoveru oznacza automatyczne utrzymanie `NO-GO` na kolejnej zmianie.
