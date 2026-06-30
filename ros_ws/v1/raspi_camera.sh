#!/bin/bash
# ══════════════════════════════════════════════════════════════════════════════
# SmartCart 라즈베리파이4 — 카메라 영상 송출
#
# 사용:
#   bash raspi_camera.sh ros2   # ROS2 토픽으로 송출 (/robocart/image_raw/compressed)
#   bash raspi_camera.sh mjpeg  # HTTP MJPEG 패스스루 송출 (http://<RPI_IP>:8090/stream)
#
# 환경변수(선택):
#   USE_FASTDDS_UNICAST=1   DDS 유니캐스트 강제 (ros2 모드, 멀티캐스트 불가 환경)
#   DEVICE  카메라 디바이스 (기본 /dev/video0)
#   PORT    HTTP 포트       (기본 8090, mjpeg 모드)
#   WIDTH / HEIGHT / FPS   해상도·프레임 (기본 640×480 @ 15fps)
# ══════════════════════════════════════════════════════════════════════════════

set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
DEVICE="${DEVICE:-/dev/video0}"

_check_device() {
    if [ ! -e "$DEVICE" ]; then
        echo "[오류] $DEVICE 없음. ls /dev/video* 로 확인하세요."
        exit 1
    fi
    echo "[확인] $DEVICE 검출됨"
}

ros2_mode() {
    source /opt/ros/humble/setup.bash
    export ROS_DOMAIN_ID="${ROS_DOMAIN_ID:-42}"

    if [ "${USE_FASTDDS_UNICAST:-0}" = "1" ]; then
        export FASTRTPS_DEFAULT_PROFILES_FILE="$SCRIPT_DIR/fastdds_raspi.xml"
        echo "[DDS] 유니캐스트 프로파일 사용: $FASTRTPS_DEFAULT_PROFILES_FILE"
    else
        echo "[DDS] 기본 디스커버리(멀티캐스트) 사용 — 연결 안 되면 USE_FASTDDS_UNICAST=1 로 재실행"
    fi

    echo "=================================================="
    echo "  SmartCart — 카메라 ROS2 모드"
    echo "  발행 토픽: /robocart/image_raw/compressed"
    echo "  ROS_DOMAIN_ID: $ROS_DOMAIN_ID"
    echo "=================================================="

    _check_device

    if ! ros2 pkg list 2>/dev/null | grep -q usb_cam; then
        echo "[설치] usb_cam 패키지 설치 중..."
        sudo apt install -y ros-humble-usb-cam ros-humble-image-transport-plugins
    fi

    echo "[시작] 카메라 노드 (해상도: 640x480, MJPEG) | 중단: Ctrl+C"
    ros2 run usb_cam usb_cam_node_exe \
        --ros-args \
        --remap __ns:=/robocart \
        -p video_device:="$DEVICE" \
        -p pixel_format:=mjpeg2rgb \
        -p image_width:=640 \
        -p image_height:=480 \
        -p framerate:=15.0 \
        -p brightness:=160
}

mjpeg_mode() {
    PORT="${PORT:-8090}"
    WIDTH="${WIDTH:-640}"
    HEIGHT="${HEIGHT:-480}"
    FPS="${FPS:-15}"

    if ! command -v ffmpeg >/dev/null 2>&1; then
        echo "[설치 필요] sudo apt install ffmpeg"
        exit 1
    fi

    # 기존 점유 프로세스 정리
    pkill -f usb_cam_node_exe 2>/dev/null || true
    pkill -f raspi_mjpeg_server.py 2>/dev/null || true
    sleep 1

    _check_device

    IP=$(hostname -I | awk '{print $1}')
    echo "=================================================="
    echo "  SmartCart — 카메라 MJPEG 모드"
    echo "  스트림:   http://$IP:$PORT/stream"
    echo "  VMware:   PI_CAM_URL=http://$IP:$PORT/stream"
    echo "  해상도:   ${WIDTH}x${HEIGHT} @ ${FPS}fps (디코드 없음)"
    echo "=================================================="

    exec python3 "$SCRIPT_DIR/raspi_mjpeg_server.py" \
        --port "$PORT" --device "$DEVICE" \
        --width "$WIDTH" --height "$HEIGHT" --fps "$FPS"
}

case "${1:-}" in
    ros2)  ros2_mode;;
    mjpeg) mjpeg_mode;;
    *) echo "사용법: bash raspi_camera.sh {ros2|mjpeg}";;
esac
