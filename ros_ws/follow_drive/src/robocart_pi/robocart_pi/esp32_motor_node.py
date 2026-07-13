#!/usr/bin/env python3
"""
[라즈베리파이] ESP32 서보 모터 노드

  /robocart/servo (std_msgs/String)  →  시리얼(/dev/ttyUSB0)  →  ESP32(mg996r)

노트북 tracker_node의 FollowActuator가 "사람 없음(검색)" 상태에서 좌우 스캔을,
"사람 인식" 상태에서 중앙 복귀를 명령으로 보낸다.

지원 명령(펌웨어 esp32_scan_motor.ino와 1:1):
  SCAN_START  좌우 스윕 시작 (45~135도)
  SCAN_STOP   스윕 정지(현재 각 유지)
  CENTER      90도 중앙 복귀
  A<각도>     지정 각도로 이동 (선택, 펌웨어가 지원할 때만)

ESP32가 연결돼 있지 않으면 명령을 로그로만 남기고 정상 동작(시뮬레이션).

실행:
  ros2 run robocart_pi esp32_motor_node
  ros2 run robocart_pi esp32_motor_node --ros-args -p port:=/dev/ttyUSB0 -p baud:=9600
"""
import rclpy
from rclpy.node import Node
from std_msgs.msg import String

try:
    import serial
except ImportError:
    serial = None


class Esp32MotorNode(Node):
    def __init__(self):
        super().__init__('esp32_motor_node')

        self.declare_parameter('port', '/dev/ttyUSB0')
        self.declare_parameter('baud', 9600)
        self.port = self.get_parameter('port').value
        self.baud = int(self.get_parameter('baud').value)

        self.ser = None
        self._open_serial()

        self.create_subscription(String, '/robocart/servo', self.on_cmd, 10)
        self.get_logger().info('ESP32 모터 노드 준비 — /robocart/servo 구독 중')

    def _open_serial(self):
        if serial is None:
            self.get_logger().error('pyserial 미설치 — 시뮬레이션 모드 (pip install pyserial)')
            return
        try:
            self.ser = serial.Serial(self.port, self.baud, timeout=0.1)
            self.get_logger().info(f'ESP32 연결됨: {self.port} @ {self.baud}bps')
        except serial.SerialException as e:
            self.ser = None
            self.get_logger().warn(
                f'ESP32 시리얼 열기 실패({self.port}): {e} — 시뮬레이션 모드로 계속')

    def on_cmd(self, msg: String):
        cmd = msg.data.strip()
        if not cmd:
            return
        if self.ser is not None:
            try:
                self.ser.write((cmd + '\n').encode())
            except serial.SerialException as e:
                self.get_logger().warn(f'시리얼 쓰기 실패: {e} — 재연결 시도')
                self.ser = None
                self._open_serial()
        else:
            self.get_logger().info(f'[SIM] ESP32 명령: {cmd}', throttle_duration_sec=1.0)

    def destroy_node(self):
        if self.ser is not None:
            try:
                self.ser.write(b'CENTER\n')
                self.ser.close()
            except serial.SerialException:
                pass
        super().destroy_node()


def main():
    rclpy.init()
    node = Esp32MotorNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
