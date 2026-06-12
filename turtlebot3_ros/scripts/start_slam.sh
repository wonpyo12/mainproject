#!/bin/bash
# SLAM(cartographer) 실행 스크립트 (Remote PC/VM에서 실행)
# 사용법: bash start_slam.sh
# 전제: 로봇에서 bringup이 이미 실행 중이어야 함

source /opt/ros/humble/setup.bash
[ -f ~/turtlebot3_ws/install/setup.bash ] && source ~/turtlebot3_ws/install/setup.bash
export TURTLEBOT3_MODEL=burger
export ROS_DOMAIN_ID=30

# 로봇 토픽 수신 확인
echo "[start_slam] 로봇 /scan 토픽 확인 중..."
if ! timeout 5 ros2 topic list 2>/dev/null | grep -q "^/scan$"; then
    echo "[start_slam] /scan 토픽이 없습니다. 로봇 bringup을 먼저 실행하세요."
    echo "  ssh ubuntu@<로봇IP> 후: ros2 launch turtlebot3_bringup robot.launch.py"
    exit 1
fi

echo "[start_slam] /scan 확인됨 — cartographer + RViz 시작"
echo "[start_slam] 별도 터미널에서 teleop 실행: ros2 run turtlebot3_teleop teleop_keyboard"
echo "[start_slam] 지도 저장(주행 완료 후): ros2 run nav2_map_server map_saver_cli -f ~/map"
exec ros2 launch turtlebot3_cartographer cartographer.launch.py
