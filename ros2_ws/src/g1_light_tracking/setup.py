from setuptools import find_packages, setup

package_name = 'g1_light_tracking'

setup(
    name=package_name,
    version='0.4.4',
    packages=find_packages(),
    data_files=[
        ('share/ament_index/resource_index/packages', ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml', 'VERSION']),
        ('share/' + package_name + '/launch', [
            'launch/prod.launch.py',
            'launch/topdown_odom.launch.py',
        ]),
        ('share/' + package_name + '/config', [
            'config/perception.yaml',
            'config/localization.yaml',
            'config/tracking.yaml',
            'config/parcel_track.yaml',
            'config/mission.yaml',
            'config/control.yaml',
            'config/camera_calibration.yaml',
            'config/depth_mapper.yaml',
            'config/topdown_odom.yaml',
            'config/visual_slam.yaml',
        ]),
        ('share/' + package_name + '/msg', [
            'msg/Detection2D.msg',
            'msg/LocalizedTarget.msg',
            'msg/TrackedTarget.msg',
            'msg/ParcelTrackBinding.msg',
            'msg/ParcelTrack.msg',
            'msg/ParcelInfo.msg',
            'msg/MissionTarget.msg',
            'msg/MissionState.msg',
            'msg/DepthNavHint.msg',
        ]),
        ('share/' + package_name + '/docs', ['docs/index.html']),
        ('share/' + package_name + '/calibration', []),
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
