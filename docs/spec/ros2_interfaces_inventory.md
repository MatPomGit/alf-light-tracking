# Inwentaryzacja interfejsów ROS2 (MVP)

## Zakres i definicja MVP
- Zakres MVP oparty o launch `light_tracking_stack.launch.py`:
  - `d435i_node`
  - `light_spot_detector_node`
  - `g1_light_follower_node`
  - `emergency_stop_node`
  - opcjonalnie (warunkowo po dostępności zależności): `unitree_cmd_vel_bridge_node`, `arm_skill_bridge_node`.
- Priorytet jakości: **lepiej odrzucić próbkę niż opublikować błędną detekcję lub komendę ruchu**.

## Kontrakt QoS (stan bieżący)
- W kodzie użyto skrótu `qos=10` dla publisher/subscriber/service, co w praktyce oznacza profil bazowy ROS2 z `depth=10`.
- Dla usług (`std_srvs/Trigger`) i tak obowiązuje semantyka request/response; `depth=10` dotyczy kolejki middleware.
- Brak jawnego `reliability/durability/history` w większości node’ów oznaczono niżej jako `GAP` (wymagana formalizacja kontraktu).

## 1) Topics (MVP)

| Interfejs | Typ | Producer (owner) | Consumer (owner) | QoS | Częstotliwość / SLA | Status kontraktu |
|---|---|---|---|---|---|---|
| `/camera/image_raw` | `sensor_msgs/msg/Image` | `d435i_node` (owner: Perception) | `light_spot_detector_node` (owner: Perception) | `depth=10`, pozostałe pola QoS niejawne | `fps` param (domyślnie 30 Hz) | OK |
| `/camera/color/image_raw` | `sensor_msgs/msg/Image` | `d435i_node` (owner: Perception) | Legacy/diagnostyka (owner: Perception) | `depth=10`, niejawne | jak wyżej; tylko gdy `publish_legacy_color_topic=true` | OK |
| `/light_tracking/detection_json` | `std_msgs/msg/String` (JSON payload) | `light_spot_detector_node` (owner: Perception) | `g1_light_follower_node` (owner: Controls) | `depth=10`, niejawne | event-driven (zależne od obrazu; praktycznie do ~30 Hz) | OK |
| `/cmd_vel_raw` | `geometry_msgs/msg/Twist` | `g1_light_follower_node` (owner: Controls) | `emergency_stop_node` przez remap `cmd_vel_in` (owner: Safety) | `depth=10`, niejawne | `control_rate_hz` (domyślnie 20 Hz) | OK |
| `/cmd_vel` | `geometry_msgs/msg/Twist` | `emergency_stop_node` przez remap `cmd_vel_out` (owner: Safety) | `unitree_cmd_vel_bridge_node` (owner: Platform Integration) / inne wykonawcze | `depth=10`, niejawne | do 20 Hz wejście + wymuszenia STOP | OK |
| `/emergency_stop/active` | `std_msgs/msg/Bool` | `emergency_stop_node` (owner: Safety) | `unitree_cmd_vel_bridge_node` (owner: Platform Integration) | `depth=10`, niejawne | watchdog `safety_tick_hz` (domyślnie 20 Hz) i zmiany stanu | OK |
| `estop_signal` | `std_msgs/msg/Bool` | zewn. interlock/HMI (owner: Safety Integrator) | `emergency_stop_node` (owner: Safety) | `depth=10`, niejawne | event-driven | GAP |
| `estop_arm` | `std_msgs/msg/Bool` | zewn. arming logic/HMI (owner: Safety Integrator) | `emergency_stop_node` (owner: Safety) | `depth=10`, niejawne | event-driven | GAP |
| `estop_heartbeat` | `std_msgs/msg/Empty` lub `std_msgs/msg/Bool` | zewn. supervisory heartbeat (owner: Safety Integrator) | `emergency_stop_node` (owner: Safety) | `depth=10`, niejawne | wg nadawcy, timeout w node (`heartbeat_timeout_s`) | GAP |
| `/api/sport/request` *(opcjonalny node)* | `unitree_api/msg/Request` | `unitree_cmd_vel_bridge_node` (owner: Platform Integration) | Unitree SDK bridge (owner: Platform Integration) | `depth=10`, niejawne | `publish_rate_hz` (domyślnie 10 Hz), burst na STOP | OK |
| `/api/sport/response` *(opcjonalny node)* | `unitree_api/msg/Response` | Unitree SDK bridge (owner: Platform Integration) | `unitree_cmd_vel_bridge_node` (owner: Platform Integration) | `depth=10`, niejawne | event-driven | GAP |
| `/arm_sdk` *(opcjonalny node)* | `unitree_hg/msg/LowCmd` | `arm_skill_bridge_node` (owner: Manipulation) | Unitree arm transport (owner: Manipulation) | `depth=10`, niejawne | sekwencyjnie wg skilli | GAP |
| `/lowstate` *(opcjonalny node)* | `unitree_hg/msg/LowState` | Unitree arm transport (owner: Manipulation) | `arm_skill_bridge_node` (owner: Manipulation) | `depth=10`, niejawne | zależne od kontrolera HW | GAP |

