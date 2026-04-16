"""Node ROS2 sterujący wzorem LED na głowie robota na podstawie stanu misji.

Moduł rozdziela logikę doboru efektu od warstwy transportu (adapter),
dzięki czemu można podmienić backend publikacji bez naruszania logiki FSM.
"""

from __future__ import annotations

import json
import math
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

import rclpy
from rclpy.node import Node
from std_msgs.msg import Bool, String

from g1_light_tracking.msg import MissionState, MissionTarget, TrackedTarget


Color = tuple[float, float, float]


@dataclass
class EffectSpec:
    """Opis efektu skonfigurowanego dla danego stanu logicznego."""

    name: str
    kind: str
    color: str = ''
    color_a: str = ''
    color_b: str = ''
    period_s: float = 2.0
    hz: float = 2.0
    speed: float = 0.6
    min_period_s: float = 0.35
    max_period_s: float = 1.8


@dataclass
class ResolvedEffect:
    """Efekt po rozstrzygnięciu priorytetów (gotowy do renderowania klatki)."""

    source: str
    priority: int
    spec: EffectSpec


class DisplayOutputAdapter(ABC):
    """Abstrakcyjny interfejs transportu do sterownika wyświetlacza LED."""

    @abstractmethod
    def send_frame(self, color: Color, brightness: float, tag: str) -> None:
        """Wysyła pojedynczą klatkę koloru do docelowego transportu."""


class RosTopicDisplayAdapter(DisplayOutputAdapter):
    """Adapter publikujący klatki LED jako JSON na ROS topicu."""

    def __init__(self, node: Node, topic: str) -> None:
        self._pub = node.create_publisher(String, topic, 20)

    def send_frame(self, color: Color, brightness: float, tag: str) -> None:
        payload = {
            'tag': tag,
            'r': round(max(0.0, min(1.0, color[0])), 4),
            'g': round(max(0.0, min(1.0, color[1])), 4),
            'b': round(max(0.0, min(1.0, color[2])), 4),
            'brightness': round(max(0.0, min(1.0, brightness)), 4),
        }
        msg = String()
        msg.data = json.dumps(payload, ensure_ascii=False)
        self._pub.publish(msg)


class VendorBridgeDisplayAdapter(DisplayOutputAdapter):
    """Adapter mostkujący do rozwiązania vendorowego (placeholder do podmiany)."""

    def __init__(self, node: Node, topic: str) -> None:
        # Dla spójności diagnostyki używamy ten sam format JSON co adapter ROS.
        # TODO: Podmienić publikację na natywny format Unitree po integracji SDK.
        self._pub = node.create_publisher(String, topic, 20)

    def send_frame(self, color: Color, brightness: float, tag: str) -> None:
        payload = {
            'vendor_bridge': True,
            'tag': tag,
            'rgb': [
                round(max(0.0, min(1.0, color[0])), 4),
                round(max(0.0, min(1.0, color[1])), 4),
                round(max(0.0, min(1.0, color[2])), 4),
            ],
            'brightness': round(max(0.0, min(1.0, brightness)), 4),
        }
        msg = String()
        msg.data = json.dumps(payload, ensure_ascii=False)
        self._pub.publish(msg)


class EffectEngine:
    """Silnik animacji generujący kolor klatki dla zadanych efektów."""

    def solid(self, color: Color, _t: float) -> Color:
        """Zwraca stały kolor bez animacji."""
        return color

    def pulse(self, color: Color, t: float, period_s: float) -> Color:
        """Animacja "oddechu" oparta o sinus, z modulacją jasności."""
        period = max(0.05, period_s)
        level = 0.25 + 0.75 * (0.5 + 0.5 * math.sin(2.0 * math.pi * t / period))
        return tuple(channel * level for channel in color)

    def scan(self, color_a: Color, color_b: Color, t: float, speed: float) -> Color:
        """Płynne skanowanie gradientu między dwoma kolorami."""
        phase = 0.5 + 0.5 * math.sin(2.0 * math.pi * t * max(0.05, speed))
        return tuple((1.0 - phase) * a + phase * b for a, b in zip(color_a, color_b))

    def blink(self, color: Color, t: float, hz: float) -> Color:
        """Miganie ostrzegawcze o zadanej częstotliwości."""
        cycle = 1.0 / max(0.1, hz)
        return color if (t % cycle) < (cycle * 0.5) else (0.0, 0.0, 0.0)

    def strobe(self, color: Color, t: float) -> Color:
        """Agresywny stroboskop dla sygnału E-STOP."""
        return self.blink(color, t=t, hz=12.0)


