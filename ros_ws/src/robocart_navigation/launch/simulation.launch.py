"""
simulation.launch.py — Gazebo Sim (Ignition Fortress) + TurtleBot4 시뮬 환경

ARM64 환경에서 Gazebo Classic 부재 → TurtleBot4 + 새 Gazebo Sim으로 대체.
TB3 Burger와 토픽 인터페이스 거의 동일 (/scan, /odom, /cmd_vel).
SLAM 알고리즘 코드는 그대로 적용 가능.

사용:
  ros2 launch robocart_navigation simulation.launch.py
  ros2 launch robocart_navigation simulation.launch.py world:=depot   # 다른 월드
  ros2 launch robocart_navigation simulation.launch.py rviz:=true

월드 옵션:
  warehouse (기본) — 마트 비슷한 매장 환경
  depot           — 창고
  maze            — 좁은 통로 다수
"""
from launch import LaunchDescription
from launch.actions import IncludeLaunchDescription, DeclareLaunchArgument
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from ament_index_python.packages import get_package_share_directory
import os


def generate_launch_description() -> LaunchDescription:
    world = LaunchConfiguration("world")
    rviz = LaunchConfiguration("rviz")
    x = LaunchConfiguration("x")
    y = LaunchConfiguration("y")

    pkg_tb4_ign = get_package_share_directory("turtlebot4_ignition_bringup")

    tb4_ignition = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(pkg_tb4_ign, "launch", "turtlebot4_ignition.launch.py")
        ),
        launch_arguments={
            "world": world,
            "rviz": rviz,
            "x": x,
            "y": y,
            "model": "standard",
            "use_sim_time": "true",
        }.items(),
    )

    return LaunchDescription([
        DeclareLaunchArgument(
            "world", default_value="warehouse",
            description="Gazebo Sim 월드 (warehouse / depot / maze)"
        ),
        DeclareLaunchArgument(
            "rviz", default_value="false",
            description="RViz 동시 실행 여부 (자율매핑 launch가 별도 RViz 띄움)"
        ),
        DeclareLaunchArgument(
            "x", default_value="0.0", description="초기 x 좌표"
        ),
        DeclareLaunchArgument(
            "y", default_value="0.0", description="초기 y 좌표"
        ),
        tb4_ignition,
    ])
