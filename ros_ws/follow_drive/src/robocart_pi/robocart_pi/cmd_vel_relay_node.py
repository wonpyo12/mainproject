#!/usr/bin/env python3
"""
[라즈베리파이] cmd_vel 중계 + 워치독 노드

  /robocart/cmd_vel (geometry_msgs/Twist, 노트북에서 발행)
      → 20Hz 중계 →  /cmd_vel  (turtlebot3_node 가 구독해 바퀴 구동)

안전 핵심:
  1) 워치독 — 노트북↔Pi 는 Wi-Fi라 끊길 수 있다. 0.5초간 새 명령이 없으면
     자동으로 0 Twist(정지)를 보낸다. (영상/네트워크 끊겨도 폭주하지 않음)
  2) 속도 상한 — burger 사양으로 하드 클램프 (linear ≤ 0.22 m/s, angular ≤ 1.0 rad/s).

실행:
  ros2 run robocart_pi cmd_vel_relay_node
"""
import rclpy
from rclpy.node import Node
from geometry_msgs.msg import Twist


class CmdVelRelayNode(Node):
    MAX_LIN = 0.22   # burger 최대 선속도(m/s)
    MAX_ANG = 1.0    # 회전 상한(rad/s) — 안전 위해 2.84 보다 보수적으로
    TIMEOUT = 0.5    # 워치독(초)
    RATE = 20.0      # 발행 주기(Hz)

    def __init__(self):
        super().__init__('cmd_vel_relay_node')

        self.declare_parameter('timeout', self.TIMEOUT)
        self.declare_parameter('max_linear', self.MAX_LIN)
        self.declare_parameter('max_angular', self.MAX_ANG)
        self.timeout = float(self.get_parameter('timeout').value)
        self.max_lin = float(self.get_parameter('max_linear').value)
        self.max_ang = float(self.get_parameter('max_angular').value)

        self.last_cmd = Twist()
        self.last_stamp = self.get_clock().now()

        self.pub = self.create_publisher(Twist, '/cmd_vel', 10)
        self.create_subscription(Twist, '/robocart/cmd_vel', self.on_cmd, 10)
        self.timer = self.create_timer(1.0 / self.RATE, self.tick)
        self._stopped_logged = False
        self.get_logger().info(
            f'cmd_vel 중계 시작 — /robocart/cmd_vel → /cmd_vel '
            f'(워치독 {self.timeout}s, 상한 lin={self.max_lin} ang={self.max_ang})')

    @staticmethod
    def _clamp(v, lim):
        return max(-lim, min(lim, v))

    def on_cmd(self, msg: Twist):
        self.last_cmd = msg
        self.last_stamp = self.get_clock().now()
        self._stopped_logged = False

    def tick(self):
        age = (self.get_clock().now() - self.last_stamp).nanoseconds * 1e-9
        out = Twist()
        if age <= self.timeout:
            out.linear.x = self._clamp(self.last_cmd.linear.x, self.max_lin)
            out.angular.z = self._clamp(self.last_cmd.angular.z, self.max_ang)
        else:
            # 워치독 — 명령 끊김 → 정지
            if not self._stopped_logged:
                self.get_logger().warn(
                    f'{self.timeout}s 동안 cmd_vel 없음 → 정지(워치독)')
                self._stopped_logged = True
        self.pub.publish(out)


def main():
    rclpy.init()
    node = CmdVelRelayNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        # 종료 시 확실히 정지
        try:
            node.pub.publish(Twist())
        except Exception:
            pass
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
