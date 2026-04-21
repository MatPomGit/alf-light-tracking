from setuptools import find_packages, setup

# [AI-CHANGE | 2026-04-21 12:10 UTC | v0.167]
# CO ZMIENIONO: Dodano `setup.py` wymagany przez `ament_python` dla budowania pakietu w workspace ROS2.
# DLACZEGO: Sam `pyproject.toml` nie gwarantował poprawnego wykrycia przez `colcon build` we wszystkich środowiskach ROS2.
# JAK TO DZIAŁA: Skrypt rejestruje pakiet Python, entrypoint node'a i instaluje pliki `launch/`, `config/` oraz manifest.
# TODO: Dodać test instalacyjny w CI sprawdzający obecność plików launch/config w install-space.
package_name = "robot_mission_control"

setup(
    name=package_name,
    version="0.1.0",
    packages=find_packages(include=[package_name, package_name + ".*"]),
    data_files=[
        ("share/ament_index/resource_index/packages", ["resource/" + package_name]),
        ("share/" + package_name, ["package.xml", "README.md"]),
        ("share/" + package_name + "/launch", ["launch/mission_control.launch.py"]),
        ("share/" + package_name + "/config", ["config/default.yaml"]),
    ],
    install_requires=["setuptools", "PyYAML>=6.0", "PySide6>=6.7"],
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
