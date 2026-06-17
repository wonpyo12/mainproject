#!/usr/bin/env python3
"""
SmartCart 라즈베리파이4 — ROS2 → USB 시리얼 브리지 노드

역할(시스템 동작 6단계):
  VMware가 발행한 /robocart/cmd (std_msgs/String) 명령을 구독해
  USB로 연결된 ESP32에 시리얼로 그대로 전달한다.

  VMware(영상처리) ──/robocart/cmd──▶ 이 노드 ──USB 시리얼──▶ ESP32 ──▶ 모터

명령 문자열: SCAN_START / SCAN_STOP / CENTER  (끝에 '\n' 붙여 송신)
ESP32 스케치(mg996r_control.ino)와 동일하게 9600 baud 사용.

의존성: rclpy(ROS2 Humble) + pyserial  (OpenCV 불필요 → 라즈베리파이 가볍게 유지)

실행:
  source /opt/ros/humble/setup.bash
  python3 raspi_cmd_bridge.py                 # 기본 포트 /dev/ttyUSB0
  python3 raspi_cmd_bridge.py --port /dev/ttyACM0 --baud 9600
"""
import argparse
import sys
import time

import rclpy
from rclpy.node import Node
from std_msgs.msg import String

try:
    import serial  # pyserial
except ImportError:
    print("[오류] pyserial 없음 → pip install pyserial", file=sys.stderr)
    sys.exit(1)

VALID_CMDS = {"SCAN_START", "SCAN_STOP", "CENTER"}


class CmdSerialBridge(Node):
    def __init__(self, port: str, baud: int):
        super().__init__("raspi_cmd_bridge")
        self.port = port
        self.baud = baud
        self.ser: serial.Serial | None = None
        self._open_serial()

        self.sub = self.create_subscription(
            String, "/robocart/cmd", self.on_cmd, 10
        )
        self.get_logger().info(
            f"구독: /robocart/cmd  →  시리얼: {self.port} @ {self.baud}bps"
        )

    def _open_serial(self) -> None:
        """ESP32 시리얼 포트 열기 (실패해도 노드는 살아있고, 명령 올 때 재시도)."""
        try:
            self.ser = serial.Serial(self.port, self.baud, timeout=1)
            time.sleep(2.0)  # ESP32 자동 리셋(부팅) 대기
            self.get_logger().info(f"[시리얼] {self.port} 연결됨")
        except serial.SerialException as e:
            self.ser = None
            self.get_logger().warn(
                f"[시리얼] {self.port} 열기 실패: {e} — 명령 수신 시 재시도"
            )

    def on_cmd(self, msg: String) -> None:
        cmd = msg.data.strip()
        if cmd not in VALID_CMDS:
            self.get_logger().warn(f"[무시] 알 수 없는 명령: {cmd!r}")
            return

        # 시리얼이 닫혀 있으면 재연결 시도
        if self.ser is None or not self.ser.is_open:
            self._open_serial()
            if self.ser is None:
                self.get_logger().error(f"[드롭] 시리얼 미연결 → {cmd} 전송 실패")
                return

        try:
            self.ser.write((cmd + "\n").encode())
            self.get_logger().info(f"CMD → ESP32: {cmd}")
        except serial.SerialException as e:
            self.get_logger().error(f"[시리얼] 전송 오류: {e} — 포트 닫고 재연결 예정")
            try:
                self.ser.close()
            except Exception:
                pass
            self.ser = None

    def destroy_node(self) -> bool:
        if self.ser is not None and self.ser.is_open:
            self.ser.close()
        return super().destroy_node()


def main() -> None:
    parser = argparse.ArgumentParser(description="ROS2 → ESP32 USB 시리얼 브리지")
    parser.add_argument("--port", default="/dev/ttyUSB0",
                        help="ESP32 시리얼 포트 (기본 /dev/ttyUSB0, 보드에 따라 /dev/ttyACM0)")
    parser.add_argument("--baud", type=int, default=9600,
                        help="보드레이트 (mg996r_control.ino와 동일하게 9600)")
    args = parser.parse_args()

    rclpy.init()
    node = CmdSerialBridge(args.port, args.baud)
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