## 2) Services (MVP)

| Interfejs | Typ | Provider (owner) | Client (owner) | QoS / timeout kontrakt | Częstotliwość użycia | Status |
|---|---|---|---|---|---|---|
| `/emergency_stop/trigger` | `std_srvs/srv/Trigger` | `emergency_stop_node` (owner: Safety) | HMI / robot_mission_control (owner: Mission Control) | brak formalnego timeoutu na poziomie spec; semantyka natychmiastowego STOP | on-demand / incydentalnie | OK |
| `/emergency_stop/clear` | `std_srvs/srv/Trigger` | `emergency_stop_node` (owner: Safety) | HMI / robot_mission_control (owner: Mission Control) | clear tylko gdy spełnione warunki bezpieczeństwa (heartbeat/arm) | on-demand / incydentalnie | OK |
| `/arm_skills/pick_box` *(opcjonalny node)* | `std_srvs/srv/Trigger` | `arm_skill_bridge_node` (owner: Manipulation) | Mission orchestration (owner: Mission Control) | brak timeoutu/SLA w spec | on-demand | GAP |
| `/arm_skills/place_box` *(opcjonalny node)* | `std_srvs/srv/Trigger` | `arm_skill_bridge_node` (owner: Manipulation) | Mission orchestration (owner: Mission Control) | brak timeoutu/SLA w spec | on-demand | GAP |
| `/arm_skills/stop` *(opcjonalny node)* | `std_srvs/srv/Trigger` | `arm_skill_bridge_node` (owner: Manipulation) | Mission orchestration (owner: Mission Control) | brak timeoutu/SLA w spec | on-demand | GAP |

## 3) Actions (MVP)

| Interfejs | Typ | Owner | Status |
|---|---|---|---|
| `GAP: action contract dla orkiestracji misji` | `TBD` | Mission Control Lead | GAP |

> Uwaga: w aktualnym kodzie runtime ROS2 dla `g1_light_tracking`/`robot_emergency_stop` nie ma serwera/klienta ROS Action (`rclpy.action`). Warstwa `ros2_ws/robot_mission_control/robot_mission_control/ros/action_clients.py` jest abstrakcyjną biblioteką bez zdefiniowanej nazwy endpointu action.

## 4) Parametry runtime (MVP)

### 4.1 Parametry krytyczne bezpieczeństwa i sterowania (kontrakt produkcyjny)

