from pathlib import Path

from setuptools import find_packages, setup

# [AI-CHANGE | 2026-04-21 12:10 UTC | v0.167]
# CO ZMIENIONO: Dodano `setup.py` wymagany przez `ament_python` dla budowania pakietu w workspace ROS2.
# DLACZEGO: Sam `pyproject.toml` nie gwarantował poprawnego wykrycia przez `colcon build` we wszystkich środowiskach ROS2.
# JAK TO DZIAŁA: Skrypt rejestruje pakiet Python, entrypoint node'a i instaluje pliki `launch/`, `config/` oraz manifest.
# TODO: Dodać test instalacyjny w CI sprawdzający obecność plików launch/config w install-space.
package_name = "robot_mission_control"


# [AI-CHANGE | 2026-04-21 10:19 UTC | v0.168]
# CO ZMIENIONO: Dodano odczyt zależności z `requirements.txt` i dołączenie tego pliku do artefaktów pakietu.
# DLACZEGO: Jedno źródło prawdy dla zależności minimalizuje ryzyko rozjazdu między pip i instalacją przez ROS2.
# JAK TO DZIAŁA: Funkcja `_read_requirements` filtruje komentarze/puste linie, a wynik trafia do `install_requires`.
# TODO: Rozdzielić zależności GUI i headless na extras, aby ułatwić testy bez środowiska graficznego.
def _read_requirements() -> list[str]:
    requirements_path = Path(__file__).resolve().parent / "requirements.txt"
    if not requirements_path.exists():
        return ["setuptools"]

    parsed: list[str] = []
    for line in requirements_path.read_text(encoding="utf-8").splitlines():
        normalized = line.strip()
        if not normalized or normalized.startswith("#"):
            continue
        parsed.append(normalized)
    return ["setuptools", *parsed]


setup(
    name=package_name,
    version="0.1.0",
    packages=find_packages(include=[package_name, package_name + ".*"]),
    data_files=[
        ("share/ament_index/resource_index/packages", ["resource/" + package_name]),
        ("share/" + package_name, ["package.xml", "README.md", "requirements.txt"]),
        ("share/" + package_name + "/launch", ["launch/mission_control.launch.py"]),
        ("share/" + package_name + "/config", ["config/default.yaml"]),
    ],
    install_requires=_read_requirements(),
    zip_safe=False,
    maintainer="Mission Control Team",
    maintainer_email="team@example.com",
    description="Desktop mission control app for robot operations.",
    license="Proprietary",
    tests_require=["pytest"],
    entry_points={
        "console_scripts": [
            "robot_mission_control = robot_mission_control.app.entrypoint:main",
        ],
    },
)
