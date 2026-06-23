from setuptools import find_packages, setup

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
        ]),
        ('share/' + package_name + '/config', [
            'config/explore_params.yaml',
        ]),
        ('share/' + package_name + '/scripts', [
            'scripts/save_map.sh',
        ]),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='HJ',
    maintainer_email='jinnnih@gmail.com',
    description='RoboCart 자율 매핑 / 네비게이션',
    license='Apache-2.0',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [],
    },
)
