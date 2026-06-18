#!/usr/bin/env python3
"""
[라파] TCP 명령 수신 서버 — Windows(노트북)의 명령을 받아 ROS2 모터 토픽으로 발행

  Windows tracker ──TCP(9998)──→ cmd_server ──ROS2──→
       "S:SCAN_START"  / "S:CENTER" / "S:A95"  →  /robocart/servo  (String) → ESP32
       "V:0.12,0.5"                            →  /robocart/cmd_vel (Twist)  → 바퀴

DDS(노트북↔라파)가 불안정해서 명령 전달만 TCP로 우회. 라파 내부 모터 제어(ROS2)는 그대로.
WSL 없이 Windows 파이썬에서 노트북 추적을 돌리기 위함.

실행 (라파):
  source /opt/ros/humble/setup.bash
  source ~/ros2_ws/test0615/install/setup.bash
  export ROS_DOMAIN_ID=30
  python3 cmd_server.py
"""
import socket
import threading

import rclpy
from rclpy.node import Node
from std_msgs.msg import String
from geometry_msgs.msg import Twist

BIND = ("0.0.0.0", 9998)


class CmdServer(Node):
    def __init__(self):
        super().__init__("cmd_server")
        self.pub_servo = self.create_publisher(String, "/robocart/servo", 10)
        self.pub_cmd = self.create_publisher(Twist, "/robocart/cmd_vel", 10)
        threading.Thread(target=self._serve, daemon=True).start()
        self.get_logger().info(f"TCP 명령 서버 대기 {BIND} → /robocart/servo, /robocart/cmd_vel")

    def _serve(self):
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind(BIND)
        srv.listen(1)
        while True:
            conn, addr = srv.accept()
            self.get_logger().info(f"노트북 연결: {addr}")
            try:
                self._recv(conn)
            except OSError:
                pass
            conn.close()
            self.get_logger().info("노트북 연결 끊김 — 안전 정지")
            self._stop()   # 연결 끊기면 바퀴 정지

    def _recv(self, conn):
        buf = b""
        while True:
            data = conn.recv(1024)
            if not data:
                break
            buf += data
            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                self._handle(line.decode(errors="ignore").strip())

    def _handle(self, line: str):
        if not line:
            return
        if line.startswith("S:"):                # 서보 명령
            m = String(); m.data = line[2:]
            self.pub_servo.publish(m)
        elif line.startswith("V:"):              # 바퀴 cmd_vel
            try:
                lin, ang = line[2:].split(",")
                t = Twist()
                t.linear.x = float(lin)
                t.angular.z = float(ang)
                self.pub_cmd.publish(t)
            except ValueError:
                pass

    def _stop(self):
        self.pub_cmd.publish(Twist())            # 0 속도 (정지)
        s = String(); s.data = "SCAN_STOP"
        self.pub_servo.publish(s)


def main():
    rclpy.init()
    node = CmdServer()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
