"""Advanced Terminal UI monitor for the g1_light_tracking pipeline.

Features
--------
- live dashboard for detections, tracks, mission, depth hint, and cmd_vel
- topic freshness with text histograms and estimated rates
- colored alarms with severity and retained alarm history
- event log for operational visibility
- health score and KPI panel
- freeze/unfreeze screen state for inspection
- track sorting modes (distance/confidence/age)
- help screen and runtime key hints
- mini trends for forward clearance and cmd_vel
- snapshot export to text and JSON

Keyboard
--------
q : quit
a : all/dashboard
d : detections
t : tracks
m : mission/depth
c : cmd_vel
s : status/rates
l : alarms log
e : event log
h : help
f : freeze/unfreeze
o : cycle track sort mode
r : clear alarm/event history
x : export text snapshot to /tmp/g1_tui_snapshot.txt
j : export JSON snapshot to /tmp/g1_tui_snapshot.json
"""

from __future__ import annotations

import curses
import json
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Deque, Dict, List, Optional, Tuple

import rclpy
from geometry_msgs.msg import Twist
from rclpy.node import Node

from g1_light_tracking.msg import (
    DepthNavHint,
    Detection2D,
    MissionState,
    MissionTarget,
    TrackedTarget,
)


class Severity(str, Enum):
    INFO = "INFO"
    WARN = "WARN"
    ALARM = "ALARM"


class TrackSortMode(str, Enum):
    DISTANCE = "distance"
    CONFIDENCE = "confidence"
    AGE = "age"


@dataclass
class TopicHeartbeat:
    name: str
    last_time: float = 0.0
    count: int = 0
    samples: Deque[float] = field(default_factory=lambda: deque(maxlen=120))

    def tick(self) -> None:
        now = time.time()
        self.last_time = now
        self.count += 1
        self.samples.append(now)

    def age(self) -> float:
        if self.last_time <= 0.0:
            return 9999.0
        return time.time() - self.last_time

    def hz(self, window_sec: float = 5.0) -> float:
        if len(self.samples) < 2:
            return 0.0
        now = time.time()
        pts = [t for t in self.samples if now - t <= window_sec]
        if len(pts) < 2:
            return 0.0
        dt = pts[-1] - pts[0]
        if dt <= 1e-6:
            return 0.0
        return float(len(pts) - 1) / dt


@dataclass
class DetectionView:
    stamp_sec: float
    target_type: str
    class_name: str
    confidence: float
    center_u: float
    center_v: float
    payload: str
    color_label: str


@dataclass
class TrackView:
    stamp_sec: float
    track_id: str
    target_type: str
    class_name: str
    confidence: float
    x: float
    y: float
    z: float
    age_sec: float
    missed_frames: int
    confirmed: bool
    payload: str


@dataclass
class MissionStateView:
    state: str = "-"
    previous_state: str = "-"
    reason: str = "-"
    active_parcel_box_track_id: str = "-"
    active_shipment_id: str = "-"
    active_target_type: str = "-"
    active_target_mode: str = "-"
    has_active_parcel: bool = False
    has_drop_target: bool = False
    is_terminal: bool = False
    confidence: float = 0.0
    stamp_sec: float = 0.0


@dataclass
class MissionTargetView:
    mode: str = "-"
    zone_mode: str = "-"
    target_type: str = "-"
    class_name: str = "-"
    confidence: float = 0.0
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0
    color_label: str = "-"
    payload: str = "-"
    stamp_sec: float = 0.0


@dataclass
class DepthHintView:
    depth_available: bool = False
    obstacle_ahead: bool = False
    forward_clearance_m: float = 0.0
    left_clearance_m: float = 0.0
    right_clearance_m: float = 0.0
    recommended_linear_scale: float = 0.0
    recommended_angular_bias: float = 0.0
    source_method: str = "-"
    stamp_sec: float = 0.0


@dataclass
class CmdVelView:
    linear_x: float = 0.0
    linear_y: float = 0.0
    linear_z: float = 0.0
    angular_x: float = 0.0
    angular_y: float = 0.0
    angular_z: float = 0.0
    stamp_sec: float = 0.0


@dataclass
class AlarmEntry:
    stamp_sec: float
    severity: Severity
    code: str
    text: str


@dataclass
class EventEntry:
    stamp_sec: float
    text: str


@dataclass
class SamplePoint:
    stamp_sec: float
    value: float


@dataclass
class KPISnapshot:
    detections_rate_hz: float = 0.0
    tracks_rate_hz: float = 0.0
    cmd_vel_rate_hz: float = 0.0
    num_active_tracks: int = 0
    num_recent_detections: int = 0
    health_score: int = 100


@dataclass
class MonitorState:
    detections: Deque[DetectionView] = field(default_factory=lambda: deque(maxlen=50))
    tracks: Dict[str, TrackView] = field(default_factory=dict)
    mission_state: MissionStateView = field(default_factory=MissionStateView)
    mission_target: MissionTargetView = field(default_factory=MissionTargetView)
    depth_hint: DepthHintView = field(default_factory=DepthHintView)
    cmd_vel: CmdVelView = field(default_factory=CmdVelView)
    heartbeats: Dict[str, TopicHeartbeat] = field(default_factory=dict)
    selected_tab: str = "all"
    frozen: bool = False
    track_sort_mode: TrackSortMode = TrackSortMode.DISTANCE
    alarms_history: Deque[AlarmEntry] = field(default_factory=lambda: deque(maxlen=200))
    events_history: Deque[EventEntry] = field(default_factory=lambda: deque(maxlen=200))
    active_alarm_codes: Dict[str, AlarmEntry] = field(default_factory=dict)
    forward_clearance_history: Deque[SamplePoint] = field(default_factory=lambda: deque(maxlen=120))
    cmd_vel_linear_history: Deque[SamplePoint] = field(default_factory=lambda: deque(maxlen=120))
    cmd_vel_angular_history: Deque[SamplePoint] = field(default_factory=lambda: deque(maxlen=120))


