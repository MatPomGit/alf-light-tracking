# AGENTS.md

## Zakres
Ten plik dotyczy pakietu:
`ros2_ws/src/g1_light_tracking/`

To jest główny pakiet runtime robota. Zawiera logikę nowoczesnego pipeline’u:
- percepcja
- lokalizacja
- tracking
- parcel binding
- misja
- sterowanie
- depth mapping
- visual SLAM
- narzędzia diagnostyczne i kompatybilnościowe

---

## Zasady lokalne dla tego pakietu

### 1. Modern pipeline jest domyślny
Nowe zmiany projektuj przede wszystkim dla ścieżki `modern`.
Warstwa `legacy` ma charakter:
- kompatybilnościowy,
- przejściowy,
- pomocniczy.

Nie pozwól, aby potrzeby warstwy legacy komplikowały architekturę modułów modern bez silnego uzasadnienia.

### 2. Każdy node ma jedną odpowiedzialność
W tym pakiecie szczególnie pilnuj rozdziału:
- `perception_node` = 2D perception only
- `localization_node` = 3D localization only
- `tracking_node` = track identity/state only
- `mission_node` = high-level selection/state only
- `control_node` = motion command generation only

Nie mieszaj tych ról.

### 3. `cmd_vel` musi być wyjaśnialny
Każda logika publikująca sterowanie ma umożliwiać odpowiedź:
- z jakiego celu pochodzi komenda,
- jaki stan misji ją wywołał,
- czy depth hint ją zmodyfikował,
- dlaczego robot jedzie / skręca / stoi.

Jeżeli dodajesz nowy warunek wpływający na ruch:
- dodaj log,
- rozważ pole diagnostyczne lub topic debug,
- nie ukrywaj tej decyzji.

### 4. Brak danych ma być jawny
Jeśli moduł nie ma danych:
- nie udawaj poprawnego działania,
- loguj warning lub info zależnie od wagi,
- przechodź w bezpieczny fallback,
- publikuj stan neutralny, jeśli to właściwe.

Dotyczy szczególnie:
- brak detekcji,
- brak CameraInfo,
- brak depth,
- brak aktywnego targetu,
- brak tracków,
- brak QR / AprilTag backendów.

### 5. Opcjonalne backendy muszą być jawne
Jeżeli backend jest opcjonalny:
- loguj, czy został załadowany,
- loguj, gdy działa fallback,
- nie ukrywaj po cichu, że funkcja jest wyłączona.

Przykład:
- QR backend unavailable
- AprilTag backend unavailable
- YOLO model load failed
- no calibration loaded, using default CameraInfo

### 6. Każdy ważny node ma dawać dobry obraz stanu
Preferowane są:
- logi startowe z konfiguracją,
- logi przejść stanu,
- logi degradacji,
- debug topics,
- heartbeat / freshness diagnostics,
- TUI compatibility.

---

## Zasady kodowania w tym pakiecie

### Struktura kodu
Preferuj:
- `nodes/` dla node’ów runtime,
- `utils/` dla czystych helperów,
- `vision/` dla algorytmów percepcji,
- osobne skrypty offline poza krytyczną logiką node’ów.

### Parametry
Wszystko, co zależy od środowiska albo strojenia, ma być parametrem:
- topic names
- thresholds
- gains
- timeouts
- paths
- enable flags
- families / backend options
- recorder/debug options

### Typy i dataclasses
Jeśli stan lokalny robi się większy:
- używaj dataclasses,
- trzymaj stan jawnie,
- unikaj chaosu na `self.*`.

### Fallback behavior
Każdy node powinien mieć sensowne zachowanie, gdy:
- wejście jeszcze nie przyszło,
- przyszło stare,
- jest niespójne,
- backend opcjonalny nie działa.

### Logging style
Logi powinny być:
- krótkie,
- konkretne,
- z nazwą stanu / celu / przyczyną,
- użyteczne przez SSH.

Nie spamuj każdej klatki bez potrzeby, ale nie ukrywaj ważnych zmian.

---

## Zasady dotyczące narzędzi pomocniczych wewnątrz pakietu

### TUI / debug / kalibracja
Takie narzędzia są mile widziane, ale:
- nie mogą być wymagane do pracy core,
- mają być uruchamiane osobno albo warunkowo,
- mają działać headless,
- mają być maksymalnie użyteczne z terminala.

### Offline tools
Skrypty offline:
- nie powinny być splątane z core runtime,
- mogą generować YAML, raporty TXT/JSON, preview,
- powinny być uruchamiane jako zwykły `python script.py`, jeśli nie wymagają ROS runtime.

---

## Zasady rozwoju tego pakietu w przyszłości

