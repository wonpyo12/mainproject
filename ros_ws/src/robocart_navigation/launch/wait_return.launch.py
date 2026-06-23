"""
wait_return.launch.py — wait / return 모드 자율주행 launch

구성:
  1) nav2_bringup bringup    : map_server + AMCL + Nav2 (저장 지도 기반)
  2) mode_controller          : /robocart/return 수신 → NavigateToPose 호출

전제:
  - 자율매핑으로 미리 저장된 지도가 maps/ 아래에 있어야 함
    (없으면 autonomous_mapping.launch.py + save_map.sh 로 먼저 생성)
  - 로봇 bringup이 이미 실행 중 (실물 RPi 또는 시뮬)

사용:
  ros2 launch robocart_navigation wait_return.launch.py \\
      map:=$(ros2 pkg prefix robocart_navigation)/share/robocart_navigation/maps/store_v1/map.yaml

  # 복귀 트리거
  ros2 topic pub /robocart/return std_msgs/Empty {} --once

  # 복귀 취소 (제자리 정지)
  ros2 topic pub /robocart/wait std_msgs/Empty {} --once
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
    map_yaml = LaunchConfiguration("map")

    pkg_nav = get_package_share_directory("robocart_navigation")
    pkg_nav2 = get_package_share_directory("nav2_bringup")

    return_params = os.path.join(pkg_nav, "config", "return_params.yaml")

    nav2_bringup = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(pkg_nav2, "launch", "bringup_launch.py")
        ),
        launch_arguments={
            "use_sim_time": use_sim_time,
            "map": map_yaml,
            "slam": "False",
        }.items(),
    )

    mode_controller = Node(
        package="robocart_navigation",
        executable="mode_controller",
        name="mode_controller",
        output="screen",
        parameters=[return_params, {"use_sim_time": use_sim_time}],
    )

    return LaunchDescription([
        DeclareLaunchArgument(
            "use_sim_time", default_value="false",
            description="실물 로봇 false, 시뮬 true"
        ),
        DeclareLaunchArgument(
            "map", description="저장된 지도 yaml 경로 (필수)"
        ),
        nav2_bringup,
        mode_controller,
    ])
