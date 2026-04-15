# TODO — analiza braków i porządkowanie repozytorium

Poniżej znajduje się uporządkowana lista braków wykrytych podczas przeglądu repozytorium `alf-light-tracking`.

## Co zostało sprawdzone

- struktura repozytorium i układ pakietu ROS 2,
- pliki build/package (`CMakeLists.txt`, `package.xml`, `setup.py`),
- skrypty uruchomieniowe w `scripts/`,
- wybrane node'y i definicje wiadomości ROS,
- testy w katalogu `test/`,
- spójność README z rzeczywistą zawartością.

## Wynik szybkiej weryfikacji

- `pytest`: **7/7 testów przechodzi**,
- kompilacja składniowa plików `.py`: **OK**,
- **nie zweryfikowano pełnego `colcon build` / runtime ROS 2**, bo środowisko ROS 2 nie było tutaj uruchomione.

---

## P0 — krytyczne braki do poprawy w pierwszej kolejności

### 1. Niespójność `MissionState.msg` względem `mission_node.py`
**Problem:** `g1_light_tracking/nodes/mission_node.py` zapisuje pola, których nie ma w `msg/MissionState.msg`:
- `active_parcel_box_track_id`
- `active_shipment_id`
- `has_active_parcel`
- `has_drop_target`
- `is_terminal`

**Skutek:** po wygenerowaniu interfejsów ROS node może się wyłożyć przy publikacji stanu misji albo dane będą niezgodne z kontraktem wiadomości.

**Do zrobienia:**
- albo rozszerzyć `msg/MissionState.msg` o te pola,
- albo uprościć `build_state_msg()` tak, aby używał wyłącznie istniejących pól.

### 2. `debug_node.py` zakłada pola, których nie ma w `MissionState.msg`
**Problem:** `debug_node.py` loguje m.in. `msg.active_parcel_box_track_id` i `msg.active_shipment_id`, ale tych pól nie ma w aktualnym pliku `msg/MissionState.msg`.

**Skutek:** ryzyko błędów runtime po stronie debugowania/telemetrii.

**Do zrobienia:**
- zsynchronizować `debug_node.py` z finalną wersją `MissionState.msg`,
- dodać test zgodności wiadomości z konsumentami.

### 3. README opisuje architekturę, której już nie ma 1:1 w repo
**Problem:** README nadal szeroko opisuje `association_node`, mimo że obecnie logika wiązania siedzi w `parcel_track_node.py`, a osobnego skryptu `scripts/association_node` brak.

**Skutek:** dokumentacja wprowadza w błąd przy uruchamianiu i rozwoju systemu.

**Do zrobienia:**
- usunąć lub wyraźnie oznaczyć stare fragmenty,
- opisać aktualny przepływ: `tracking -> parcel_track -> mission`,
- poprawić wszystkie przykłady `ros2 run`, które nadal wskazują na `association_node`.

---

## P1 — ważne braki build/package/release

### 4. `setup.py` nie odpowiada temu, co obiecuje README
**Problem:** README opisuje extras (`standalone`, `full`) i bazowe zależności (`numpy`, `opencv-python`), ale `setup.py` ma tylko:
- `install_requires=['setuptools']`

Nie ma żadnych `extras_require`.

**Skutek:** dokumentacja instalacji jest myląca; instalacja przez `pip install -e .[standalone]` w obecnym stanie nie odpowiada opisowi.

**Do zrobienia:**
- zdecydować, czy `setup.py` ma wspierać extras,
- jeśli tak: dodać `extras_require`,
- jeśli nie: poprawić README i zostawić zależności wyłącznie w plikach `requirements-*.txt`.

### 5. Mechanizm `version_bump.py` nie aktualizuje `setup.py`
**Problem:** `scripts/version_bump.py` podmienia literalne `version='x.y.z'`, ale `setup.py` czyta wersję dynamicznie z pliku `VERSION`.

**Skutek:** hook próbuje aktualizować `setup.py`, ale regex niczego tam realnie nie zmienia.

**Do zrobienia:**
- uprościć skrypt tak, aby aktualizował tylko `VERSION` i `package.xml`,
- albo zmienić strategię wersjonowania na jedną spójną metodę.

### 6. Uszkodzony / mylący `scripts/install_git_hooks.sh` w pakiecie
**Problem:** plik `ros2_ws/src/g1_light_tracking/scripts/install_git_hooks.sh` ma błędny początek:
- `#!/usr/bin/env python3`
- samotny `\`
- dopiero potem `#!/usr/bin/env bash`

**Skutek:** plik wygląda na przypadkowo uszkodzony i może być wykonywany nieprzewidywalnie.

**Do zrobienia:**
- usunąć błędny nagłówek,
- zostawić jedną poprawną wersję bash,
- rozważyć usunięcie tego pliku całkowicie, jeśli wystarczają wersje z root i `ros2_ws/`.

### 7. Zduplikowane skrypty instalacji hooków
**Problem:** podobne skrypty istnieją w trzech miejscach:
- `install_git_hooks.sh`
- `ros2_ws/install_git_hooks.sh`
- `ros2_ws/src/g1_light_tracking/scripts/install_git_hooks.sh`