Jeżeli funkcja przestaje być lokalna dla tego pakietu i zaczyna być:
- osobnym recorderem,
- osobnym systemem telemetry,
- osobnym systemem diagnostics,
- osobnym zestawem kalibracyjnym,
- osobnym systemem symulacyjnym,

to rozważ wydzielenie jej do nowej paczki zamiast dalszego rozbudowywania `g1_light_tracking`.

Ten pakiet powinien pozostać możliwie blisko głównej logiki robota.

---

## Checklista przed zmianą w `g1_light_tracking`

1. Czy zmiana wspiera pipeline modern?
2. Czy nie miesza odpowiedzialności node’ów?
3. Czy brak danych prowadzi do bezpiecznego fallbacku?
4. Czy operator będzie wiedział, co się dzieje?
5. Czy logi są wystarczające do pracy przez SSH?
6. Czy zmiana nie wymaga GUI?
7. Czy komunikacja idzie przez ROS2?
8. Czy moduł pomocniczy nie stał się przypadkiem wymagany dla core?
9. Czy nowy kod da się w przyszłości wydzielić do osobnej paczki?
10. Czy nowa decyzja wpływająca na robot motion jest wyjaśnialna?

Najważniejsza lokalna zasada:
**Ten pakiet ma prowadzić robota w sposób bezpieczny, przewidywalny i maksymalnie czytelny diagnostycznie.**


---

## Lokalna polityka komentarzy i TODO w `g1_light_tracking`

### Wszystkie opisy kodu pisz po polsku
W tym pakiecie obowiązuje zasada:
- komentarze,
- docstringi,
- opisy klas,
- opisy funkcji,
- opisy metod,
- wyjaśnienia logiki,

mają być pisane w **języku polskim**.

Dopuszczalne jest pozostawienie nazw technicznych po angielsku, np.:
- `cmd_vel`,
- `Detection2D`,
- `MissionState`,
- `DepthNavHint`,
- `CameraInfo`,
- nazwy bibliotek,
- nazwy parametrów ROS2.

Ale opis ich sensu i działania powinien być po polsku.

### Opisuj każdą ważną klasę, funkcję i metodę
Jeżeli tworzysz lub rozbudowujesz:
- node ROS2,
- klasę pomocniczą,
- funkcję przetwarzania danych,
- metodę sterowania,
- callback,
- narzędzie offline,

dodaj komentarze i opisy, które wyjaśniają:
- rolę elementu,
- znaczenie wejść i wyjść,
- zachowanie fallback,
- wpływ na bezpieczeństwo lub diagnostykę,
- intencję projektową.

W szczególności opisuj:
- logikę decyzji misji,
- logikę sterowania ruchem,
- powody filtracji detekcji,
- fallback przy braku danych,
- moduły diagnostyczne i monitorujące.

### Komentarze mają tłumaczyć „dlaczego”
Najbardziej wartościowe są komentarze, które tłumaczą:
- dlaczego zastosowano takie rozwiązanie,
- dlaczego node działa w taki sposób,
- dlaczego coś jest opcjonalne,
- dlaczego fallback wygląda właśnie tak,
- dlaczego dane są publikowane w danym formacie.

Nie ograniczaj się do komentarzy typu „tu ustawiamy zmienną”.

### TODO mają być utrzymywane i rozwijane
Agenci mają aktywnie dodawać `TODO:` tam, gdzie:
- widać oczywisty kierunek ulepszenia,
- kod jest tymczasowy,
- architektura wymaga dalszego rozdziału,
- trzeba dodać safety checks,
- trzeba poprawić obserwowalność,
- trzeba wydzielić funkcję do osobnej paczki,
- warto dodać konfigurację, testy lub diagnostykę.

TODO powinno być:
- krótkie,
- konkretne,
- technicznie użyteczne.

### Zakaz usuwania komentarzy i TODO bez związku z edytowanym kodem
Agenci nie mogą usuwać istniejących:
- komentarzy,
- docstringów,
- opisów klas i metod,
- TODO,

jeżeli nie edytują dokładnie tego fragmentu logiki.

Można je usunąć lub zmienić tylko wtedy, gdy:
- dotyczą kodu właśnie modyfikowanego,
- stały się nieaktualne,
- zostały wykonane,
- wymagają doprecyzowania po zmianie architektury.

Komentarze i TODO są tu traktowane jako część dokumentacji operacyjnej pakietu.

### Aktualizuj opis równolegle ze zmianą logiki
Jeżeli zmieniasz:
- sposób działania node’a,
- przepływ danych,
- zachowanie fallback,
- sterowanie,
- diagnostykę,
- znaczenie pól wiadomości,

to masz obowiązek zaktualizować komentarze i TODO tak, by nadal odpowiadały rzeczywistemu zachowaniu kodu.
