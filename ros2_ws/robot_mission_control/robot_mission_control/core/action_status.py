from __future__ import annotations

from enum import Enum


# [AI-CHANGE | 2026-04-21 17:42 UTC | v0.178]
# CO ZMIENIONO: Dodano wspólną semantykę statusów akcji dla warstwy ROS transport oraz UI/StateStore.
# DLACZEGO: Ujednolicenie eliminuje mieszanie nazw transportowych i domenowych oraz stabilizuje logikę widoku.
# JAK TO DZIAŁA: `ActionStatusLabel` jest źródłem prawdy dla etykiet domenowych, a
#                `ACTION_STATUS_FROM_GOAL_STATUS_CODE` tłumaczy kody `action_msgs/msg/GoalStatus` 0-6.
# TODO: Rozważyć osobny status `NO_DATA` dla przypadków, gdy status jest semantycznie nieznany, ale transport aktywny.
class ActionStatusLabel(str, Enum):
    UNKNOWN = "UNKNOWN"
    ACCEPTED = "ACCEPTED"
    RUNNING = "RUNNING"
    CANCEL_REQUESTED = "CANCEL_REQUESTED"
    SUCCEEDED = "SUCCEEDED"
    CANCELED = "CANCELED"
    ABORTED = "ABORTED"


ACTION_STATUS_FROM_GOAL_STATUS_CODE: dict[int, ActionStatusLabel] = {
    0: ActionStatusLabel.UNKNOWN,
    1: ActionStatusLabel.ACCEPTED,
    2: ActionStatusLabel.RUNNING,
    3: ActionStatusLabel.CANCEL_REQUESTED,
    4: ActionStatusLabel.SUCCEEDED,
    5: ActionStatusLabel.CANCELED,
    6: ActionStatusLabel.ABORTED,
}
