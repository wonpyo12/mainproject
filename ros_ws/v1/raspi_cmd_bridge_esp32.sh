#!/bin/bash
# 라즈베리파이4 실행 스크립트 — ROS2 명령(/robocart/cmd)을 ESP32에 USB 시리얼로 전달
#
# 동작: VMware가 발행한 모터 명령을 구독해 USB로 연결된 ESP32에 시리얼 송신.
#       (카메라 노드 raspi_camera_launch.sh 와 별도 터미널에서 함께 실행)
#
# 사전 조건:
#   pip3 install pyserial          # 또는: sudo apt install python3-serial
#
# 실행:
#   bash raspi_cmd_bridge_esp32.sh                    # 기본 포트 /dev/ttyUSB0
#   bash raspi_cmd_bridge_esp32.sh --port /dev/ttyACM0

set -e
source /opt/ros/humble/setup.bash

export ROS_DOMAIN_ID=42          # VMware와 반드시 동일하게 설정

# WiFi 공유기 환경: ROS2 기본 디스커버리(멀티캐스트)로 자동 연결됨.
# 공유기가 멀티캐스트를 막을 때만 유니캐스트 사용 (fastdds_raspi.xml IP 수정 후):
#   USE_FASTDDS_UNICAST=1 bash raspi_cmd_bridge_esp32.sh
if [ "${USE_FASTDDS_UNICAST:-0}" = "1" ]; then
    export FASTRTPS_DEFAULT_PROFILES_FILE="$(cd "$(dirname "$0")" && pwd)/fastdds_raspi.xml"
    echo "[DDS] 유니캐스트 프로파일 사용: $FASTRTPS_DEFAULT_PROFILES_FILE"
else
    echo "[DDS] 기본 디스커버리(멀티캐스트) 사용 — 연결 안 되면 USE_FASTDDS_UNICAST=1 로 재실행"
fi

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "=================================================="
echo "  SmartCart — 라즈베리파이 명령 브리지 (ROS2 → ESP32 시리얼)"
echo "  구독 토픽: /robocart/cmd"
echo "  ROS_DOMAIN_ID: $ROS_DOMAIN_ID"
echo "=================================================="
echo ""

# ESP32 포트 자동 안내 (인수 미지정 시)
if [ -z "$*" ] && [ ! -e /dev/ttyUSB0 ] && [ -e /dev/ttyACM0 ]; then
    echo "[안내] /dev/ttyUSB0 없음, /dev/ttyACM0 발견 → --port /dev/ttyACM0 로 실행합니다."
    set -- --port /dev/ttyACM0
fi

echo "중단: Ctrl+C"
echo ""
python3 "$SCRIPT_DIR/raspi_cmd_bridge_esp32.py" "$@"
