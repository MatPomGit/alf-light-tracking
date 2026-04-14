from setuptools import find_packages, setup
from pathlib import Path

package_name = 'g1_light_tracking'

def files_in(rel_dir):
    p = Path(rel_dir)
    if not p.exists():
        return []
    return [str(x) for x in sorted(p.iterdir()) if x.is_file()]

version = Path('VERSION').read_text(encoding='utf-8').strip() if Path('VERSION').exists() else '0.4.0'

setup(
    name=package_name,
    version=version,
    packages=find_packages(),
    data_files=[
        ('share/ament_index/resource_index/packages', ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml', 'VERSION']),
        ('share/' + package_name + '/launch', files_in('launch')),
        ('share/' + package_name + '/config', files_in('config')),
        ('share/' + package_name + '/msg', files_in('msg')),
        ('share/' + package_name + '/docs', files_in('docs')),
    ],
    install_requires=[
        'setuptools',
        'numpy',
        'opencv-python',
    ],
    extras_require={
        'standalone': [
            'ultralytics',
            'pyzbar',
            'pupil-apriltags',
        ],
        'full': [
            'ultralytics',
            'pyzbar',
            'pupil-apriltags',
        ],
    },
    zip_safe=True,
    maintainer='Mateusz Pomianek',
    maintainer_email='matpomianek@gmail.com',
    description='ROS 2 hybrid package with ament_cmake and Python nodes for perception, tracking, navigation, depth support and visual SLAM.',
    license='Apache-2.0',
)