| Parametr | Node (owner) | Domyślna wartość / źródło | Wpływ na bezpieczeństwo/jakość | Status |
|---|---|---|---|---|
| `light_spot_detector_node.min_detection_confidence` | Perception | `0.5379` (`perception.yaml`) | Zbyt niski próg = ryzyko fałszywych detekcji; preferować odrzucenie | OK |
| `light_spot_detector_node.min_detection_score` | Perception | `0.5407` (`perception.yaml`) | Drugi filtr jakości detekcji | OK |
| `light_spot_detector_node.min_top1_top2_margin` | Perception | `0.0` (`perception.yaml`) | Rozstrzyganie niejednoznacznych kandydatów | GAP |
| `light_spot_detector_node.max_saturated_ratio` | Perception | `0.0002518` (`perception.yaml`) | Odrzucanie prześwietlonych fałszywych hotspotów | OK |
| `g1_light_follower_node.control_rate_hz` | Controls | `20.0` (`control.yaml`) | Częstotliwość pętli sterowania | OK |
| `g1_light_follower_node.detection_timeout_s` | Controls | `0.6` (`control.yaml`) | Po timeout niepewna detekcja nie może sterować ruchem | OK |
| `g1_light_follower_node.min_confidence_for_control` | Controls | `0.6` (kod) | Bramka jakości dla ruchu | OK |
| `g1_light_follower_node.required_stable_frames` | Controls | `3` (kod) | Odrzuca pojedyncze, niestabilne trafienia | OK |
| `/**.heartbeat_timeout_s` | Safety | `0.25` (`emergency_stop.yaml`) | Brak heartbeat => STOP | OK |
| `/**.require_heartbeat_to_run` | Safety | `true` (`emergency_stop.yaml`) | Fail-safe: bez heartbeat brak ruchu | OK |
| `/**.zero_publish_rate_hz` | Safety | `30.0` (`emergency_stop.yaml`) | Częstotliwość aktywnego wymuszania komendy zero | GAP |
| `/**.safety_tick_hz` | Safety | `20.0` (kod) | Watchdog E-STOP i publikacja `/emergency_stop/active` | OK |
| `unitree_cmd_vel_bridge_node.stop_command_min_interval_s` *(opcjonalny)* | Platform Integration | `0.2` (`bridge.yaml`) | Ogranicza flood hard-stop przy aktywnym E-STOP | OK |

### 4.2 Parametry funkcjonalne i integracyjne (pełna lista deklarowana)
- `d435i_node`: `width`, `height`, `fps`, `image_topic`, `legacy_color_topic`, `publish_legacy_color_topic`, `frame_id`.
- `light_spot_detector_node`: `camera_topic`, `detection_topic`, `camera_frame`, `log_detections`, `detection_log_interval_s`, `brightness_threshold`, `blur_kernel`, `morph_kernel`, `min_area`, `min_detection_confidence`, `min_detection_score`, `min_top1_top2_margin`, `ring_thickness_px`, `saturation_level`, `min_mean_contrast`, `min_peak_sharpness`, `max_saturated_ratio`, `confidence_weight_shape`, `confidence_weight_brightness`, `confidence_weight_contrast`, `confidence_weight_sharpness`, `confidence_saturation_penalty_weight`, `min_persistence_frames`, `dynamic_roi_enabled`, `dynamic_roi_size_px`, `dynamic_roi_expand_on_miss`, `legacy_mode`.
- `g1_light_follower_node`: `detection_topic`, `cmd_vel_topic`, `control_rate_hz`, `target_distance_m`, `detection_timeout_s`, `min_area`, `k_linear`, `k_angular`, `max_linear_speed`, `max_angular_speed`, `allow_backward`, `linear_no_depth_speed`, `camera_cx`, `log_nonzero_cmd_vel`, `cmd_vel_log_interval_s`, `cmd_vel_nonzero_eps`, `log_rejection_reasons`, `rejection_log_interval_s`, `log_cmd_vel_subscribers`, `cmd_vel_subscribers_log_interval_s`, `min_confidence_for_control`, `required_stable_frames`.
- `emergency_stop_node`: `use_heartbeat`, `heartbeat_msg_type`, `heartbeat_timeout_s`, `enable_trigger_services`, `require_arm_to_clear`, `safety_tick_hz` + parametry z pliku globalnego (`start_in_stop`, `zero_publish_rate_hz`, `require_heartbeat_to_run`).
- `unitree_cmd_vel_bridge_node` *(opcjonalny)*: `cmd_vel_topic`, `unitree_request_topic`, `max_vx`, `max_vy`, `max_vyaw`, `cmd_timeout_s`, `publish_rate_hz`, `api_response_topic`, `switch_to_normal`, `startup_delay_s`, `start_fsm_id`, `enable_balance_mode`, `balance_mode`, `velocity_duration_s`, `log_cmd_vel_rx`, `log_cmd_vel_tx`, `log_subscribers`, `log_interval_s`, `estop_active_topic`, `stop_command_min_interval_s`.
- `arm_skill_bridge_node` *(opcjonalny)*: `service_prefix`, `arm_sdk_topic`, `lowstate_topic`.

