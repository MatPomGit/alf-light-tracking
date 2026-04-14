from setuptools import find_packages, setup
from pathlib import Path

package_name = 'g1_light_tracking'
version = Path('VERSION').read_text(encoding='utf-8').strip() if Path('VERSION').exists() else '0.4.0'

setup(
    name=package_name,
    version=version,
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages', ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml', 'VERSION']),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='Mateusz Pomianek',
    maintainer_email='matpomianek@gmail.com',
    description='ROS 2 hybrid package with Python nodes for perception, tracking, navigation, depth support and visual SLAM.',
    license='Apache-2.0',
    tests_require=['pytest'],
)
