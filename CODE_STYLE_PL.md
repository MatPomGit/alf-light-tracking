# CODE_STYLE_PL.md

## Cel

Ten plik definiuje praktyczny standard pisania kodu w repozytorium `alf-light-tracking`, ze szczególnym naciskiem na:
- Python,
- ROS2,
- pracę headless przez SSH,
- wysoką obserwowalność systemu,
- komentarze i docstringi w języku polskim.

Ten dokument uzupełnia:
- `AGENTS.md` w root repo,
- `ros2_ws/AGENTS.md`,
- `ros2_ws/src/g1_light_tracking/AGENTS.md`.

---

## 1. Zasady ogólne

### 1.1. Kod ma być czytelny lokalnie
Programista powinien rozumieć plik bez zgadywania:
- jaka jest rola modułu,
- co robi klasa,
- co robi funkcja,
- skąd przychodzą dane,
- co jest publikowane,
- jakie są fallbacki,
- jakie są ograniczenia.

### 1.2. Komentarze i docstringi po polsku
W tym repo:
- komentarze,
- docstringi,
- opisy klas,
- opisy funkcji,
- opisy metod,
- TODO

piszemy **po polsku**.

Nazwy techniczne mogą pozostać po angielsku, np.:
- `cmd_vel`
- `MissionState`
- `CameraInfo`
- `Detection2D`
- `DepthNavHint`
- `YOLO`
- `AprilTag`

Ale ich sens należy opisywać po polsku.

### 1.3. Komentarz ma tłumaczyć sens
Dobry komentarz odpowiada na pytania:
- po co ten kod istnieje,
- dlaczego działa właśnie tak,
- kiedy fallback jest aktywny,
- co jest ważne operacyjnie,
- jakie są ograniczenia.

Zły komentarz tylko powtarza kod.

---

## 2. Standard modułu Python

Każdy istotny moduł powinien zaczynać się od krótkiego docstringu.

### Wzór

```python
"""Node ROS 2 odpowiedzialny za ...

Moduł:
- odbiera ...
- przetwarza ...
- publikuje ...

Główne założenia:
- ...
- ...
"""
```

### Przykład

```python
"""Node ROS 2 odpowiedzialny za wybór aktywnego celu misji.

Moduł zbiera dane z trackingu i logiki logistycznej, a następnie publikuje
stan misji oraz aktualny cel do sterowania. Node nie steruje robotem bezpośrednio,
ale przygotowuje decyzję dla warstwy control.

Główne założenia:
- brak aktywnego celu nie może powodować awarii,
- stan misji ma być zrozumiały diagnostycznie,
- decyzje mają być obserwowalne przez logi i topic statusowy.
"""
```

---

## 3. Standard opisu klasy

Każda ważna klasa powinna mieć docstring po polsku.

### Wzór

```python
class ExampleClass:
    """Krótki opis roli klasy.

    Klasa odpowiada za ...
    Przechowuje stan ...
    Udostępnia logikę ...
    """
```

### Przykład

```python
class TuiMonitorNode(Node):
    """Terminalowy monitor stanu pipeline'u ROS2.

    Klasa subskrybuje najważniejsze topiki systemu, buduje lokalny stan
    diagnostyczny i prezentuje go w postaci TUI działającego w terminalu.
    Nie wpływa na sterowanie robotem i ma charakter wyłącznie obserwacyjny.
    """
```

---

## 4. Standard opisu funkcji i metod

Każda funkcja lub metoda o znaczeniu większym niż trywialne powinna mieć opis.

### Wzór

```python
def function_name(arg1: str, arg2: int) -> bool:
    """Opisuje, co robi funkcja.

    Argumenty:
    - arg1: opis
    - arg2: opis

    Zwraca:
    - opis wyniku

    Uwagi:
    - ważne ograniczenia
    - istotne fallbacki
    """
```

### Przykład

