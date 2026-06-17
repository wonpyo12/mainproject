#!/usr/bin/env python3
"""
camera_node — RPi4용 웹캠 캡처 노드 (가벼움)

역할:
  USB 웹캠 → JPEG 압축 → ROS 토픽 `/robocart/image_raw/compressed` 발행

설계 포인트:
  - 캡처 스레드를 분리하여 메인 ROS 루프가 막혀도 캡처 끊김 없음
  - 압축(JPEG)으로 무선 네트워크 부하 최소화
  - QoS: BEST_EFFORT (영상은 약간 누락돼도 최신성이 더 중요)
"""
from __future__ import annotations

import threading
import time

import cv2
import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, HistoryPolicy
from sensor_msgs.msg import CompressedImage


class CameraNode(Node):

    def __init__(self) -> None:
        super().__init__("camera_node")

        # ── 파라미터 ─────────────────────────────────────
        self.declare_parameter("device_id", 0)         # /dev/video0
        self.declare_parameter("width", 640)
        self.declare_parameter("height", 480)
        self.declare_parameter("fps_target", 30)
        self.declare_parameter("jpeg_quality", 70)     # 70 = 적당한 화질/크기
        self.declare_parameter("publish_topic", "/robocart/image_raw/compressed")

        device_id = self.get_parameter("device_id").value
        self.w = self.get_parameter("width").value
        self.h = self.get_parameter("height").value
        self.fps_target = self.get_parameter("fps_target").value
        self.jpeg_quality = self.get_parameter("jpeg_quality").value
        topic = self.get_parameter("publish_topic").value

        # ── 웹캠 열기 (자동 폴백: 지정 ID 실패 시 0/1/2 순차 시도) ──
        # 환경에 따라 카메라가 /dev/video0 또는 /dev/video1 에 매핑됨
        # (메타데이터 디바이스가 0번이고 실제 카메라가 1번인 케이스 등)
        candidates = [device_id] + [d for d in (0, 1, 2) if d != device_id]
        self.cap = None
        self.device_id_used = None
        for d in candidates:
            print(f"[camera_node] /dev/video{d} 시도...")
            cap = cv2.VideoCapture(d)
            if not cap.isOpened():
                print(f"  [SKIP] /dev/video{d} 열기 실패")
                cap.release()
                continue
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.w)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.h)
            cap.set(cv2.CAP_PROP_FPS, self.fps_target)
            # 프레임 검증 (밝기 1 이상이어야 정상)
            for _ in range(5):
                cap.read()
            ret, frame = cap.read()
            if not ret or frame is None or float(frame.mean()) < 1.0:
                br = f"{float(frame.mean()):.1f}" if ret and frame is not None else "N/A"
                print(f"  [SKIP] /dev/video{d} 빈/검은 프레임 (밝기={br})")
                cap.release()
                continue
            print(f"  [OK] /dev/video{d} 채택 (밝기={float(frame.mean()):.0f})")
            self.cap = cap
            self.device_id_used = d
            break

        if self.cap is None:
            raise RuntimeError("사용 가능한 웹캠 없음 (/dev/video 0/1/2 모두 실패)")

        # ── ROS 퍼블리셔 (BEST_EFFORT QoS) ───────────────
        qos = QoSProfile(
            reliability=ReliabilityPolicy.BEST_EFFORT,
            history=HistoryPolicy.KEEP_LAST,
            depth=1,
        )
        self.pub = self.create_publisher(CompressedImage, topic, qos)
        print(f"  [OK] 토픽 발행: {topic}")

        # ── 캡처 스레드 (분리) ───────────────────────────
        self._frame: cv2.Mat | None = None
        self._frame_lock = threading.Lock()
        self._running = True
        self._capture_thread = threading.Thread(target=self._capture_loop, daemon=True)
        self._capture_thread.start()

        # ── 퍼블리시 타이머 (ROS 루프) ───────────────────
        period = 1.0 / self.fps_target
        self.create_timer(period, self._publish_latest)

        # 통계
        self._pub_count = 0
        self._last_log = time.time()

    # ──────────────────────────────────────────────────
    def _capture_loop(self) -> None:
        """별도 스레드에서 최대한 빨리 캡처. 최신 프레임만 유지."""
        while self._running:
            ok, frame = self.cap.read()
            if not ok:
                time.sleep(0.01)
                continue
            with self._frame_lock:
                self._frame = frame

    # ──────────────────────────────────────────────────
    def _publish_latest(self) -> None:
        """타이머 콜백: 최신 프레임을 JPEG 압축해서 발행."""
        with self._frame_lock:
            frame = None if self._frame is None else self._frame.copy()

        if frame is None:
            return

        # JPEG 인코딩 (압축)
        ok, buf = cv2.imencode(
            ".jpg", frame,
            [int(cv2.IMWRITE_JPEG_QUALITY), self.jpeg_quality],
        )
        if not ok:
            return

        msg = CompressedImage()
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.header.frame_id = "camera"
        msg.format = "jpeg"
        msg.data = buf.tobytes()
        self.pub.publish(msg)

        # 1초마다 fps 로그
        self._pub_count += 1
        now = time.time()
        if now - self._last_log >= 1.0:
            fps = self._pub_count / (now - self._last_log)
            print(f"[camera_node] 발행 {fps:.1f} fps")
            self._pub_count = 0
            self._last_log = now

    # ──────────────────────────────────────────────────
    def destroy_node(self) -> bool:
        self._running = False
        if self._capture_thread.is_alive():
            self._capture_thread.join(timeout=1.0)
        if self.cap.isOpened():
            self.cap.release()
        print("[camera_node] 종료")
        return super().destroy_node()


def main(args=None) -> None:
    rclpy.init(args=args)
    node = None
    try:
        node = CameraNode()
        rclpy.spin(node)
    except KeyboardInterrupt:
        print("\n[camera_node] Ctrl+C 종료")
    finally:
        if node is not None:
            node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