class TuiMonitorNode(Node):
    def __init__(self) -> None:
        super().__init__("tui_monitor_node")

        self.declare_parameter("detections_topic", "/perception/detections")
        self.declare_parameter("tracks_topic", "/tracking/targets")
        self.declare_parameter("mission_state_topic", "/mission/state")
        self.declare_parameter("mission_target_topic", "/mission/target")
        self.declare_parameter("depth_hint_topic", "/navigation/depth_hint")
        self.declare_parameter("cmd_vel_topic", "/cmd_vel")
        self.declare_parameter("stale_after_sec", 1.5)
        self.declare_parameter("drop_tracks_after_sec", 3.0)
        self.declare_parameter("alarm_dedup_sec", 2.0)

        self.stale_after_sec = float(self.get_parameter("stale_after_sec").value)
        self.drop_tracks_after_sec = float(self.get_parameter("drop_tracks_after_sec").value)
        self.alarm_dedup_sec = float(self.get_parameter("alarm_dedup_sec").value)

        self.state = MonitorState()
        self.lock = threading.Lock()
        self._running = True
        self._last_screen_snapshot: Optional[MonitorState] = None
        self._last_alarm_emit: Dict[str, float] = {}

        self._register_heartbeat("detections")
        self._register_heartbeat("tracks")
        self._register_heartbeat("mission_state")
        self._register_heartbeat("mission_target")
        self._register_heartbeat("depth_hint")
        self._register_heartbeat("cmd_vel")

        self.create_subscription(
            Detection2D,
            str(self.get_parameter("detections_topic").value),
            self.on_detection,
            50,
        )
        self.create_subscription(
            TrackedTarget,
            str(self.get_parameter("tracks_topic").value),
            self.on_track,
            50,
        )
        self.create_subscription(
            MissionState,
            str(self.get_parameter("mission_state_topic").value),
            self.on_mission_state,
            20,
        )
        self.create_subscription(
            MissionTarget,
            str(self.get_parameter("mission_target_topic").value),
            self.on_mission_target,
            20,
        )
        self.create_subscription(
            DepthNavHint,
            str(self.get_parameter("depth_hint_topic").value),
            self.on_depth_hint,
            20,
        )
        self.create_subscription(
            Twist,
            str(self.get_parameter("cmd_vel_topic").value),
            self.on_cmd_vel,
            20,
        )

        self.create_timer(0.5, self.prune_tracks)
        self.create_timer(0.5, self.evaluate_alarms)

    def _register_heartbeat(self, name: str) -> None:
        self.state.heartbeats[name] = TopicHeartbeat(name=name)

    def _append_sample(self, series: Deque[SamplePoint], value: float) -> None:
        series.append(SamplePoint(stamp_sec=time.time(), value=float(value)))

    def _prune_series(self, series: Deque[SamplePoint], max_age_sec: float = 30.0) -> None:
        now = time.time()
        while series and (now - series[0].stamp_sec) > max_age_sec:
            series.popleft()

    def _event(self, text: str) -> None:
        self.state.events_history.appendleft(EventEntry(stamp_sec=time.time(), text=text))

    def _emit_alarm(self, code: str, severity: Severity, text: str) -> None:
        now = time.time()
        prev = self._last_alarm_emit.get(code, 0.0)
        if now - prev < self.alarm_dedup_sec:
            self.state.active_alarm_codes[code] = AlarmEntry(
                stamp_sec=now, severity=severity, code=code, text=text
            )
            return
        self._last_alarm_emit[code] = now
        entry = AlarmEntry(stamp_sec=now, severity=severity, code=code, text=text)
        self.state.alarms_history.appendleft(entry)
        self.state.active_alarm_codes[code] = entry
        self._event(f"{severity}: {text}")

    def _clear_alarm(self, code: str) -> None:
        self.state.active_alarm_codes.pop(code, None)

    @staticmethod
    def ros_time_to_sec(stamp) -> float:
        return float(stamp.sec) + float(stamp.nanosec) * 1e-9

    def on_detection(self, msg: Detection2D) -> None:
        with self.lock:
            self.state.heartbeats["detections"].tick()
            self.state.detections.appendleft(
                DetectionView(
                    stamp_sec=self.ros_time_to_sec(msg.stamp),
                    target_type=msg.target_type,
                    class_name=msg.class_name,
                    confidence=float(msg.confidence),
                    center_u=float(msg.center_u),
                    center_v=float(msg.center_v),
                    payload=msg.payload,
                    color_label=msg.color_label,
                )
            )

    def on_track(self, msg: TrackedTarget) -> None:
        with self.lock:
            self.state.heartbeats["tracks"].tick()
            self.state.tracks[msg.track_id] = TrackView(
                stamp_sec=self.ros_time_to_sec(msg.stamp),
                track_id=msg.track_id,
                target_type=msg.target_type,
                class_name=msg.class_name,
                confidence=float(msg.confidence),
                x=float(msg.position.x),
                y=float(msg.position.y),
                z=float(msg.position.z),
                age_sec=float(msg.age_sec),
                missed_frames=int(msg.missed_frames),
                confirmed=bool(msg.is_confirmed),
                payload=msg.payload,
            )

    def on_mission_state(self, msg: MissionState) -> None:
        with self.lock:
            self.state.heartbeats["mission_state"].tick()
            self.state.mission_state = MissionStateView(
                state=msg.state,
                previous_state=msg.previous_state,
                reason=msg.reason,
                active_parcel_box_track_id=msg.active_parcel_box_track_id,
                active_shipment_id=msg.active_shipment_id,
                active_target_type=msg.active_target_type,
                active_target_mode=msg.active_target_mode,
                has_active_parcel=bool(msg.has_active_parcel),
                has_drop_target=bool(msg.has_drop_target),
                is_terminal=bool(msg.is_terminal),
                confidence=float(msg.confidence),
                stamp_sec=self.ros_time_to_sec(msg.stamp),
            )

    def on_mission_target(self, msg: MissionTarget) -> None:
        with self.lock:
            self.state.heartbeats["mission_target"].tick()
            self.state.mission_target = MissionTargetView(
                mode=msg.mode,
                zone_mode=msg.zone_mode,
                target_type=msg.target_type,
                class_name=msg.class_name,
                confidence=float(msg.confidence),
                x=float(msg.position.x),
                y=float(msg.position.y),
                z=float(msg.position.z),
                color_label=msg.color_label,
                payload=msg.payload,
                stamp_sec=self.ros_time_to_sec(msg.stamp),
            )

    def on_depth_hint(self, msg: DepthNavHint) -> None:
        with self.lock:
            self.state.heartbeats["depth_hint"].tick()
            self.state.depth_hint = DepthHintView(
                depth_available=bool(msg.depth_available),
                obstacle_ahead=bool(msg.obstacle_ahead),
                forward_clearance_m=float(msg.forward_clearance_m),
                left_clearance_m=float(msg.left_clearance_m),
                right_clearance_m=float(msg.right_clearance_m),
                recommended_linear_scale=float(msg.recommended_linear_scale),
                recommended_angular_bias=float(msg.recommended_angular_bias),
                source_method=msg.source_method,
                stamp_sec=self.ros_time_to_sec(msg.stamp),
            )
            self._append_sample(self.state.forward_clearance_history, float(msg.forward_clearance_m))

    def on_cmd_vel(self, msg: Twist) -> None:
        with self.lock:
            self.state.heartbeats["cmd_vel"].tick()
            self.state.cmd_vel = CmdVelView(
                linear_x=float(msg.linear.x),
                linear_y=float(msg.linear.y),
                linear_z=float(msg.linear.z),
                angular_x=float(msg.angular.x),
                angular_y=float(msg.angular.y),
                angular_z=float(msg.angular.z),
                stamp_sec=time.time(),
            )
            self._append_sample(self.state.cmd_vel_linear_history, float(msg.linear.x))
            self._append_sample(self.state.cmd_vel_angular_history, float(msg.angular.z))

    def prune_tracks(self) -> None:
        now = time.time()
        with self.lock:
            self._prune_series(self.state.forward_clearance_history)
            self._prune_series(self.state.cmd_vel_linear_history)
            self._prune_series(self.state.cmd_vel_angular_history)
            stale = [
                track_id
                for track_id, track in self.state.tracks.items()
                if now - track.stamp_sec > self.drop_tracks_after_sec
            ]
            for track_id in stale:
                self.state.tracks.pop(track_id, None)
                self._event(f"Track dropped due to staleness: {track_id}")

    def evaluate_alarms(self) -> None:
        with self.lock:
            now = time.time()

            # topic freshness alarms
            for name, hb in self.state.heartbeats.items():
                age = hb.age()
                lost_code = f"topic_lost:{name}"
                stale_code = f"topic_stale:{name}"
                if age > self.stale_after_sec * 3.0:
                    self._emit_alarm(lost_code, Severity.ALARM, f"Topic lost: {name} age={age:.2f}s")
                    self._clear_alarm(stale_code)
                elif age > self.stale_after_sec:
                    self._emit_alarm(stale_code, Severity.WARN, f"Topic stale: {name} age={age:.2f}s")
                    self._clear_alarm(lost_code)
                else:
                    self._clear_alarm(lost_code)
                    self._clear_alarm(stale_code)

            # operational alarms
            if len(self.state.tracks) == 0:
                self._emit_alarm("tracks:none", Severity.WARN, "No active tracks")
            else:
                self._clear_alarm("tracks:none")

            dh = self.state.depth_hint
            cv = self.state.cmd_vel
            ms = self.state.mission_state
            mt = self.state.mission_target

            if dh.depth_available and dh.obstacle_ahead:
                self._emit_alarm(
                    "depth:obstacle",
                    Severity.ALARM,
                    f"Obstacle ahead front={dh.forward_clearance_m:.2f}m",
                )
            else:
                self._clear_alarm("depth:obstacle")

            if dh.depth_available and cv.linear_x > 0.0 and dh.forward_clearance_m <= 0.45:
                self._emit_alarm(
                    "cmd:unsafe_forward",
                    Severity.ALARM,
                    f"Forward cmd with low clearance v={cv.linear_x:.2f} front={dh.forward_clearance_m:.2f}",
                )
            else:
                self._clear_alarm("cmd:unsafe_forward")

            if mt.mode in ("idle", "-") and abs(cv.linear_x) > 0.01:
                self._emit_alarm(
                    "cmd:idle_mismatch",
                    Severity.ALARM,
                    "cmd_vel active while mission target is idle",
                )
            else:
                self._clear_alarm("cmd:idle_mismatch")

            if abs(cv.angular_z) > 0.8:
                self._emit_alarm(
                    "cmd:high_angular",
                    Severity.WARN,
                    f"High angular cmd {cv.angular_z:+.2f}",
                )
            else:
                self._clear_alarm("cmd:high_angular")

            if ms.is_terminal:
                self._emit_alarm(
                    "mission:terminal",
                    Severity.WARN,
                    f"Mission terminal state: {ms.state}",
                )
            else:
                self._clear_alarm("mission:terminal")

            # cleanup old active alarms that were not refreshed
            outdated = [
                code for code, entry in self.state.active_alarm_codes.items()
                if now - entry.stamp_sec > max(self.alarm_dedup_sec * 2.0, 5.0)
                and not code.startswith("topic_")
                and code not in {"tracks:none", "depth:obstacle", "cmd:unsafe_forward", "cmd:idle_mismatch", "cmd:high_angular", "mission:terminal"}
            ]
            for code in outdated:
                self._clear_alarm(code)

    def snapshot(self) -> MonitorState:
        with self.lock:
            snap = MonitorState()
            snap.detections = deque(self.state.detections, maxlen=50)
            snap.tracks = dict(self.state.tracks)
            snap.mission_state = self.state.mission_state
            snap.mission_target = self.state.mission_target
            snap.depth_hint = self.state.depth_hint
            snap.cmd_vel = self.state.cmd_vel
            snap.heartbeats = dict(self.state.heartbeats)
            snap.selected_tab = self.state.selected_tab
            snap.frozen = self.state.frozen
            snap.track_sort_mode = self.state.track_sort_mode
            snap.alarms_history = deque(self.state.alarms_history, maxlen=200)
            snap.events_history = deque(self.state.events_history, maxlen=200)
            snap.active_alarm_codes = dict(self.state.active_alarm_codes)
            snap.forward_clearance_history = deque(self.state.forward_clearance_history, maxlen=120)
            snap.cmd_vel_linear_history = deque(self.state.cmd_vel_linear_history, maxlen=120)
            snap.cmd_vel_angular_history = deque(self.state.cmd_vel_angular_history, maxlen=120)
            return snap

    def set_tab(self, tab: str) -> None:
        with self.lock:
            self.state.selected_tab = tab

    def toggle_freeze(self) -> None:
        with self.lock:
            self.state.frozen = not self.state.frozen
            self._event(f"{'Frozen' if self.state.frozen else 'Unfrozen'} screen updates")

    def clear_histories(self) -> None:
        with self.lock:
            self.state.alarms_history.clear()
            self.state.events_history.clear()
            self._event("Cleared alarm and event history")

    def cycle_track_sort_mode(self) -> None:
        with self.lock:
            modes = list(TrackSortMode)
            idx = modes.index(self.state.track_sort_mode)
            self.state.track_sort_mode = modes[(idx + 1) % len(modes)]
            self._event(f"Track sort mode -> {self.state.track_sort_mode.value}")

    def export_snapshot_json(self, path: str) -> str:
        snap = self.snapshot()
        payload = {
            "exported_at": time.time(),
            "selected_tab": snap.selected_tab,
            "frozen": snap.frozen,
            "track_sort_mode": snap.track_sort_mode.value,
            "mission_state": snap.mission_state.__dict__,
            "mission_target": snap.mission_target.__dict__,
            "depth_hint": snap.depth_hint.__dict__,
            "cmd_vel": snap.cmd_vel.__dict__,
            "heartbeats": {
                name: {
                    "last_time": hb.last_time,
                    "count": hb.count,
                    "age_sec": hb.age(),
                    "hz": hb.hz(),
                }
                for name, hb in snap.heartbeats.items()
            },
            "detections": [d.__dict__ for d in list(snap.detections)],
            "tracks": {k: v.__dict__ for k, v in snap.tracks.items()},
            "active_alarms": [
                {"stamp_sec": a.stamp_sec, "severity": a.severity.value, "code": a.code, "text": a.text}
                for a in snap.active_alarm_codes.values()
            ],
            "alarm_history": [
                {"stamp_sec": a.stamp_sec, "severity": a.severity.value, "code": a.code, "text": a.text}
                for a in list(snap.alarms_history)
            ],
            "event_history": [
                {"stamp_sec": e.stamp_sec, "text": e.text}
                for e in list(snap.events_history)
            ],
            "forward_clearance_history": [
                {"stamp_sec": s.stamp_sec, "value": s.value}
                for s in list(snap.forward_clearance_history)
            ],
            "cmd_vel_linear_history": [
                {"stamp_sec": s.stamp_sec, "value": s.value}
                for s in list(snap.cmd_vel_linear_history)
            ],
            "cmd_vel_angular_history": [
                {"stamp_sec": s.stamp_sec, "value": s.value}
                for s in list(snap.cmd_vel_angular_history)
            ],
        }
        Path(path).write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        with self.lock:
            self._event(f"Exported JSON snapshot -> {path}")
        return path

    def export_snapshot_text(self, path: str) -> str:
        snap = self.snapshot()
        lines = []
        lines.append("g1_light_tracking TUI snapshot")
        lines.append(f"exported_at={compact_ts(time.time())}")
        lines.append(f"tab={snap.selected_tab} frozen={snap.frozen} sort={snap.track_sort_mode.value}")
        lines.append("")
        lines.append("MISSION_STATE")
        for k, v in snap.mission_state.__dict__.items():
            lines.append(f"  {k}: {v}")
        lines.append("")
        lines.append("MISSION_TARGET")
        for k, v in snap.mission_target.__dict__.items():
            lines.append(f"  {k}: {v}")
        lines.append("")
        lines.append("DEPTH_HINT")
        for k, v in snap.depth_hint.__dict__.items():
            lines.append(f"  {k}: {v}")
        lines.append("")
        lines.append("CMD_VEL")
        for k, v in snap.cmd_vel.__dict__.items():
            lines.append(f"  {k}: {v}")
        lines.append("")
        lines.append("HEARTBEATS")
        for name, hb in snap.heartbeats.items():
            lines.append(f"  {name}: age={hb.age():.2f}s hz={hb.hz():.2f} count={hb.count}")
        lines.append("")
        lines.append("ACTIVE_ALARMS")
        for a in snap.active_alarm_codes.values():
            lines.append(f"  [{a.severity.value}] {compact_ts(a.stamp_sec)} {a.code} {a.text}")
        lines.append("")
        lines.append("TRACKS")
        for trk in sort_tracks(list(snap.tracks.values()), snap.track_sort_mode):
            lines.append(
                f"  {trk.track_id} {trk.target_type} conf={trk.confidence:.2f} "
                f"xyz=({trk.x:.2f},{trk.y:.2f},{trk.z:.2f}) age={trk.age_sec:.1f} "
                f"miss={trk.missed_frames} confirmed={trk.confirmed}"
            )
        lines.append("")
        lines.append("DETECTIONS")
        for det in list(snap.detections):
            lines.append(
                f"  {det.target_type}/{det.class_name} conf={det.confidence:.2f} "
                f"uv=({det.center_u:.1f},{det.center_v:.1f}) payload={det.payload}"
            )
        Path(path).write_text("\n".join(lines), encoding="utf-8")
        with self.lock:
            self._event(f"Exported text snapshot -> {path}")
        return path

    def stop(self) -> None:
        self._running = False


