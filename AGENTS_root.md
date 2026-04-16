# AGENTS.md

## Zakres
Ten plik dotyczy **całego repozytorium** `alf-light-tracking`.

Repo rozwija oprogramowanie robotyczne dla **Unitree G1 EDU**, uruchamiane na:
- Ubuntu 22.04
- ROS 2
- platformie wbudowanej klasy Jetson
- środowisku headless, zwykle przez SSH

To jest dokument nadrzędny. Jeżeli w podkatalogach istnieją kolejne pliki `AGENTS.md`, traktuj je jako **uszczegółowienie** dla danego obszaru.

---

## Priorytety projektu

1. Robot ma działać stabilnie i przewidywalnie.
2. Cała komunikacja runtime ma iść przez ROS2.
3. System ma być obserwowalny przez terminal.
4. Moduły pomocnicze nie mogą psuć głównej pętli działania robota.
5. Repo ma być gotowe na rozrost o nowe osobne paczki.

---

## Zasady nadrzędne

### 1. Headless first
Zakładaj brak monitora i brak GUI.
Nie projektuj kluczowych funkcji tak, aby wymagały:
- X11
- Wayland
- `DISPLAY`
- Qt GUI
- `cv2.imshow`

GUI może istnieć tylko jako funkcja opcjonalna. Każdy moduł musi poprawnie działać przez SSH.

### 2. ROS2 jako jedyna magistrala
Wszystkie moduły komunikują się przez:
- topic
- message
- service
- action
- parametry ROS2
- TF, jeśli potrzebne

Nie buduj ukrytych zależności runtime przez pliki, współdzieloną pamięć, lokalne sockety albo importowanie stanu z innych node’ów.

### 3. Odporność głównej pętli
Core robot loop musi działać nawet wtedy, gdy nie działają moduły pomocnicze, np.:
- TUI
- debug monitor
- recorder
- rosbag
- eksport raportów
- replay
- narzędzia kalibracyjne
- moduły developerskie

### 4. Maksymalna obserwowalność
Programista ma rozumieć:
- co robot widzi,
- co robot śledzi,
- jaki ma stan misji,
- jakie publikuje sterowanie,
- dlaczego podjął daną decyzję,
- czego mu brakuje.

Dlatego preferowane są:
- czytelne logi,
- topici statusowe,
- topici diagnostyczne,
- jawne powody przejść stanów,
- heartbeat,
- alarmy i stale detection.

### 5. Modułowość i przyszły rozwój
Nowe większe funkcjonalności powinny trafiać do **osobnych paczek ROS2** w `ros2_ws/src/`.
Przykłady:
- rosbag tools
- diagnostics
- telemetry
- simulation tools
- calibration tools

Pakiet główny nie powinien być uzależniony od obecności dodatków.

---

## Reguły projektowe

### Dodawanie nowego modułu
Przed implementacją odpowiedz:
- jaka jest jedna główna odpowiedzialność modułu,
- jakie ma topici wejściowe,
- jakie ma topici wyjściowe,
- jakie ma stany,
- co robi, gdy brakuje danych,
- czy jest częścią core, czy dodatkiem.

### Bezpieczeństwo runtime
Jeśli dane są stare, niespójne albo niebezpieczne:
- lepiej przejść w fallback,
- lepiej wyhamować,
- lepiej opublikować neutralne sterowanie,
- lepiej zgłosić alarm niż zgadywać.

### Debugowalność
Każdy ważny moduł ma pozwalać odpowiedzieć:
- czy działa,
- na jakich topicach działa,
- jaką ma konfigurację,
- czy ma aktualne dane,
- co aktualnie robi,
- dlaczego robi to, co robi.

---

## Zasady jakości kodu

Preferuj:
- małe funkcje,
- jawne typy i dataclasses,
- czytelne nazwy,
- parametry ROS2 zamiast hardcode,
- prosty fallback,
- jawne logowanie decyzji.

Unikaj:
- modułów „wszystko w jednym”,
- ukrytych efektów ubocznych,
- wymagania GUI,
- opcjonalnych backendów bez fallbacku,
- blokowania core loop przez debug tools.

---

## Struktura dokumentów dla agentów

- `AGENTS.md` w root repo: zasady globalne
- `ros2_ws/AGENTS.md`: zasady dla workspace ROS2
- `ros2_ws/src/g1_light_tracking/AGENTS.md`: zasady dla pakietu głównego

Najważniejsza zasada:
**Robot ma działać autonomicznie, ale człowiek przez SSH ma zawsze rozumieć, co robot robi, dlaczego i czego mu brakuje.**


---

## Zasady dokumentowania kodu i komentarzy

### Komentarze i opisy w kodzie mają być po polsku
Agenci mają tworzyć komentarze i opisy kodu w **języku polskim**, chyba że istnieje silny techniczny powód, by pozostawić element po angielsku, np.:
- nazwa standardu,
- nazwa API,
- nazwa protokołu,
- nazwa biblioteki,
- nazwa wiadomości ROS2.

### Opisuj sens, nie tylko składnię
W kodzie należy dodawać:
- komentarze modułowe,
- opisy klas,
- opisy funkcji,
- opisy metod,
- komentarze przy ważnych fragmentach logiki.

Komentarze mają wyjaśniać:
- **po co** dany element istnieje,
- **jaką rolę pełni**,
- **jak działa**,
- **jakie ma ograniczenia**,
- **dlaczego zastosowano takie rozwiązanie**.

Nie wystarczy opisywać samej składni.

### Obowiązkowe opisy dla klas, funkcji i metod
Jeżeli agent tworzy lub istotnie przebudowuje:
- klasę,
- funkcję,
- metodę,
- node ROS2,
- skrypt CLI,
- moduł pomocniczy,

powinien dodać lub zaktualizować:
- krótki opis klasy,
- krótki opis funkcji/metody,
- komentarze przy nieoczywistych miejscach logiki.

### TODO są obowiązkowym narzędziem planowania technicznego
Agenci mają dodawać w kodzie adnotacje:
- `TODO:`
- opcjonalnie z krótkim uzasadnieniem lub kierunkiem rozwoju

TODO powinny wskazywać:
- co warto poprawić później,
- co jest ograniczeniem bieżącej wersji,
- co należałoby zoptymalizować,
- co warto wydzielić lub uogólnić w przyszłości.

### Nie usuwaj istniejących komentarzy i TODO bez powodu
Agenci **nie mogą usuwać istniejących komentarzy, opisów i adnotacji TODO**, chyba że:
- edytują dokładnie ten fragment kodu, którego komentarz dotyczy,
- komentarz stał się fałszywy po zmianie logiki,
- TODO zostało zrealizowane albo zastąpione nowszym, dokładniejszym TODO.

W szczególności:
- nie wolno „czyścić” komentarzy hurtowo,
- nie wolno usuwać TODO tylko dlatego, że przeszkadzają wizualnie,
- nie wolno usuwać opisów klas i metod tylko po to, by skrócić plik.

### Aktualizuj komentarze razem z kodem
Jeżeli agent zmienia logikę klasy, funkcji lub metody, ma obowiązek sprawdzić, czy:
- opis nadal jest prawdziwy,
- TODO nadal ma sens,
- komentarze nie wprowadzają w błąd.

Komentarz nie może pozostawać sprzeczny z kodem.
