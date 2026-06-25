from setuptools import find_packages, setup
from glob import glob

package_name = 'robocart_navigation'

setup(
    name=package_name,
    version='0.1.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages',
            ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        ('share/' + package_name + '/launch', [
            'launch/autonomous_mapping.launch.py',
            'launch/wait_return.launch.py',
            'launch/simulation.launch.py',
        ]),
        ('share/' + package_name + '/config', [
            'config/explore_params.yaml',
            'config/return_params.yaml',
        ]),
        ('share/' + package_name + '/scripts', [
            'scripts/save_map.sh',
        ]),
        ('share/' + package_name + '/worlds', glob('worlds/*.sdf')),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='HJ',
    maintainer_email='jinnnih@gmail.com',
    description='RoboCart 자율 매핑 / 네비게이션',
    license='Apache-2.0',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            'mode_controller        = robocart_navigation.mode_controller:main',
            'return_trigger_bridge  = robocart_navigation.return_trigger_bridge:main',
            'dock_pose_recorder     = robocart_navigation.dock_pose_recorder:main',
        ],
    },
)