def safe_addstr(win, y: int, x: int, text: str, attr: int = 0) -> None:
    h, w = win.getmaxyx()
    if y < 0 or y >= h or x >= w:
        return
    try:
        win.addnstr(y, x, text, max(0, w - x - 1), attr)
    except curses.error:
        pass


def init_colors() -> None:
    if curses.has_colors():
        curses.start_color()
        curses.use_default_colors()
        curses.init_pair(1, curses.COLOR_GREEN, -1)    # OK
        curses.init_pair(2, curses.COLOR_YELLOW, -1)   # WARN
        curses.init_pair(3, curses.COLOR_RED, -1)      # ALARM
        curses.init_pair(4, curses.COLOR_CYAN, -1)     # INFO
        curses.init_pair(5, curses.COLOR_MAGENTA, -1)  # TITLE


def color_ok() -> int:
    return curses.color_pair(1) if curses.has_colors() else 0


def color_warn() -> int:
    return curses.color_pair(2) if curses.has_colors() else 0


def color_alarm() -> int:
    return curses.color_pair(3) if curses.has_colors() else 0


def color_info() -> int:
    return curses.color_pair(4) if curses.has_colors() else 0


def color_title() -> int:
    return curses.color_pair(5) if curses.has_colors() else 0


def severity_attr(sev: Severity) -> int:
    if sev == Severity.ALARM:
        return color_alarm()
    if sev == Severity.WARN:
        return color_warn()
    return color_info()


