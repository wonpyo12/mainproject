// ── SLAM 맵 메타데이터 (HJ 브랜치 map_classroom_final.yaml 과 동일) ──
// 픽셀 크기는 map_classroom_final.pgm 헤더(P5 113 139) 값.
export const MAP = {
  image: '/map_classroom_final.png',
  widthPx: 113,
  heightPx: 139,
  resolution: 0.05,          // m/pixel
  originX: -0.889,           // 맵 좌하단의 월드 좌표 (m)
  originY: -3.14,
};

// ROS 월드 좌표(m) → 이미지 위 백분율 좌표.
// ROS 는 y 가 위쪽(+), 이미지는 아래쪽(+) 이라 세로축을 뒤집는다.
export function worldToPct(x, y) {
  const px = (x - MAP.originX) / MAP.resolution;
  const py = (y - MAP.originY) / MAP.resolution;
  return {
    left: (px / MAP.widthPx) * 100,
    top: 100 - (py / MAP.heightPx) * 100,
  };
}
