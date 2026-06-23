"""
autonomous_mapping.launch.py — 자율 매핑 통합 실행

구성 (한 launch로 3개 노드 묶음):
  1) turtlebot3_cartographer  : SLAM (지도 생성)
  2) nav2_bringup navigation   : 로컬 경로 계획 + 컨트롤 (explore_lite 의존성)
  3) explore_lite              : 프론티어 탐색 (어디로 갈지 결정)

전제:
  로봇 bringup이 이미 실행 중이어야 함
    실물 — ssh ubuntu@192.168.0.67 → ros2 launch turtlebot3_bringup robot.launch.py

사용:
  ros2 launch robocart_navigation autonomous_mapping.launch.py
"""
import os
from launch import LaunchDescription
from launch.actions import IncludeLaunchDescription, DeclareLaunchArgument
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from ament_index_python.packages import get_package_share_directory


def generate_launch_description() -> LaunchDescription:
    use_sim_time = LaunchConfiguration("use_sim_time")

    pkg_nav = get_package_share_directory("robocart_navigation")
    pkg_cartographer = get_package_share_directory("turtlebot3_cartographer")
    pkg_nav2 = get_package_share_directory("nav2_bringup")

    explore_params = os.path.join(pkg_nav, "config", "explore_params.yaml")

    cartographer = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(pkg_cartographer, "launch", "cartographer.launch.py")
        ),
        launch_arguments={"use_sim_time": use_sim_time}.items(),
    )

    nav2_navigation = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(pkg_nav2, "launch", "navigation_launch.py")
        ),
        launch_arguments={"use_sim_time": use_sim_time}.items(),
    )

    explore_node = Node(
        package="explore_lite",
        executable="explore",
        name="explore_node",
        output="screen",
        parameters=[explore_params, {"use_sim_time": use_sim_time}],
    )

    return LaunchDescription([
        DeclareLaunchArgument(
            "use_sim_time",
            default_value="false",
            description="실물 로봇은 false, 시뮬은 true",
        ),
        cartographer,
        nav2_navigation,
        explore_node,
    ])
