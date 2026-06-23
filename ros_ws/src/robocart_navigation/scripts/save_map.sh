#!/bin/bash
# save_map.sh — 자율 매핑 종료 시 지도를 타임스탬프 폴더에 저장
#
# 사용:
#   bash save_map.sh                 # 기본: maps/YYYYMMDD-HHMM/map
#   bash save_map.sh store_v1        # 라벨 지정: maps/store_v1/map

set -e

LABEL="${1:-$(date +%Y%m%d-%H%M)}"

PKG_PATH="$(ros2 pkg prefix robocart_navigation 2>/dev/null || echo "")"
if [ -n "$PKG_PATH" ]; then
  MAPS_DIR="$PKG_PATH/share/robocart_navigation/maps"
else
  MAPS_DIR="$HOME/maps"
fi

TARGET="$MAPS_DIR/$LABEL"
mkdir -p "$TARGET"

echo "==> 지도 저장 위치: $TARGET"
ros2 run nav2_map_server map_saver_cli -f "$TARGET/map"

echo "==> 저장 완료"
ls -la "$TARGET"
