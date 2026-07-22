# -*- coding: utf-8 -*-
"""[ROS2 로봇 제어 노드 모듈] ros_node.py
- 주요 역할: ROS2 노드(RobotController)를 생성하여 모터 속도(/cmd_vel P제어), Nav2 원점 복귀, AMCL 좌표 기록 및 TCP 제어 신호 수신 관리.
- 주요 구성:
  1. RobotController (ROS2 메인 노드)
  2. /robocart/resume, wait, return, reset 제어 토픽 연동
  3. compute (인물 BBox 위치 기반 P제어 전진/회전 속도 계산)
  4. lidar_bridge (카메라 일시 유실 시 라이다 거리 기반 백업 추적)
  5. search_rotate (완전 유실 시 제자리 회전 탐색)
  6. send_nav_goal & cancel_nav (Nav2 자율복귀 목표 전송 및 취소)
"""

from __future__ import annotations

import math
import time

from .config import (
    ACC_ANG, ACC_LIN_DOWN, ACC_LIN_UP, ALLOW_REVERSE, BRIDGE_CONE_DEG,
    BRIDGE_MAX_LIN, BRIDGE_MAX_M, BRIDGE_MIN_M, BRIDGE_MAX_SEC,
    BURGER_MAX_ANG, BURGER_MAX_LIN, CALIB_K, CENTER_DEADBAND,
    CENTER_HOLD_GAIN, DIST_FAR_CM, DIST_NEAR_CM, FRONT_STOP_M, KP_ANG,
    KP_LIN_DIST, MAX_ANG, MAX_LIN, MAX_LIN_REV, SEARCH_ANG,
    SEARCH_HALF_PERIOD, TARGET_DIST_CM
)
from .utils import DBG, _clamp, _quat_to_yaw, _yaw_to_quat, set_robot_led

try:
    import rclpy
    from rclpy.action import ActionClient
    from rclpy.node import Node
    from rclpy.qos import qos_profile_sensor_data
    from geometry_msgs.msg import PoseStamped, PoseWithCovarianceStamped, Twist
    from nav2_msgs.action import NavigateToPose
    from sensor_msgs.msg import LaserScan
    from std_msgs.msg import Empty, String
    _ROS2_OK = True
except Exception:
    _ROS2_OK = False


