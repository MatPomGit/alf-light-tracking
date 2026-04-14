# g1_light_tracking

Wersja rozszerzona względem MVP:
- własne wiadomości ROS 2 zamiast JSON w `std_msgs/String`,
- hook pod AprilTag (`pupil_apriltags`),
- lepszy szkielet lokalizacji kartonu:
  - QR + PnP,
  - fallback: bbox + znane wymiary,
  - miejsce do dodania keypointów narożników kartonu.

## Główne node'y

- `perception_node`
- `localization_node`
- `mission_node`
- `control_node`
- `debug_node`

## Zależności Pythona

```bash
pip install opencv-python numpy ultralytics pyzbar pupil-apriltags
```

## Budowanie

To jest pakiet mieszany: Python + własne `msg`, dlatego używa `ament_cmake`.

```bash
cd ~/ros2_ws/src
cp -r g1_light_tracking ./g1_light_tracking
cd ~/ros2_ws
colcon build --packages-select g1_light_tracking
source install/setup.bash
ros2 launch g1_light_tracking prod.launch.py
```

## Co jest realnie dodane

- `msg/Detection2D.msg`
- `msg/LocalizedTarget.msg`
- `msg/MissionTarget.msg`
- `msg/ParcelInfo.msg`
- realne skrypty startowe w `scripts/`
- `perception_node.py` publikuje detekcje w typie własnej wiadomości
- `localization_node.py` publikuje cele z pozycją 3D
- `mission_node.py` publikuje uproszczony cel misji
- `localization_node.py` ma dwa tryby dla kartonu:
  1. QR/PnP,
  2. bbox + znane wymiary jako fallback

## Nadal wymaga dopracowania

- dokładne mapowanie klas YOLO do Twojego zbioru danych,
- dopięcie pełnego pose estimation kartonu z narożników,
- tf i poprawna projekcja na podłogę,
- polityka bezpieczeństwa i handover z manipulatorem.


## Ulepszone śledzenie w czasie

Dodano osobny `tracking_node`, który:
- przypisuje stałe `track_id`,
- łączy detekcje z poprzednimi śladami metodą nearest-neighbour,
- wygładza pozycję filtrem EMA,
- utrzymuje ślad przez kilka klatek przy chwilowym zaniku,
- publikuje `TrackedTarget`.

To nadal jest lekki tracker MVP, ale znacząco poprawia stabilność wobec migotania detekcji.


## Wiązanie QR -> parcel_box track_id

Dodano `association_node`, który:
- słucha `TrackedTarget`,
- utrzymuje najnowsze tracki QR i `parcel_box`,
- przypisuje QR do najbliższego kartonu w obrazie,
- premiuje przypadek, gdy środek QR leży wewnątrz bbox kartonu,
- publikuje stabilne wiązanie `ParcelTrackBinding`.

Dzięki temu treść QR może być przypisana do konkretnego `parcel_box_track_id`, co jest podstawą do dalszego śledzenia tej samej przesyłki w czasie.


## Rzeczywisty bbox w śledzeniu

`LocalizedTarget.msg` i `TrackedTarget.msg` zostały rozszerzone o:
- `x_min`
- `y_min`
- `x_max`
- `y_max`

Dzięki temu:
- tracker utrzymuje rzeczywisty obszar obiektu w obrazie,
- `association_node` używa prawdziwego bbox-a kartonu,
- wiązanie `QR -> parcel_box_track_id` nie opiera się już na sztucznej aproksymacji wokół środka.
