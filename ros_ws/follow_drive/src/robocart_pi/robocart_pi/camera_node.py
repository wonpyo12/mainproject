#!/usr/bin/env python3
"""
[라즈베리파이] 카메라 송출 노드

  /dev/video0  →  cv2.imencode(jpg)  →  /image/compressed (sensor_msgs/CompressedImage)

노트북의 tracker_node가 이 토픽을 구독해 OpenCV 코어로 계산한다.
원본(raw) 640x480은 Wi-Fi에서 ~13MB/s라 끊기므로 반드시 JPEG 압축으로 보낸다.
QoS는 BEST_EFFORT + depth=1 (오래된 프레임 버리고 항상 최신만).

실행:
  ros2 run robocart_pi camera_node
  ros2 run robocart_pi camera_node --ros-args -p device:=0 -p fps:=15.0 -p jpeg_quality:=70
"""
import cv2
import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy
from sensor_msgs.msg import CompressedImage


class CameraNode(Node):
    def __init__(self):
        super().__init__('camera_node')

        self.declare_parameter('device', 0)
        self.declare_parameter('width', 640)
        self.declare_parameter('height', 480)
        self.declare_parameter('fps', 15.0)
        self.declare_parameter('jpeg_quality', 70)

        self.device = self.get_parameter('device').value
        self.width = int(self.get_parameter('width').value)
        self.height = int(self.get_parameter('height').value)
        self.fps = float(self.get_parameter('fps').value)
        self.jpeg_quality = int(self.get_parameter('jpeg_quality').value)

        qos = QoSProfile(depth=1, reliability=ReliabilityPolicy.BEST_EFFORT)
        self.pub = self.create_publisher(CompressedImage, '/image/compressed', qos)

        # C920 등 일부 USB 카메라는 기본 백엔드로 안 열림 → V4L2 명시
        self.cap = cv2.VideoCapture(self.device, cv2.CAP_V4L2)
        # 주의: 이 카메라는 OpenCV 해상도 설정 시 캡처가 깨짐(0x0).
        # → 네이티브로 열고 tick()에서 소프트웨어 리사이즈 (width/height 는 목표 출력).
        self.cap.set(cv2.CAP_PROP_FPS, self.fps)
        # 내부 버퍼 최소화 — 항상 최신 프레임 (지원 안 하는 백엔드는 무시)
        try:
            self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        except cv2.error:
            pass

        if not self.cap.isOpened():
            self.get_logger().error(
                f'카메라 열기 실패: device={self.device}. /dev/video* 권한/연결 확인')
        else:
            self.get_logger().info(
                f'카메라 {self.device} {self.width}x{self.height} @ {self.fps}fps '
                f'→ /image/compressed (jpeg q={self.jpeg_quality})')

        self.frames = 0
        self.timer = self.create_timer(1.0 / max(self.fps, 1.0), self.tick)

    def tick(self):
        ok, frame = self.cap.read()
        if not ok or frame is None:
            self.get_logger().warn('프레임 읽기 실패', throttle_duration_sec=2.0)
            return
        # 네이티브 프레임을 목표 해상도로 소프트웨어 리사이즈 (전송량/지연 감소)
        if frame.shape[1] != self.width or frame.shape[0] != self.height:
            frame = cv2.resize(frame, (self.width, self.height))

        ok, jpg = cv2.imencode(
            '.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, self.jpeg_quality])
        if not ok:
            return

        msg = CompressedImage()
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.header.frame_id = 'camera'
        msg.format = 'jpeg'
        msg.data = jpg.tobytes()
        self.pub.publish(msg)

        self.frames += 1
        if self.frames % 150 == 0:
            self.get_logger().info(f'{self.frames} 프레임 송출')

    def destroy_node(self):
        if self.cap is not None:
            self.cap.release()
        super().destroy_node()


def main():
    rclpy.init()
    node = CameraNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
