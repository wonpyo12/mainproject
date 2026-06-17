"""
robot.launch.py — RPi4에서 실행 (가벼운 노드 묶음)
  - camera_node  : 웹캠 → ROS 압축 이미지
  - motor_node   : 소켓 수신 → ESP32 시리얼

사용 예:
  ros2 launch robocart_follower robot.launch.py
"""
import os
from launch import LaunchDescription
from launch_ros.actions import Node
from ament_index_python.packages import get_package_share_directory


def generate_launch_description() -> LaunchDescription:
    pkg_share = get_package_share_directory("robocart_follower")
    params_file = os.path.join(pkg_share, "config", "follower_params.yaml")

    return LaunchDescription([
        Node(
            package="robocart_follower",
            executable="camera_node",
            name="camera_node",
            output="screen",
            parameters=[params_file],
        ),
        Node(
            package="robocart_follower",
            executable="motor_node",
            name="motor_node",
            output="screen",
            parameters=[params_file],
        ),
    ])
