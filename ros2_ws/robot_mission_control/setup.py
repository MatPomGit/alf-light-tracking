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
# [AI-CHANGE | 2026-04-24 10:48 UTC | v0.201]
# CO ZMIENIONO: Uogólniono loader zależności tak, aby czytać osobne pliki dla runtime core oraz extras UI.
# DLACZEGO: Rozdzielenie pakietów umożliwia uruchamianie testów backendowych bez instalacji PySide6.
# JAK TO DZIAŁA: Funkcja przyjmuje nazwę pliku, filtruje puste linie/komentarze i zwraca listę do `install_requires` lub `extras_require`.
# TODO: Dodać walidację wykrywającą cykliczne odwołania `-r` przy przyszłej rozbudowie plików requirements.
def _read_requirements(filename: str) -> list[str]:
    requirements_path = Path(__file__).resolve().parent / filename
    if not requirements_path.exists():
        return []

    parsed: list[str] = []
    for line in requirements_path.read_text(encoding="utf-8").splitlines():
        normalized = line.strip()
        if not normalized or normalized.startswith("#"):
            continue
        parsed.append(normalized)
    return parsed


setup(
    name=package_name,
    version="0.1.0",
    packages=find_packages(include=[package_name, package_name + ".*"]),
    data_files=[
        ("share/ament_index/resource_index/packages", ["resource/" + package_name]),
        ("share/" + package_name, ["package.xml", "README.md", "requirements.txt", "requirements-core.txt", "requirements-ui.txt"]),
        ("share/" + package_name + "/launch", ["launch/mission_control.launch.py"]),
        ("share/" + package_name + "/config", ["config/default.yaml", "config/action_backend.yaml"]),
    ],
# [AI-CHANGE | 2026-04-24 10:48 UTC | v0.201]
    # CO ZMIENIONO: Bazowe zależności instalacyjne przeniesiono do `requirements-core.txt` i dodano extra `ui`.
    # DLACZEGO: Instalacja pod testy core/ROS nie powinna wymagać bibliotek GUI.
    # JAK TO DZIAŁA: `install_requires` ładuje tylko backend, a `extras_require["ui"]` dodaje PySide6 dla aplikacji desktopowej.
    # TODO: Dodać extra `ci` agregujące zestaw headless + narzędzia raportowania pokrycia.
    install_requires=["setuptools", *_read_requirements("requirements-core.txt")],
    extras_require={"ui": _read_requirements("requirements-ui.txt")},
    # [AI-CHANGE | 2026-04-23 14:44 UTC | v0.189]
    # CO ZMIENIONO: Dodano `package_data` i `include_package_data`, aby dystrybuować asset logo UI.
    # DLACZEGO: Bez jawnego dołączenia plików nie-pythonowych logo nie trafi do instalacji pakietu ROS2.
    # JAK TO DZIAŁA: Wzorzec `ui/assets/*.svg` trafia do wheel/install-space i może być wczytany przez MainWindow.
    # TODO: Rozszerzyć reguły o PNG/SVG oraz walidację obecności wszystkich assetów podczas builda.
    package_data={package_name: ["ui/assets/*.svg"]},
    include_package_data=True,
    zip_safe=False,
    maintainer="Mission Control Team",
    maintainer_email="team@example.com",
    description="Desktop mission control app for robot operations.",
    license="Proprietary",
    tests_require=["pytest"],
    entry_points={
        "console_scripts": [
            "robot_mission_control = robot_mission_control.app.entrypoint:main",
            # [AI-CHANGE | 2026-04-25 08:51 UTC | v0.202]
            # CO ZMIENIONO: Dodano entrypoint serwera testowego Action do uruchomień E2E przez `ros2 run`.
            # DLACZEGO: Test runtime ma obejmować realny przepływ goal/feedback/result/cancel bez mockowania klienta.
            # JAK TO DZIAŁA: `ros2 run robot_mission_control mission_step_action_test_server` startuje lokalny ActionServer
            #                obsługujący kontrakt `MissionStep` na endpointcie `/mission_control/execute_step`.
            # TODO: Dodać drugi entrypoint scenariusza awaryjnego (forced abort), aby walidować ścieżki błędów UI.
            "mission_step_action_test_server = robot_mission_control.e2e.mission_step_action_test_server:main",
        ],
    },
)