**Skutek:** trudniej utrzymać repo; łatwo o drift między wersjami.

**Do zrobienia:**
- zostawić jeden kanoniczny skrypt,
- w pozostałych miejscach ewentualnie dać cienkie wrappery albo usunąć duplikaty.

---

## P2 — porządek repozytorium i higiena projektu

### 8. Artefakty developerskie są w repo
**Problem:** w drzewie pakietu znajdują się:
- `__pycache__/`
- `.pytest_cache/`

**Skutek:** repo jest zaśmiecone i mniej przewidywalne.

**Do zrobienia:**
- usunąć artefakty z repo,
- dodać porządny `.gitignore` w root projektu.

### 9. Brak sensownego `.gitignore` w repozytorium
**Problem:** praktycznie brak realnego `.gitignore` dla Pythona/ROS 2.

**Do zrobienia:** dodać wpisy co najmniej dla:
- `__pycache__/`
- `.pytest_cache/`
- `*.pyc`
- `build/`
- `install/`
- `log/`
- `.venv/`
- `.idea/`, `.vscode/`
- artefaktów modeli / danych lokalnych

### 10. Repo zawiera raporty techniczne jako stałe pliki robocze
**Problem:** w głównym katalogu pakietu leżą raporty typu:
- `BUILD_FIX_REPORT.txt`
- `CONSISTENCY_AUDIT_REPORT.txt`
- `EXECUTABLE_AUDIT_REPORT.txt`
- `MSG_ALIGNMENT_REPORT.txt`

**Skutek:** nie jest jasne, czy są częścią produktu, czy tylko jednorazowym outputem prac porządkowych.

**Do zrobienia:**
- przenieść je do `docs/maintenance/` albo `docs/audits/`,
- albo usunąć z repo, jeśli były tylko tymczasowe.

### 11. Pusty katalog `calibration/`
**Problem:** katalog istnieje, ale jest pusty.

**Skutek:** nie wiadomo, czy to placeholder, czy brakujący zasób.

**Do zrobienia:**
- jeśli potrzebny: dodać README i przykładowe pliki,
- jeśli niepotrzebny: usunąć.

### 12. `REPO_LAYOUT.txt` i README dublują część informacji
**Problem:** struktura repo jest opisana w więcej niż jednym miejscu.

**Skutek:** ryzyko rozjazdu dokumentacji.

**Do zrobienia:**
- wybrać jedno źródło prawdy dla układu repo,
- w drugim pliku zostawić tylko krótki odnośnik.

---

## P3 — testy, walidacja i utrzymanie jakości

### 13. Testy nie łapią niespójności kontraktów ROS
**Problem:** obecne testy przechodzą, ale nie wykrywają problemu z polami `MissionState`.

**Do zrobienia:**
- dodać test zgodności node -> msg,
- najlepiej dodać testy integracyjne lub kontraktowe dla custom messages.

### 14. Brak walidacji dokumentacji vs kod
**Problem:** README zawiera nieaktualne komendy i opisy architektury.

**Do zrobienia:**
- dodać checklistę release/doc sync,
- przy większych zmianach architektury aktualizować README w tym samym PR.

### 15. Brak automatycznej kontroli jakości w CI
**Problem:** w repo nie widać konfiguracji CI dla:
- `pytest`
- lintingu
- sprawdzenia importów / składni
- opcjonalnie podstawowego build sanity check

**Do zrobienia:**
- dodać CI (np. GitHub Actions),
- minimalny pipeline: `pytest`, `python -m py_compile`, podstawowy lint,
- jeśli możliwe: osobny job dla środowiska ROS 2.

### 16. Brak jednoznacznego rozdziału trybu ROS i standalone
**Problem:** repo wspiera zarówno ROS 2, jak i standalone, ale granica odpowiedzialności nie jest do końca jasno opisana.

**Do zrobienia:**
- doprecyzować w README:
  - co jest wspierane w ROS,
  - co działa standalone,
  - które profile są eksperymentalne,
  - które zależności są wymagane w którym trybie.

---

## Proponowana kolejność prac

1. Naprawić kontrakt `MissionState` + zsynchronizować `mission_node.py` i `debug_node.py`.
2. Posprzątać README i usunąć wzmianki o nieistniejącym `association_node` jako aktywnym komponencie.
3. Ujednolicić instalację zależności (`setup.py` vs `requirements*.txt`).
4. Naprawić / zredukować skrypty `install_git_hooks.sh`.
5. Dodać `.gitignore` i usunąć artefakty developerskie z repo.
6. Dodać testy kontraktowe i prosty CI.

---

## Ocena ogólna

Repozytorium jest **sensownie ułożone katalogowo** i ma już bazę do dalszego rozwoju, ale nadal ma kilka braków typowych dla projektu po większym refaktorze:
- dokumentacja nie nadąża za kodem,
- interfejsy ROS nie są w pełni zsynchronizowane z implementacją,
- są ślady prac technicznych i artefakty developerskie,
- brakuje automatycznych bezpieczników jakości.

Największe ryzyko nie leży teraz w składni czy testach jednostkowych, tylko w **niespójności kontraktów runtime i dokumentacji operacyjnej**.
