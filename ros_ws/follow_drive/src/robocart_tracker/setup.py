from setuptools import setup

package_name = 'robocart_tracker'

setup(
    name=package_name,
    version='0.1.0',
    packages=[package_name],
    data_files=[
        ('share/ament_index/resource_index/packages',
            ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='robocart',
    maintainer_email='msk7676@naver.com',
    description='노트북 추적 노드: 영상 구독 → smart_cart_core → cmd_vel + servo 발행.',
    license='MIT',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            'tracker_node = robocart_tracker.tracker_node:main',
        ],
    },
)
