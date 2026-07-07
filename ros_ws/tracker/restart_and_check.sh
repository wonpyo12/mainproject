#!/usr/bin/env bash
# tracker 완전 재시작 + annotated 발행 검증 (WSL)
set +e
source /opt/ros/humble/setup.bash
source ~/robocart_ws/install/setup.bash
export ROS_DOMAIN_ID=0

pkill -9 -f "robocart_tracker.tracker_node" 2>/dev/null
sleep 2

cd ~/robocart_run
nohup python3 -u -m robocart_tracker.tracker_node > /tmp/tracker.log 2>&1 &
TPID=$!
echo "[restart] tracker PID=$TPID  — 모델 로드 대기"

# 최대 70초 동안 annotated 발행 여부 확인
for i in $(seq 1 14); do
  sleep 5
  R=$(timeout 4 ros2 topic hz /image/annotated 2>/dev/null | grep -oE 'average rate: [0-9.]+' | head -1)
  if [ -n "$R" ]; then
    echo "[restart] OK 인식화면 발행: $R"
    C=$(timeout 4 ros2 topic hz /image/compressed 2>/dev/null | grep -oE 'average rate: [0-9.]+' | head -1)
    echo "[restart] 카메라 수신: $C"
    exit 0
  fi
done
echo "[restart] FAIL — 70초 내 annotated 미발행 (프레임 수신 안됨)"
echo "[restart] tracker 로그 마지막:"
tail -5 /tmp/tracker.log
exit 1