```python
def apply_depth_navigation(self, twist: Twist) -> Twist:
    """Modyfikuje komendę ruchu na podstawie wskazówek z mapy głębi.

    Argumenty:
    - twist: bazowa komenda ruchu wyliczona z aktywnego celu misji

    Zwraca:
    - komendę ruchu po uwzględnieniu ograniczeń bezpieczeństwa wynikających z głębi

    Uwagi:
    - jeżeli brak danych depth, funkcja zwraca komendę bez zmian
    - jeżeli przeszkoda jest zbyt blisko, ruch do przodu jest zerowany
    """
```

---

## 5. Kiedy komentarz inline jest obowiązkowy

Dodaj komentarz nad blokiem kodu, gdy:
- logika nie jest oczywista,
- działa fallback,
- moduł świadomie degraduje funkcjonalność,
- decyzja wpływa na bezpieczeństwo,
- przetwarzanie danych ma ważne ograniczenie,
- wybierany jest „najmniej zły” kompromis.

### Przykład dobry

```python
# Depth hint działa tu jako warstwa bezpieczeństwa, a nie pełny planner.
# Dlatego tylko skaluje lub blokuje komendę zamiast wyznaczać nową trajektorię.
twist = self.apply_depth_navigation(twist)
```

### Przykład zły

```python
# Ustawiamy twist
twist = self.apply_depth_navigation(twist)
```

---

## 6. Standard TODO

### 6.1. TODO są obowiązkowe tam, gdzie to ma sens
Używaj `TODO:` do oznaczania:
- przyszłych ulepszeń,
- braków architektonicznych,
- miejsc do optymalizacji,
- brakującej diagnostyki,
- przyszłego wydzielenia do osobnej paczki,
- brakujących testów,
- brakujących zabezpieczeń runtime.

### 6.2. TODO ma być konkretne
Złe TODO:

```python
# TODO: poprawić
```

Dobre TODO:

```python
# TODO: Dodać heartbeat topic publikujący świeżość danych z depth mappera,
# aby TUI i debug node mogły wykrywać utratę sensora bez zgadywania po braku wiadomości.
```

### 6.3. Preferowany format TODO

```python
# TODO: [co zrobić]
# Powód: [dlaczego to jest potrzebne]
```

albo krócej:

```python
# TODO: Wydzielić eksport telemetry do osobnej paczki ROS2, aby nie obciążać pakietu core.
```

### 6.4. Nie usuwaj TODO bez związku z edytowanym kodem
Nie wolno usuwać TODO:
- hurtowo,
- dla „porządku wizualnego”,
- bez realizacji,
- bez aktualizacji logiki, której dotyczy.

Można usunąć TODO tylko wtedy, gdy:
- zostało wykonane,
- przestało mieć sens po przebudowie kodu,
- zastępujesz je lepszym, dokładniejszym TODO.

---

## 7. Standard logowania

### 7.1. Logi mają pomagać operatorowi przez SSH
Log powinien wyjaśniać:
- co wystartowało,
- z jaką konfiguracją,
- na jakich topicach pracuje,
- jaki backend jest aktywny,
- jaki fallback został użyty,
- dlaczego node zmienił stan,
- dlaczego coś odrzucił,
- dlaczego publikuje taką komendę ruchu.

### 7.2. Przykłady dobrych logów

```python
self.get_logger().info(
    f"Perception node started. image_topic={self.image_topic}, "
    f"enable_qr={self.enable_qr}, enable_apriltag={self.enable_apriltag}"
)
```

```python
self.get_logger().warning(
    "QR backend unavailable: pyzbar failed to import. "
    "Node will continue without QR detection."
)
```

```python
self.get_logger().info(
    f"Mission state changed: {previous_state} -> {new_state}, reason={reason}"
)
```

### 7.3. Przykłady złych logów

```python
self.get_logger().info("OK")
```

```python
self.get_logger().info("Działa")
```

```python
self.get_logger().warning("Błąd")
```

### 7.4. Nie spamuj bez potrzeby
Nie loguj każdej klatki obrazu, jeśli nie wnosi to wartości.
Loguj:
- zmiany stanu,
- błędy,
- degradację,
- aktywację fallbacku,
- ważne decyzje.

---

## 8. Standard dla node'ów ROS2

