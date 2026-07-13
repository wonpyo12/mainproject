#!/usr/bin/env bash
# 모든 tracker 확실히 종료 → web_stream 보장 → 등록 노드 foreground 실행
source /opt/ros/humble/setup.bash
source ~/robocart_ws/install/setup.bash
export ROS_DOMAIN_ID=0

# tracker 0 될 때까지 반복 종료
for round in 1 2 3 4 5 6; do
  PIDS=$(pgrep -f "robocart_tracker.tracker_node")
  [ -z "$PIDS" ] && break
  for p in $PIDS; do kill -9 "$p" 2>/dev/null; done
  sleep 2
done
echo "[prep] 남은 tracker: $(pgrep -f robocart_tracker.tracker_node | wc -l)"

# 이전 register 잔여 종료
for p in $(pgrep -f "register_node.py"); do kill -9 "$p" 2>/dev/null; done
sleep 1

# web_stream(annotated) 보장
if ! ss -ltn 2>/dev/null | grep -q ':8090'; then
  nohup python3 ~/web_stream_node.py > /tmp/web.log 2>&1 &
  sleep 2
fi
echo "[prep] web_stream: $(ss -ltn 2>/dev/null | grep -c ':8090')"

# 등록 노드 foreground 실행 (출력 그대로 보임)
cd ~/robocart_run
echo "[prep] 등록 시작 — 브라우저 localhost:8090 보며 정면→뒤돌기"
exec python3 -u register_node.py
