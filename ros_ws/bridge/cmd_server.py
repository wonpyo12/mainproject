#!/usr/bin/env python3
"""
[라파] TCP 명령 수신 서버 — Windows(노트북)의 명령을 받아 ROS2 모터 토픽으로 발행

  Windows tracker ──TCP(9998)──→ cmd_server ──ROS2──→
       "S:SCAN_START"  / "S:CENTER" / "S:A95"  →  /robocart/servo  (String) → ESP32
       "V:0.12,0.5"                            →  /robocart/cmd_vel (Twist)  → 바퀴

  앱(백엔드) ──TCP(9998)──→ cmd_server ──ROS2──→
       "HALT"    → 정지 래치 ON  : 이후 V: 주행명령 무시 + 0속도 유지(그 자리 정지)
       "RESUME"  → 정지 래치 OFF : 다시 트래커 주행명령 통과
       "RETURN"  → /robocart/return (String "RETURN_HOME") 발행 → SLAM 복귀 노드 트리거
                   + 정지 래치 ON(추종 주행이 nav2 와 /cmd_vel 을 다투지 않게)

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
        self.pub_return = self.create_publisher(String, "/robocart/return", 10)
        self.halted = False   # 정지 래치 — True 면 V: 주행명령을 무시하고 0속도 유지
        threading.Thread(target=self._serve, daemon=True).start()
        self.get_logger().info(
            f"TCP 명령 서버 대기 {BIND} → /robocart/servo, /robocart/cmd_vel, /robocart/return")

    def _serve(self):
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind(BIND)
        srv.listen(5)
        # 클라이언트마다 스레드로 처리 — 트래커(영구 연결)와 앱 백엔드(1회성 정지/복귀
        # 연결)가 동시에 붙어도 막히지 않게 한다.
        while True:
            conn, addr = srv.accept()
            threading.Thread(target=self._client, args=(conn, addr), daemon=True).start()

    def _client(self, conn, addr):
        self.get_logger().info(f"클라이언트 연결: {addr}")
        state = {"drove": False}   # 이 연결이 V:(주행)을 보냈는지 — 트래커 식별용
        try:
            self._recv(conn, state)
        except OSError:
            pass
        conn.close()
        # 주행 클라이언트(트래커)가 끊겼을 때만 안전 정지. 백엔드의 1회성
        # 제어 연결(HALT/RESUME/RETURN)이 끊긴다고 바퀴를 멈추면 안 됨.
        if state["drove"]:
            self.get_logger().info(f"주행 연결 끊김 {addr} — 안전 정지")
            self._stop()
        else:
            self.get_logger().info(f"제어 연결 종료 {addr}")

    def _recv(self, conn, state):
        buf = b""
        while True:
            data = conn.recv(1024)
            if not data:
                break
            buf += data
            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                self._handle(line.decode(errors="ignore").strip(), state)

    def _handle(self, line: str, state):
        if not line:
            return
        cmd = line.upper()
        if cmd == "HALT":                        # 앱 정지 버튼 — 그 자리 래치 정지
            self.halted = True
            self.pub_cmd.publish(Twist())        # 즉시 0속도
            self.get_logger().info("HALT — 정지 래치 ON (주행명령 무시)")
            return
        if cmd == "RESUME":                      # 앱 추종 시작 — 래치 해제
            self.halted = False
            self.get_logger().info("RESUME — 정지 래치 OFF")
            return
        if cmd == "RETURN":                      # 앱 복귀 버튼 — SLAM 홈 복귀 트리거
            self.halted = True                   # 추종 주행 멈춰 nav2 에 /cmd_vel 양보
            self.pub_cmd.publish(Twist())
            r = String(); r.data = "RETURN_HOME"
            self.pub_return.publish(r)
            self.get_logger().info("RETURN — /robocart/return=RETURN_HOME 발행, 추종 정지")
            return
        if line.startswith("S:"):                # 서보 명령
            m = String(); m.data = line[2:]
            self.pub_servo.publish(m)
        elif line.startswith("V:"):              # 바퀴 cmd_vel
            state["drove"] = True                # 주행 클라이언트(트래커) 표시
            if self.halted:                      # 정지 래치 중엔 주행명령 무시 → 0속도 유지
                self.pub_cmd.publish(Twist())
                return
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
