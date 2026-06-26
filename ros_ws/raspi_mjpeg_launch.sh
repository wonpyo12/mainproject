#!/bin/bash
# 라즈베리파이4 — C920 MJPEG HTTP 패스스루 송출 실행
#
# usb_cam(ROS2) 대신 사용. DDS를 거치지 않고 영상을 HTTP로 직접 송출하여
# WiFi 불안정·RPi CPU 포화 문제를 회피한다. (명령은 여전히 raspi_cmd_bridge_esp32.py + ROS2)
#
# 사전 조건: sudo apt install ffmpeg
# 실행:      bash raspi_mjpeg_launch.sh
# VMware:    PI_CAM_URL=http://<RPI_IP>:8090/stream 로 robocart_main.py --mjpeg 실행

set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

PORT="${PORT:-8090}"
DEVICE="${DEVICE:-/dev/video0}"
WIDTH="${WIDTH:-640}"
HEIGHT="${HEIGHT:-480}"
FPS="${FPS:-15}"

# 카메라 점유 충돌 방지: 기존 usb_cam / 이전 송출 서버 정리
pkill -f usb_cam_node_exe 2>/dev/null || true
pkill -f raspi_mjpeg_server.py 2>/dev/null || true
sleep 1

if [ ! -e "$DEVICE" ]; then
    echo "[오류] $DEVICE 없음. ls /dev/video* 로 확인하세요."
    exit 1
fi
if ! command -v ffmpeg >/dev/null 2>&1; then
    echo "[설치 필요] sudo apt install ffmpeg"
    exit 1
fi

IP=$(hostname -I | awk '{print $1}')
echo "=================================================="
echo "  SmartCart — 라즈베리파이 MJPEG 패스스루 송출"
echo "  스트림:   http://$IP:$PORT/stream"
echo "  VMware:   PI_CAM_URL=http://$IP:$PORT/stream"
echo "  해상도:   ${WIDTH}x${HEIGHT} @ ${FPS}fps (디코드 없음)"
echo "=================================================="

exec python3 "$SCRIPT_DIR/raspi_mjpeg_server.py" \
    --port "$PORT" --device "$DEVICE" \
    --width "$WIDTH" --height "$HEIGHT" --fps "$FPS"