def heartbeat_status(age: float, stale_after_sec: float) -> str:
    if age > 999.0:
        return "NO DATA"
    if age <= stale_after_sec:
        return "OK"
    if age <= stale_after_sec * 3.0:
        return "STALE"
    return "LOST"


def heartbeat_attr(age: float, stale_after_sec: float) -> int:
    if age > 999.0:
        return color_alarm()
    if age <= stale_after_sec:
        return color_ok()
    if age <= stale_after_sec * 3.0:
        return color_warn()
    return color_alarm()


def compact_ts(ts: float) -> str:
    if ts <= 0.0:
        return "-"
    return time.strftime("%H:%M:%S", time.localtime(ts))


def make_bar(value: float, scale: float, width: int, full_char: str = "#") -> str:
    n = max(0, min(width, int(value * scale)))
    return full_char * n


def compute_kpis(snap: MonitorState, stale_after_sec: float) -> KPISnapshot:
    k = KPISnapshot()
    k.detections_rate_hz = snap.heartbeats.get("detections", TopicHeartbeat("d")).hz()
    k.tracks_rate_hz = snap.heartbeats.get("tracks", TopicHeartbeat("t")).hz()
    k.cmd_vel_rate_hz = snap.heartbeats.get("cmd_vel", TopicHeartbeat("c")).hz()
    k.num_active_tracks = len(snap.tracks)
    k.num_recent_detections = len(snap.detections)

    score = 100
    for hb in snap.heartbeats.values():
        age = hb.age()
        if age > stale_after_sec * 3.0:
            score -= 20
        elif age > stale_after_sec:
            score -= 8

    if snap.depth_hint.depth_available and snap.depth_hint.obstacle_ahead:
        score -= 12
    if len(snap.tracks) == 0:
        score -= 8
    if snap.mission_state.is_terminal:
        score -= 10
    if snap.mission_target.mode in ("idle", "-") and abs(snap.cmd_vel.linear_x) > 0.01:
        score -= 20

    k.health_score = max(0, min(100, score))
    return k


