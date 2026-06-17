#!/bin/bash
# VMware(Ubuntu + ROS2) — SmartCart 영상처리 노드 실행
#
# 역할: 라즈베리파이 카메라 영상(/robocart/image_raw/compressed) 구독 →
#       OpenCV(YOLO+ReID) 처리 → 모터 명령(/robocart/cmd) 발행.
#       명령은 라즈베리파이가 USB 시리얼로 ESP32에 전달한다.
#
# 실행:
#   bash vmware_run.sh [--register] [--reset]

set -e
source /opt/ros/humble/setup.bash

export ROS_DOMAIN_ID=42          # 라즈베리파이와 반드시 동일하게 설정

# WiFi 공유기 환경: ROS2 기본 디스커버리(멀티캐스트)로 자동 연결됨.
# 공유기가 멀티캐스트를 막을 때만 유니캐스트 사용 (fastdds_vmware.xml IP 수정 후):
#   USE_FASTDDS_UNICAST=1 bash vmware_run.sh
if [ "${USE_FASTDDS_UNICAST:-0}" = "1" ]; then
    export FASTRTPS_DEFAULT_PROFILES_FILE="$(cd "$(dirname "$0")" && pwd)/fastdds_vmware.xml"
    echo "[DDS] 유니캐스트 프로파일 사용: $FASTRTPS_DEFAULT_PROFILES_FILE"
else
    echo "[DDS] 기본 디스커버리(멀티캐스트) 사용 — 연결 안 되면 USE_FASTDDS_UNICAST=1 로 재실행"
fi

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROBOCART_DIR="$SCRIPT_DIR/../OpenCV/Opencv/robocart"

echo "=================================================="
echo "  SmartCart — VMware 영상처리 노드"
echo "  ROS_DOMAIN_ID: $ROS_DOMAIN_ID"
echo "  VMware IP:     $(hostname -I | awk '{print $1}')"
echo "  구독: /robocart/image_raw/compressed  (라즈베리파이 카메라)"
echo "  발행: /robocart/cmd                   (ESP32 모터 명령)"
echo "=================================================="
echo ""

cd "$ROBOCART_DIR"

# 가상환경 활성화 (있으면)
if [ -f "venv/bin/activate" ]; then
    source venv/bin/activate
    echo "[venv] 가상환경 활성화됨"
fi

python3 robocart_main.py --ros2 "$@"
