"""
remote.launch.py — VM에서 실행 (무거운 노드 + 시각화)
  - inference_node : 이미지 구독 → YOLO + 매칭 → 소켓 송신
  - rviz2          : /robocart/image_overlay/compressed 시각화

사용 예:
  ros2 launch robocart_follower remote.launch.py
  ros2 launch robocart_follower remote.launch.py rviz:=false   # RViz 비활성화
"""
import os
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.conditions import IfCondition
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from ament_index_python.packages import get_package_share_directory


def generate_launch_description() -> LaunchDescription:
    pkg_share = get_package_share_directory("robocart_follower")
    params_file = os.path.join(pkg_share, "config", "follower_params.yaml")
    rviz_config = os.path.join(pkg_share, "config", "follower.rviz")

    return LaunchDescription([
        DeclareLaunchArgument("rviz", default_value="true",
                              description="RViz 자동 실행 여부"),
        Node(
            package="robocart_follower",
            executable="inference_node",
            name="inference_node",
            output="screen",
            parameters=[params_file],
        ),
        Node(
            package="rviz2",
            executable="rviz2",
            name="rviz2",
            arguments=["-d", rviz_config],
            output="screen",
            condition=IfCondition(LaunchConfiguration("rviz")),
        ),
    ])
