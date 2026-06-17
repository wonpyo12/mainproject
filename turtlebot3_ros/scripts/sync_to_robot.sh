#!/bin/bash
# robocart_follower 패키지를 RPi4 로 동기화
# 사용법: bash sync_to_robot.sh [robot_ip]
#   기본 IP: 192.168.0.67  (--test SSID 기준)

ROBOT_IP="${1:-192.168.0.67}"
ROBOT_USER="ubuntu"
LOCAL_PKG="$(cd "$(dirname "$0")/.." && pwd)/../ros_ws/src/robocart_follower/"
REMOTE_PKG="~/ros_ws/src/robocart_follower/"

if [ ! -d "$LOCAL_PKG" ]; then
  echo "[FAIL] 로컬 패키지 없음: $LOCAL_PKG"
  exit 1
fi

echo "=== robocart_follower 동기화 ==="
echo "  로컬  : $LOCAL_PKG"
echo "  원격  : $ROBOT_USER@$ROBOT_IP:$REMOTE_PKG"

ping -c 1 -W 2 "$ROBOT_IP" >/dev/null 2>&1 || {
  echo "[FAIL] $ROBOT_IP 에 ping 실패 — 로봇 전원/네트워크 확인"
  exit 1
}

# 빌드 산출물(__pycache__, build, install) 제외하고 동기화
rsync -avz --delete \
  --exclude='__pycache__/' \
  --exclude='*.pyc' \
  --exclude='build/' \
  --exclude='install/' \
  --exclude='log/' \
  "$LOCAL_PKG" "$ROBOT_USER@$ROBOT_IP:$REMOTE_PKG"

if [ $? -eq 0 ]; then
  echo "[OK] 동기화 완료"
  echo ">> 다음 단계 (RPi4 SSH 후):"
  echo "     cd ~/ros_ws && colcon build --packages-select robocart_follower"
  echo "     source install/setup.bash"
  echo "     ros2 launch robocart_follower robot.launch.py"
else
  echo "[FAIL] rsync 실패"
  exit 1
fi
