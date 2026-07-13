#!/usr/bin/env bash
# 모든 web_stream 확실히 종료 후 1개만 시작 (원본 카메라 직접 구독)
source /opt/ros/humble/setup.bash
export ROS_DOMAIN_ID=0

cp /mnt/d/YH/ros_ws/web_stream/web_stream_node.py ~/web_stream_node.py

for round in 1 2 3 4 5; do
  PIDS=$(pgrep -f "web_stream_node.py")
  [ -z "$PIDS" ] && break
  for p in $PIDS; do kill -9 "$p" 2>/dev/null; done
  sleep 1
done
# 포트도 강제 해제
command -v fuser >/dev/null && fuser -k 8090/tcp 2>/dev/null
sleep 2
echo "[web] 잔여 web_stream: $(pgrep -f web_stream_node.py | wc -l)"

# 인자: $1 = 토픽 (기본 /image/compressed = 원본). 등록/추적 땐 /image/annotated
TOPIC="${1:-/image/compressed}"
setsid python3 ~/web_stream_node.py --ros-args -p topic:="$TOPIC" > /tmp/web.log 2>&1 < /dev/null &
disown
sleep 6
echo "[web] $(grep -a 구독 /tmp/web.log | tail -1)"
echo "[web] 프로세스 수: $(pgrep -f web_stream_node.py | wc -l)"