Każdy node powinien zawierać:
1. docstring modułu,
2. opis klasy node’a,
3. log startowy z konfiguracją,
4. komentarze przy ważnych callbackach,
5. komentarze przy fallbackach,
6. TODO tam, gdzie architektura jest tymczasowa,
7. jawne parametry ROS2,
8. bezpieczne zachowanie przy braku danych.

### Minimalny wzór

```python
class ExampleNode(Node):
    """Node odpowiedzialny za ...

    Node odbiera ...
    Publikuje ...
    W przypadku braku danych przechodzi w ...
    """

    def __init__(self):
        super().__init__("example_node")

        self.declare_parameter("input_topic", "/input")
        self.declare_parameter("output_topic", "/output")

        self.input_topic = str(self.get_parameter("input_topic").value)
        self.output_topic = str(self.get_parameter("output_topic").value)

        self.pub = self.create_publisher(...)
        self.create_subscription(...)

        self.get_logger().info(
            f"Example node started. input_topic={self.input_topic}, output_topic={self.output_topic}"
        )

    def callback(self, msg):
        """Obsługuje pojedynczą wiadomość wejściową i publikuje wynik.

        W przypadku danych niekompletnych funkcja przechodzi w bezpieczny fallback.
        """
        ...
```

---

## 9. Standard dla skryptów offline

Skrypt offline również wymaga:
- docstringu modułu,
- opisu celu skryptu,
- opisu parametrów wejściowych,
- opisu wyników,
- komentarzy przy ważnej logice,
- TODO dla ulepszeń,
- raportowania do terminala i/lub pliku.

### Przykład
- kalibracja z folderu zdjęć,
- generowanie YAML,
- raport tekstowy,
- eksport JSON,
- analiza rosbag,
- replay danych.

Nie mieszaj takiego skryptu bez potrzeby z runtime node’em ROS2.

---

## 10. Standard dla komentarzy przy bezpieczeństwie i fallbacku

Każde miejsce wpływające na bezpieczeństwo albo ruch robota powinno być opisane.

### Przykład

```python
# Jeżeli nie ma aktywnego celu misji, publikujemy zerową komendę,
# aby robot nie kontynuował ruchu na podstawie nieaktualnego stanu.
if mission.mode in ("idle", "handover_ready"):
    self.pub.publish(Twist())
    return
```

### Przykład

```python
# Brak CameraInfo nie zatrzymuje całego pipeline'u, ale ogranicza precyzję lokalizacji.
# Dlatego node działa dalej i przechodzi na uproszczoną metodę estymacji.
```

---

## 11. Zasady edycji istniejącego kodu

Jeżeli zmieniasz istniejący kod:
- sprawdź docstring,
- sprawdź komentarze,
- sprawdź TODO,
- zaktualizuj je, jeśli logika się zmieniła.

Nie zostawiaj komentarza, który kłamie.

### Obowiązek aktualizacji
Zmieniłeś:
- zachowanie fallbacku,
- parametry,
- znaczenie funkcji,
- stan node’a,
- semantykę wiadomości,
- logikę sterowania,

to musisz odpowiednio zaktualizować:
- komentarz,
- docstring,
- TODO,
- log startowy lub log przejścia stanu.

---

## 12. Minimalna checklista autora zmiany

Przed zakończeniem pracy sprawdź:
1. Czy moduł ma docstring?
2. Czy klasy mają opisy?
3. Czy ważne funkcje i metody mają opisy?
4. Czy złożona logika ma komentarze po polsku?
5. Czy fallbacki są wyjaśnione?
6. Czy są TODO dla oczywistych przyszłych ulepszeń?
7. Czy nie usunąłeś cudzych komentarzy bez potrzeby?
8. Czy logi pomagają zrozumieć stan robota przez SSH?
9. Czy komentarze są zgodne z aktualnym kodem?

---

## 13. Najważniejsza zasada praktyczna

Kod w tym repo ma być nie tylko poprawny technicznie.

Ma też być:
- zrozumiały,
- obserwowalny,
- łatwy do debugowania,
- bezpieczny operacyjnie,
- gotowy do dalszego rozwoju.

Dlatego komentarze, docstringi i TODO nie są dodatkiem.
Są częścią jakości kodu.
