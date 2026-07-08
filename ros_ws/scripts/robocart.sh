#!/usr/bin/env bash
# RoboCart 노트북(WSL) 노드 통합 제어 — "노드는 항상 정확히 1개" 보장
#
# 사용법:
#   bash robocart.sh stop       모든 노드 확실히 종료
#   bash robocart.sh status     노드 개수 + 토픽 수신율
#   bash robocart.sh view       카메라만 보기 (web_stream 1개, 원본 표시)
#   bash robocart.sh register   사용자 등록 (tracker 정지 → register 실행)
#   bash robocart.sh track      추적 시작 (register 정지 → tracker 1개)
#
# 이슈 #2 해결: 그동안 셸 따옴표 문제로 kill 이 실패해 노드가 누적되던 것을,
# 파일 스크립트 + PID/포트 기반 종료로 고정.

# 주의: set -u 금지 — ROS setup.bash 가 unbound 변수를 참조해 깨짐
ROS_SETUP=/opt/ros/humble/setup.bash
WS_SETUP=~/robocart_ws/install/setup.bash
RUN_DIR=~/robocart_run
WEB=~/web_stream_node.py
PORT=8090
# 라파 IP / 카메라 TCP 스트림 (DDS 우회). 환경변수로 덮어쓸 수 있음.
PI_IP="${PI_IP:-192.168.0.3}"
PI_CAM_URL="${PI_CAM_URL:-http://$PI_IP:$PORT/stream}"

src() { source "$ROS_SETUP"; [ -f "$WS_SETUP" ] && source "$WS_SETUP"; export ROS_DOMAIN_ID=0; }

# 패턴에 해당하는 프로세스를 0이 될 때까지 확실히 종료 (자기 자신 제외)
kill_all() {
  local pat="$1"
  for r in 1 2 3 4 5; do
    local pids
    pids=$(pgrep -f "$pat" | grep -vw "$$" || true)
    [ -z "$pids" ] && return 0
    for p in $pids; do kill -9 "$p" 2>/dev/null; done
    sleep 1
  done
}

free_port() { command -v fuser >/dev/null && fuser -k ${PORT}/tcp 2>/dev/null; sleep 1; }

# tracker 는 SIGTERM 먼저 — 종료 정리 핸들러(세션 데이터 삭제)가 돌게 한 뒤,
# 남으면 SIGKILL. (일회용 등록 데이터를 종료 시 지우기 위함)
stop_tracker() {
  for p in $(pgrep -f "robocart_tracker.tracker_node" | grep -vw "$$"); do
    kill -TERM "$p" 2>/dev/null
  done
  sleep 2
  kill_all "robocart_tracker.tracker_node"
}
stop_register() { kill_all "register_node.py"; }
stop_web()      { kill_all "web_stream_node.py"; free_port; }

cnt() { pgrep -f "$1" | grep -vw "$$" | wc -l; }

# web_stream 을 정확히 1개 보장 (인자: 토픽)
ensure_web() {
  local topic="${1:-/image/annotated}"
  stop_web
  src
  setsid python3 "$WEB" --ros-args -p topic:="$topic" > /tmp/web.log 2>&1 < /dev/null &
  disown
  sleep 5
}

case "${1:-status}" in
  stop)
    stop_tracker; stop_register; stop_web
    echo "[stop] tracker=$(cnt robocart_tracker.tracker_node) register=$(cnt register_node.py) web=$(cnt web_stream_node.py)"
    ;;

  status)
    src
    echo "=== 노드 개수 ==="
    echo "  tracker : $(cnt robocart_tracker.tracker_node)"
    echo "  register: $(cnt register_node.py)"
    echo "  web     : $(cnt web_stream_node.py)  (포트 $PORT: $(ss -ltn 2>/dev/null | grep -c :$PORT))"
    echo "=== 토픽 수신율 (각 4초) ==="
    echo -n "  /image/compressed : "; timeout 4 ros2 topic hz /image/compressed 2>/dev/null | grep -oE 'average rate: [0-9.]+' | head -1 || echo "없음"
    echo -n "  /image/annotated  : "; timeout 4 ros2 topic hz /image/annotated  2>/dev/null | grep -oE 'average rate: [0-9.]+' | head -1 || echo "없음"
    ;;

  view)
    stop_tracker; stop_register
    ensure_web /image/annotated   # annotated 우선, 없으면 원본 폴백(풀레이트)
    echo "[view] web=$(cnt web_stream_node.py) → http://localhost:$PORT/"
    ;;

  register)
    stop_tracker; stop_register
    ensure_web /image/annotated
    echo "[register] web 준비 완료 → 등록 시작 (브라우저 localhost:$PORT)"
    src; cd "$RUN_DIR"
    # 2번째 인자(user-id)가 있을 때만 전달 — 빈 인자 전달 방지
    if [ -n "${2:-}" ]; then
      exec python3 -u register_node.py --user-id "$2"
    else
      exec python3 -u register_node.py
    fi
    ;;

  track)
    stop_tracker; stop_register
    ensure_web /image/annotated
    src; cd "$RUN_DIR"
    export PI_CAM_URL   # tracker 가 라파 카메라를 TCP 로 받음 (DDS 우회)
    echo "[track] 카메라 입력: $PI_CAM_URL"
    setsid env PI_CAM_URL="$PI_CAM_URL" python3 -u -m robocart_tracker.tracker_node > /tmp/tracker.log 2>&1 < /dev/null &
    disown
    echo "[track] tracker 시작 — 모델 로드 ~30초 (로그: /tmp/tracker.log)"
    echo "[track] tracker=$(cnt robocart_tracker.tracker_node) web=$(cnt web_stream_node.py)"
    ;;

  *)
    echo "사용법: bash robocart.sh {stop|status|view|register|track}"
    exit 1
    ;;
esac
