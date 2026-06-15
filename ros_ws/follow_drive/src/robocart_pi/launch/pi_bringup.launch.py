#!/usr/bin/env python3
"""
[라즈베리파이] 통합 실행 런치

  camera_node          카메라 → /image/compressed
  esp32_motor_node     /robocart/servo → ESP32 시리얼
  cmd_vel_relay_node   /robocart/cmd_vel → /cmd_vel (워치독)
  turtlebot3 robot.launch.py  OpenCR 브링업 (바퀴/IMU/LDS)  ← with_tb3:=true 일 때

실행:
  ros2 launch robocart_pi pi_bringup.launch.py
  # 터틀봇 브링업을 별도 터미널에서 따로 돌리고 싶으면:
  ros2 launch robocart_pi pi_bringup.launch.py with_tb3:=false
"""
import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.conditions import IfCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    esp32_port = LaunchConfiguration('esp32_port')
    esp32_baud = LaunchConfiguration('esp32_baud')
    camera_device = LaunchConfiguration('camera_device')
    with_tb3 = LaunchConfiguration('with_tb3')

    tb3_bringup = get_package_share_directory('turtlebot3_bringup')

    return LaunchDescription([
        DeclareLaunchArgument('esp32_port', default_value='/dev/ttyUSB0'),
        DeclareLaunchArgument('esp32_baud', default_value='9600'),
        DeclareLaunchArgument('camera_device', default_value='0'),
        DeclareLaunchArgument('with_tb3', default_value='true',
                              description='turtlebot3 robot.launch.py 동시 실행 여부'),

        Node(
            package='robocart_pi', executable='camera_node',
            name='camera_node', output='screen',
            parameters=[{'device': camera_device}],
        ),
        Node(
            package='robocart_pi', executable='esp32_motor_node',
            name='esp32_motor_node', output='screen',
            parameters=[{'port': esp32_port, 'baud': esp32_baud}],
        ),
        Node(
            package='robocart_pi', executable='cmd_vel_relay_node',
            name='cmd_vel_relay_node', output='screen',
        ),

        IncludeLaunchDescription(
            PythonLaunchDescriptionSource(
                os.path.join(tb3_bringup, 'launch', 'robot.launch.py')),
            condition=IfCondition(with_tb3),
        ),
    ])