def draw_header(stdscr, title: str, tab: str, frozen: bool, sort_mode: TrackSortMode) -> None:
    flags = []
    if frozen:
        flags.append("FROZEN")
    flags.append(f"sort={sort_mode.value}")
    safe_addstr(stdscr, 0, 0, title, curses.A_BOLD | color_title())
    safe_addstr(
        stdscr,
        1,
        0,
        f"Tab: {tab} | {' | '.join(flags)} | q quit | h help | f freeze | o sort | r clear logs",
        color_info(),
    )


def draw_heartbeats(stdscr, snap: MonitorState, stale_after_sec: float, start_y: int) -> int:
    safe_addstr(stdscr, start_y, 0, "TOPIC STATUS / RATE", curses.A_BOLD)
    y = start_y + 1
    safe_addstr(stdscr, y, 0, "topic             status   age[s]   hz     histogram")
    y += 1

    for name, hb in snap.heartbeats.items():
        age = hb.age()
        hz = hb.hz()
        status = heartbeat_status(age, stale_after_sec)
        attr = heartbeat_attr(age, stale_after_sec)

        bar = make_bar(hz, scale=2.0, width=24)
        safe_addstr(
            stdscr,
            y,
            0,
            f"{name:<16} {status:<7} {age:>6.2f}  {hz:>5.2f}  ",
            attr,
        )
        safe_addstr(stdscr, y, 42, bar, attr)
        y += 1

    return y


