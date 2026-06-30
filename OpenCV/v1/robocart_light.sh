#!/bin/bash
# ══════════════════════════════════════════════════════════════════════════════
# robocart_light — RPi4 단독 실행 래퍼
#   setup   : venv(--system-site-packages) 생성 + onnxruntime 설치
#   run     : 기존 프로필로 추종 (없으면 자동 등록)
#   register: 재등록 후 추종
#   stop / status / log
#
# apt 의 python3-opencv / python3-numpy 를 그대로 쓰기 위해 venv 는
# --system-site-packages 로 만든다. (pip 로 opencv/numpy 재설치하지 않음)
#
# 작업 폴더 규칙: 이 스크립트는 ~/robocart_light_sh/ 안에서 실행한다.
# ══════════════════════════════════════════════════════════════════════════════
set +u
HERE="$(cd "$(dirname "$0")" && pwd)"
VENV="$HERE/venv"
PIDFILE="/tmp/robocart_light.pid"
LOG="/tmp/robocart_light.log"
export ROS_DOMAIN_ID="${ROS_DOMAIN_ID:-42}"   # 라파/TurtleBot3 실제 설정값(42)에 맞춤

setup() {
    echo "[setup] apt: python3-pip python3-venv (sudo 필요)"
    sudo apt-get update -y
    sudo apt-get install -y python3-pip python3-venv
    echo "[setup] venv 생성 (--system-site-packages)"
    python3 -m venv --system-site-packages "$VENV"
    "$VENV/bin/pip" install --upgrade pip
    "$VENV/bin/pip" install -r "$HERE/requirements_pi.txt"
    echo "[setup] 확인:"
    "$VENV/bin/python" - <<'PY'
import cv2, numpy, onnxruntime
print("  cv2", cv2.__version__, "| numpy", numpy.__version__, "| ort", onnxruntime.__version__)
PY
    echo "[setup] 완료"
}

_run() {
    cd "$HERE" || exit 1
    [ -d "$VENV" ] || { echo "[run] venv 없음 → 먼저 'bash robocart_light.sh setup'"; exit 1; }
    # 중복 실행 방지: 이전 인스턴스가 떠 있으면 먼저 정지(카메라 0 동시 점유 충돌 방지).
    if pgrep -f robocart_light_main.py >/dev/null 2>&1; then
        echo "[run] 기존 인스턴스 감지 → 정지 후 재시작 (카메라 충돌 방지)"
        pkill -f robocart_light_main.py 2>/dev/null
        sleep 1
    fi
    # --follow(wheel_control.py → rclpy) 사용 시 ROS2 환경(PYTHONPATH)이 필요.
    # venv 가 --system-site-packages 라도 rclpy 는 PYTHONPATH 로만 들어오므로
    # 항상 source 해둔다(--follow 없으면 영향 없음).
    source /opt/ros/humble/setup.bash 2>/dev/null || true
    echo "[run] args=$*  로그:$LOG"
    setsid bash -c "echo \$\$ > '$PIDFILE'; exec '$VENV/bin/python' robocart_light_main.py $*" \
        >"$LOG" 2>&1 &
    for _ in $(seq 1 20); do [ -s "$PIDFILE" ] && break; sleep 0.1; done
    sleep 1
    echo "[run] PID $(cat "$PIDFILE" 2>/dev/null)  →  http://$(hostname -I | awk '{print $1}'):8080"
}

_wheeltest() {
    cd "$HERE" || exit 1
    source /opt/ros/humble/setup.bash 2>/dev/null || true
    PY="$VENV/bin/python"; [ -x "$PY" ] || PY="python3"
    "$PY" wheel_control.py "$@"
}

stop() {
    local p; p="$(cat "$PIDFILE" 2>/dev/null)"
    [ -n "$p" ] && kill -TERM "-$p" 2>/dev/null
    rm -f "$PIDFILE"
    echo "[stop] 완료"
}

case "${1:-}" in
    setup)     setup;;
    run)       shift; _run "$@";;
    register)  shift; _run --register "$@";;
    follow)    shift; _run --follow "$@";;
    wheeltest) shift; _wheeltest "$@";;
    stop)      stop;;
    status)    p="$(cat "$PIDFILE" 2>/dev/null)"; [ -n "$p" ] && kill -0 "$p" 2>/dev/null && echo "running PID $p" || echo "stopped";;
    log)       tail -f "$LOG";;
    *) echo "사용법: bash robocart_light.sh {setup|run|register|follow|wheeltest|stop|status|log} [추가인자]"
       echo "  wheeltest --test spin --secs 2   # 인식 없이 /cmd_vel 배선 점검";;
esac
