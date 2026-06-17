#!/bin/bash
# RoboCart 사람 추종 사전 점검 스크립트 (로봇/RPi4 에서 실행)
# 사용법: bash check_follower.sh

PASS=0; FAIL=0; WARN=0
ok()   { echo "  [OK]   $1"; PASS=$((PASS+1)); }
bad()  { echo "  [FAIL] $1"; FAIL=$((FAIL+1)); }
warn() { echo "  [WARN] $1"; WARN=$((WARN+1)); }

echo "=== RoboCart 사람 추종 사전 점검 ==="

echo "[1] USB 장치"
ls /dev/video0 >/dev/null 2>&1 && ok "/dev/video0 (웹캠)" \
  || bad "웹캠 미인식 — USB 연결 확인"
ls /dev/ttyUSB0 >/dev/null 2>&1 && ok "/dev/ttyUSB0 (ESP32)" \
  || { ls /dev/ttyACM0 >/dev/null 2>&1 && warn "ESP32가 /dev/ttyACM0 — YAML의 serial_port 수정 필요" \
       || bad "ESP32 미인식 — USB/펌웨어 확인"; }

echo "[2] 시리얼/비디오 권한"
groups | grep -q dialout && ok "dialout 그룹 포함" \
  || bad "dialout 없음 → sudo usermod -aG dialout \$USER 후 재로그인"
groups | grep -q video   && ok "video 그룹 포함" \
  || warn "video 없음 → sudo usermod -aG video \$USER 후 재로그인 (권장)"

echo "[3] Python 패키지"
python3 -c "import cv2"     2>/dev/null && ok "OpenCV"   || bad "OpenCV 없음 → sudo apt install python3-opencv"
python3 -c "import rclpy"   2>/dev/null && ok "rclpy"    || bad "rclpy 없음 → ROS2 환경 확인"
python3 -c "import serial"  2>/dev/null && ok "pyserial" || bad "pyserial 없음 → sudo apt install python3-serial"

echo "[4] ROS 환경"
[ -n "$ROS_DOMAIN_ID" ] && ok "ROS_DOMAIN_ID=$ROS_DOMAIN_ID" \
  || bad "ROS_DOMAIN_ID 미설정 → export ROS_DOMAIN_ID=30"
[ -f ~/ros_ws/install/robocart_follower/share/robocart_follower/package.xml ] \
  && ok "robocart_follower 빌드됨" \
  || warn "robocart_follower 미빌드 → cd ~/ros_ws && colcon build --packages-select robocart_follower"

echo "[5] 네트워크"
ip=$(hostname -I | awk '{print $1}')
[ -n "$ip" ] && ok "IP: $(hostname -I)" || bad "네트워크 미연결"
ss -ltn 2>/dev/null | grep -q ':9999 ' && warn "포트 9999 이미 사용 중 — 다른 motor_node 가 떠 있을 수 있음" \
  || ok "포트 9999 사용 가능"

echo "===================================="
echo "결과: 통과 $PASS / 경고 $WARN / 실패 $FAIL"
if [ $FAIL -eq 0 ]; then
  echo ">> 실행 가능: ros2 launch robocart_follower robot.launch.py"
else
  echo ">> 실패 항목을 해결한 뒤 다시 실행하세요"
  exit 1
fi
