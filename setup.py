from setuptools import find_packages, setup

package_name = 'g1_light_tracking'

setup(
    name=package_name,
    version='0.3.0',
    packages=find_packages(),
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='Mateusz Pomianek',
    maintainer_email='matpomianek@gmail.com',
    description='Production-leaning ROS 2 Python skeleton with custom messages, OpenCV, YOLOv8n, QR, AprilTag hooks, temporal target tracking, and QR-to-parcel binding.',
    license='Apache-2.0',
)
