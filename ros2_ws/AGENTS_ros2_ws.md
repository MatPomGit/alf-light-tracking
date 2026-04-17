# AGENTS.md

## Zakres
Ten plik dotyczy katalogu `ros2_ws/` i wszystkich pakietów ROS2 budowanych w tym workspace.

To jest poziom pośredni pomiędzy globalnym `AGENTS.md` w root repo a lokalnymi zasadami pakietów.

---

## Rola workspace

`ros2_ws/` jest kanonicznym miejscem do:
- `colcon build`
- `source install/setup.bash`
- uruchamiania launcherów ROS2
- integrowania wielu paczek

Każdy nowy pakiet powinien być projektowany tak, aby mógł współistnieć z innymi bez psucia całego workspace.

---

## Zasady dla paczek ROS2

### 1. Paczki mają być luźno powiązane
Komunikacja między paczkami ma iść przez ROS2 interfaces.
Nowa paczka:
- nie może wymagać bezpośredniego dostępu do runtime memory innej paczki,
- nie może psuć builda core, jeśli jest opcjonalna,
- nie może być obowiązkowa dla ruchu robota, jeśli jest tylko narzędziem pomocniczym.

### 2. Pakiety opcjonalne muszą być naprawdę opcjonalne
Dotyczy to np.:
- rosbag recorder
- telemetry
- monitoring
- replay
- wizualizacji
- toolingu offline

Ich brak, zła konfiguracja albo crash nie mogą zatrzymać:
- percepcji,
- lokalizacji,
- trackingu,
- misji,
- sterowania.

### 3. Launchery mają być przewidywalne
Launch file ma:
- jasno pokazywać, jakie node’y startują,
- umożliwiać warunkowe uruchamianie funkcji opcjonalnych,
- nie ukrywać krytycznej logiki biznesowej.

Preferowane podejście:
- jeden główny launcher core,
- osobne launchery dla debug/tools/legacy,
- argumenty launch dla rozszerzeń opcjonalnych.

### 4. Build i zależności
Nowe paczki mają:
- deklarować zależności jawnie,
- nie zakładać obecności środowiska desktopowego,
- nie wprowadzać ciężkich zależności bez potrzeby,
- być ostrożne z pakietami GPU/specyficznymi dla sprzętu.

Jeśli zależność jest opcjonalna, projektuj fallback.

---

## Zasady dotyczące topiców i interfejsów

### 1. Nazwy topiców mają być spójne
Preferowane grupowanie:
- `/perception/...`
- `/localization/...`
- `/tracking/...`
- `/mission/...`
- `/navigation/...`
- `/debug/...`
- `/camera/...`

### 2. Interfejsy mają być stabilne
Nie zmieniaj istniejących wiadomości bez oceny wpływu downstream.
Jeśli trzeba, rozważ:
- nowe pole kompatybilne wstecz,
- nową wiadomość,
- adapter.

### 3. Diagnostyka jako część interfejsu
Jeżeli moduł ma wpływ na decyzje robota, rozważ dodatkowy topic:
- status
- health
- alarm
- explanation
- statistics

---

## Headless i SSH

W obrębie workspace wszystkie paczki muszą zakładać, że będą uruchamiane:
- bez monitora,
- przez terminal,
- w sesji SSH,
- na robocie bez GUI.

Dlatego:
- preferuj CLI, TUI, YAML, raporty tekstowe, JSON,
- unikaj wymagania okienek graficznych,
- każdy moduł GUI musi być opcjonalny i bezpiecznie wyłączalny.

---

## Rozszerzalność

Nowe paczki powinny być projektowane tak, aby:
- dało się je dołączyć później do `ros2_ws/src/`,
- ich brak nie wymagał zmian w paczkach core,
- dało się je uruchamiać z osobnych launcherów,
- mogły subskrybować dane core bez ingerencji w logikę core.

Przykład dobrej integracji:
- recorder subskrybuje topici i zapisuje dane,
- ale nie jest wymagany do pracy robota.

Przykład złej integracji:
- core mission node wymaga działania recorder node, bo inaczej nie publikuje decyzji.

---

## Checklista dla zmian w workspace

Przed zatwierdzeniem zmiany sprawdź:
1. Czy nowa paczka jest rzeczywiście potrzebna w tym workspace?
2. Czy nie powinna być osobnym narzędziem offline?
3. Czy jej brak nie zepsuje builda i runtime core?
4. Czy launchery pozostają czytelne?
5. Czy wszystko da się uruchomić z terminala?
6. Czy nowe interfejsy są spójne z istniejącym nazewnictwem?


---

## Zasady dokumentowania kodu w paczkach ROS2

### Komentarze i docstringi pisz po polsku
W obrębie workspace ROS2 komentarze, docstringi i opisy techniczne mają być tworzone w **języku polskim**.
Nazwy techniczne, nazwy wiadomości, topiców, klas i API mogą pozostać po angielsku, ale opis ich sensu ma być po polsku.

### Każdy node i skrypt ma być opisany
Każdy ważny plik wykonywalny powinien zawierać opis:
- do czego służy,
- jakie dane przyjmuje,
- co publikuje lub zapisuje,
- czy należy do core, czy do warstwy pomocniczej.

Dotyczy to szczególnie:
- node’ów ROS2,
- launcherów,
- skryptów offline,
- bridge’y,
- recorderów,
- narzędzi kalibracyjnych,
- modułów diagnostycznych.

### Opisuj klasy, funkcje i metody
Nowy lub mocno zmieniany kod powinien zawierać komentarze i opisy po polsku dla:
- klas,
- funkcji,
- metod,
- złożonych callbacków,
- fragmentów odpowiedzialnych za fallback lub safety behavior.

Komentarz ma tłumaczyć sens decyzji projektowej i działanie logiki, a nie tylko powtarzać kod.

### Adnotacje TODO są częścią procesu rozwoju
W kodzie należy zostawiać `TODO:` dotyczące:
- przyszłych ulepszeń,
- braków architektonicznych,
- miejsc do wydzielenia do osobnej paczki,
- optymalizacji,
- poprawy diagnostyki,
- przyszłych mechanizmów safety lub observability.

### Nie kasuj istniejących komentarzy i TODO
Nie wolno usuwać istniejących:
- komentarzy,
- docstringów,
- opisów klas i metod,
- TODO,

chyba że agent edytuje dokładnie ten obszar kodu i aktualizuje go do nowego stanu.
Komentarze i TODO traktuj jako część wiedzy projektowej, nie jako zbędny szum.
