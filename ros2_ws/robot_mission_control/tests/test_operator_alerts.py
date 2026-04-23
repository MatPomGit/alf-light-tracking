from __future__ import annotations

from datetime import datetime, timezone

from robot_mission_control.core import DataQuality, StateValue
from robot_mission_control.ui.operator_alerts import OperatorAlerts


# [AI-CHANGE | 2026-04-23 16:30 UTC | v0.188]
# CO ZMIENIONO: Dodano testy rejestru `OperatorAlerts` dla scenariuszy:
#               publikacja, ACK operatora oraz automatyczne zamknięcie po powrocie do `VALID`.
# DLACZEGO: Mechanizm alertów ma być deterministyczny i zgodny z zasadą bezpieczeństwa
#           (nie zgłaszać fałszywego „OK” przed potwierdzonym stanem VALID).
# JAK TO DZIAŁA: Testy budują sztuczny snapshot StateStore i asertywnie sprawdzają aktywne alerty,
#                flagę ACK i `closed_at` po synchronizacji ze stanem poprawnym.
# TODO: Dodać test retencji historii i limitu liczby alertów po wdrożeniu polityki TTL.
def test_sync_creates_and_closes_alert_for_unavailable_then_valid_state() -> None:
    registry = OperatorAlerts()
    now = datetime(2026, 4, 23, 16, 30, tzinfo=timezone.utc)
    unavailable_item = StateValue(
        value=None,
        timestamp=now,
        source="test_source",
        quality=DataQuality.UNAVAILABLE,
        reason_code="missing_data",
    )
    registry.sync_from_snapshot({"ros_connection_status": unavailable_item})

    active = registry.active_alerts()
    assert len(active) == 1
    assert active[0].severity == "HIGH"
    assert active[0].code == "missing_data"

    valid_item = StateValue(
        value="CONNECTED",
        timestamp=now.replace(minute=31),
        source="test_source",
        quality=DataQuality.VALID,
        reason_code=None,
    )
    registry.sync_from_snapshot({"ros_connection_status": valid_item})
    assert registry.active_alerts() == []


def test_ack_marks_active_alert_without_closing_it() -> None:
    registry = OperatorAlerts()
    now = datetime(2026, 4, 23, 16, 30, tzinfo=timezone.utc)
    error_item = StateValue(
        value=None,
        timestamp=now,
        source="diagnostics",
        quality=DataQuality.ERROR,
        reason_code="bridge_error",
    )
    registry.sync_from_snapshot({"action_status": error_item})
    active = registry.active_alerts()
    assert len(active) == 1

    acknowledged = registry.ack_alert(alert_id=active[0].alert_id, operator_id="test_operator")
    assert acknowledged is not None
    assert acknowledged.acknowledged is True
    assert acknowledged.acknowledged_by == "test_operator"
    assert acknowledged.closed_at is None
