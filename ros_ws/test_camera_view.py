#!/usr/bin/env python3
"""
라즈베리파이 카메라 영상 확인 스크립트

실행:
  python3 test_camera_view.py            # 창(imshow) + 터미널 FPS + 최신 프레임 저장
  python3 test_camera_view.py --no-gui   # 창 없이 터미널 FPS + 파일 저장만 (검은 창 회피)

종료: ESC 또는 q (창 사용 시) / Ctrl+C

비고: VMware에서 cv2.imshow 창이 검게만 뜨는 경우(렌더링 버그)에도
      터미널 FPS 로그와 /tmp/cam_live.jpg 로 수신 여부를 확인할 수 있다.
"""
# cv2/numpy는 시스템 설치본(~/.local, opencv-contrib-python 단일)을 사용한다.
# venv 의 cv2 는 opencv-python + opencv-contrib-python 가 동시 설치돼 번들 Qt 충돌로
# imshow 가 검은 창만 뜨므로 venv 경로를 일부러 추가하지 않는다.
import argparse
import sys
import time

import rclpy
from rclpy.node import Node
from sensor_msgs.msg import CompressedImage
import cv2
import numpy as np

LIVE_PATH = '/tmp/cam_live.jpg'   # 최신 프레임 저장 위치 (데스크탑 이미지 뷰어로 열어 확인)


class CameraViewer(Node):
    def __init__(self, use_gui: bool):
        super().__init__('camera_viewer')
        self.use_gui = use_gui
        self.frame_count = 0
        self.t0 = time.time()
        self.last_log = self.t0
        self.sub = self.create_subscription(
            CompressedImage,
            '/robocart/image_raw/compressed',
            self.callback,
            10
        )
        print('카메라 영상 대기 중... (라즈베리파이 카메라 노드 실행됐는지 확인)', flush=True)
        if not use_gui:
            print(f'[--no-gui] 창 없이 동작. 최신 프레임: {LIVE_PATH}', flush=True)

    def callback(self, msg):
        arr = np.frombuffer(bytes(msg.data), np.uint8)
        frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if frame is None:
            return
        self.frame_count += 1

        # 최신 프레임을 파일로 저장 (표시가 안 돼도 수신/디코드 확인용)
        cv2.imwrite(LIVE_PATH, frame)

        # 터미널 FPS 로그 (약 1초마다) — 창이 검어도 '실시간 수신'을 확인
        now = time.time()
        if now - self.last_log >= 1.0:
            fps = self.frame_count / max(now - self.t0, 1e-6)
            print(f'[수신] frame={self.frame_count}  '
                  f'평균 {fps:.1f} FPS  size={frame.shape[1]}x{frame.shape[0]}  '
                  f'mean밝기={frame.mean():.0f}', flush=True)
            self.last_log = now

        if self.use_gui:
            cv2.putText(frame, f'Frame: {self.frame_count}', (10, 30),
                        cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
            cv2.putText(frame, 'Raspberry Pi Camera - OK', (10, 65),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
            cv2.imshow('SmartCart - 카메라 확인', frame)
            if cv2.waitKey(1) & 0xFF in [27, ord('q')]:
                rclpy.shutdown()


def main():
    parser = argparse.ArgumentParser(description='라즈베리파이 카메라 영상 확인')
    parser.add_argument('--no-gui', action='store_true',
                        help='cv2 창 없이 터미널 FPS + /tmp/cam_live.jpg 저장만')
    args = parser.parse_args()

    rclpy.init()
    node = CameraViewer(use_gui=not args.no_gui)
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        cv2.destroyAllWindows()


if __name__ == '__main__':
    main()
