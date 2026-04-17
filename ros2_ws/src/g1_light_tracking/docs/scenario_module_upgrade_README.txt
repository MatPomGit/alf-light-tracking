Proponowane zmiany w repo:

1. Nowy plik helpera FSM:
   ros2_ws/src/g1_light_tracking/g1_light_tracking/utils/scenario_fsm.py

2. Podmiana mission_node:
   ros2_ws/src/g1_light_tracking/g1_light_tracking/nodes/mission_node.py

3. Nowy plik scenariusza:
   ros2_ws/src/g1_light_tracking/config/mission_scenario_default.yaml

4. Uzupełnienie config/mission.yaml o parametr:
   scenario_file: src/g1_light_tracking/config/mission_scenario_default.yaml

Co daje ta zmiana:
- definicja maszyny stanów misji przestaje być zaszyta w kodzie,
- można tworzyć różne scenariusze zachowania robota bez przepisywania node'a,
- zachowany jest fallback do scenariusza wbudowanego,
- istniejący model wiadomości ROS2 pozostaje bez zmian.

Przykładowe uruchomienie:
cd ros2_ws
source install/setup.bash
ros2 run g1_light_tracking mission_node --ros-args --params-file src/g1_light_tracking/config/mission.yaml
