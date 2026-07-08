#!/usr/bin/env python3
"""
[라파/VM] 로봇 실시간 위치·텔레메트리 브리지 — ROS2 → 백엔드 HTTP

  /amcl_pose     (map 프레임, Nav2/AMCL 가동 시) ─┐
  /odom          (odom 프레임 폴백)               ├→ POST /api/hardware/pose      (5Hz)
  /battery_state (터틀봇 OpenCR 전압)            ─┴→ POST /api/hardware/telemetry (0.2Hz, 하트비트 겸용)
                                                     → socket.io room:admin → 웹 매장지도/대시보드

AMCL 을 한 번이라도 받으면: 마지막 /amcl_pose 에 그 이후의 /odom 이동량(델타)을
합성해 항상 map 프레임의 연속 위치를 보낸다 (Nav2 map→odom TF 와 같은 원리).
  ※ AMCL 은 로봇이 움직일 때만 간헐 발행 → 단순 시간 폴백으로 odom 원좌표와
    번갈아 보내면 좌표계가 달라 마커가 튄다. 그래서 폴백이 아니라 합성.
AMCL 을 아직 못 받았으면 /odom 원좌표를 그대로 보낸다(frame='odom').
텔레메트리는 pose 유무와 무관하게 주기 전송 → 웹의 온라인/오프라인 판정 하트비트.

주의: ROS_DOMAIN_ID 를 pose 를 발행하는 스택과 맞춰야 한다!
  - turtlebot3_bringup 을 도메인 지정 없이 켰으면 → 0 (기본값)
  - 커스텀 스택(cmd_server 등)은 → 30

실행 (라파):
  source /opt/ros/humble/setup.bash
  export ROS_DOMAIN_ID=0   # ← bringup 과 동일하게
  python3 pose_bridge.py --ros-args -p backend_url:=http://localhost:3000
"""
import json
import math
import threading
import time
import urllib.request

import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy
from geometry_msgs.msg import PoseWithCovarianceStamped
from nav_msgs.msg import Odometry
from sensor_msgs.msg import BatteryState

SEND_HZ = 5.0          # pose 전송 주기
TELEM_SEC = 5.0        # 텔레메트리(배터리·CPU온도) 전송 주기
ODOM_STALE_SEC = 3.0   # odom 이 이 시간 이상 끊기면 전송 중단(로봇 죽음)

# 터틀봇3 3셀 LiPo 전압 → 잔량 % (선형 근사, 12.6V 만충 / 10.8V 방전)
BATT_V_FULL = 12.6
BATT_V_EMPTY = 10.8


def yaw_from_quat(q):
    """쿼터니언 → yaw(rad). 평면 주행이라 roll/pitch 무시."""
    return math.atan2(2.0 * (q.w * q.z + q.x * q.y),
                      1.0 - 2.0 * (q.y * q.y + q.z * q.z))


def read_cpu_temp():
    """라파 SoC 온도(℃). 실패 시 None."""
    try:
        with open("/sys/class/thermal/thermal_zone0/temp") as f:
            return round(int(f.read().strip()) / 1000.0, 1)
    except OSError:
        return None


