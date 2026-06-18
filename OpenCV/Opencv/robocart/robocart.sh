#!/bin/bash
# ══════════════════════════════════════════════════════════════════════════════
# SmartCart robocart 제어 (VMware) — PID 파일 기반 start / stop / restart / status
#
# 이름 기반 pkill 을 쓰지 않는다. (pkill -f "robocart_main.py" 는 그 문자열을 포함한
#  제어 셸 자신까지 죽여 self-kill 을 일으켰다.) 대신 시작 시 setsid 로 새 프로세스
#  그룹을 만들고 그 PID 를 파일에 기록 → 종료는 정확히 그 그룹만 신호로 정리한다.
#  → self-kill 없음, 옛 프로세스 잔존 없음.
#
# 사용 (기존 'python3 robocart_main.py ...' 직접 실행을 대체):
#   bash robocart.sh start [추가인자]   # 영상=MJPEG(HTTP), 명령=ROS2, 웹출력
#   bash robocart.sh start --register   # 새로 등록 후 추종
#   bash robocart.sh restart            # 정리 후 재시작 (기존 프로필로 추종)
#   bash robocart.sh stop               # 종료(SIGTERM→필요시 SIGKILL)
#   bash robocart.sh status
#   bash robocart.sh log                # 실행 로그 따라보기
#
# 환경변수(선택):
#   PI_CAM_URL    라즈베리파이 MJPEG 스트림 (기본 http://192.168.0.2:8090/stream)
#   ROS_DOMAIN_ID (기본 42)
# ══════════════════════════════════════════════════════════════════════════════
# 주의: set -u 는 쓰지 않는다. ROS(/opt/ros/humble/setup.bash)·venv activate 가
#       미정의 변수를 다수 참조해 set -u 와 충돌, 출력 없이 즉시 종료된다.

ROBO_DIR="$(cd "$(dirname "$0")" && pwd)"
PIDFILE="/tmp/robocart.pid"
LOG="/tmp/robocart_run.log"

PI_CAM_URL="${PI_CAM_URL:-http://192.168.0.2:8090/stream}"
export ROS_DOMAIN_ID="${ROS_DOMAIN_ID:-42}"

_pid()       { cat "$PIDFILE" 2>/dev/null; }
is_running() {
    local p; p="$(_pid)"
    [ -n "$p" ] && kill -0 "$p" 2>/dev/null
}

stop() {
    if ! is_running; then
        echo "[stop] 실행 중 아님"
        rm -f "$PIDFILE"
        return 0
    fi
    local p; p="$(_pid)"
    echo "[stop] 프로세스그룹 $p 종료 (SIGTERM)..."
    kill -TERM "-$p" 2>/dev/null || kill -TERM "$p" 2>/dev/null
    for _ in $(seq 1 25); do        # 최대 ~7.5초 정상종료 대기
        is_running || break
        sleep 0.3
    done
    if is_running; then
        echo "[stop] 미응답 → 강제종료 (SIGKILL)"
        kill -KILL "-$p" 2>/dev/null || kill -KILL "$p" 2>/dev/null
        sleep 0.5
    fi
    rm -f "$PIDFILE"
    echo "[stop] 완료"
}

start() {
    if is_running; then
        echo "[start] 이미 실행 중 (PID $(_pid)). 재시작은 'restart'."
        return 0
    fi
    cd "$ROBO_DIR" || { echo "[start] 디렉터리 없음: $ROBO_DIR"; exit 1; }
    source /opt/ros/humble/setup.bash 2>/dev/null || true
    [ -f venv/bin/activate ] && source venv/bin/activate
    export PI_CAM_URL

    echo "[start] PI_CAM_URL=$PI_CAM_URL"
    echo "[start] args=$* (없으면 기존 프로필로 추종)"
    # setsid 로 새 세션을 만들고, 그 안에서 'exec python3' 로 bash 를 python 으로 치환한다
    #  → python 이 곧 세션/프로세스그룹 리더(PGID=PID). 그 PID 를 exec 직전에 $$ 로 PIDFILE
    #    에 직접 기록하므로, 예전처럼 setsid/bash PID 와 실제 python PID 가 어긋나 자식이
    #    그룹 밖 고아로 살아남는 일이 없다 → stop 이 'kill -그룹' 으로 한 번에 정리.
    # '<<< 1' (herestring): 기존 프로필 프롬프트 '1/2/3' 에 1(기존 추종) 자동 입력.
    #    예전 'echo 1 | python3' 파이프라인은 python 을 별도 그룹의 고아로 만들어 stop 이
    #    놓쳤다(→ 8080 포트 잔존·재시작 충돌). 파이프 자식을 없애 그 문제를 제거한다.
    rm -f "$PIDFILE"
    setsid bash -c "echo \$\$ > '$PIDFILE'; exec python3 robocart_main.py --mjpeg '$PI_CAM_URL' --web $* <<< 1" \
        >"$LOG" 2>&1 &
    for _ in $(seq 1 20); do [ -s "$PIDFILE" ] && break; sleep 0.1; done
    sleep 1
    if is_running; then
        echo "[start] PID $(_pid)  로그:$LOG"
        echo "[start] 웹 화면: http://localhost:8080"
    else
        echo "[start] 기동 실패 — 로그 확인: tail -40 $LOG"
        rm -f "$PIDFILE"
        exit 1
    fi
}

status() {
    if is_running; then
        echo "[status] 실행 중  PID $(_pid)"
        ps -o pid,ppid,etime,cmd -p "$(_pid)" 2>/dev/null
    else
        echo "[status] 정지됨"
    fi
}

case "${1:-}" in
    start)   shift; start "$@";;
    stop)    stop;;
    restart) shift; stop; sleep 1; start "$@";;
    status)  status;;
    log)     tail -f "$LOG";;
    *) echo "사용법: bash robocart.sh {start|stop|restart|status|log} [추가인자]";;
esac