def draw_kpis(stdscr, snap: MonitorState, stale_after_sec: float, start_y: int) -> int:
    k = compute_kpis(snap, stale_after_sec)
    health_attr = color_ok() if k.health_score >= 85 else color_warn() if k.health_score >= 60 else color_alarm()

    safe_addstr(stdscr, start_y, 0, "KPI / HEALTH", curses.A_BOLD)
    y = start_y + 1
    safe_addstr(
        stdscr,
        y,
        0,
        f"health={k.health_score:3d}  det_hz={k.detections_rate_hz:5.2f}  "
        f"trk_hz={k.tracks_rate_hz:5.2f}  cmd_hz={k.cmd_vel_rate_hz:5.2f}  "
        f"tracks={k.num_active_tracks:3d}  detections={k.num_recent_detections:3d}",
        health_attr,
    )
    y += 1
    safe_addstr(stdscr, y, 0, f"[{'#' * (k.health_score // 5):<20}]", health_attr)
    return y + 1


def draw_alarms(stdscr, snap: MonitorState, start_y: int, max_rows: int = 6) -> int:
    safe_addstr(stdscr, start_y, 0, "ACTIVE ALARMS", curses.A_BOLD)
    y = start_y + 1

    active = list(snap.active_alarm_codes.values())
    active.sort(key=lambda a: (a.severity != Severity.ALARM, -a.stamp_sec))

    if not active:
        safe_addstr(stdscr, y, 0, "OK: no active alarms", color_ok())
        return y + 1

    for alarm in active[:max_rows]:
        safe_addstr(
            stdscr,
            y,
            0,
            f"{alarm.severity:<5} {compact_ts(alarm.stamp_sec)} {alarm.text}",
            severity_attr(alarm.severity) | curses.A_BOLD,
        )
        y += 1

    return y


def draw_detections(stdscr, snap: MonitorState, start_y: int, max_rows: int) -> int:
    safe_addstr(stdscr, start_y, 0, "LATEST DETECTIONS", curses.A_BOLD)
    y = start_y + 1
    safe_addstr(stdscr, y, 0, "type         cls          conf    uv              color      payload")
    y += 1
    for det in list(snap.detections)[:max_rows]:
        attr = color_info() if det.confidence >= 0.75 else color_warn() if det.confidence < 0.35 else 0
        safe_addstr(
            stdscr,
            y,
            0,
            f"{det.target_type[:12]:<12} {det.class_name[:12]:<12} {det.confidence:>5.2f}  "
            f"({det.center_u:>6.1f},{det.center_v:>6.1f})  {det.color_label[:10]:<10}  {det.payload[:32]}",
            attr,
        )
        y += 1
    return y


def sort_tracks(tracks: List[TrackView], mode: TrackSortMode) -> List[TrackView]:
    if mode == TrackSortMode.CONFIDENCE:
        return sorted(tracks, key=lambda t: (not t.confirmed, -t.confidence, t.z))
    if mode == TrackSortMode.AGE:
        return sorted(tracks, key=lambda t: (not t.confirmed, -t.age_sec, t.z))
    return sorted(tracks, key=lambda t: (not t.confirmed, t.z, -t.confidence))


def draw_tracks(stdscr, snap: MonitorState, start_y: int, max_rows: int) -> int:
    safe_addstr(stdscr, start_y, 0, "ACTIVE TRACKS", curses.A_BOLD)
    y = start_y + 1
    safe_addstr(stdscr, y, 0, "track_id      type         conf   xyz[m]                    age   miss conf?")
    y += 1

    tracks = sort_tracks(list(snap.tracks.values()), snap.track_sort_mode)
    for trk in tracks[:max_rows]:
        attr = color_ok() if trk.confirmed else color_warn()
        if trk.missed_frames > 3:
            attr = color_alarm()
        safe_addstr(
            stdscr,
            y,
            0,
            f"{trk.track_id[:12]:<12} {trk.target_type[:12]:<12} {trk.confidence:>5.2f} "
            f"({trk.x:>6.2f},{trk.y:>6.2f},{trk.z:>6.2f})  {trk.age_sec:>5.1f}  "
            f"{trk.missed_frames:>4d}  {str(trk.confirmed):<5}",
            attr,
        )
        y += 1
    return y


def draw_mission(stdscr, snap: MonitorState, start_y: int) -> int:
    ms = snap.mission_state
    mt = snap.mission_target
    dh = snap.depth_hint

    state_attr = color_warn() if ms.is_terminal else color_ok() if ms.state not in ("-", "idle") else 0

    safe_addstr(stdscr, start_y, 0, "MISSION", curses.A_BOLD)
    y = start_y + 1
    safe_addstr(stdscr, y, 0, f"state={ms.state} prev={ms.previous_state} terminal={ms.is_terminal} reason={ms.reason[:40]}", state_attr)
    y += 1
    safe_addstr(
        stdscr,
        y,
        0,
        f"active_box={ms.active_parcel_box_track_id} shipment={ms.active_shipment_id} "
        f"target_type={ms.active_target_type} mode={ms.active_target_mode}",
    )
    y += 1
    safe_addstr(
        stdscr,
        y,
        0,
        f"mission_target mode={mt.mode} zone={mt.zone_mode} type={mt.target_type} cls={mt.class_name} "
        f"conf={mt.confidence:.2f} xyz=({mt.x:.2f},{mt.y:.2f},{mt.z:.2f})",
    )
    y += 1
    safe_addstr(stdscr, y, 0, f"payload={mt.payload[:70]}")
    y += 2

    depth_attr = color_ok()
    if dh.depth_available and dh.obstacle_ahead:
        depth_attr = color_alarm()
    elif dh.depth_available and dh.forward_clearance_m < 0.8:
        depth_attr = color_warn()

    safe_addstr(stdscr, y, 0, "DEPTH HINT", curses.A_BOLD)
    y += 1
    safe_addstr(
        stdscr,
        y,
        0,
        f"available={dh.depth_available} obstacle={dh.obstacle_ahead} "
        f"front={dh.forward_clearance_m:.2f} left={dh.left_clearance_m:.2f} right={dh.right_clearance_m:.2f}",
        depth_attr,
    )
    y += 1
    safe_addstr(
        stdscr,
        y,
        0,
        f"linear_scale={dh.recommended_linear_scale:.2f} angular_bias={dh.recommended_angular_bias:.2f} "
        f"src={dh.source_method}",
        depth_attr,
    )
    return y + 1