class PoseBridge(Node):
    def __init__(self):
        super().__init__("pose_bridge")
        self.declare_parameter("backend_url", "http://192.168.0.9:3000")
        self.declare_parameter("robot_serial", "CartMe-ROS2-08")
        self.backend = self.get_parameter("backend_url").value.rstrip("/")
        self.serial = self.get_parameter("robot_serial").value

        self.lock = threading.Lock()
        self.odom = None        # 현재 odom (x, y, theta)
        self.odom_at = 0.0
        self.amcl = None        # 마지막 AMCL 보정 위치 (map 프레임)
        self.amcl_odom = None   # 그 시점의 odom (델타 계산 기준점)
        self.battery = None     # %
        self.fail_logged = False

        # BEST_EFFORT 구독은 RELIABLE/BEST_EFFORT 어느 발행자와도 QoS 호환
        qos = QoSProfile(depth=10, reliability=ReliabilityPolicy.BEST_EFFORT)
        self.create_subscription(
            PoseWithCovarianceStamped, "/amcl_pose", self._on_amcl, qos)
        self.create_subscription(Odometry, "/odom", self._on_odom, qos)
        self.create_subscription(BatteryState, "/battery_state", self._on_batt, qos)

        self.create_timer(1.0 / SEND_HZ, self._tick_pose)
        self.create_timer(TELEM_SEC, self._tick_telemetry)

        self.get_logger().info(
            f"pose_bridge v2 시작 → {self.backend} (pose {SEND_HZ}Hz, telemetry {TELEM_SEC}s)")

    def _on_amcl(self, msg):
        p = msg.pose.pose
        with self.lock:
            # AMCL 보정 수신 — 이 시점의 odom 을 델타 기준점으로 함께 저장
            self.amcl = (p.position.x, p.position.y, yaw_from_quat(p.orientation))
            self.amcl_odom = self.odom

    def _on_odom(self, msg):
        p = msg.pose.pose
        with self.lock:
            self.odom = (p.position.x, p.position.y, yaw_from_quat(p.orientation))
            self.odom_at = time.time()

    def _on_batt(self, msg):
        # percentage 필드가 유효하면 사용, 아니면 전압 선형 근사
        pct = None
        if msg.percentage and 0.0 < msg.percentage <= 1.0:
            pct = msg.percentage * 100.0
        elif msg.percentage and 1.0 < msg.percentage <= 100.0:
            pct = msg.percentage
        elif msg.voltage and msg.voltage > 1.0:
            pct = (msg.voltage - BATT_V_EMPTY) / (BATT_V_FULL - BATT_V_EMPTY) * 100.0
        if pct is not None:
            with self.lock:
                self.battery = max(0.0, min(100.0, pct))

    def _tick_pose(self):
        now = time.time()
        with self.lock:
            if not self.odom or now - self.odom_at > ODOM_STALE_SEC:
                return  # odom 자체가 끊김 — 보낼 pose 없음
            if self.amcl and self.amcl_odom:
                # map 위치 = 마지막 AMCL 보정 ⊕ (그 이후 odom 델타)
                xa, ya, tha = self.amcl
                xo0, yo0, tho0 = self.amcl_odom
                xo, yo, tho = self.odom
                dx, dy, dth = xo - xo0, yo - yo0, tho - tho0
                a = tha - tho0   # odom 델타를 map 방향으로 돌리는 회전
                pose = (xa + math.cos(a) * dx - math.sin(a) * dy,
                        ya + math.sin(a) * dx + math.cos(a) * dy,
                        tha + dth)
                frame = "map"
            else:
                pose, frame = self.odom, "odom"  # AMCL 아직 없음
        body = {"x": pose[0], "y": pose[1], "theta": pose[2],
                "frame": frame, "robotSerialNumber": self.serial}
        # HTTP 는 타이머(ROS 스핀)를 막지 않게 별도 스레드에서
        threading.Thread(target=self._post, args=("pose", body), daemon=True).start()

    def _tick_telemetry(self):
        with self.lock:
            batt = self.battery
        body = {"battery": batt, "cpuTemp": read_cpu_temp(),
                "robotSerialNumber": self.serial}
        threading.Thread(target=self._post, args=("telemetry", body), daemon=True).start()

    def _post(self, path, body):
        req = urllib.request.Request(
            f"{self.backend}/api/hardware/{path}", data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json"}, method="POST")
        try:
            urllib.request.urlopen(req, timeout=2).read()
            if self.fail_logged:
                self.get_logger().info("백엔드 전송 복구")
                self.fail_logged = False
        except Exception as e:
            if not self.fail_logged:  # 실패 로그는 상태 변화 때 1번만
                self.get_logger().warning(f"백엔드 전송 실패(반복 생략): {e}")
                self.fail_logged = True


def main():
    rclpy.init()
    node = PoseBridge()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    node.destroy_node()
    rclpy.shutdown()


if __name__ == "__main__":
    main()
