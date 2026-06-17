"""
remote.launch.py — VM에서 실행 (무거운 노드)
  - inference_node : 이미지 구독 → YOLO + 매칭 → 소켓 송신

사용 예:
  ros2 launch robocart_follower remote.launch.py
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
            executable="inference_node",
            name="inference_node",
            output="screen",
            parameters=[params_file],
        ),
    ])