if _ROS2_OK:

    class RobotController(Node):
        """추종 속도 발행 + Nav2 원점 복귀 + 상태(FOLLOW/RETURN/IDLE/STOPPED) 관리."""

        def __init__(self, topic: str = "cmd_vel", esp_ip: str | None = None, pi_ip: str | None = None,
                     ang_sign: float = 1.0):
            super().__init__("person_follower_nav2_v3")
            self.esp_ip = esp_ip
            self.pi_ip = pi_ip
            self.ang_sign = ang_sign
            self._last_bearing = 0.0
            self._last_seen_t = None
            self.trigger_register = False
            self.is_registered = False

            self.create_subscription(Empty, "/robocart/wait", self._wait_cb, 10)
            self.create_subscription(Empty, "/robocart/resume", self._resume_cb, 10)
            self.create_subscription(String, "/robocart/return", self._return_cb, 10)
            self.create_subscription(Empty, "/robocart/reset", self._reset_cb, 10)

            self.cmd_vel_pub = self.create_publisher(Twist, topic, 10)
            self.nav_client = ActionClient(self, NavigateToPose, "navigate_to_pose")
            self.create_subscription(PoseWithCovarianceStamped, "amcl_pose",
                                     self._amcl_cb, 10)
            self.create_subscription(LaserScan, "scan", self._scan_cb, qos_profile_sensor_data)

            self.latest_scan = None
            self.start_x = 0.0
            self.start_y = 0.0
            self.start_yaw = 0.0
            self.has_start_pose = False

            self.state = "STOPPED"
            self.last_v = 0.0
            self.last_w = 0.0
            self.last_dist_cm = 0.0
            self._search_start = None
            self._search_dir = 1.0
            self._nav_goal_handle = None
            self.get_logger().info(f"RobotController v3 준비 (FOLLOW + Nav2 RETURN). ESP_IP: {self.esp_ip}")

            set_robot_led(self.esp_ip, "STOPPED")

        def _wait_cb(self, msg):
            DBG.log("ros_cmd", cmd="wait", prev_state=self.state)
            self.cancel_nav()
            self.state = "STOPPED"
            self.send_stop()
            set_robot_led(self.esp_ip, "STOPPED")
            self.get_logger().info("[Cmd] 앱/웹 정지(HALT) 명령 수신 -> STOPPED 상태 전환. LED 빨간불.")

        def _resume_cb(self, msg):
            DBG.log("ros_cmd", cmd="resume", prev_state=self.state)
            if self.state != "FOLLOW":
                self.cancel_nav()
                if not self.is_registered:
                    self.trigger_register = True
                    self.get_logger().info("[Cmd] 앱/웹 시작(RESUME) 명령 수신 -> 신규 사용자 등록 시작 예정.")
                else:
                    self.state = "FOLLOW"
                    self.send_stop()
                    set_robot_led(self.esp_ip, "STANDBY")
                    self.get_logger().info("[Cmd] 앱/웹 시작(RESUME) 명령 수신 -> 주행 활성화 (기등록 사용자). LED 노란불.")

        def _return_cb(self, msg):
            DBG.log("ros_cmd", cmd="return", data=str(msg.data), prev_state=self.state)
            if msg.data == "RETURN_HOME":
                if self.state != "RETURN":
                    self.state = "RETURN"
                    self.is_registered = False
                    self.send_stop()
                    set_robot_led(self.esp_ip, "RUNNING")
                    self.get_logger().info("[Cmd] 복귀(RETURN) 수신 -> 정지·RETURN 전환. 주행은 RPi return_controller 전담.")

        def _reset_cb(self, msg):
            DBG.log("ros_cmd", cmd="reset", prev_state=self.state)
            if self.state == "RETURN":
                self.state = "STOPPED"
                self.send_stop()
                set_robot_led(self.esp_ip, "STOPPED")
                self.get_logger().info("[Cmd] 복귀 완료(reset) 수신 -> STOPPED. 다음 사용자 대기.")

        def _amcl_cb(self, msg):
            p0 = msg.pose.pose
            yaw0 = _quat_to_yaw(p0.orientation.x, p0.orientation.y,
                                p0.orientation.z, p0.orientation.w)
            now_p = time.time()
            if now_p - getattr(self, "_pose_log_t", 0.0) >= 1.0:
                self._pose_log_t = now_p
                DBG.log("pose", x=round(p0.position.x, 3), y=round(p0.position.y, 3),
                        yaw=round(math.degrees(yaw0), 1), state=self.state)
            if not self.has_start_pose:
                p = msg.pose.pose
                self.start_x = p.position.x
                self.start_y = p.position.y
                self.start_yaw = _quat_to_yaw(p.orientation.x, p.orientation.y,
                                              p.orientation.z, p.orientation.w)
                self.has_start_pose = True
                DBG.log("nav", act="start_pose", x=round(self.start_x, 3),
                        y=round(self.start_y, 3), yaw=round(math.degrees(self.start_yaw), 1))
                self.get_logger().info(
                    f"시작 위치 저장: ({self.start_x:.2f}, {self.start_y:.2f}, "
                    f"{math.degrees(self.start_yaw):.0f}deg)"
                )

        def _scan_cb(self, msg):
            self.latest_scan = msg

        def front_blocked(self) -> bool:
            scan = self.latest_scan
            if scan is None or not scan.ranges:
                return False
            n = len(scan.ranges)
            k = max(1, n // 24)
            idxs = list(range(0, k)) + list(range(n - k, n))
            vals = [scan.ranges[i] for i in idxs
                    if scan.ranges[i] > 0.0 and math.isfinite(scan.ranges[i])]
            return bool(vals) and min(vals) < FRONT_STOP_M

        @staticmethod
        def _bearing_to_idx(scan, bearing_rad):
            if scan.angle_increment <= 0.0:
                return None
            n = len(scan.ranges)
            return int(round((bearing_rad - scan.angle_min) / scan.angle_increment)) % n

        def _lidar_dist_cm(self, cx_norm):
            scan = self.latest_scan
            if scan is None or not scan.ranges:
                return None
            bearing_rad = (0.5 - cx_norm) * math.radians(70.0)
            center = self._bearing_to_idx(scan, bearing_rad)
            if center is None:
                return None
            n = len(scan.ranges)
            half = max(1, int(round(math.radians(15.0) / scan.angle_increment)))
            valid = []
            for offset in range(-half, half + 1):
                r = scan.ranges[(center + offset) % n]
                if scan.range_min < r < scan.range_max and math.isfinite(r):
                    valid.append(r)
            return min(valid) * 100.0 if valid else None

        def compute(self, bbox, frame_w, frame_h, is_tracking):
            if not is_tracking or bbox is None or frame_w <= 0:
                self.last_dist_cm = 0.0
                return 0.0, 0.0
            x1, y1, x2, y2 = bbox
            cx = (x1 + x2) / 2.0
            cx_norm = cx / frame_w
            self._last_bearing = (0.5 - cx_norm) * math.radians(70.0)
            self._last_seen_t = time.time()

            lidar_cm = self._lidar_dist_cm(cx_norm)
            if lidar_cm is not None:
                dist_cm = lidar_cm
                self._dist_mode = "LiDAR"
            else:
                dist_cm = CALIB_K / max(1, x2 - x1)
                self._dist_mode = "Camera"
            self.last_dist_cm = dist_cm

            if DIST_NEAR_CM <= dist_cm <= DIST_FAR_CM:
                v = 0.0
            else:
                err = dist_cm - TARGET_DIST_CM
                v = _clamp(KP_LIN_DIST * err, -MAX_LIN, MAX_LIN)
                if v < 0:
                    v = 0.0 if not ALLOW_REVERSE else max(v, -MAX_LIN_REV)

            err_c = (cx - frame_w / 2.0) / (frame_w / 2.0)
            w = 0.0 if abs(err_c) < CENTER_DEADBAND else _clamp(
                -KP_ANG * err_c * self.ang_sign, -MAX_ANG, MAX_ANG
            )
            if w != 0.0:
                self._search_dir = 1.0 if w > 0 else -1.0
            if v > 0:
                v *= max(0.0, 1.0 - abs(err_c) * CENTER_HOLD_GAIN)
            return v, w

        def lidar_bridge(self):
            if self._last_seen_t is None or time.time() - self._last_seen_t > BRIDGE_MAX_SEC:
                return None
            scan = self.latest_scan
            if scan is None or not scan.ranges:
                return None
            n = len(scan.ranges)
            center = self._bearing_to_idx(scan, self._last_bearing)
            if center is None:
                return None
            half = max(1, int(round(math.radians(BRIDGE_CONE_DEG) / scan.angle_increment)))
            best = None
            for off in range(-half, half + 1):
                idx = (center + off) % n
                r = scan.ranges[idx]
                if (scan.range_min < r < scan.range_max and math.isfinite(r)
                        and BRIDGE_MIN_M < r < BRIDGE_MAX_M):
                    if best is None or r < best[0]:
                        ang = scan.angle_min + idx * scan.angle_increment
                        ang = math.atan2(math.sin(ang), math.cos(ang))
                        best = (r, ang)
            if best is None:
                return None
            dist_cm = best[0] * 100.0
            self._last_bearing = best[1]
            self.last_dist_cm = dist_cm
            self._dist_mode = "BRIDGE"
            if DIST_NEAR_CM <= dist_cm <= DIST_FAR_CM:
                v = 0.0
            else:
                v = _clamp(KP_LIN_DIST * (dist_cm - TARGET_DIST_CM), 0.0, BRIDGE_MAX_LIN)
            w = _clamp(KP_ANG * best[1] * self.ang_sign, -MAX_ANG, MAX_ANG)
            return v, w

        def search_rotate(self):
            now = time.time()
            if self._search_start is None:
                self._search_start = now
            self.last_dist_cm = 0.0
            self._dist_mode = "SEARCH"
            phase = int((now - self._search_start) / SEARCH_HALF_PERIOD)
            w = self._search_dir * (SEARCH_ANG if phase % 2 == 0 else -SEARCH_ANG)
            return 0.0, w

        def reset_search(self):
            self._search_start = None

        def send_velocity(self, v, w):
            if self.state != "FOLLOW":
                return
            if v > 0 and self.front_blocked():
                v = 0.0
            now = time.time()
            dt = _clamp(now - getattr(self, "_sm_t", now), 0.02, 0.3)
            self._sm_t = now
            up, down = ACC_LIN_UP * dt, ACC_LIN_DOWN * dt
            if abs(v) > abs(self.last_v):
                v = _clamp(v, self.last_v - up, self.last_v + up)
            else:
                v = _clamp(v, self.last_v - down, self.last_v + down)
            w = _clamp(w, self.last_w - ACC_ANG * dt, self.last_w + ACC_ANG * dt)
            self.publish(v, w)

        def publish(self, v, w):
            v = _clamp(float(v), -BURGER_MAX_LIN, BURGER_MAX_LIN)
            w = _clamp(float(w), -BURGER_MAX_ANG, BURGER_MAX_ANG)
            msg = Twist()
            msg.linear.x = v
            msg.angular.z = w
            self.cmd_vel_pub.publish(msg)
            self.last_v, self.last_w = v, w

        def send_stop(self):
            self.publish(0.0, 0.0)

        def send_nav_goal(self, x, y, yaw):
            if not self.nav_client.wait_for_server(timeout_sec=2.0):
                self.get_logger().warn("Nav2 액션 서버 없음 → 복귀 불가. FOLLOW 유지.")
                DBG.log("nav", act="server_missing")
                self.state = "FOLLOW"
                return
            qx, qy, qz, qw = _yaw_to_quat(yaw)
            goal = NavigateToPose.Goal()
            goal.pose.header.frame_id = "map"
            goal.pose.header.stamp = self.get_clock().now().to_msg()
            goal.pose.pose.position.x = float(x)
            goal.pose.pose.position.y = float(y)
            goal.pose.pose.orientation.z = qz
            goal.pose.pose.orientation.w = qw
            self.get_logger().info(f"복귀 목표 전송: ({x:.2f}, {y:.2f})")
            DBG.log("nav", act="goal_sent", x=round(float(x), 3), y=round(float(y), 3),
                    yaw=round(math.degrees(yaw), 1), state=self.state)
            fut = self.nav_client.send_goal_async(goal)
            fut.add_done_callback(self._nav_resp_cb)

        def _nav_resp_cb(self, future):
            gh = future.result()
            if not gh.accepted:
                self.get_logger().warn("복귀 목표 거부됨 → FOLLOW 복귀.")
                DBG.log("nav", act="rejected")
                self.state = "FOLLOW"
                return
            DBG.log("nav", act="accepted")
            self._nav_goal_handle = gh
            gh.get_result_async().add_done_callback(self._nav_done_cb)

        def _nav_done_cb(self, future):
            self._nav_goal_handle = None
            try:
                _st = future.result().status
            except Exception:
                _st = -1
            DBG.log("nav", act="done", status=_st, state=self.state)
            if self.state == "RETURN":
                self.get_logger().info("원점 도착 → 정지(STOPPED). 추종 재개는 앱 시작(QR) 또는 '추종' 입력.")
                self.state = "STOPPED"
                self.send_stop()
                set_robot_led(self.esp_ip, "STOPPED")

        def cancel_nav(self):
            if self._nav_goal_handle is not None:
                DBG.log("nav", act="cancel", state=self.state)
                try:
                    self._nav_goal_handle.cancel_goal_async()
                except Exception:
                    pass
                self._nav_goal_handle = None

else:
    RobotController = None   # type: ignore
