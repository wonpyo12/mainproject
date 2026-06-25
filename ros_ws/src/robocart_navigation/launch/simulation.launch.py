"""
simulation.launch.py — Gazebo Sim (Ignition Fortress) + TurtleBot4 시뮬 환경

ARM64 환경에서 Gazebo Classic 부재 → TurtleBot4 + 새 Gazebo Sim으로 대체.
TB3 Burger와 토픽 인터페이스 거의 동일 (/scan, /odom, /cmd_vel).
SLAM 알고리즘 코드는 그대로 적용 가능.

⚠️ ARM64 + ogre2 렌더 엔진에서 Qt/QML 세그폴트 발생 → headless 권장.
   시각화는 RViz로 (cartographer launch에 포함됨).

사용:
  # 헤드리스 (권장, 안정적) — Gazebo GUI 없이 서버만, RViz로 시각화
  ros2 launch robocart_navigation simulation.launch.py headless:=true

  # GUI 시도 (불안정할 수 있음)
  ros2 launch robocart_navigation simulation.launch.py

  # 다른 월드 / 초기 위치
  ros2 launch robocart_navigation simulation.launch.py world:=warehouse x:=0 y:=0

월드 옵션:
  robocart_classroom (기본) — 연희직업전문학원 시연 공간 (커스텀)
  warehouse                 — TB4 기본 창고 월드
  depot, maze               — TB4 다른 월드
"""
import os
from launch import LaunchDescription
from launch.actions import IncludeLaunchDescription, DeclareLaunchArgument, SetEnvironmentVariable
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration, PythonExpression
from ament_index_python.packages import get_package_share_directory


def generate_launch_description() -> LaunchDescription:
    world = LaunchConfiguration("world")
    rviz = LaunchConfiguration("rviz")
    x = LaunchConfiguration("x")
    y = LaunchConfiguration("y")
    yaw = LaunchConfiguration("yaw")
    headless = LaunchConfiguration("headless")

    pkg_tb4_ign = get_package_share_directory("turtlebot4_ignition_bringup")
    pkg_nav = get_package_share_directory("robocart_navigation")
    worlds_dir = os.path.join(pkg_nav, "worlds")

    existing_path = os.environ.get("GZ_SIM_RESOURCE_PATH", "")
    new_path = (
        f"{worlds_dir}{os.pathsep}{existing_path}" if existing_path else worlds_dir
    )
    set_resource_path = SetEnvironmentVariable(
        name="GZ_SIM_RESOURCE_PATH", value=new_path
    )
    set_legacy_path = SetEnvironmentVariable(
        name="IGN_GAZEBO_RESOURCE_PATH", value=new_path
    )

    # headless=true → '-s -r' (서버만 + 자동 시작), GUI 비활성화
    gz_args = PythonExpression([
        "'-s -r' if '", headless, "' == 'true' else ''"
    ])

    tb4_ignition = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(pkg_tb4_ign, "launch", "turtlebot4_ignition.launch.py")
        ),
        launch_arguments={
            "world": world,
            "rviz": rviz,
            "x": x,
            "y": y,
            "yaw": yaw,
            "model": "standard",
            "use_sim_time": "true",
            "gz_args": gz_args,
        }.items(),
    )

    return LaunchDescription([
        DeclareLaunchArgument(
            "world", default_value="robocart_classroom",
            description="Gazebo Sim 월드 (robocart_classroom / warehouse / depot / maze)"
        ),
        DeclareLaunchArgument(
            "rviz", default_value="false",
            description="RViz 동시 실행 (자율매핑 launch가 별도 RViz 띄움)"
        ),
        DeclareLaunchArgument(
            "headless", default_value="false",
            description="true면 Gazebo GUI 비활성 (서버만 + 자동 시작) — ARM64 안정성 ↑"
        ),
        DeclareLaunchArgument(
            "x", default_value="0.0", description="초기 x 좌표"
        ),
        DeclareLaunchArgument(
            "y", default_value="-1.5", description="초기 y 좌표 (도킹 스테이션)"
        ),
        DeclareLaunchArgument(
            "yaw", default_value="1.5708", description="초기 yaw (rad, 기본: 사물함 방향)"
        ),
        set_resource_path,
        set_legacy_path,
        tb4_ignition,
    ])
