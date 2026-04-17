from setuptools import find_packages, setup

package_name = 'g1_light_tracking'

setup(
    name=package_name,
    version='0.1.0',
    packages=find_packages(include=[package_name, package_name + '.*']),
    data_files=[
        ('share/ament_index/resource_index/packages', ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        (
            'share/' + package_name + '/launch',
            ['launch/light_tracking_stack.launch.py', 'launch/light_tracking_turtlesim.launch.py'],
        ),
        (
            'share/' + package_name + '/config',
            ['config/perception.yaml', 'config/control.yaml', 'config/bridge.yaml'],
        ),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='Your Name',
    maintainer_email='you@example.com',
    description='Single-package ROS2 stack for Unitree G1 light tracking using JSON messages.',
    license='Apache-2.0',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            'd435i_node = g1_light_tracking.d435i_node:main',
            'light_spot_detector_node = g1_light_tracking.light_spot_detector_node:main',
            'g1_light_follower_node = g1_light_tracking.g1_light_follower_node:main',
            'unitree_cmd_vel_bridge_node = g1_light_tracking.unitree_cmd_vel_bridge_node:main',
            'arm_skill_bridge_node = g1_light_tracking.arm_skill_bridge_node:main',
            'csv_detection_replay_node = g1_light_tracking.csv_detection_replay_node:main',
            'turtlesim_cmd_vel_bridge_node = g1_light_tracking.turtlesim_cmd_vel_bridge_node:main',
        ],
    },
)