class HeadDisplayStateNode(Node):
    """Node mapujący stan misji i bezpieczeństwa na efekt LED głowy robota."""

    def __init__(self) -> None:
        super().__init__('head_display_state_node')

        # Parametry topików wejściowych i wyjściowych.
        self.declare_parameter('mission_state_topic', '/mission/state')
        self.declare_parameter('mission_target_topic', '/mission/target')
        self.declare_parameter('tracked_target_topic', '/tracking/targets')
        self.declare_parameter('estop_topic', '/safety/estop')
        self.declare_parameter('safety_warning_topic', '/safety/warning')
        self.declare_parameter('output_mode', 'ros_topic')
        self.declare_parameter('output_topic', '/head_display/command')
        self.declare_parameter('vendor_output_topic', '/unitree/head_display/command')

        # Parametry czasowe i jasność.
        self.declare_parameter('publish_hz', 20.0)
        self.declare_parameter('mission_timeout_s', 2.0)
        self.declare_parameter('brightness', 0.45)

        # Parametry mapowania stanów i palety.
        self.declare_parameter('palette', {})
        self.declare_parameter('effects', {})
        self.declare_parameter('state_map', {})
        self.declare_parameter('fallback_effect', 'diagnostic')
        self.declare_parameter('idle_effect', 'idle')
        self.declare_parameter('safety_warning_effect', 'terminal_error')
        self.declare_parameter('estop_effect', 'estop')

        self.engine = EffectEngine()
        self.last_mission_state: MissionState | None = None
        self.last_mission_state_time = self.get_clock().now()
        self.last_mission_target: MissionTarget | None = None
        self.last_tracked_target: TrackedTarget | None = None
        self.estop_active = False
        self.safety_warning_active = False

        self.palette = self._load_palette()
        self.effects = self._load_effects()
        self.state_map = self._load_state_map()

        self.output_adapter = self._build_output_adapter()

        mission_state_topic = str(self.get_parameter('mission_state_topic').value)
        self.create_subscription(MissionState, mission_state_topic, self._on_mission_state, 20)

        mission_target_topic = str(self.get_parameter('mission_target_topic').value)
        self.create_subscription(MissionTarget, mission_target_topic, self._on_mission_target, 20)

        tracked_target_topic = str(self.get_parameter('tracked_target_topic').value)
        self.create_subscription(TrackedTarget, tracked_target_topic, self._on_tracked_target, 20)

        self.create_subscription(Bool, str(self.get_parameter('estop_topic').value), self._on_estop, 20)
        self.create_subscription(
            Bool,
            str(self.get_parameter('safety_warning_topic').value),
            self._on_safety_warning,
            20,
        )

        publish_hz = max(1.0, float(self.get_parameter('publish_hz').value))
        self.timer = self.create_timer(1.0 / publish_hz, self._on_tick)

        self.get_logger().info(
            'HeadDisplayStateNode started: '
            f'output_mode={self.get_parameter("output_mode").value}, '
            f'mission_state_topic={mission_state_topic}, publish_hz={publish_hz}'
        )

    def _load_palette(self) -> dict[str, Color]:
        """Wczytuje słownik nazwanych kolorów z parametrów."""
        raw = self.get_parameter('palette').value
        if not isinstance(raw, dict):
            self.get_logger().warning('Parameter palette is not a dictionary; using defaults.')
            return self._default_palette()

        palette: dict[str, Color] = {}
        for name, values in raw.items():
            if not isinstance(values, (list, tuple)) or len(values) != 3:
                continue
            palette[str(name)] = (
                float(values[0]),
                float(values[1]),
                float(values[2]),
            )
        if not palette:
            return self._default_palette()
        return palette

    def _default_palette(self) -> dict[str, Color]:
        """Paleta awaryjna gdy YAML nie dostarcza poprawnych danych."""
        return {
            'blue_soft': (0.15, 0.3, 1.0),
            'turquoise': (0.0, 0.9, 0.8),
            'violet': (0.5, 0.1, 1.0),
            'amber': (1.0, 0.55, 0.05),
            'white': (1.0, 1.0, 1.0),
            'cyan': (0.0, 1.0, 1.0),
            'green': (0.0, 1.0, 0.2),
            'gold': (1.0, 0.8, 0.15),
            'red': (1.0, 0.0, 0.0),
            'diag_neutral': (0.8, 0.8, 0.8),
        }

    def _load_effects(self) -> dict[str, EffectSpec]:
        """Wczytuje specyfikacje efektów z parametru YAML."""
        raw = self.get_parameter('effects').value
        effects: dict[str, EffectSpec] = {}
        if isinstance(raw, dict):
            for effect_name, config in raw.items():
                if not isinstance(config, dict):
                    continue
                effects[str(effect_name)] = EffectSpec(
                    name=str(effect_name),
                    kind=str(config.get('kind', 'solid')),
                    color=str(config.get('color', 'diag_neutral')),
                    color_a=str(config.get('color_a', config.get('color', 'diag_neutral'))),
                    color_b=str(config.get('color_b', config.get('color', 'diag_neutral'))),
                    period_s=float(config.get('period_s', 2.0)),
                    hz=float(config.get('hz', 2.0)),
                    speed=float(config.get('speed', 0.6)),
                    min_period_s=float(config.get('min_period_s', 0.35)),
                    max_period_s=float(config.get('max_period_s', 1.8)),
                )

        if effects:
            return effects

        return {
            'idle': EffectSpec(name='idle', kind='pulse', color='blue_soft', period_s=2.2),
            'diagnostic': EffectSpec(name='diagnostic', kind='pulse', color='diag_neutral', period_s=1.0),
            'search_scan': EffectSpec(
                name='search_scan',
                kind='scan',
                color_a='turquoise',
                color_b='violet',
                speed=0.8,
            ),
            'approach': EffectSpec(
                name='approach',
                kind='pulse',
                color='amber',
                min_period_s=0.25,
                max_period_s=1.8,
            ),
            'align': EffectSpec(name='align', kind='scan', color_a='white', color_b='cyan', speed=0.45),
            'drop': EffectSpec(name='drop', kind='solid', color='green'),
            'handover_ready': EffectSpec(name='handover_ready', kind='solid', color='gold'),
            'terminal_error': EffectSpec(name='terminal_error', kind='blink', color='red', hz=2.5),
            'estop': EffectSpec(name='estop', kind='strobe', color='red'),
        }

    def _load_state_map(self) -> dict[str, str]:
        """Wczytuje mapowanie stan FSM -> nazwa efektu."""
        raw = self.get_parameter('state_map').value
        state_map: dict[str, str] = {}
        if isinstance(raw, dict):
            for state_name, effect_name in raw.items():
                state_map[str(state_name).strip().lower()] = str(effect_name)

        if state_map:
            return state_map

        return {
            'idle': 'idle',
            'search': 'search_scan',
            'navigate': 'search_scan',
            'approach': 'approach',
            'approach_person': 'approach',
            'align': 'align',
            'drop': 'drop',
            'handover_ready': 'handover_ready',
            'terminal': 'terminal_error',
            'error': 'terminal_error',
            'failed': 'terminal_error',
        }

    def _build_output_adapter(self) -> DisplayOutputAdapter:
        """Buduje adapter zgodnie z parametrem output_mode."""
        output_mode = str(self.get_parameter('output_mode').value)
        if output_mode == 'vendor_bridge':
            return VendorBridgeDisplayAdapter(
                self,
                str(self.get_parameter('vendor_output_topic').value),
            )
        return RosTopicDisplayAdapter(self, str(self.get_parameter('output_topic').value))

    def _on_mission_state(self, msg: MissionState) -> None:
        """Callback bieżącego stanu misji."""
        self.last_mission_state = msg
        self.last_mission_state_time = self.get_clock().now()

    def _on_mission_target(self, msg: MissionTarget) -> None:
        """Callback celu misji; dane opcjonalne dla efektów kontekstowych."""
        self.last_mission_target = msg

    def _on_tracked_target(self, msg: TrackedTarget) -> None:
        """Callback ostatniego tracku; wykorzystywany m.in. przy podejściu."""
        self.last_tracked_target = msg

    def _on_estop(self, msg: Bool) -> None:
        """Aktualizuje najwyższy priorytet bezpieczeństwa (E-STOP)."""
        self.estop_active = bool(msg.data)

    def _on_safety_warning(self, msg: Bool) -> None:
        """Aktualizuje flagę ostrzeżenia safety."""
        self.safety_warning_active = bool(msg.data)

    def _mission_state_fresh(self) -> bool:
        """Sprawdza czy ostatni MissionState nie jest przeterminowany."""
        if self.last_mission_state is None:
            return False
        elapsed = (self.get_clock().now() - self.last_mission_state_time).nanoseconds / 1e9
        return elapsed <= float(self.get_parameter('mission_timeout_s').value)

    def _normalize_mission_state(self, state: str) -> str:
        """Normalizuje nazwy stanów, aby mapowanie YAML było stabilne."""
        cleaned = state.strip().lower()
        if cleaned.startswith('approach'):
            return 'approach'
        return cleaned

    def _resolve_effect(self) -> ResolvedEffect:
        """Rozstrzyga efekt zgodnie z priorytetami: E-STOP > safety > mission > idle/fallback."""
        if self.estop_active:
            return ResolvedEffect('estop', 100, self._effect_by_name(str(self.get_parameter('estop_effect').value)))

        if self.safety_warning_active:
            return ResolvedEffect(
                'safety_warning',
                80,
                self._effect_by_name(str(self.get_parameter('safety_warning_effect').value)),
            )

        if self._mission_state_fresh() and self.last_mission_state is not None:
            state_key = self._normalize_mission_state(self.last_mission_state.state)
            effect_name = self.state_map.get(state_key)
            if self.last_mission_state.is_terminal and effect_name is None:
                effect_name = 'terminal_error'
            if effect_name:
                return ResolvedEffect('mission', 50, self._effect_by_name(effect_name))

        if self.last_mission_state is None:
            return ResolvedEffect('diagnostic_fallback', 20, self._effect_by_name(str(self.get_parameter('fallback_effect').value)))

        return ResolvedEffect('idle_fallback', 10, self._effect_by_name(str(self.get_parameter('idle_effect').value)))

    def _effect_by_name(self, effect_name: str) -> EffectSpec:
        """Zwraca efekt po nazwie lub diagnostyczny fallback gdy wpis nie istnieje."""
        if effect_name in self.effects:
            return self.effects[effect_name]
        self.get_logger().warning(f'Unknown effect "{effect_name}", using diagnostic fallback.')
        return self.effects.get('diagnostic', EffectSpec(name='diagnostic', kind='pulse', color='diag_neutral'))

    def _color(self, name: str) -> Color:
        """Pobiera kolor z palety lub zwraca neutralny szary przy błędzie konfiguracji."""
        return self.palette.get(name, self.palette.get('diag_neutral', (0.7, 0.7, 0.7)))

    def _distance_hint(self) -> float | None:
        """Estymuje dystans celu dla dynamicznego przyspieszania efektu podejścia."""
        if self.last_mission_target is not None:
            z = float(self.last_mission_target.position.z)
            if z > 0.01:
                return z
        if self.last_tracked_target is not None:
            z = float(self.last_tracked_target.position.z)
            if z > 0.01:
                return z
        return None

    def _render_effect(self, effect: EffectSpec, t: float) -> Color:
        """Renderuje klatkę RGB dla konkretnego typu efektu."""
        if effect.kind == 'solid':
            return self.engine.solid(self._color(effect.color), t)

        if effect.kind == 'pulse':
            period_s = effect.period_s
            # Dla stanu approach modulujemy okres względem dystansu celu.
            if effect.name == 'approach':
                distance = self._distance_hint()
                if distance is not None:
                    ratio = max(0.0, min(1.0, distance / 2.5))
                    period_s = effect.min_period_s + (effect.max_period_s - effect.min_period_s) * ratio
            return self.engine.pulse(self._color(effect.color), t, period_s=period_s)

        if effect.kind == 'scan':
            return self.engine.scan(self._color(effect.color_a), self._color(effect.color_b), t, speed=effect.speed)

        if effect.kind == 'blink':
            return self.engine.blink(self._color(effect.color), t, hz=effect.hz)

        if effect.kind == 'strobe':
            return self.engine.strobe(self._color(effect.color), t)

        self.get_logger().warning(f'Unsupported effect kind "{effect.kind}"; using solid fallback.')
        return self.engine.solid(self._color('diag_neutral'), t)

    def _on_tick(self) -> None:
        """Generuje i publikuje kolejną klatkę efektu LED."""
        t = self.get_clock().now().nanoseconds / 1e9
        resolved = self._resolve_effect()
        color = self._render_effect(resolved.spec, t)
        brightness = float(self.get_parameter('brightness').value)
        tag = f'{resolved.source}:{resolved.spec.name}'
        self.output_adapter.send_frame(color, brightness, tag)


def main(args: list[str] | None = None) -> None:
    """Punkt wejścia dla skryptu uruchamiającego node."""
    rclpy.init(args=args)
    node = HeadDisplayStateNode()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
