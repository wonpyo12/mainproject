#!/bin/bash
# TurtleBot3 Bringup 사전 점검 스크립트 (로봇/RPi4에서 실행)
# 사용법: bash check_robot.sh

PASS=0; FAIL=0
ok()   { echo "  [OK]   $1"; PASS=$((PASS+1)); }
bad()  { echo "  [FAIL] $1"; FAIL=$((FAIL+1)); }

echo "=== TurtleBot3 Bringup 사전 점검 ==="

echo "[1] USB 장치"
[ -e /dev/ttyACM0 ] && ok "/dev/ttyACM0 (OpenCR)" || bad "OpenCR 미인식 — 보드 전원/케이블 확인"
[ -e /dev/ttyUSB0 ] && ok "/dev/ttyUSB0 (LiDAR)"  || bad "LiDAR 미인식 — USB 케이블 확인"

echo "[2] 시리얼 권한"
groups | grep -q dialout && ok "dialout 그룹 포함" \
  || bad "dialout 없음 → sudo usermod -aG dialout \$USER 후 재로그인"

echo "[3] 환경변수"
src="$HOME/.bashrc"
grep -q "TURTLEBOT3_MODEL=burger" $src && ok "TURTLEBOT3_MODEL=burger" || bad "TURTLEBOT3_MODEL 미설정"
grep -q "LDS_MODEL=LDS-02"        $src && ok "LDS_MODEL=LDS-02"        || bad "LDS_MODEL 미설정 (라이다 모델 불일치 주의!)"
grep -q "ROS_DOMAIN_ID=30"        $src && ok "ROS_DOMAIN_ID=30"        || bad "ROS_DOMAIN_ID 미설정"

echo "[4] 네트워크"
ip=$(hostname -I | awk '{print $1}')
[ -n "$ip" ] && ok "IP: $(hostname -I)" || bad "네트워크 미연결"

echo "===================================="
echo "결과: 통과 $PASS / 실패 $FAIL"
[ $FAIL -eq 0 ] && echo ">> bringup 실행 가능: ros2 launch turtlebot3_bringup robot.launch.py" \
  || echo ">> 실패 항목을 해결한 후 다시 실행하세요"
