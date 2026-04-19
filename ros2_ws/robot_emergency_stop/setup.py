from setuptools import find_packages, setup

# [AI-CHANGE | 2026-04-19 20:47 UTC | v0.125]
# CO ZMIENIONO: Dodano konfigurację instalacji nowego pakietu `robot_emergency_stop` z pojedynczym entry pointem węzła.
# DLACZEGO: Użytkownik wymaga jednego, prostego punktu uruchomieniowego bez sprzężenia z innymi pakietami projektu.
# JAK TO DZIAŁA: `console_scripts` rejestruje komendę `emergency_stop_node`, która uruchamia funkcję `main` z dedykowanego modułu.
# TODO: Dodać automatyczną walidację metadanych pakietu (linting setup.py) w CI.
package_name = 'robot_emergency_stop'

setup(
    name=package_name,
    version='0.1.0',
    packages=find_packages(include=[package_name, package_name + '.*']),
    data_files=[
        ('share/ament_index/resource_index/packages', ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml', 'README.md']),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='Your Name',
    maintainer_email='you@example.com',
    description='ROS2 emergency stop package with topic/service interface.',
    license='Apache-2.0',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            'emergency_stop_node = robot_emergency_stop.emergency_stop_node:main',
        ],
    },
)
