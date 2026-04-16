# Wyznaczanie i interpretacja współrzędnych XYZ w `localization_node`

Ten dokument opisuje, **jak w projekcie `g1_light_tracking` wyznaczane są współrzędne `X`, `Y`, `Z`**
oraz jak interpretować ich wzrost i spadek podczas działania systemu.

## 1. Skąd biorą się wartości `X`, `Y`, `Z`

Węzeł `localization_node` publikuje obiekt `LocalizedTarget` z polem `position`.
Wartości są wyznaczane metodą zależną od typu celu i dostępnych danych (`source_method`).

Najczęstsza ścieżka (gdy dostępna jest mapa głębi) wygląda tak:

1. Z detekcji 2D pobierany jest prostokąt obiektu (`x_min`, `y_min`, `x_max`, `y_max`).
2. Dla ograniczonego ROI wokół środka obiektu wybierane są poprawne próbki głębi.
3. `Z` jest medianą tych próbek (odległość od kamery).
4. `X` i `Y` są liczone z modelu kamery pinhole:

   - `X = (u - cx) * Z / fx`
   - `Y = (v - cy) * Z / fy`

   gdzie `u, v` to środek detekcji w pikselach, a `fx, fy, cx, cy` pochodzą z `CameraInfo`.

Jeśli głębia nie jest dostępna, node używa fallbacków, m.in.:

- projekcji punktu piksela na płaszczyznę podłogi (`floor_projection`) dla `light_spot`,
- estymacji odległości z znanej szerokości obiektu (`known_width_*`),
- estymacji pozy z geometrii markera (`pnp_qr`, `pnp_apriltag`).

## 2. Interpretacja kierunków osi

W praktyce kierunki zależą od aktywnego `frame_id` (układu odniesienia), ale dla typowego
układu kamery optycznej interpretacja jest następująca:

- `Z` — odległość „do przodu” od kamery,
- `X` — przesunięcie w bok (prawo/lewo),
- `Y` — przesunięcie pionowe w obrazie (dla układu optycznego zwykle dodatnie w dół).

> Uwaga: zawsze sprawdzaj `frame_id` i konfigurację TF w danym wdrożeniu.
> Ten sam obiekt może mieć inne znaki osi po transformacji do innej ramki (np. `base_link`).

## 3. Co oznacza wzrost i spadek każdej wartości

### Oś `Z`

- **`Z` rośnie** → obiekt jest dalej od kamery.
- **`Z` maleje** → obiekt zbliża się do kamery.

### Oś `X`

Dla typowego optical frame:

- **`X` rośnie** → obiekt przesuwa się bardziej na prawo względem osi kamery.
- **`X` maleje** → obiekt przesuwa się bardziej na lewo.

### Oś `Y`

Dla typowego optical frame:

- **`Y` rośnie** → obiekt przesuwa się niżej w polu widzenia.
- **`Y` maleje** → obiekt przesuwa się wyżej.

## 4. Ważne uwagi praktyczne

1. `source_method` mówi o jakości i pochodzeniu estymacji. Np. metoda oparta o głębię (`depth_*`)
   zwykle jest bardziej bezpośrednia niż fallback `known_width_*`.
2. Zmiana parametrów kamery (`fx`, `fy`, `cx`, `cy`) lub kalibracji wpływa bezpośrednio na `X/Y`.
3. Przy słabej głębi (szum, odbicia, brak próbek) wartości mogą chwilowo skakać.
4. Jeśli porównujesz `XYZ` między modułami, upewnij się, że dane są w tej samej ramce
   (`frame_id` + ewentualne transformacje TF).

## 5. Jak kalibracja i plik kalibracyjny wpływają na `XYZ`

W praktycznym wdrożeniu parametry kamery nie są wpisywane ręcznie do node'a, tylko trafiają
do systemu przez `CameraInfo`. Te wartości są zwykle ładowane przez sterownik kamery z pliku
powstałego po kalibracji (najczęściej YAML).

Typowy plik kalibracyjny zawiera m.in.:

- macierz kamery `K` (`fx`, `fy`, `cx`, `cy`),
- współczynniki dystorsji `D`,
- czasem też macierz projekcji `P` i macierz rektyfikacji `R`.

Wpływ na lokalizację w `localization_node`:

1. `fx`, `fy`, `cx`, `cy` wpływają bezpośrednio na przeliczenie piksela na `X/Y`:
   - błędne `fx/fy` -> niepoprawna skala przesunięcia bocznego,
   - błędne `cx/cy` -> systematyczny offset `X/Y` (stałe „przesunięcie” pozycji).
2. Dystorsja (`D`) wpływa szczególnie na metody geometryczne (np. `pnp_qr`, `pnp_apriltag`):
   - niedokładna kalibracja pogarsza estymację pozy markera,
   - błąd rośnie zwykle przy krawędziach obrazu.
3. Gdy `Z` pochodzi z mapy głębi, jakość kalibracji nadal jest ważna:
   - `Z` jest brane z depth ROI, ale `X/Y` nadal zależy od `K`,
   - przy złym dopasowaniu RGB-depth (intrinsics/extrinsics) obiekt może mieć poprawne `Z`,
     ale przesunięte `X/Y`.

Wniosek praktyczny: po każdej zmianie kamery, obiektywu, rozdzielczości lub istotnej
zmianie montażu kamery należy odświeżyć kalibrację i upewnić się, że właściwy plik
kalibracyjny jest faktycznie używany przez node publikujący `CameraInfo`.

## 6. Krótki przykład interpretacji

Jeśli obserwujesz kolejne próbki:

- `Z`: `2.4 -> 2.1 -> 1.8`
- `X`: `0.1 -> 0.3 -> 0.5`

to oznacza to, że obiekt **zbliża się** do kamery i jednocześnie przemieszcza się bardziej
w prawo względem osi kamery.
