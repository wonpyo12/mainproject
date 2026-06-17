#!/bin/bash
# 라즈베리파이4 실행 스크립트 — C920 카메라 영상을 ROS2 토픽으로 발행
#
# 사전 조건:
#   sudo apt install ros-humble-usb-cam ros-humble-image-transport-plugins
#
# 실행:
#   bash raspi_camera_launch.sh

set -e
source /opt/ros/humble/setup.bash

export ROS_DOMAIN_ID=42          # VMware와 반드시 동일하게 설정

# WiFi 공유기 환경: ROS2 기본 디스커버리(멀티캐스트)로 자동 연결됨.
# 공유기가 멀티캐스트를 막아 디스커버리가 안 될 때만 유니캐스트 사용:
#   1) ip addr 로 라즈베리파이/VMware 현재 IP 확인 후 fastdds_raspi.xml 의 주소 수정
#   2) USE_FASTDDS_UNICAST=1 bash raspi_camera_launch.sh
if [ "${USE_FASTDDS_UNICAST:-0}" = "1" ]; then
    export FASTRTPS_DEFAULT_PROFILES_FILE="$(cd "$(dirname "$0")" && pwd)/fastdds_raspi.xml"
    echo "[DDS] 유니캐스트 프로파일 사용: $FASTRTPS_DEFAULT_PROFILES_FILE"
else
    echo "[DDS] 기본 디스커버리(멀티캐스트) 사용 — 연결 안 되면 USE_FASTDDS_UNICAST=1 로 재실행"
fi

echo "=================================================="
echo "  SmartCart — 라즈베리파이 카메라 노드"
echo "  발행 토픽: /robocart/image_raw/compressed"
echo "  ROS_DOMAIN_ID: $ROS_DOMAIN_ID"
echo "=================================================="
echo ""

# 카메라 디바이스 확인
if [ ! -e /dev/video0 ]; then
    echo "[오류] /dev/video0 없음."
    echo "  USB 카메라 연결 여부와 다음 명령으로 확인:"
    echo "  ls /dev/video*"
    exit 1
fi
echo "[확인] /dev/video0 검출됨"

# 필수 패키지 확인
if ! ros2 pkg list 2>/dev/null | grep -q usb_cam; then
    echo "[설치] usb_cam 패키지 설치 중..."
    sudo apt install -y ros-humble-usb-cam ros-humble-image-transport-plugins
fi

echo "[시작] 카메라 노드 (네임스페이스: /robocart, 해상도: 640x480, MJPEG)"
echo "중단: Ctrl+C"
echo ""

# usb_cam: MJPEG 스트림을 받아 RGB로 디코드 → image_transport가
#          /robocart/image_raw/compressed 를 자동 발행
ros2 run usb_cam usb_cam_node_exe \
    --ros-args \
    --remap __ns:=/robocart \
    -p video_device:=/dev/video0 \
    -p pixel_format:=mjpeg2rgb \
    -p image_width:=640 \
    -p image_height:=480 \
    -p framerate:=15.0 \
    -p brightness:=160
