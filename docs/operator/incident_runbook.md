# Runbook incydentów (operacyjny)

## Akceptacja operacyjna
- Status: `ZATWIERDZONE`
- Data akceptacji (UTC): `2026-04-27`
- Właściciel akceptacji: `@ops_oncall`
- Zakres: Stage 0, obsługa incydentów percepcji i backendu ROS.

## Cel dokumentu
Ten runbook definiuje jednolity sposób obsługi awarii dla stanowisk operatorskich Stage 0.
Priorytet: **najpierw bezpieczeństwo i jakość danych, potem dostępność funkcji**.

## Zasada nadrzędna (fail-safe)
Jeżeli istnieje ryzyko błędnej detekcji, system ma zwrócić **brak wyniku** (`None`/odrzucenie próbki), a nie wynik niepewny.

## Szybki triage (pierwsze 5 minut)
1. Potwierdź status globalny pipeline (`NOMINAL`/`DEGRADED`/`FAIL_SAFE`).
2. Potwierdź jakość danych (`DataQuality`) i dominujący `reason_code`.
3. Zabezpiecz dowody: logi, metryki i rosbag z okna incydentu.
4. Ustal wpływ: lokalny komponent vs. awaria całego systemu.
5. Podejmij decyzję `GO/NO-GO` dla automatyki (domyślnie `NO-GO` przy niepewności).

## Macierz incydentów (akcja operatorska)

| ID | Trigger | Natychmiastowa reakcja (L1) | Eskalacja | Rollback | Kryterium zamknięcia |
|---|---|---|---|---|---|
| INC-01 | Brak detekcji przy aktywnych wejściach | Potwierdź `DataQuality`; utrzymaj blokadę publikacji dla `UNCERTAIN/BAD/MISSING`. | L2 po 10 min ciągłego braku wyniku. | Restart wyłącznie warstwy percepcji; bez resetu całego stosu. | 20 kolejnych próbek `GOOD` i stabilna świeżość topiców. |
| INC-02 | `TIME_DESYNC` | Natychmiast `NO-GO`; wstrzymaj akcje zależne od percepcji. | Natychmiast L2, L3 po 15 min utrzymującego się offsetu. | Przywróć źródło czasu referencyjnego, odczekaj okno stabilizacji. | Brak alarmu `TIME_DESYNC` przez 5 min. |
| INC-03 | `FAIL_SAFE` | Przejdź na procedurę ręczną i zablokuj publikację detekcji. | Natychmiast Incident Commander + L2/L3. | Powrót do ostatniej stabilnej konfiguracji + kontrolowany restart. | Formalny `GO` dyżuru technicznego i pozytywny sanity check. |
| INC-04 | `SENSOR_TIMEOUT` | Rozróżnij awarię sensora od transportu; odrzuć zależne próbki. | L2 po 5 min lub natychmiast dla sensora krytycznego. | Restart pojedynczego drivera, ewentualnie przełączenie na redundancję. | Stabilny heartbeat i komplet ramek w 3 oknach kontrolnych. |
| INC-05 | Degradacja obrazu/głębi | Oznacz próbki jako `UNCERTAIN`; wyłącz decyzje automatyczne. | L2 gdy trwa >10 min lub >30% próbek odrzuconych. | Powrót do parametrów referencyjnych kamery/depth. | Trend odrzuceń wraca poniżej progu operacyjnego. |

## Drabina eskalacji i SLA
- **L1 Operator:** triage, zabezpieczenie dowodów, rollback lokalny.
- **L2 Inżynier dyżurny:** diagnostyka przyczynowa, korekty konfiguracji runtime.
- **L3 Owner komponentu:** hotfix, decyzja o ograniczeniu funkcjonalności.
- **Incident Commander:** decyzja o wznowieniu automatyki po incydencie krytycznym.

## Artefakty wymagane przy każdym incydencie
- timestamp start/stop incydentu (UTC),
- status pipeline i `DataQuality`,
- `reason_code` dominujący i pomocniczy,
- identyfikator hosta oraz profil środowiska (H1/H2/H3...),
- link do paczki dowodowej: `logs + metrics + rosbag`.

## Kryteria wznowienia wdrożeń po incydencie
Wdrożenie może wrócić do harmonogramu tylko gdy:
1. Incydent ma status `RESOLVED` i zamknięty postmortem techniczny.
2. Środowisko przechodzi hard gates (`ALLOW/BLOCK`) bez odstępstw.
3. Smoke launch i sanity check nie zgłaszają błędów krytycznych.
4. Brak otwartych regresji bezpieczeństwa danych.

## Minimalna checklista zmiany dyżuru
- aktywne incydenty i ich ownerzy,
- aktualne `NO-GO`/`GO` dla automatyki,
- ostatnia stabilna konfiguracja rollback (`golden config`),
- status przestrzeni dyskowej pod rosbag,
- ryzyka znane na najbliższe 24h.
