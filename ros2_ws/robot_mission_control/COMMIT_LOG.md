<!-- [AI-CHANGE | 2026-04-21 15:52 UTC | v0.176] -->
<!-- CO ZMIENIONO: Dodano dedykowany dziennik zmian commitowych dla modułu robot_mission_control. -->
<!-- DLACZEGO: Wymaganie projektu mówi o opisie zmian przy każdym commicie w osobnym pliku modułu. -->
<!-- JAK TO DZIAŁA: Każdy kolejny commit dopisuje nową sekcję z datą, SHA i zakresem zmian. -->
<!-- TODO: Zautomatyzować aktualizację tego pliku hookiem commit-msg lub skryptem release. -->

# Commit log — robot_mission_control


<!--
[AI-CHANGE | 2026-04-27 12:03 UTC | v0.203]
CO ZMIENIONO: Dodano sekcję zakresu COMMIT_LOG.md, która formalizuje rozdział odpowiedzialności między dokumentami.
DLACZEGO: Dzięki temu historia commitów/PR nie dubluje backlogu, planu wdrożenia ani changelogu releasowego.
JAK TO DZIAŁA: Wpisy w tym pliku opisują wyłącznie techniczne zmiany commitowe i referują do innych dokumentów zamiast kopiować ich treść.
TODO: Wprowadzić szablon PR wymagający jawnego wskazania, czy zmiana powinna trafić do CHANGELOG.md.
-->
## Zakres dokumentu
- Ten plik zawiera wyłącznie historię commitów i PR (techniczny dziennik zmian).
- Fakty releasowe publikujemy wyłącznie w `CHANGELOG.md`.
- Fakty backlogowe (`Status`, `Owner`, `Data przeglądu`, `DoD`) publikujemy wyłącznie w `TASKS.md`.
- Procedury rollout/rollback publikujemy wyłącznie w `DEPLOYMENT_PLAN.md`.

<!--
[AI-CHANGE | 2026-04-27 12:03 UTC | v0.203]
CO ZMIENIONO: Dodano wpis commitowy dokumentujący rozdzielenie odpowiedzialności między TASKS.md, DEPLOYMENT_PLAN.md, CHANGELOG.md i COMMIT_LOG.md.
DLACZEGO: Potrzebujemy jawnego śladu technicznego dla reguły "jeden fakt = jedno źródło prawdy".
JAK TO DZIAŁA: Sekcja poniżej rejestruje commit porządkujący granice dokumentów i wskazuje zakres modyfikacji.
TODO: Dodać automatyczne generowanie wpisu COMMIT_LOG.md z diffu plików dokumentacyjnych.
-->

<!--
[AI-CHANGE | 2026-04-27 13:53 UTC | v0.201]
CO ZMIENIONO: Dodano wpis commitowy dokumentujący uproszczenie README do jednego bloku meta i przeniesienie historii zmian do COMMIT_LOG.md.
DLACZEGO: Utrzymanie wielu bloków meta w README obniża czytelność; historia techniczna powinna być przechowywana centralnie w logu commitów.
JAK TO DZIAŁA: Nowa sekcja rejestruje decyzję dokumentacyjną i wskazuje granicę odpowiedzialności README vs COMMIT_LOG.md.
TODO: Rozszerzyć format wpisu o pole "Zakres plików", aby szybciej odtwarzać wpływ zmian dokumentacyjnych.
-->
## 2026-04-27 | v0.201 | (pending commit)

- Uproszczono `README.md`: pozostawiono jeden blok meta `[AI-CHANGE]` na początku dokumentu.
- Usunięto historyczne bloki meta z treści README i przeniesiono ślad decyzji do `COMMIT_LOG.md`.
- Doprecyzowano, że fakty releasowe pozostają w `CHANGELOG.md`, a historia techniczna dokumentu w `COMMIT_LOG.md`.

## 2026-04-27 | v0.203 | (pending commit)

- Dodano sekcje "Granice dokumentu" w `TASKS.md`, `DEPLOYMENT_PLAN.md`, `CHANGELOG.md` i `COMMIT_LOG.md`.
- Ustalono formalny podział odpowiedzialności: backlog (`TASKS.md`), rollout/rollback (`DEPLOYMENT_PLAN.md`), release (`CHANGELOG.md`), historia commitów/PR (`COMMIT_LOG.md`).
- Uproszczono wpis release `0.1.0` w `CHANGELOG.md`, aby nie dublować szczegółów technicznych z `COMMIT_LOG.md`.

<!--
[AI-CHANGE | 2026-04-27 13:05 UTC | v0.203]
CO ZMIENIONO: Dodano wpis commitowy dokumentujący porządkowanie nagłówków meta-zmian w TASKS.md oraz archiwum przeniesionych wpisów.
DLACZEGO: Historia zmian ma pozostać dostępna bez dublowania opisów na początku aktywnego backlogu.
JAK TO DZIAŁA: Nowa sekcja opisuje zakres porządkującego commitu, a niżej znajduje się archiwum trzech starszych wpisów meta-zmian.
TODO: Ustandaryzować format sekcji archiwum meta-zmian i walidować go automatycznie w CI.
-->

## 2026-04-27 | v0.203 | (bieżący commit)

- Uporządkowano sekcję nagłówkową `TASKS.md`: pozostawiono jeden aktualny blok meta-zmiany.
- Historyczne wpisy meta-zmian usunięte z początku `TASKS.md` przeniesiono do `COMMIT_LOG.md`, aby nie dublować opisów.
- Zachowano zasadę jednego źródła prawdy: backlog operacyjny pozostaje w `TASKS.md`, a historia zmian w logu commitów.

