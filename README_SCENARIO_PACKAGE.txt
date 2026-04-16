Tak — tę paczkę należy rozpakować i podmienić poprzednie pliki.

Ta wersja zawiera już:
1. obsługę wielu nazwanych scenariuszy,
2. wybór scenariusza po `scenario_name`,
3. domyślne zachowanie: gdy `scenario_name` jest puste, uruchamiany jest pierwszy scenariusz z pliku,
4. poprawiony `prod.launch.py`, który przekazuje:
   - scenario_file
   - scenario_name

Pliki w paczce:
- ros2_ws/src/g1_light_tracking/g1_light_tracking/utils/scenario_fsm.py
- ros2_ws/src/g1_light_tracking/g1_light_tracking/nodes/mission_node.py
- ros2_ws/src/g1_light_tracking/config/mission_scenarios.yaml
- ros2_ws/src/g1_light_tracking/config/mission.yaml
- ros2_ws/src/g1_light_tracking/launch/prod.launch.py

Przykłady:

1. Bez podania scenariusza:
   uruchomi się pierwszy scenariusz z pliku mission_scenarios.yaml

   cd ros2_ws
   source install/setup.bash
   ros2 launch g1_light_tracking prod.launch.py

2. Jawny scenariusz delivery:
   cd ros2_ws
   source install/setup.bash
   ros2 launch g1_light_tracking prod.launch.py scenario_name:=delivery

3. Jawny scenariusz handover_only:
   cd ros2_ws
   source install/setup.bash
   ros2 launch g1_light_tracking prod.launch.py scenario_name:=handover_only

4. Jawny scenariusz shelf_inspection:
   cd ros2_ws
   source install/setup.bash
   ros2 launch g1_light_tracking prod.launch.py scenario_name:=shelf_inspection

Jeżeli chcesz użyć innego pliku scenariuszy:
   ros2 launch g1_light_tracking prod.launch.py scenario_file:=/pelna/sciezka/do/innych_scenariuszy.yaml
