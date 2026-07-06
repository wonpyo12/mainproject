#!/usr/bin/env python3
"""
FollowActuator — smart_cart_core 가 호출하는 `servo` 객체를 그대로 대체한다.

기존 tracker_node.py 의 RosServo 와 **완전히 동일한 인터페이스**
(move_to / start_sweep / hold / center / close + mode / current_angle / connected)
를 제공하되, 내부에서 두 액추에이터로 명령을 분배한다:

  · 사람 인식(추적) = core 가 move_to(angle) 호출
        → TurtleBot3:  /robocart/cmd_vel (Twist)  바퀴로 사람을 향해 회전+전진
        → ESP32:       /robocart/servo "CENTER"   서보는 중앙 유지(스캔 중지)

  · 사람 없음(검색) = core 가 start_sweep() 호출
        → ESP32:       /robocart/servo "SCAN_START"  서보 좌우 스캔
        → TurtleBot3:  cmd_vel = 0  (바퀴 정지 — 사용자 확정)

회전 제어: 서보 목표각(angle)이 곧 사람의 수평 위치를 나타낸다.
  err = angle - CENTER            (중앙보다 한쪽으로 치우친 정도)
  angular.z = clamp(-K_ROT * err / CENTER, ±MAX_ANG)
전진: 고정 속도(FORWARD_SPEED). 사람이 화면에서 사라지면 core 가 start_sweep 으로
전환하므로 자동으로 정지된다.

K_ROT 부호/CENTER/FORWARD_SPEED 는 ROS 파라미터로 노출 — 실제 방향 보고 튜닝.
"""
import time

from geometry_msgs.msg import Twist
from rclpy.node import Node
from std_msgs.msg import String


class FollowActuator:
    SERVO_MIN_INTERVAL = 0.1   # 서보 String 명령 최소 간격(초)

    def __init__(self, node: Node):
        self._node = node

        # ── 튜닝 파라미터 ───────────────────────────────────────
        node.declare_parameter('center_angle', 90.0)   # core 중앙각 규약과 일치시킬 것
        node.declare_parameter('k_rot', 1.0)           # 회전 P 게인(부호=회전 방향)
        node.declare_parameter('forward_speed', 0.12)  # 고정 전진 속도(m/s)
        node.declare_parameter('max_angular', 1.0)     # 회전 상한(rad/s)
        node.declare_parameter('deadband_deg', 5.0)    # 중앙 근처 회전 무시 폭(도)

        self.center = float(node.get_parameter('center_angle').value)
        self.k_rot = float(node.get_parameter('k_rot').value)
        self.forward = float(node.get_parameter('forward_speed').value)
        self.max_ang = float(node.get_parameter('max_angular').value)
        self.deadband = float(node.get_parameter('deadband_deg').value)

        # ── 퍼블리셔 ────────────────────────────────────────────
        self._pub_cmd = node.create_publisher(Twist, '/robocart/cmd_vel', 10)
        self._pub_servo = node.create_publisher(String, '/robocart/servo', 10)

        # ── RosServo 호환 상태 ──────────────────────────────────
        self.connected = True
        self.mode = 'hold'                 # 'track' / 'sweep' / 'hold'
        self.current_angle = self.center
        self._last_servo_cmd = None
        self._last_servo_send = 0.0

    # ── 내부 유틸 ──────────────────────────────────────────────
    def _send_servo(self, cmd: str, force: bool = False):
        now = time.time()
        if not force and cmd == self._last_servo_cmd:
            return
        if not force and (now - self._last_servo_send) < self.SERVO_MIN_INTERVAL:
            return
        self._last_servo_cmd = cmd
        self._last_servo_send = now
        m = String()
        m.data = cmd
        self._pub_servo.publish(m)

    def _publish_twist(self, lin: float, ang: float):
        t = Twist()
        t.linear.x = float(lin)
        t.angular.z = float(ang)
        self._pub_cmd.publish(t)

    @staticmethod
    def _clamp(v, lim):
        return max(-lim, min(lim, v))

    # ── core 가 호출하는 servo 인터페이스 ──────────────────────
    def move_to(self, angle: float):
        """추적 중 — 사람을 향해 바퀴 회전 + 전진. 서보는 중앙 유지."""
        self.mode = 'track'
        self.current_angle = float(angle)

        # 추적 진입 시 서보 스캔 멈추고 중앙 정렬(중복 전송은 _send_servo 가 걸러줌)
        self._send_servo('CENTER')

        err = float(angle) - self.center
        if abs(err) <= self.deadband:
            ang = 0.0
        else:
            ang = self._clamp(-self.k_rot * (err / self.center), self.max_ang)
        self._publish_twist(self.forward, ang)

    def start_sweep(self):
        """검색(사람 없음) — ESP32 서보 좌우 스캔, 바퀴 정지."""
        self.mode = 'sweep'
        self._send_servo('SCAN_START')
        self._publish_twist(0.0, 0.0)

    def hold(self):
        """정지 — 바퀴 정지, 서보 스캔 중지."""
        self.mode = 'hold'
        self._send_servo('SCAN_STOP')
        self._publish_twist(0.0, 0.0)

    def center(self):
        """서보 중앙 복귀 + 바퀴 정지."""
        self.mode = 'track'
        self._send_servo('CENTER', force=True)
        self._publish_twist(0.0, 0.0)

    def close(self):
        """종료 — 확실히 정지."""
        self._send_servo('CENTER', force=True)
        self._publish_twist(0.0, 0.0)
