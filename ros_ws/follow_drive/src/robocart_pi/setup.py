import os
from glob import glob

from setuptools import setup

package_name = 'robocart_pi'

setup(
    name=package_name,
    version='0.1.0',
    packages=[package_name],
    data_files=[
        ('share/ament_index/resource_index/packages',
            ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        (os.path.join('share', package_name, 'launch'),
            glob('launch/*.launch.py')),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='robocart',
    maintainer_email='msk7676@naver.com',
    description='라즈베리파이 노드: 카메라 송출 / ESP32 서보 / cmd_vel watchdog 중계.',
    license='MIT',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            'camera_node = robocart_pi.camera_node:main',
            'esp32_motor_node = robocart_pi.esp32_motor_node:main',
            'cmd_vel_relay_node = robocart_pi.cmd_vel_relay_node:main',
        ],
    },
)
