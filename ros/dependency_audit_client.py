from __future__ import annotations

# [AI-CHANGE | 2026-04-21 05:40 UTC | v0.165]
# CO ZMIENIONO: Dodano moduł kompatybilności `ros/dependency_audit_client.py`, który eksportuje
#               klienta audytu zależności i modele statusów z pakietu `robot_mission_control`.
# DLACZEGO: Część narzędzi ROS odwołuje się do ścieżki `ros/dependency_audit_client.py`; ten plik
#           zapewnia stabilny punkt importu bez dublowania logiki i bez ryzyka rozjazdu kontraktu.
# JAK TO DZIAŁA: Moduł re-eksportuje `DependencyStatusClient` oraz typy raportu, które już obsługują
#                statusy OK/MISSING/WRONG_VERSION/UNKNOWN, a przy braku odpowiedzi zwracają UNKNOWN.
# TODO: Dodać test integracyjny importu dla ścieżki `ros/dependency_audit_client.py` w CI.

from robot_mission_control.ros.dependency_audit_client import (  # noqa: F401
    DependencyAuditClient,
    DependencyRequirement,
    DependencyStatusClient,
    DependencyStatusCode,
    DependencyStatusContract,
    DependencyStatusItem,
    DependencyStatusReport,
)

__all__ = [
    "DependencyAuditClient",
    "DependencyRequirement",
    "DependencyStatusClient",
    "DependencyStatusCode",
    "DependencyStatusContract",
    "DependencyStatusItem",
    "DependencyStatusReport",
]