## Archiwum meta-zmian przeniesionych z TASKS.md

<!--
[AI-CHANGE | 2026-04-27 13:11 UTC | v0.202]
CO ZMIENIONO: Rozszerzono archiwum o dwa dosłownie przeniesione bloki meta-zmian z TASKS.md (drugi blok nagłówkowy i blok historyczny ze środka dokumentu).
DLACZEGO: Utrzymujemy tylko jeden aktualny blok meta w TASKS.md, a starsze opisy zmian przechowujemy wyłącznie w COMMIT_LOG.md.
JAK TO DZIAŁA: Poniższe sekcje kopiują techniczną treść przeniesionych bloków bez mieszania jej z aktywnym backlogiem.
TODO: Dodać walidator CI, który wykrywa bloki [AI-CHANGE] poza pierwszym blokiem nagłówkowym TASKS.md.
-->
### 2026-04-27 12:03 UTC | v0.203
- CO ZMIENIONO: Dodano sekcję granic odpowiedzialności TASKS.md względem DEPLOYMENT_PLAN.md, CHANGELOG.md i COMMIT_LOG.md.
- DLACZEGO: Użytkownik wymaga, aby ten sam fakt nie był równolegle utrzymywany w wielu plikach.
- JAK TO DZIAŁA: TASKS.md pozostaje jedynym miejscem na statusy, ownerów, daty przeglądu i DoD zadań; pozostałe dokumenty są tylko referencjami.
- TODO: Dodać automatyczny test markdown sprawdzający, czy sekcja "Granice dokumentu" istnieje i nie została osłabiona.

### 2026-04-24 23:18 UTC | v0.202
- CO ZMIENIONO: Dodano dowód realizacji zadania RMC-ACT-001 (finalny kontrakt Action + walidacja runtime).
- DLACZEGO: Po dodaniu pakietu `robot_mission_control_interfaces` i testów zgodności kontraktu zadanie spełnia DoD.
- JAK TO DZIAŁA: W backlogu oznaczamy status `DONE` oraz wskazujemy artefakty: `MissionStep.action`, walidacja w `app.py`, test zgodności `tests/test_action_contract_runtime_alignment.py`.
- TODO: Uzupełnić o link do PR merge i datę zamknięcia po scaleniu do gałęzi głównej.

### 2026-04-27 12:20 UTC | v0.203
- CO ZMIENIONO: Dodano jawne wskazanie, że TASKS.md jest jedynym aktywnym backlogiem wykonawczym.
- DLACZEGO: Ujednolicenie źródła prawdy dla statusów, ownerów, review i DoD.
- JAK TO DZIAŁA: Sekcja polityki backlogu wymusza prowadzenie aktywnych zadań tylko tutaj.
- TODO: Dodać walidator CI sprawdzający obecność wymaganych pól metadanych dla każdego zadania.

### 2026-04-27 09:05 UTC | v0.203
- CO ZMIENIONO: Zaktualizowano backlog dla OPS-001 i OPS-002: statusy ustawiono na `DONE`, dodano linki do artefaktów wykonawczych i jawne pola akceptacji operacyjnej.
- DLACZEGO: Zadania były oznaczone jako `PLANNED`, mimo że runbook i macierz środowisk istnieją; backlog musiał odzwierciedlić stan faktyczny i DoD operacyjne.
- JAK TO DZIAŁA: Sekcja weryfikacji statusów wskazuje dowody dokumentacyjne, a każde zadanie OPS ma komplet: status, data przeglądu, link ticketowy, link do artefaktu i stempel akceptacji.
- TODO: Dodać automatyczny check w CI, który blokuje `PLANNED` dla zadań mających istniejące artefakty i podpis akceptacji.

### 2026-04-24 22:07 UTC | v0.202
- CO ZMIENIONO: Zweryfikowano statusy zadań względem istniejącej implementacji i testów, oznaczono zadania realnie ukończone jako `DONE`, a częściowo wykonane jako `IN_PROGRESS`; zaktualizowano też kolejność realizacji.
- DLACZEGO: Celem jest wiarygodny plan wykonawczy bez fałszywych statusów `READY` dla prac już wdrożonych.
- JAK TO DZIAŁA: Status każdego zadania wynika z dowodów w repozytorium (testy/implementacja); `DONE` stosujemy wyłącznie tam, gdzie DoD ma pokrycie w kodzie, a luki oznaczamy jako `IN_PROGRESS` lub `PLANNED`.
- TODO: Dodać automatyczny skrypt CI, który mapuje zadania z `TASKS.md` na dowody (`tests/`, `setup.py`, `docs/`) i flaguje rozjazdy statusów.

## 2026-04-21 | v0.177 | (bieżący commit)

- Naprawiono konflikt ścieżki runtime: `app/bootstrap.py` został rozszerzony o `submit_quick_action`.
- Podłączono callback szybkich akcji do `MainWindow`, aby przyciski ControlsTab realnie wysyłały komendy ROS2.
- Ujednolicono payloady szybkich komend oraz fallbacki `unknown_quick_command` / `goal_already_running`.

## 2026-04-21 | v0.176 | (bieżący commit)

- Rozbudowano moduł `Controls` o szybkie akcje misji (patrol, powrót do bazy, pauza, wznowienie).
- Rozszerzono `RosBridgeService` o obsługę ROS2 Action: send/cancel/progress/result.
- Dodano delegację szybkich akcji przez `MainWindow`.
- Uzupełniono README o opis nowych funkcji operatorskich i zakres komunikacji ROS2.

## Szablon dla kolejnych commitów

```text
## YYYY-MM-DD | v0.<N> | <short_sha>
- Zmiana 1...
- Zmiana 2...
```