## Rejestr GAP (owner + termin domknięcia)

| GAP ID | Opis luki | Owner | Termin domknięcia | Kryterium domknięcia |
|---|---|---|---|---|
| GAP-ROS2-001 | Brak formalnego profilu QoS (`reliability/durability/history`) dla topiców krytycznych (`/camera/image_raw`, `/light_tracking/detection_json`, `/cmd_vel_raw`, `/cmd_vel`, `/emergency_stop/active`). | ROS2 Tech Lead | 2026-04-30 | Jawna tabela QoS + odzwierciedlenie w kodzie (QoSProfile), test integracyjny.
| GAP-ROS2-002 | Brak spisanej częstotliwości publikacji dla topiców zewnętrznych `estop_signal`, `estop_arm`, `estop_heartbeat`. | Safety Integrator | 2026-04-24 | Minimalna/max częstotliwość i timeouty wpisane do spec + test HIL.
| GAP-ROS2-003 | Brak formalnego kontraktu timeout/SLA dla usług `/arm_skills/*`. | Manipulation Lead | 2026-05-06 | Spec czasu odpowiedzi, retry policy i semantyka błędów Trigger.
| GAP-ROS2-004 | Brak zdefiniowanego endpointu ROS Action dla orkiestracji misji mimo gotowej warstwy abstrakcyjnej po stronie Mission Control. | Mission Control Lead | 2026-05-15 | Nazwa action, typ Goal/Result/Feedback, polityka cancel/retry.
| GAP-ROS2-005 | Parametr `min_top1_top2_margin` ustawiony na `0.0` wymaga decyzji kalibracyjnej dla środowiska produkcyjnego. | Perception Lead | 2026-04-27 | Raport kalibracji + wartość graniczna zatwierdzona eksperymentalnie.
| GAP-ROS2-006 | Parametr `zero_publish_rate_hz` nie jest jednoznacznie opisany względem `safety_tick_hz` (duplikacja odpowiedzialności za częstotliwość STOP). | Safety Lead | 2026-04-27 | Jedna polityka częstotliwości STOP i spójna implementacja/spec.
| GAP-ROS2-007 | Brak jednoznacznego kontraktu typu i semantyki dla `/api/sport/response` oraz topiców manipulatora (`/arm_sdk`, `/lowstate`) w dokumencie interfejsów nadrzędnych. | Platform Integration Lead | 2026-05-08 | Załączony ICD (Interface Control Document) dla Unitree API/HG.

## Check DoD: „100% interfejsów MVP ma właściciela i kontrakt”
- **Owner:** spełnione dla wszystkich pozycji (także GAP ma przypisanego właściciela).
- **Kontrakt:** częściowo spełnione.
  - Spełnione dla głównej ścieżki detekcja → sterowanie → E-STOP.
  - Niespełnione dla pozycji oznaczonych `GAP` w tabelach i rejestrze.
- **Wniosek:** DoD **jeszcze niezamknięte**; do domknięcia wymagane zamknięcie `GAP-ROS2-001..007`.
