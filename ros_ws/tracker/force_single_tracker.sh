#!/usr/bin/env bash
# 모든 tracker 인스턴스를 확실히 종료하고 정확히 1개만 실행
source /opt/ros/humble/setup.bash
source ~/robocart_ws/install/setup.bash
export ROS_DOMAIN_ID=0

# 0이 될 때까지 반복 종료 (pkill 자기매칭 회피 위해 PID 직접 kill)
for round in 1 2 3 4 5; do
  PIDS=$(pgrep -f "robocart_tracker.tracker_node")
  [ -z "$PIDS" ] && break
  for p in $PIDS; do kill -9 "$p" 2>/dev/null; done
  sleep 2
done

N=$(pgrep -f "robocart_tracker.tracker_node" | wc -l)
echo "[clean] 정리 후 tracker 수: $N"

# 정확히 1개 시작
cd ~/robocart_run
nohup python3 -u -m robocart_tracker.tracker_node > /tmp/tracker.log 2>&1 &
echo "[clean] 새 tracker PID=$!"

# annotated 발행 확인
for i in 1 2 3 4 5 6 7 8 9 10 11 12; do
  sleep 5
  R=$(timeout 4 ros2 topic hz /image/annotated 2>/dev/null | grep -oE 'average rate: [0-9.]+' | head -1)
  if [ -n "$R" ]; then
    echo "[clean] OK 단일 tracker 발행: $R"
    echo "[clean] tracker 수: $(pgrep -f robocart_tracker.tracker_node | wc -l)"
    exit 0
  fi
done
echo "[clean] FAIL annotated 미발행"
exit 1
