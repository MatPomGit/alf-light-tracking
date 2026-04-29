from __future__ import annotations

from pathlib import Path
import xml.etree.ElementTree as ET


# [AI-CHANGE | 2026-04-29 13:51 UTC | v0.333]
# CO ZMIENIONO: Dodano test poprawności XML dla manifestów `package.xml` w workspace ROS2.
# DLACZEGO: `colcon` i ament zatrzymują build na niepoprawnym XML, a błąd może powstać nawet w komentarzu,
#           zanim uruchomi się właściwa konfiguracja pakietu.
# JAK TO DZIAŁA: Test parsuje każdy manifest w `ros2_ws`, sprawdza obecność nazwy i typu buildu oraz wymusza
#                zgodność `robot_mission_control` z `ament_cmake` po scaleniu interfejsu Action.
# TODO: Rozszerzyć test o walidację zależności wymaganych przez `rosidl_generate_interfaces`.
def test_ros2_package_manifests_are_parseable_and_have_build_type() -> None:
    workspace_root = Path(__file__).resolve().parents[2]
    package_paths = sorted(workspace_root.glob("*/package.xml"))

    assert package_paths
    for package_path in package_paths:
        root = ET.parse(package_path).getroot()
        package_name = root.findtext("name")
        build_type = root.findtext("export/build_type")

        assert package_name
        assert build_type
        if package_name == "robot_mission_control":
            assert build_type == "ament_cmake"
