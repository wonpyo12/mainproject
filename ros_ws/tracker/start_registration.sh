#!/usr/bin/env bash
# 처음부터: tracker 정지 → web_stream(annotated) 확인 → 등록 노드 시작
source /opt/ros/humble/setup.bash
source ~/robocart_ws/install/setup.bash
export ROS_DOMAIN_ID=0

# 1) tracker 정지 (등록 중 카메라/화면 충돌 방지)
pkill -9 -f "robocart_tracker.tracker_node" 2>/dev/null
sleep 2

# 2) web_stream 이 /image/annotated 를 보도록 보장 (localhost:8090)
if ! ss -ltn 2>/dev/null | grep -q ':8090'; then
  nohup python3 ~/web_stream_node.py > /tmp/web.log 2>&1 &
  sleep 2
fi

# 3) 등록 노드 시작 (서보 중앙 고정 → 정면/뒤돌기 자동 촬영)
cd ~/robocart_run
nohup python3 -u register_node.py > /tmp/register.log 2>&1 &
echo "[register] 시작됨 PID=$!  — 브라우저 localhost:8090 보며 따라하세요"
echo "[register] 모델 로드(약 30초) 후 카메라 화면이 뜹니다"
