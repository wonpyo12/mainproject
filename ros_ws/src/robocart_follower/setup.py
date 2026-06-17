from setuptools import find_packages, setup

package_name = 'robocart_follower'

setup(
    name=package_name,
    version='0.1.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages',
            ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        ('share/' + package_name + '/launch', [
            'launch/robot.launch.py',
            'launch/remote.launch.py',
        ]),
        ('share/' + package_name + '/config', [
            'config/follower_params.yaml',
        ]),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='HJ',
    maintainer_email='jinnnih@gmail.com',
    description='RoboCart 사람 추종 시스템 (분산 처리)',
    license='Apache-2.0',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            # RPi4에서 실행 (가벼움)
            'camera_node = robocart_follower.camera_node:main',
            'motor_node  = robocart_follower.motor_node:main',
            # VM에서 실행 (무거움)
            'inference_node = robocart_follower.inference_node:main',
        ],
    },
)
