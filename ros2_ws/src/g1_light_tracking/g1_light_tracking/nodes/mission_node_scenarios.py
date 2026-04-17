"""ROS 2 node wysokopoziomowej logiki zadania.

MissionNode obserwuje tracki i stan przesyłek, wybiera cel misji oraz publikuje dwa rodzaje
informacji: bieżący stan automatu (`MissionState`) oraz docelowy obiekt do śledzenia / podejścia
(`MissionTarget`).

W tej wersji maszyna stanów nie jest już zaszyta na sztywno w kodzie. Konkretne scenariusze
mogą być ładowane z pliku YAML, co pozwala stroić i rozwijać zachowanie robota bez przepisywania
samego node'a.
"""

from __future__ import annotations

import time

import rclpy
from rclpy.node import Node

from g1_light_tracking.msg import (
    MissionState,
    MissionTarget,
    ParcelInfo,
    ParcelTrack,
    TrackedTarget,
)
from g1_light_tracking.utils.scenario_fsm import (
    ScenarioDefinition,
    evaluate_condition,
    load_scenario_definition,
)


class MissionNode(Node):
    """Node ROS 2 odpowiedzialny za logikę misji i wybór aktywnego celu."""

    def __init__(self):
        super().__init__('mission_node')

        self.declare_parameter('tracked_topic', '/tracking/targets')
        self.declare_parameter('parcel_track_topic', '/tracking/parcel_tracks')
        self.declare_parameter('mission_topic', '/mission/target')
        self.declare_parameter('mission_state_topic', '/mission/state')
        self.declare_parameter('parcel_info_topic', '/mission/parcel_info')

        self.declare_parameter('color_pickup_values', ['green', 'yellow'])
        self.declare_parameter('color_dropoff_values', ['blue', 'red'])

        self.declare_parameter('prefer_identified_parcels', True)
        self.declare_parameter('parcel_timeout_sec', 3.0)
        self.declare_parameter('state_hold_sec', 1.0)

        # Nowy parametr: ścieżka do pliku scenariusza FSM.
        # Jeżeli jest pusta, node używa scenariusza wbudowanego.
        self.declare_parameter('scenario_file', '')

        self.pickup_colors = set(self.get_parameter('color_pickup_values').value)
        self.dropoff_colors = set(self.get_parameter('color_dropoff_values').value)
        self.prefer_identified_parcels = bool(self.get_parameter('prefer_identified_parcels').value)
        self.parcel_timeout_sec = float(self.get_parameter('parcel_timeout_sec').value)
        self.state_hold_sec = float(self.get_parameter('state_hold_sec').value)

        scenario_file = str(self.get_parameter('scenario_file').value)
        self.scenario = self.load_scenario(scenario_file)

        self.latest_tracked_by_id = {}
        self.latest_parcel_tracks = {}
        self.latest_parcel_time = {}
        self.latest_tracked_time = {}

        self.current_state = self.scenario.initial_state
        self.previous_state = ''
        self.state_since = time.time()
        self.active_parcel_box_track_id = ''
        self.active_shipment_id = ''

        self.mission_pub = self.create_publisher(MissionTarget, self.get_parameter('mission_topic').value, 20)
        self.state_pub = self.create_publisher(MissionState, self.get_parameter('mission_state_topic').value, 20)
        self.parcel_pub = self.create_publisher(ParcelInfo, self.get_parameter('parcel_info_topic').value, 20)

        self.create_subscription(TrackedTarget, self.get_parameter('tracked_topic').value, self.on_tracked, 50)
        self.create_subscription(ParcelTrack, self.get_parameter('parcel_track_topic').value, self.on_parcel_track, 20)

        self.timer = self.create_timer(0.20, self.tick)

        self.get_logger().info(
            f"MissionNode started. scenario={self.scenario.name}, "
            f"initial_state={self.scenario.initial_state}, "
            f"scenario_file={scenario_file or '<built-in>'}"
        )

    def load_scenario(self, scenario_file: str) -> ScenarioDefinition:
        """Wczytuje scenariusz z pliku lub używa scenariusza domyślnego."""
        try:
            scenario = load_scenario_definition(scenario_file)
            return scenario
        except Exception as exc:
            self.get_logger().warning(
                f"Nie udało się wczytać scenario_file={scenario_file!r}: {exc}. "
                "Używam scenariusza wbudowanego."
            )
            return load_scenario_definition(None)

    def on_tracked(self, msg: TrackedTarget):
        self.latest_tracked_by_id[msg.track_id] = msg
        self.latest_tracked_time[msg.track_id] = time.time()

    def on_parcel_track(self, msg: ParcelTrack):
        self.latest_parcel_tracks[msg.parcel_box_track_id] = msg
        self.latest_parcel_time[msg.parcel_box_track_id] = time.time()

        p = ParcelInfo()
        p.stamp = msg.stamp
        p.shipment_id = msg.shipment_id
        p.pickup_zone = msg.pickup_zone
        p.dropoff_zone = msg.dropoff_zone
        p.parcel_type = msg.parcel_type
        p.mass_kg = msg.mass_kg
        p.raw_payload = msg.raw_payload
        if msg.has_qr:
            self.parcel_pub.publish(p)

    def tick(self):
        """Pełny przebieg polityki misji wykonywany cyklicznie."""
        self.cleanup_stale()

        best_parcel = self.select_best_parcel_track()
        light = self.select_first_target('light_spot')
        shelf = self.select_first_target('shelf')
        person = self.select_first_target('person')
        planar = self.select_first_target('planar_surface')

        context = {
            "parcel": best_parcel,
            "light": light,
            "shelf": shelf,
            "person": person,
            "planar": planar,
        }

        self.advance_state(context)
        mission = self.build_mission(context)
        self.mission_pub.publish(mission)
        self.state_pub.publish(self.build_state_msg(context))

    def state_elapsed(self) -> float:
        return time.time() - self.state_since

    def set_state(self, new_state: str):
        if new_state != self.current_state:
            self.previous_state = self.current_state
            self.current_state = new_state
            self.state_since = time.time()
            self.get_logger().info(
                f"Mission state changed: {self.previous_state} -> {self.current_state}"
            )

    def build_predicates(self, context: dict) -> dict:
        """Buduje słownik prostych predykatów używanych przez scenariusz FSM."""
        parcel = context["parcel"]
        light = context["light"]
        shelf = context["shelf"]
        person = context["person"]
        planar = context["planar"]

        elapsed = self.state_elapsed()

        return {
            "parcel_exists": parcel is not None,
            "parcel_has_qr": bool(parcel is not None and parcel.has_qr),
            "parcel_identified": bool(parcel is not None and parcel.logistics_state == 'identified'),
            "person_exists": person is not None,
            "shelf_exists": shelf is not None,
            "light_exists": light is not None,
            "planar_exists": planar is not None,
            "light_color_in_zone": bool(
                light is not None and light.color_label in (self.pickup_colors | self.dropoff_colors)
            ),
            "light_aligned_for_drop": bool(
                light is not None and abs(light.position.x) < 0.15 and light.position.z < 0.8
            ),
            "person_missing_timeout": bool(person is None and elapsed > self.state_hold_sec),
            "parcel_missing_timeout": bool(parcel is None and elapsed > self.state_hold_sec),
            "light_missing_timeout": bool(light is None and elapsed > self.state_hold_sec),
            "navigate_missing_timeout": bool(
                shelf is None and parcel is None and elapsed > max(2.0, self.state_hold_sec)
            ),
            "drop_finished_timeout": bool(elapsed > 1.5),
        }

    def execute_actions(self, actions: list[str], context: dict):
        """Wykonuje proste akcje pomocnicze przypisane do przejścia."""
        parcel = context["parcel"]

        for action in actions:
            if action == "set_active_parcel_from_parcel" and parcel is not None:
                self.active_parcel_box_track_id = parcel.parcel_box_track_id
                self.active_shipment_id = parcel.shipment_id
            elif action == "clear_active_parcel":
                self.active_parcel_box_track_id = ''
                self.active_shipment_id = ''
            else:
                self.get_logger().warning(f"Nieznana akcja scenariusza: {action}")

    def advance_state(self, context: dict):
        """Przesuwa FSM na podstawie aktualnego scenariusza z pliku."""
        state_def = self.scenario.states.get(self.current_state)
        if state_def is None:
            self.get_logger().error(
                f"Aktualny stan {self.current_state!r} nie istnieje w scenariuszu. "
                f"Wracam do initial_state={self.scenario.initial_state!r}."
            )
            self.set_state(self.scenario.initial_state)
            return

        predicates = self.build_predicates(context)

        for transition in state_def.transitions:
            elapsed = self.state_elapsed()
            if elapsed < transition.min_state_time:
                continue
            if transition.max_state_time is not None and elapsed > transition.max_state_time:
                continue
            if evaluate_condition(transition.condition, predicates):
                self.execute_actions(transition.actions, context)
                self.set_state(transition.target)
                return

    def build_mission(self, context: dict) -> MissionTarget:
        """Buduje MissionTarget na podstawie bieżącego stanu i polityki scenariusza."""
        parcel = context["parcel"]
        light = context["light"]
        shelf = context["shelf"]
        person = context["person"]
        planar = context["planar"]

        mission = MissionTarget()
        mission.mode = self.current_state

        state_def = self.scenario.states.get(self.current_state)
        target_policy = state_def.target_policy if state_def is not None else "generic"

        if target_policy == 'person' and person is not None:
            return self.mission_from_tracked(person, self.current_state)

        if target_policy == 'parcel' and parcel is not None:
            return self.mission_from_parcel_track(parcel, self.current_state)

        if target_policy == 'align':
            if light is not None:
                return self.mission_from_light(light)
            if planar is not None:
                return self.mission_from_tracked(planar, 'planar_alignment')

        if target_policy == 'drop':
            if light is not None:
                m = self.mission_from_light(light)
                m.mode = 'drop'
                return m

        if parcel is not None:
            return self.mission_from_parcel_track(parcel, 'parcel_approach')
        if light is not None:
            return self.mission_from_light(light)
        if shelf is not None:
            return self.mission_from_tracked(shelf, 'shelf_approach')
        if person is not None:
            return self.mission_from_tracked(person, 'handover_ready')
        if planar is not None:
            return self.mission_from_tracked(planar, 'planar_alignment')
        return mission

    def select_best_parcel_track(self):
        if not self.latest_parcel_tracks:
            return None
        candidates = list(self.latest_parcel_tracks.values())

        def rank(msg: ParcelTrack):
            identified = 1 if msg.logistics_state == 'identified' else 0
            confirmed = 1 if msg.is_confirmed else 0
            has_qr = 1 if msg.has_qr else 0
            confidence = float(msg.confidence)
            close_bonus = -float(msg.position.z)
            active_bonus = 1 if (self.active_parcel_box_track_id and msg.parcel_box_track_id == self.active_parcel_box_track_id) else 0
            if self.prefer_identified_parcels:
                return (active_bonus, identified, confirmed, has_qr, confidence, close_bonus)
            return (active_bonus, confirmed, has_qr, confidence, close_bonus)

        candidates.sort(key=rank, reverse=True)
        return candidates[0]

    def select_first_target(self, target_type: str):
        for target in self.latest_tracked_by_id.values():
            if target.target_type == target_type:
                return target
        return None

    def mission_from_parcel_track(self, parcel: ParcelTrack, mode: str) -> MissionTarget:
        mission = MissionTarget()
        mission.stamp = parcel.stamp
        mission.frame_id = parcel.frame_id
        mission.target_type = 'parcel_track'
        mission.class_name = 'parcel_box'
        mission.confidence = parcel.confidence
        mission.position = parcel.position
        mission.payload = parcel.raw_payload
        mission.mode = mode
        return mission

    def mission_from_light(self, target: TrackedTarget) -> MissionTarget:
        mission = MissionTarget()
        mission.stamp = target.stamp
        mission.frame_id = target.frame_id
        mission.target_type = target.target_type
        mission.class_name = target.class_name
        mission.confidence = target.confidence
        mission.position = target.position
        mission.color_label = target.color_label
        mission.payload = target.payload
        mission.mode = 'light_guided'
        if target.color_label in self.pickup_colors:
            mission.zone_mode = 'pickup'
        elif target.color_label in self.dropoff_colors:
            mission.zone_mode = 'dropoff'
        else:
            mission.zone_mode = 'unknown'
        return mission

    def mission_from_tracked(self, target: TrackedTarget, mode: str) -> MissionTarget:
        mission = MissionTarget()
        mission.stamp = target.stamp
        mission.frame_id = target.frame_id
        mission.target_type = target.target_type
        mission.class_name = target.class_name
        mission.confidence = target.confidence
        mission.position = target.position
        mission.color_label = target.color_label
        mission.payload = target.payload
        mission.mode = mode
        return mission

    def build_state_msg(self, context: dict) -> MissionState:
        """Buduje MissionState wraz z opisem powodu bieżącego stanu."""
        parcel = context["parcel"]
        light = context["light"]
        shelf = context["shelf"]
        person = context["person"]
        planar = context["planar"]

        msg = MissionState()
        msg.stamp = self.get_clock().now().to_msg()
        msg.frame_id = parcel.frame_id if parcel is not None else 'base_link'
        msg.state = self.current_state
        msg.previous_state = self.previous_state
        msg.active_parcel_box_track_id = self.active_parcel_box_track_id
        msg.active_shipment_id = self.active_shipment_id
        msg.has_active_parcel = parcel is not None
        msg.has_drop_target = (light is not None) or (planar is not None) or (shelf is not None)
        msg.is_terminal = self.current_state in self.scenario.terminal_states
        msg.reason = self.describe_reason()

        if parcel is not None:
            msg.track_id = parcel.parcel_box_track_id
            msg.parcel_box_track_id = parcel.parcel_box_track_id
            msg.qr_track_id = parcel.qr_track_id
            msg.shipment_id = parcel.shipment_id
            msg.pickup_zone = parcel.pickup_zone
            msg.dropoff_zone = parcel.dropoff_zone
            msg.parcel_type = parcel.parcel_type
            msg.mass_kg = float(parcel.mass_kg)
            msg.raw_payload = parcel.raw_payload
            msg.has_qr = bool(parcel.has_qr)
            msg.logistics_state = parcel.logistics_state
            msg.is_confirmed = bool(parcel.is_confirmed)
            msg.confidence = float(parcel.confidence)
            msg.active_target_type = 'parcel_track'
            msg.active_target_mode = self.current_state
        else:
            active_target = light or shelf or person or planar
            if active_target is not None:
                msg.track_id = active_target.track_id
                msg.confidence = float(active_target.confidence)
                msg.active_target_type = active_target.target_type
                msg.active_target_mode = self.current_state

        return msg

    def describe_reason(self) -> str:
        """Zwraca opis stanu pobrany z aktualnego scenariusza."""
        state_def = self.scenario.states.get(self.current_state)
        if state_def is None:
            return 'unknown'
        return state_def.reason or f'state={self.current_state}'

    def cleanup_stale(self):
        now = time.time()
        stale_parcels = [k for k, t in self.latest_parcel_time.items() if (now - t) > self.parcel_timeout_sec]
        for k in stale_parcels:
            self.latest_parcel_time.pop(k, None)
            self.latest_parcel_tracks.pop(k, None)

        stale_targets = [k for k, t in self.latest_tracked_time.items() if (now - t) > self.parcel_timeout_sec]
        for k in stale_targets:
            self.latest_tracked_time.pop(k, None)
            self.latest_tracked_by_id.pop(k, None)


def main(args=None):
    rclpy.init(args=args)
    node = MissionNode()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()
