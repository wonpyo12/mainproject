#!/usr/bin/env bash
# [라파] 로봇 브릿지 노드 통합 실행 스크립트 (run_bridge.sh)
#
# 사용법:
#   bash run_bridge.sh start    # 모든 브릿지 노드(cmd_server, return, pose_bridge) 실행
#   bash run_bridge.sh stop     # 모든 브릿지 노드 안전 종료
#   bash run_bridge.sh status   # 현재 가동 중인 노드 상태 확인
#

ROS_SETUP=/opt/ros/humble/setup.bash
DOMAIN_ID=0

# ROS2 환경 로드 함수
src() {
  if [ -f "$ROS_SETUP" ]; then
    source "$ROS_SETUP"
  else
    echo "[오류] ROS2 setup 파일을 찾을 수 없습니다: $ROS_SETUP"
    exit 1
  fi
  export ROS_DOMAIN_ID=$DOMAIN_ID
}

# 프로세스 개수 세기 함수
cnt() {
  pgrep -f "$1" | grep -vw "$$" | wc -l
}

# 프로세스 강제 종료 함수
kill_node() {
  local pat="$1"
  local pids
  pids=$(pgrep -f "$pat" | grep -vw "$$" || true)
  if [ -n "$pids" ]; then
    for p in $pids; do
      kill -9 "$p" 2>/dev/null
    done
  fi
}

case "${1:-status}" in
  start)
    echo "=== 로봇 브릿지 서비스 시작 ==="
    src
    
    # 1. 기존에 돌고 있는 노드 종료 (중복 실행 방지)
    echo "기존 프로세스 정리 중..."
    kill_node "cmd_server.py"
    kill_node "return_controller.py"
    kill_node "pose_bridge.py"
    sleep 1

    # 2. cmd_server.py 실행 (백그라운드)
    echo "1) cmd_server.py 실행 중..."
    python3 cmd_server.py > cmd_server.log 2>&1 &
    
    # 3. return_controller.py 실행 (백그라운드)
    echo "2) return_controller.py 실행 중..."
    python3 return_controller.py > return_controller.log 2>&1 &
    
    # 4. pose_bridge.py 실행 (백그라운드)
    echo "3) pose_bridge.py 실행 중..."
    python3 pose_bridge.py > pose_bridge.log 2>&1 &
    
    sleep 2
    echo "실행 완료! (로그는 각각 cmd_server.log, return_controller.log, pose_bridge.log 에 기록됩니다.)"
    echo "현재 작동 상태:"
    echo "  cmd_server       : $(cnt cmd_server.py)개 가동 중"
    echo "  return_controller: $(cnt return_controller.py)개 가동 중"
    echo "  pose_bridge      : $(cnt pose_bridge.py)개 가동 중"
    ;;

  stop)
    echo "=== 로봇 브릿지 서비스 종료 ==="
    kill_node "cmd_server.py"
    kill_node "return_controller.py"
    kill_node "pose_bridge.py"
    echo "모든 브릿지 노드가 종료되었습니다."
    ;;

  status)
    echo "=== 로봇 브릿지 노드 상태 ==="
    echo "  cmd_server.py    : $(cnt cmd_server.py)개 실행 중"
    echo "  return_controller: $(cnt return_controller.py)개 실행 중"
    echo "  pose_bridge.py   : $(cnt pose_bridge.py)개 실행 중"
    ;;

  *)
    echo "사용법: bash run_bridge.sh {start|stop|status}"
    exit 1
    ;;
esac
