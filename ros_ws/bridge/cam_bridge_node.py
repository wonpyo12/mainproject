#!/usr/bin/env python3
"""
[WSL 쪽] 카메라 브리지 노드 — Windows 하드웨어를 ROS2 토픽으로 변환

  TCP 수신 'F' 패킷(JPEG)  → /image/compressed (sensor_msgs/CompressedImage)
  TCP 수신 'S' 패킷("P95") → /servo_state      (std_msgs/String)
  /servo_cmd 구독       → TCP 'C' 패킷 (서보 명령)
  /image/annotated 구독 → TCP 'V' 패킷 (추적 결과 화면 → Windows에서 표시)

로봇이 준비되면 이 노드는 로봇의 실제 카메라 노드(v4l2_camera 등)와
모터 노드로 대체된다. 토픽 인터페이스는 동일하게 유지.

실행 (WSL):
  source /opt/ros/humble/setup.bash
  python3 cam_bridge_node.py
"""
import socket
import struct
import threading
import time

import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy
from sensor_msgs.msg import CompressedImage
from std_msgs.msg import String

BIND = ("0.0.0.0", 5005)


class CamBridgeNode(Node):
    def __init__(self):
        super().__init__('cam_bridge_node')
        qos = QoSProfile(depth=1, reliability=ReliabilityPolicy.BEST_EFFORT)
        self.pub_img   = self.create_publisher(CompressedImage, '/image/compressed', qos)
        self.pub_state = self.create_publisher(String, '/servo_state', 10)
        self.create_subscription(String, '/servo_cmd', self.on_cmd, 10)
        self.create_subscription(CompressedImage, '/image/annotated',
                                 self.on_annotated, qos)

        self.client = None
        self.client_lock = threading.Lock()
        self.frames = 0
        threading.Thread(target=self.server_loop, daemon=True).start()

    def _send_packet(self, ptype: bytes, payload: bytes):
        with self.client_lock:
            c = self.client
        if c:
            try:
                c.sendall(ptype + struct.pack(">I", len(payload)) + payload)
            except OSError:
                pass

    # ── /servo_cmd → TCP 'C' 패킷 ───────────────────────────────
    def on_cmd(self, msg: String):
        self._send_packet(b"C", msg.data.strip().encode())

    # ── /image/annotated → TCP 'V' 패킷 (Windows 표시용) ────────
    def on_annotated(self, msg: CompressedImage):
        self._send_packet(b"V", bytes(msg.data))

    # ── TCP 서버: Windows 브리지 접속 대기 ──────────────────────
    def server_loop(self):
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind(BIND)
        srv.listen(1)
        self.get_logger().info(f'Windows 브리지 대기 중 {BIND}')
        while True:
            conn, addr = srv.accept()
            self.get_logger().info(f'브리지 연결됨: {addr}')
            with self.client_lock:
                self.client = conn
            try:
                self.recv_loop(conn)
            except OSError:
                pass
            with self.client_lock:
                self.client = None
            conn.close()
            self.get_logger().info('브리지 연결 끊김 — 재접속 대기')

    def _recv_exact(self, conn, n: int) -> bytes:
        buf = b""
        while len(buf) < n:
            chunk = conn.recv(n - len(buf))
            if not chunk:
                raise OSError("closed")
            buf += chunk
        return buf

    def recv_loop(self, conn):
        while True:
            head = self._recv_exact(conn, 5)
            ptype, length = head[:1], struct.unpack(">I", head[1:])[0]
            payload = self._recv_exact(conn, length)

            if ptype == b"F":
                msg = CompressedImage()
                msg.header.stamp = self.get_clock().now().to_msg()
                msg.format = "jpeg"
                msg.data = payload
                self.pub_img.publish(msg)
                self.frames += 1
                if self.frames % 200 == 0:
                    self.get_logger().info(f'{self.frames} 프레임 발행')
            elif ptype == b"S":
                s = String()
                s.data = payload.decode(errors="ignore")
                self.pub_state.publish(s)


def main():
    rclpy.init()
    node = CamBridgeNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
