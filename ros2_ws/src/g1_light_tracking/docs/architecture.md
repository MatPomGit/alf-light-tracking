# Architektura i działanie `g1_light_tracking`

## 1. Cel systemu

`g1_light_tracking` jest eksperymentalnym pipeline’em percepcyjno-decyzyjnym dla scen logistycznych. System ma odpowiadać na pytanie: *co widzę, gdzie to jest, czy to jest ten sam obiekt co przed chwilą i czy ma znaczenie dla bieżącej misji robota?*

Najważniejsza idea architektoniczna to separacja etapów. Każdy moduł robi jedną rzecz dobrze i publikuje wynik przez jawny kontrakt ROS 2. Dzięki temu łatwo znaleźć źródło problemu: błąd może leżeć w percepcji 2D, w lokalizacji 3D, w trackingu albo w logice zadania, ale nie miesza się od razu ze wszystkim naraz.

## 2. Przepływ danych

```text
kamera RGB / depth
        |
        v
perception_node  ----> Detection2D
        |
        v
localization_node ----> LocalizedTarget
        |
        v
tracking_node ----> TrackedTarget
        |                    |
        |                    +--> mission_node ----> MissionState / MissionTarget / ParcelInfo
        |
        +--> parcel_track_node ----> ParcelTrack / ParcelTrackBinding

Depth image --> depth_mapper_node ----> DepthNavHint ----> control_node
MissionTarget -------------------------------------------> control_node -> Twist
```

## 3. Warstwy odpowiedzialności

### Warstwa percepcji
Na wejściu znajduje się surowy obraz. Wynikiem tej warstwy są obiekty opisane w pikselach: bbox, środek obrazu, pewność, payload i typ celu. To nadal stan „co widać na obrazie”, bez pełnej wiedzy o geometrii sceny.

### Warstwa lokalizacji
Tutaj obiekt dostaje pozycję 3D. Źródłem może być głębia, przybliżenie geometryczne albo inna heurystyka. Szczególnie ważne jest pole `source_method`, bo mówi operatorowi, czy pozycja pochodzi z solidnej głębi, czy z estymacji awaryjnej.

### Warstwa trackingu
To etap, który odpowiada na pytanie „czy ten obiekt to ten sam obiekt co w poprzednich klatkach?”. Tracking stabilizuje identyfikatory, wygładza pozycję i może kompensować globalny ruch kamery. Ta warstwa izoluje logikę wyższych poziomów od krótkotrwałego szumu detekcji.

### Warstwa domenowa
Na tym poziomie system zaczyna rozumieć scenę w kategoriach biznesowych. `parcel_track_node` nie interesuje się już tylko bboxem i pozycją, ale pyta: który QR należy do którego kartonu i jaki jest stan paczki? `mission_node` idzie krok dalej i odpowiada: czy istnieje cel, za którym należy podążać, oraz w jakim stanie jest automat misji.

### Warstwa sterowania
To końcowa translacja percepcji i decyzji na ruch robota. Implementacja jest świadomie prosta: ma być łatwa do strojenia, czytelna i dobra do demonstracji całego pipeline’u, a nie zastępować złożony stack planowania ruchu.

## 3a. Nowy przepływ bezpieczeństwa, head display i nagrywania

```text
MissionTarget -> control_node -> /cmd_vel/raw -> safety_stop_node -> /cmd_vel
MissionState ---------------------------------> head_display_state_node -> /head_display/effect
MissionState ---------------------------------> rosbag_recorder_node -> /rosbag_recorder/status
```

Powyższy przepływ rozdziela odpowiedzialność:
- `control_node` generuje ruch roboczy bez decyzji o latched E-STOP,
- `safety_stop_node` jest jedyną warstwą decydującą o zatrzymaniu awaryjnym,
- `head_display_state_node` mapuje FSM misji na efekt operatorski LED,
- `rosbag_recorder_node` raportuje jawny status rejestracji telemetrii.

## 4. Najważniejsze moduły kodu

## `g1_light_tracking/nodes/`
Każdy plik w tym katalogu odpowiada jednemu node’owi ROS 2. W praktyce najważniejsze do zrozumienia systemu są:

- `perception_node.py` — wejście systemu i pierwsza normalizacja danych.
- `localization_node.py` — przejście z układu obrazu do układu przestrzennego.
- `tracking_node.py` — stabilizacja tożsamości i filtracja czasowa.
- `parcel_track_node.py` — logika łączenia QR z kartonem.
- `mission_node.py` — automat wysokiego poziomu.
- `control_node.py` — wygenerowanie `Twist`.

## `g1_light_tracking/utils/`
Tu znajdują się czyste funkcje, struktury stanu i heurystyki, które łatwo testować jednostkowo. To najwygodniejsze miejsce do pracy nad algorytmami bez uruchamiania całego ROS 2.

## `g1_light_tracking/standalone/`
Tryb standalone służy do lokalnych eksperymentów. Umożliwia szybkie sprawdzenie działania fragmentów pipeline’u bez budowania całego workspace. To dobre miejsce na prototypowanie lub demo na pojedynczej maszynie developerskiej.

## 5. Kluczowe kontrakty wiadomości

Warto czytać system od wiadomości, bo to one definiują granice między etapami.

- `Detection2D.msg` — obiekt w pikselach, zwykle chwilowy.
- `LocalizedTarget.msg` — obiekt w przestrzeni 3D, nadal bez trwałej tożsamości.
- `TrackedTarget.msg` — obiekt z identyfikatorem toru i historią.
- `ParcelTrack.msg` — przesyłka jako byt domenowy.
- `MissionState.msg` — stan automatu zadania.
- `MissionTarget.msg` — obiekt przekazywany do sterowania.
- `DepthNavHint.msg` — reaktywna wskazówka bezpieczeństwa z głębi.

Jeżeli którykolwiek z tych kontraktów się zmienia, zwykle wymaga to sprawdzenia wszystkich modułów w dół i w górę pipeline’u. To jeden z najważniejszych punktów spójności repo.

## 6. Typowe scenariusze działania

### Scenariusz A: wykrycie paczki z QR
1. `perception_node` wykrywa karton i odczytuje QR.
2. `localization_node` nadaje obserwacjom pozycję 3D.
3. `tracking_node` przypisuje lub utrzymuje identyfikatory torów.
4. `parcel_track_node` kojarzy QR z kartonem i publikuje pełny stan paczki.
5. `mission_node` może uznać taką paczkę za cel misji.
6. `control_node` zaczyna generować komendy do podejścia.

### Scenariusz B: krótkotrwały zanik detekcji
1. Detekcja na chwilę znika lub ma niską pewność.
2. `tracking_node` utrzymuje tor przez kilka klatek dzięki licznikowi `missed_frames` i ewentualnej predykcji Kalmana.
3. Logika misji nie musi natychmiast porzucać celu.

### Scenariusz C: przeszkoda przed robotem
1. `depth_mapper_node` analizuje głębię i wykrywa mały prześwit do przodu.
2. Publikowany `DepthNavHint` ogranicza ruch liniowy i sugeruje skręt.
3. `control_node` modyfikuje bazowy `Twist` wynikający z `MissionTarget`.

## 7. Jak rozwijać system bez chaosu

Najbezpieczniejszy sposób rozwoju repo to trzymanie się istniejącego rozdziału odpowiedzialności:

- nowe źródła detekcji dodawaj w percepcji,
- nowe metody lokalizacji dodawaj w lokalizacji,
- nowe heurystyki dopasowania i filtracji dodawaj w trackingu,
- nowe stany biznesowe dodawaj w warstwie `parcel_track` / `mission`,
- nowe zachowania ruchowe dodawaj w sterowaniu.

Jeżeli pojedynczy node zaczyna jednocześnie „widzieć”, „decydować” i „sterować”, to zwykle znak, że architektura zaczyna się mieszać.

## 8. Jak czytać repo po raz pierwszy

Najbardziej efektywna kolejność wejścia w kod:

1. `README.md` i ten dokument.
2. katalog `msg/`.
3. `launch/prod.launch.py`.
4. `nodes/perception_node.py`, `localization_node.py`, `tracking_node.py`.
5. `nodes/parcel_track_node.py`, `mission_node.py`, `control_node.py`.
6. `utils/` i `test/`.

To pozwala najpierw zrozumieć kontrakty i przepływ danych, a dopiero potem szczegóły implementacyjne.

## 9. Workflow nagrywania rosbag (rosbag_recorder_node)

Pipeline można uruchomić z opcjonalnym node'em `rosbag_recorder_node`, który zarządza procesem `ros2 bag record`.
Node startuje warunkowo przez launch argument `with_rosbag:=true` i czyta parametry z `config/rosbag_recorder.yaml`.

### Kluczowe parametry
- `output_dir`, `bag_prefix` — lokalizacja i prefiks nazw sesji.
- `record_all_topics`, `topics_allowlist` — nagrywanie wszystkich topiców albo jawnej listy.
- `compression_mode`, `compression_format` — kompresja rosbag2.
- `split_size_mb` — podział worka po limicie rozmiaru.
- `start_on_launch` — czy node ma zacząć nagrywać od startu.
- `record_only_when_mission_active` — czy nagrywanie zależy od aktywności FSM.

### Automatyczne sterowanie wg FSM
Node subskrybuje `/mission/state` (`MissionState`) i wylicza, czy misja jest aktywna.
Jeżeli `record_only_when_mission_active=true`, nagrywanie jest aktywne tylko poza stanami terminalnymi/
bezczynności. Dzięki temu można ograniczyć rozmiar danych do momentów istotnych operacyjnie.

### Sterowanie ręczne i rotacja
- `/rosbag_recorder/enable` (`std_srvs/srv/SetBool`) — ręczne start/stop.
- `/rosbag_recorder/rotate` (`std_srvs/srv/SetBool`) — opcjonalna rotacja aktywnej sesji.

### Bezpieczne zamykanie procesu
Przy zatrzymaniu node wysyła najpierw `SIGINT`, następnie po timeout `SIGTERM` i awaryjnie `SIGKILL`.
Każde zatrzymanie jest logowane z przyczyną (`manual`, `automatic_reconcile`, `node_shutdown`, itp.).

### Metadane sesji
Dla każdej sesji zapisywany jest JSON obok katalogu bag'a (np. `<bag_name>_session.json`).
Plik zawiera m.in. timestamp uruchomienia, powód startu/zatrzymania, stan misji na starcie i podpowiedź scenariusza.

## 10. Checklista operacyjna

### Start misji
1. Uruchom system launch i potwierdź wybrany tryb (`mode`).
2. Zweryfikuj, że `control_node` publikuje na `/cmd_vel/raw`.
3. Sprawdź czy `safety_stop_node` jest aktywny (`with_safety_stop:=true`) i publikuje `/safety/estop_state`.
4. Potwierdź heartbeat `MissionState` i poprawny cel `MissionTarget`.
5. Jeśli używany jest head display, sprawdź publikację `/head_display/effect`.
6. Jeśli wymagane logowanie danych, włącz `with_rosbag:=true` i sprawdź `/rosbag_recorder/status`.
7. Dopiero po powyższej walidacji przejdź do ruchu robota.

### Awaryjne zatrzymanie + recovery
1. Wywołaj `/safety/estop/trigger` i potwierdź `E-STOP active=true`.
2. Zweryfikuj, że `/cmd_vel` jest zerowany (brak ruchu robota).
3. Zidentyfikuj przyczynę w logu (`manual`, watchdog, depth obstacle, brak mission heartbeat).
4. Usuń przyczynę źródłową (np. przeszkoda, brak danych wejściowych, błąd node’a).
5. Potwierdź stabilność telemetryczną (`/mission/state`, `/navigation/depth_hint`, `/rosbag_recorder/status`).
6. Wywołaj `/safety/estop/reset` i sprawdź, że `E-STOP active=false`.
7. Wznowienie ruchu wykonuj stopniowo, obserwując `debug_node` lub `tui_monitor_node`.