def draw_cmd_vel(stdscr, snap: MonitorState, start_y: int) -> int:
    cv = snap.cmd_vel
    safe_addstr(stdscr, start_y, 0, "CMD_VEL", curses.A_BOLD)
    y = start_y + 1

    lin_attr = color_ok() if abs(cv.linear_x) < 0.01 else color_info()
    ang_attr = color_ok() if abs(cv.angular_z) < 0.01 else color_info()
    if abs(cv.angular_z) > 0.8:
        ang_attr = color_warn()

    safe_addstr(
        stdscr,
        y,
        0,
        f"linear  x={cv.linear_x:+.3f} y={cv.linear_y:+.3f} z={cv.linear_z:+.3f}",
        lin_attr,
    )
    y += 1
    safe_addstr(
        stdscr,
        y,
        0,
        f"angular x={cv.angular_x:+.3f} y={cv.angular_y:+.3f} z={cv.angular_z:+.3f}",
        ang_attr,
    )
    y += 1

    lin_mag = abs(cv.linear_x)
    ang_mag = abs(cv.angular_z)
    safe_addstr(stdscr, y, 0, f"v [{'#' * min(20, int(lin_mag * 40)):<20}]")
    y += 1
    safe_addstr(stdscr, y, 0, f"w [{'#' * min(20, int(ang_mag * 20)):<20}]")
    return y + 1


def draw_alarm_history(stdscr, snap: MonitorState, start_y: int, max_rows: int) -> int:
    safe_addstr(stdscr, start_y, 0, "ALARM HISTORY", curses.A_BOLD)
    y = start_y + 1
    for entry in list(snap.alarms_history)[:max_rows]:
        safe_addstr(
            stdscr,
            y,
            0,
            f"{compact_ts(entry.stamp_sec)} {entry.severity:<5} {entry.text}",
            severity_attr(entry.severity),
        )
        y += 1
    return y


def draw_event_log(stdscr, snap: MonitorState, start_y: int, max_rows: int) -> int:
    safe_addstr(stdscr, start_y, 0, "EVENT LOG", curses.A_BOLD)
    y = start_y + 1
    for entry in list(snap.events_history)[:max_rows]:
        safe_addstr(stdscr, y, 0, f"{compact_ts(entry.stamp_sec)} {entry.text}", color_info())
        y += 1
    return y


def render_sparkline(values: List[float], width: int, min_value: Optional[float] = None, max_value: Optional[float] = None) -> str:
    ticks = " .:-=+*#%@"
    if not values:
        return "-" * max(1, width)
    if len(values) > width:
        step = len(values) / float(width)
        sampled = [values[int(i * step)] for i in range(width)]
    else:
        sampled = values[:]
        if len(sampled) < width:
            sampled = [sampled[0]] * (width - len(sampled)) + sampled
    lo = min_value if min_value is not None else min(sampled)
    hi = max_value if max_value is not None else max(sampled)
    if hi - lo < 1e-9:
        return ticks[0] * len(sampled)
    out = []
    for v in sampled:
        idx = int((v - lo) / (hi - lo) * (len(ticks) - 1))
        idx = max(0, min(len(ticks) - 1, idx))
        out.append(ticks[idx])
    return "".join(out)


def draw_trends(stdscr, snap: MonitorState, start_y: int, width: int = 48) -> int:
    safe_addstr(stdscr, start_y, 0, "MINI TRENDS", curses.A_BOLD)
    y = start_y + 1

    fc_vals = [s.value for s in list(snap.forward_clearance_history)]
    cv_lin_vals = [s.value for s in list(snap.cmd_vel_linear_history)]
    cv_ang_vals = [s.value for s in list(snap.cmd_vel_angular_history)]

    fc_last = fc_vals[-1] if fc_vals else 0.0
    cv_lin_last = cv_lin_vals[-1] if cv_lin_vals else 0.0
    cv_ang_last = cv_ang_vals[-1] if cv_ang_vals else 0.0

    fc_attr = color_alarm() if fc_vals and fc_last <= 0.45 else color_warn() if fc_vals and fc_last <= 0.8 else color_ok()
    safe_addstr(
        stdscr, y, 0,
        f"forward_clearance_m {fc_last:6.2f} |{render_sparkline(fc_vals, width, 0.0, max(1.5, max(fc_vals) if fc_vals else 1.5))}|",
        fc_attr
    )
    y += 1

    safe_addstr(
        stdscr, y, 0,
        f"cmd_vel.linear.x    {cv_lin_last:+6.2f} |{render_sparkline(cv_lin_vals, width, -0.2, 0.5)}|",
        color_info()
    )
    y += 1

    ang_attr = color_warn() if cv_ang_vals and abs(cv_ang_last) > 0.8 else color_info()
    safe_addstr(
        stdscr, y, 0,
        f"cmd_vel.angular.z   {cv_ang_last:+6.2f} |{render_sparkline(cv_ang_vals, width, -1.5, 1.5)}|",
        ang_attr
    )
    return y + 1


