from __future__ import annotations

from datetime import datetime, timezone

from robot_mission_control.core import DataQuality, StateValue
from robot_mission_control.ui.operator_alerts import OperatorAlerts


# [AI-CHANGE | 2026-04-30 23:50 UTC | v0.201]
# CO ZMIENIONO: Dodano regresyjne testy cyklu raise/clear dla alertów mapowych, w tym regułę
#               wygaszania po kolejnych próbkach VALID oraz mapowanie priorytetów MAP_*.
# DLACZEGO: Musimy potwierdzić, że incydent mapy nie znika po pojedynczym VALID i że krytyczne
#           kody mapowe otrzymują odpowiedni severity zgodny z polityką bezpieczeństwa.
# JAK TO DZIAŁA: Testy najpierw podnoszą alert mapowy, potem podają serię VALID i sprawdzają,
#                że zamknięcie następuje dopiero po osiągnięciu progu clear-streak.
# TODO: Dodać scenariusz mieszany (VALID, potem ponowny błąd), który resetuje licznik wygaszania.
def test_map_alert_raise_and_clear_requires_two_valid_samples() -> None:
    registry = OperatorAlerts(valid_clear_streak=2)
    now = datetime(2026, 4, 30, 23, 50, tzinfo=timezone.utc)

    stale_item = StateValue(
        value="STALE",
        timestamp=now,
        source="map_tab",
        quality=DataQuality.STALE,
        reason_code="MAP_POSE_STALE",
    )
    registry.sync_from_snapshot({"map_data_quality": stale_item})
    active = registry.active_alerts()
    assert len(active) == 1
    assert active[0].code == "MAP_POSE_STALE"
    assert active[0].severity == "HIGH"
    assert registry.active_map_incidents_count() == 1

    valid_first = StateValue(
        value="VALID",
        timestamp=now.replace(second=1),
        source="map_tab",
        quality=DataQuality.VALID,
        reason_code=None,
    )
    registry.sync_from_snapshot({"map_data_quality": valid_first})
    assert len(registry.active_alerts()) == 1

    valid_second = StateValue(
        value="VALID",
        timestamp=now.replace(second=2),
        source="map_tab",
        quality=DataQuality.VALID,
        reason_code=None,
    )
    registry.sync_from_snapshot({"map_data_quality": valid_second})
    assert registry.active_alerts() == []
    assert registry.active_map_incidents_count() == 0


def test_map_tf_missing_is_critical_and_can_be_acknowledged() -> None:
    registry = OperatorAlerts(valid_clear_streak=2)
    now = datetime(2026, 4, 30, 23, 50, tzinfo=timezone.utc)

    tf_missing = StateValue(
        value=None,
        timestamp=now,
        source="map_tab",
        quality=DataQuality.UNAVAILABLE,
        reason_code="MAP_TF_MISSING",
    )
    registry.sync_from_snapshot({"map_tf_status": tf_missing})

    active = registry.active_alerts()
    assert len(active) == 1
    assert active[0].severity == "CRITICAL"
    assert active[0].code == "MAP_TF_MISSING"

    acknowledged = registry.ack_alert(alert_id=active[0].alert_id, operator_id="test_operator")
    assert acknowledged is not None
    assert acknowledged.acknowledged is True
    assert acknowledged.closed_at is None