def draw_help(stdscr, start_y: int) -> int:
    safe_addstr(stdscr, start_y, 0, "HELP", curses.A_BOLD)
    lines = [
        "a dashboard   d detections   t tracks   m mission/depth   c cmd_vel",
        "s status/rates   l alarms log   e event log   h help",
        "f freeze/unfreeze current screen   o cycle track sort mode   r clear logs   q quit",
        "x export snapshot text   j export snapshot json",
        "Color semantics: green=healthy, yellow=warning, red=alarm, cyan=info/activity",
    ]
    y = start_y + 1
    for line in lines:
        safe_addstr(stdscr, y, 0, line)
        y += 1
    return y


def tui_loop(stdscr, node: TuiMonitorNode) -> None:
    curses.curs_set(0)
    stdscr.nodelay(True)
    stdscr.timeout(100)
    init_colors()

    frozen_snapshot: Optional[MonitorState] = None

    while rclpy.ok():
        live_snap = node.snapshot()
        if live_snap.frozen:
            if frozen_snapshot is None:
                frozen_snapshot = live_snap
            snap = frozen_snapshot
        else:
            frozen_snapshot = None
            snap = live_snap

        stdscr.erase()
        draw_header(stdscr, "g1_light_tracking TUI monitor+", snap.selected_tab, live_snap.frozen, snap.track_sort_mode)

        h, _ = stdscr.getmaxyx()
        y = 3

        if snap.selected_tab == "all":
            y = draw_kpis(stdscr, snap, node.stale_after_sec, y) + 1
            y = draw_heartbeats(stdscr, snap, node.stale_after_sec, y) + 1
            y = draw_alarms(stdscr, snap, y, max_rows=6) + 1
            y = draw_mission(stdscr, snap, y) + 1
            y = draw_cmd_vel(stdscr, snap, y) + 1
            y = draw_trends(stdscr, snap, y) + 1
            rem = max(4, h - y - 1)
            rows_each = max(3, rem // 2)
            y = draw_detections(stdscr, snap, y, rows_each) + 1
            draw_tracks(stdscr, snap, y, rows_each)
        elif snap.selected_tab == "detections":
            y = draw_kpis(stdscr, snap, node.stale_after_sec, y) + 1
            draw_detections(stdscr, snap, y, h - y - 2)
        elif snap.selected_tab == "tracks":
            y = draw_kpis(stdscr, snap, node.stale_after_sec, y) + 1
            draw_tracks(stdscr, snap, y, h - y - 2)
        elif snap.selected_tab == "mission":
            y = draw_heartbeats(stdscr, snap, node.stale_after_sec, y) + 1
            y = draw_alarms(stdscr, snap, y, max_rows=5) + 1
            y = draw_mission(stdscr, snap, y) + 1
            draw_trends(stdscr, snap, y)
        elif snap.selected_tab == "cmd_vel":
            y = draw_heartbeats(stdscr, snap, node.stale_after_sec, y) + 1
            y = draw_alarms(stdscr, snap, y, max_rows=5) + 1
            y = draw_cmd_vel(stdscr, snap, y) + 1
            draw_trends(stdscr, snap, y)
        elif snap.selected_tab == "status":
            y = draw_kpis(stdscr, snap, node.stale_after_sec, y) + 1
            y = draw_heartbeats(stdscr, snap, node.stale_after_sec, y) + 1
            y = draw_alarms(stdscr, snap, y, max_rows=10) + 1
            draw_trends(stdscr, snap, y)
        elif snap.selected_tab == "alarms":
            draw_alarm_history(stdscr, snap, y, h - y - 2)
        elif snap.selected_tab == "events":
            draw_event_log(stdscr, snap, y, h - y - 2)
        elif snap.selected_tab == "help":
            draw_help(stdscr, y)

        stdscr.refresh()

        key = stdscr.getch()
        if key == ord("q"):
            break
        if key == ord("a"):
            node.set_tab("all")
        elif key == ord("d"):
            node.set_tab("detections")
        elif key == ord("t"):
            node.set_tab("tracks")
        elif key == ord("m"):
            node.set_tab("mission")
        elif key == ord("c"):
            node.set_tab("cmd_vel")
        elif key == ord("s"):
            node.set_tab("status")
        elif key == ord("l"):
            node.set_tab("alarms")
        elif key == ord("e"):
            node.set_tab("events")
        elif key == ord("h"):
            node.set_tab("help")
        elif key == ord("f"):
            node.toggle_freeze()
        elif key == ord("o"):
            node.cycle_track_sort_mode()
        elif key == ord("r"):
            node.clear_histories()
        elif key == ord("x"):
            node.export_snapshot_text("/tmp/g1_tui_snapshot.txt")
        elif key == ord("j"):
            node.export_snapshot_json("/tmp/g1_tui_snapshot.json")

    node.stop()


def main(args=None) -> None:
    rclpy.init(args=args)
    node = TuiMonitorNode()

    executor = rclpy.executors.MultiThreadedExecutor()
    executor.add_node(node)

    spin_thread = threading.Thread(target=executor.spin, daemon=True)
    spin_thread.start()

    try:
        curses.wrapper(lambda stdscr: tui_loop(stdscr, node))
    finally:
        executor.shutdown()
        node.destroy_node()
        rclpy.shutdown()
        spin_thread.join(timeout=1.0)


if __name__ == "__main__":
    main()
