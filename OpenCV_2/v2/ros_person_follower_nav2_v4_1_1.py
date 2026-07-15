#!/usr/bin/env python3
"""
ros_person_follower_nav2_v4 — 등록 사용자 인식 + 추종 + Nav2 원점 복귀 (분산 처리판)

v2 대비 변경
  - ReID 모델 OSNet-x0.25 → OSNet-x1.0 교체 (임베딩 품질↑, 인식률 향상 목적).
    ※ x0.25↔x1.0 임베딩은 비호환 → 프로필 분리(robocart_profile_v3.json), 재등록 필요.

설계
  - 인식부: robocart_light(YOLOv8n-ONNX + OSNet-ONNX + 색상) 파이프라인을 그대로 이식.
            DetectionWorker(비동기 검출) + KCF 보간 + 등록(앞/뒤) + ReID/색상/위치 가중 스코어링.
            → "아무나"가 아니라 '등록된 1명'만 추종한다.
  - 영상부: 라즈베리파이 pi_camera_streamer.py 의 MJPEG(:5000)을 VM이 받아 추론(분산 처리).
            (작업순서 1번: 로컬 카메라 → 분산 MJPEG 수신으로 교체)
  - 주행부: ros_person_follower_nav2.py 의 주행/복귀 기능을 RobotController 한 노드로 통합.
            FOLLOW = 인식 bbox → /cmd_vel(Twist) P제어,  RETURN = Nav2 navigate_to_pose 복귀.
            터미널에 '복귀'/'추종' 입력으로 모드 전환(원본과 동일 UX).

추가 기능
  - 재등록 시 기존 프로필 파일을 먼저 삭제(기록 누적 방지).
  - 판정 인식률(%)을 화면 박스 라벨 / 상단 HUD / 터미널 로그에 표시.

실행(VM)
  source /opt/ros/humble/setup.bash
  export TURTLEBOT3_MODEL=burger
  # (선택) Nav2 복귀를 쓰려면 별도 터미널에서 navigation2 + rviz 먼저 기동
  python3 ros_person_follower_nav2_v4.py --pi-ip 192.168.0.23 --register

  q : 종료 / 터미널에 '복귀' 또는 '추종' 입력 : 모드 전환

의존(같은 폴더): light_features.py, light_models.py, models_light/
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
import threading
import time
import urllib.request
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np

import light_features as LF
from light_models import OnnxYolo, OnnxReID, FaceOrient

# ── ROS2 (없어도 인식-only 로 동작하도록 graceful) ─────────────────────────────
try:
    import rclpy
    from rclpy.node import Node
    from rclpy.action import ActionClient
    from rclpy.qos import qos_profile_sensor_data
    from geometry_msgs.msg import Twist, PoseStamped, PoseWithCovarianceStamped
    from sensor_msgs.msg import LaserScan
    from nav2_msgs.action import NavigateToPose
    _ROS2_OK = True
except Exception:
    _ROS2_OK = False


HERE = Path(__file__).resolve().parent
MODELS_DIR   = HERE / "models_light"
PROFILE_PATH = HERE / "robocart_profile_v3.json"
RECORD_SEC = 0.0   # --record-sec: 화면 녹화 시간(초), 0=끔
_REC = None        # 녹화 상태(VideoWriter 등) — run_tracking 내부에서 초기화

REID_ONNX  = MODELS_DIR / "osnet_x1_0.onnx"
REID_MODEL_NAME = "x1_0"   # main()에서 --reid-model 값으로 갱신. 프로필 호환성 검사용
YUNET_ONNX = MODELS_DIR / "face_detection_yunet.onnx"
YOLO_ONNX_BY_SZ = {320: MODELS_DIR / "yolov8n.onnx",
                   256: MODELS_DIR / "yolov8n_256.onnx",
                   192: MODELS_DIR / "yolov8n_192.onnx"}

DETECT_INTERVAL = 8      # 검출 사이 KCF 보간 프레임 수
KCF_MAX_AGE     = 40     # KCF 단독 보간 허용 최대 (초과 시 강제 재검출)

WINDOW = "robocart v3 - Registered User Follow + Nav2"


def pick_yolo_onnx(imgsz: int):
    p = YOLO_ONNX_BY_SZ.get(imgsz)
    if p and p.exists():
        return p, imgsz
    return MODELS_DIR / "yolov8n.onnx", 320


# ══════════════════════════════════════════════════════════════════════════════
# 디버그 로그 (JSONL) — analyze_debug.py 로 분석
# ══════════════════════════════════════════════════════════════════════════════

class DebugLog:
    """인식/주행 이벤트를 debug_logs/run_*.jsonl 에 기록. 비활성화 시 no-op."""

    def __init__(self, enabled: bool = False):
        self.f = None
        self.path = None
        if enabled:
            d = HERE / "debug" / "debug_logs"
            d.mkdir(parents=True, exist_ok=True)
            self.path = d / f"run_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jsonl"
            self.f = open(self.path, "w", encoding="utf-8", buffering=1)  # 줄 단위 flush

    def log(self, ev: str, **kw):
        if self.f is None:
            return
        kw["ev"] = ev
        kw["t"] = round(time.time(), 3)
        try:
            self.f.write(json.dumps(kw, ensure_ascii=False) + "\n")
        except Exception:
            pass


DBG = DebugLog(enabled=False)   # main()에서 --no-debug-log 아니면 활성화


# ══════════════════════════════════════════════════════════════════════════════
# 분산 카메라 — 라즈베리파이 MJPEG(:5000) 수신 (작업순서 1번)
# ══════════════════════════════════════════════════════════════════════════════

class MjpegCamera:
    """HTTP MJPEG 스트림을 직접 파싱해 최신 프레임만 보관.

    OpenCV FFMPEG 백엔드의 네트워크 스트림 크래시(Segfault/Abort)를 피하려고
    urllib 로 바이트를 받아 JPEG 경계(FFD8..FFD9)로 직접 잘라 디코드한다.
    (ros_person_follower_nav2.py 의 VideoCaptureThreaded 와 동일 전략)

    인터페이스는 robocart_light 의 Camera 와 동일: read()->frame|None / opened() / stop()
    """

    def __init__(self, url: str, mirror: bool = False):
        self.url = url
        self._mirror = mirror          # True: 좌우반전 보정 (카메라가 거울상일 때)
        self._frame: np.ndarray | None = None
        self._frame_at = 0.0           # 마지막 프레임 수신 시각 (신선도 판정)
        self._rx_n = 0                 # 수신 프레임 카운터 (fps 진단용)
        self._running = True
        self._th = threading.Thread(target=self._loop, daemon=True)
        self._th.start()

    def rx_count(self) -> int:
        return self._rx_n

    def _loop(self):
        while self._running:
            stream = None
            try:
                stream = urllib.request.urlopen(self.url, timeout=3.0)
                buf = b""
                while self._running:
                    chunk = stream.read(8192)
                    if not chunk:
                        break
                    buf += chunk
                    # 최신 프레임만 디코드: 버퍼에 완성 JPEG이 여러 장 쌓여 있으면
                    # 마지막 한 장만 취하고 이전 것은 폐기 (디코드가 수신을 못 따라갈 때
                    # 지연이 계속 누적되는 것을 방지)
                    b = buf.rfind(b"\xff\xd9")    # 마지막 JPEG EOI
                    if b == -1:
                        continue
                    a = buf.rfind(b"\xff\xd8", 0, b)   # 그 앞의 SOI
                    if a == -1:
                        buf = buf[b + 2:]
                        continue
                    jpg = buf[a:b + 2]
                    buf = buf[b + 2:]
                    f = cv2.imdecode(np.frombuffer(jpg, np.uint8), cv2.IMREAD_COLOR)
                    if f is not None:
                        if self._mirror:
                            f = cv2.flip(f, 1)   # 좌우반전 보정 (인식·라이다 방위 일관)
                        self._frame = f
                        self._frame_at = time.time()
                        self._rx_n += 1
            except Exception:
                # 프레임은 지우지 않음 — read()의 신선도 검사가 오래된 프레임을 걸러줌.
                # (여기서 None 으로 지우면 잠깐의 끊김에도 화면이 검게 멈춤)
                pass
            finally:
                if stream is not None:
                    try:
                        stream.close()
                    except Exception:
                        pass
            if self._running:
                time.sleep(0.3)               # 재연결 대기 (1.0→0.3: 끊김 시 공백 단축)

    def read(self):
        # 2초 이상 오래된 프레임은 없는 것으로 처리 (끊긴 스트림으로 주행 판단 방지)
        f = self._frame
        if f is None or time.time() - self._frame_at > 2.0:
            return None
        return f.copy()

    def opened(self):
        return self._running

    def stop(self):
        self._running = False


# ══════════════════════════════════════════════════════════════════════════════
# 주행 제어 노드 — FOLLOW(bbox→cmd_vel) + RETURN(Nav2 복귀)
# ══════════════════════════════════════════════════════════════════════════════

# TurtleBot3 Burger 하드 속도 한계 (절대 초과 금지)
BURGER_MAX_LIN = 0.22
BURGER_MAX_ANG = 2.84

# 거리 추정(bbox 폭 핀홀): 거리[cm] = CALIB_K / bbox_width[px]  (실차 보정 필요)
CALIB_K        = 22000.0
# 거리 유지 기준: TARGET 35 / NEAR 30 / FAR 40 cm (NEAR 30cm > FRONT_STOP 25cm)
TARGET_DIST_CM = 35.0
DIST_NEAR_CM   = 30.0
DIST_FAR_CM    = 40.0
CENTER_DEADBAND = 0.05   # 0.08→0.05: 중앙 유지 판정 강화
# 중앙 우선 주행: |중심 오차|×이 값 만큼 전진 감속 (1.5면 오차 0.67에서 전진 0)
CENTER_HOLD_GAIN = 1.5

KP_LIN_DIST = 0.006      # 0.004→0.006: 사람 보행 속도 대응 (err 20cm 이상이면 MAX_LIN 도달)
KP_ANG      = 0.8        # 0.5→0.8: 회전 추종 반응 강화 (시야 이탈 방지)
MAX_LIN     = 0.16       # [07-15] 0.18의 90% — 전원 상황 맞춤 감속 (원복: 0.18)
MAX_LIN_REV = 0.08
MAX_ANG     = 0.9        # [07-15] 1.0의 90% — 제자리 회전 전류 피크 완화 (원복: 1.0)
ALLOW_REVERSE = True

FRONT_STOP_M = 0.25      # 전방 라이다 이 거리 이내 장애물이면 전진 0 (안전)

# 유실 탐색: 등록자 놓치면 제자리서 좌우 교대 저속 회전(v=0)으로 재탐색
SEARCH_ANG         = 0.20   # 탐색 회전 각속도(rad/s)
SEARCH_HALF_PERIOD = 15.7   # 한 방향 회전 지속(초) — 좌우 180도(π rad) 회전: π/SEARCH_ANG ≈ 15.7초
SEARCH_START_DELAY = 5.0   # 유실 후 이 시간(초) 동안은 정지 대기, 넘겨야 탐색 회전 시작

# 등록 촬영: 방향(front/back)당 최소 샘플 수 — 미달이면 REG_MAX_SEC까지 수집 연장
REG_MIN_SAMPLES = 20
REG_MAX_SEC     = 15.0

# 라이다 브리징: 카메라 유실 직후 마지막 방위의 라이다 덩어리(사람 다리)를 잠시 추종
BRIDGE_MAX_SEC  = 2.0    # 마지막 카메라 추적 후 이 시간까지만 브리징 허용
BRIDGE_CONE_DEG = 20     # 마지막 방위 ± 탐색 콘(도)
BRIDGE_MIN_M    = 0.2    # 이보다 가까우면 무시 (로봇 자신/벽 오인 방지)
BRIDGE_MAX_M    = 1.5    # 이보다 멀면 사람 아님으로 간주
BRIDGE_MAX_LIN  = 0.10   # 브리징 중 전진 상한 (보수적, 후진 없음)
# 등록 중 YOLO 재검출 주기(샘플 단위) — 사이 프레임은 직전 bbox 재사용(ReID만)
REG_DETECT_EVERY = 5

# 부드러운 주행: 속도 명령 가속도 제한 (계단식 명령 → 미끄러지듯 변화)
ACC_LIN_UP   = 0.25   # 전진 가속 한계 (m/s²)
ACC_LIN_DOWN = 0.80   # 감속 한계 (안전상 감속은 빠르게)
ACC_ANG      = 2.5    # 회전 가속 한계 (rad/s²)

# 검출 공백 시 bbox 속도 외삽(예측 조향): 옛 위치가 아닌 현재 추정 위치로 조향
PRED_MAX_SEC = 0.8    # 마지막 검출 후 외삽 허용 최대 시간
PRED_MAX_VX  = 400.0  # 수평 이동 외삽 속도 상한 (px/s)


def _clamp(x, lo, hi):
    return max(lo, min(hi, x))


def _yaw_to_quat(yaw: float):
    return (0.0, 0.0, math.sin(yaw / 2.0), math.cos(yaw / 2.0))


def _quat_to_yaw(x, y, z, w):
    return math.atan2(2.0 * (w * z + x * y), 1.0 - 2.0 * (y * y + z * z))


if _ROS2_OK:

    class RobotController(Node):
        """추종 속도 발행 + Nav2 원점 복귀 + 상태(FOLLOW/RETURN/IDLE/STOPPED) 관리."""

        def __init__(self, topic: str = "cmd_vel", esp_ip: str = None, pi_ip: str = None,
                     ang_sign: float = 1.0):
            super().__init__("person_follower_nav2_v3")
            self.esp_ip = esp_ip
            self.pi_ip = pi_ip
            self.ang_sign = ang_sign   # 회전 방향 반전용 (-1.0: 카메라 미러/모터 배선 반대일 때)
            self._last_bearing = 0.0   # 마지막 카메라 추적 방위(rad, +=좌) — 라이다 브리징용
            self._last_seen_t = None   # 마지막 카메라 추적 시각
            self.trigger_register = False
            self.is_registered = False
            
            # 백엔드/앱 연동 제어 명령 구독
            from std_msgs.msg import Empty, String
            self.create_subscription(Empty, "/robocart/wait", self._wait_cb, 10)
            self.create_subscription(Empty, "/robocart/resume", self._resume_cb, 10)
            self.create_subscription(String, "/robocart/return", self._return_cb, 10)

            self.cmd_vel_pub = self.create_publisher(Twist, topic, 10)
            self.nav_client = ActionClient(self, NavigateToPose, "navigate_to_pose")
            self.create_subscription(PoseWithCovarianceStamped, "amcl_pose",
                                     self._amcl_cb, 10)
            # /scan 퍼블리셔는 BEST_EFFORT(센서 표준) → 기본 QoS(RELIABLE)로는 콜백이 안 불림.
            # sensor_data QoS(BEST_EFFORT)로 구독해야 라이다 거리(_lidar_dist_cm)가 동작한다.
            self.create_subscription(LaserScan, "scan", self._scan_cb, qos_profile_sensor_data)

            self.latest_scan = None
            self.start_x = 0.0
            self.start_y = 0.0
            self.start_yaw = 0.0
            self.has_start_pose = False

            self.state = "STOPPED"          # FOLLOW / RETURN / STOPPED
            self.last_v = 0.0
            self.last_w = 0.0
            self.last_dist_cm = 0.0
            self._search_start = None      # 유실 탐색 회전 시작 시각
            self._search_dir = 1.0         # 유실 탐색 시작 방향 — 마지막으로 본 박스 쪽(+1 좌 / -1 우)
            self._nav_goal_handle = None   # 진행 중 Nav2 목표 핸들(취소용)
            self.get_logger().info(f"RobotController v3 준비 (FOLLOW + Nav2 RETURN). ESP_IP: {self.esp_ip}")
            
            # 구동 시작 시 정지 상태(빨간불)로 대기
            set_robot_led(self.esp_ip, "STOPPED")

        # ── 앱/웹 제어 토픽 구독 콜백 ──
        # [이슈 #48] 외부 명령이 jsonl에 안 남아 정지 원인 특정 불가했음 → ros_cmd 이벤트로 기록
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
                    self.is_registered = False  # 다음 사용자를 위해 등록 리셋
                    self.send_stop()
                    set_robot_led(self.esp_ip, "RUNNING")
                    if not self.has_start_pose:
                        self.get_logger().warn("AMCL 시작 위치 미저장 → (0,0) 복귀 시도.")
                    self.send_nav_goal(self.start_x, self.start_y, self.start_yaw)
                    self.get_logger().info("[Cmd] 앱/웹 복귀(RETURN) 명령 수신 -> RETURN 상태 전환 (등록 리셋). LED 초록불.")

        # ── 구독 콜백 ──
        def _amcl_cb(self, msg):
            # [복귀 디버깅] 1초 간격 AMCL 위치 기록 — 복귀 궤적·위치 흔들림 분석용
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
                    f"{math.degrees(self.start_yaw):.0f}deg)")

        def _scan_cb(self, msg):
            self.latest_scan = msg

        def front_blocked(self) -> bool:
            """전방 좁은 콘에 FRONT_STOP_M 이내 장애물이 있으면 True (전진 차단용)."""
            scan = self.latest_scan
            if scan is None or not scan.ranges:
                return False
            n = len(scan.ranges)
            k = max(1, n // 24)                      # 전방 ±(약15도) 콘
            idxs = list(range(0, k)) + list(range(n - k, n))
            vals = [scan.ranges[i] for i in idxs
                    if scan.ranges[i] > 0.0 and math.isfinite(scan.ranges[i])]
            return bool(vals) and min(vals) < FRONT_STOP_M

        @staticmethod
        def _bearing_to_idx(scan, bearing_rad):
            """방위각(rad, 정면 0·CCW+) → ranges 인덱스.
            ranges 개수가 360이 아니어도(실측 246) angle_min/increment로 정확히 매핑."""
            if scan.angle_increment <= 0.0:
                return None
            n = len(scan.ranges)
            return int(round((bearing_rad - scan.angle_min) / scan.angle_increment)) % n

        def _lidar_dist_cm(self, cx_norm):
            """bbox 중심 방위각 ±15도 라이다 최솟값(cm). 유효 값 없으면 None."""
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
            return min(valid) * 100.0 if valid else None  # m → cm

        # ── FOLLOW: bbox → (v, w) ──
        def compute(self, bbox, frame_w, frame_h, is_tracking):
            if not is_tracking or bbox is None or frame_w <= 0:
                self.last_dist_cm = 0.0
                return 0.0, 0.0
            x1, y1, x2, y2 = bbox
            cx = (x1 + x2) / 2.0
            cx_norm = cx / frame_w
            # 라이다 브리징용: 마지막 추적 방위/시각 기록
            self._last_bearing = (0.5 - cx_norm) * math.radians(70.0)
            self._last_seen_t = time.time()

            # 라이다 우선, 없으면 bbox 폭 핀홀 폴백
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
                -KP_ANG * err_c * self.ang_sign, -MAX_ANG, MAX_ANG)
            if w != 0.0:
                # 사람이 화면 한쪽에 있을 때 그 쪽을 기억 → 유실 시 그 방향부터 탐색
                self._search_dir = 1.0 if w > 0 else -1.0
            # 중앙 우선 주행: 사람이 중앙에서 벗어날수록 전진을 감속해
            # 회전으로 먼저 중앙에 모은다 (가장자리로 밀려 시야 이탈하는 것 방지)
            if v > 0:
                v *= max(0.0, 1.0 - abs(err_c) * CENTER_HOLD_GAIN)
            return v, w

        # ── 라이다 브리징: 카메라 유실 직후 마지막 방위의 라이다 덩어리를 잠시 추종 ──
        def lidar_bridge(self):
            """카메라 추적이 끊긴 직후(BRIDGE_MAX_SEC 이내) 마지막 방위 ±콘에서
            사람으로 추정되는 가장 가까운 라이다 반사체를 향해 (v, w)를 만든다.
            조건이 안 되면 None (호출부에서 정지 처리)."""
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
            best = None   # (dist_m, bearing_rad)
            for off in range(-half, half + 1):
                idx = (center + off) % n
                r = scan.ranges[idx]
                if (scan.range_min < r < scan.range_max and math.isfinite(r)
                        and BRIDGE_MIN_M < r < BRIDGE_MAX_M):
                    if best is None or r < best[0]:
                        ang = scan.angle_min + idx * scan.angle_increment
                        ang = math.atan2(math.sin(ang), math.cos(ang))  # [-π, π] 정규화
                        best = (r, ang)
            if best is None:
                return None
            dist_cm = best[0] * 100.0
            self._last_bearing = best[1]      # 덩어리 방향으로 갱신 (이동 추적)
            self.last_dist_cm = dist_cm
            self._dist_mode = "BRIDGE"
            if DIST_NEAR_CM <= dist_cm <= DIST_FAR_CM:
                v = 0.0
            else:
                v = _clamp(KP_LIN_DIST * (dist_cm - TARGET_DIST_CM), 0.0, BRIDGE_MAX_LIN)
            w = _clamp(KP_ANG * best[1] * self.ang_sign, -MAX_ANG, MAX_ANG)
            return v, w

        # ── 유실 시 좌우 탐색 회전 (v=0, w=±SEARCH_ANG 교대) ──
        def search_rotate(self):
            now = time.time()
            if self._search_start is None:
                self._search_start = now
            self.last_dist_cm = 0.0
            self._dist_mode = "SEARCH"
            phase = int((now - self._search_start) / SEARCH_HALF_PERIOD)
            # 마지막으로 박스가 보였던 방향(_search_dir)부터 돌기 시작 → 반대쪽 헛돌기 방지
            w = self._search_dir * (SEARCH_ANG if phase % 2 == 0 else -SEARCH_ANG)
            return 0.0, w

        def reset_search(self):
            self._search_start = None

        def send_velocity(self, v, w):
            """FOLLOW 상태에서만 실제 발행 (RETURN 중엔 Nav2가 /cmd_vel 통제).
            가속도 제한 필터로 명령 급변을 걸러 부드럽게 주행."""
            if self.state != "FOLLOW":
                return
            if v > 0 and self.front_blocked():       # 안전: 전방 막히면 전진 취소
                v = 0.0
            now = time.time()
            dt = _clamp(now - getattr(self, "_sm_t", now), 0.02, 0.3)
            self._sm_t = now
            # 전진: 가속은 완만하게, 감속(정지 방향)은 빠르게 (안전)
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

        # ── RETURN: Nav2 복귀 ──
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
            self._nav_goal_handle = gh       # 취소 대비 핸들 보관
            gh.get_result_async().add_done_callback(self._nav_done_cb)

        def _nav_done_cb(self, future):
            self._nav_goal_handle = None
            try:
                _st = future.result().status   # 4=SUCCEEDED 5=CANCELED 6=ABORTED
            except Exception:
                _st = -1
            DBG.log("nav", act="done", status=_st, state=self.state)
            if self.state == "RETURN":       # 사용자가 이미 '추종'으로 전환했으면 유지
                self.get_logger().info("원점 도착 → 정지(STOPPED). 추종 재개는 앱 시작(QR) 또는 '추종' 입력.")
                self.state = "STOPPED"       # 복귀 완료 후 자동 추종 금지 (다음 사용자 대기)
                self.send_stop()
                set_robot_led(self.esp_ip, "STOPPED")

        def cancel_nav(self):
            """진행 중인 Nav2 복귀 목표 취소 (/cmd_vel 중복 발행 방지)."""
            if self._nav_goal_handle is not None:
                DBG.log("nav", act="cancel", state=self.state)
                try:
                    self._nav_goal_handle.cancel_goal_async()
                except Exception:
                    pass
                self._nav_goal_handle = None

else:
    RobotController = None   # type: ignore


# ══════════════════════════════════════════════════════════════════════════════
# 특징 추출 / 프로필
# ══════════════════════════════════════════════════════════════════════════════

def extract_features(crop, reid: OnnxReID):
    return {"reid_emb": reid.embed(crop), "color": LF.extract_color(crop)}


def _avg_embed(embs):
    embs = [e for e in embs if e]
    if not embs:
        return []
    m = np.mean(np.asarray(embs, np.float32), axis=0)
    n = float(np.linalg.norm(m))
    return (m / n).tolist() if n > 0 else m.tolist()


def _pick_diverse(embs, k=8):
    """수집 시간축에서 고르게 k개 대표 샘플 선택 (자세 다양성 확보).
    매칭 시 max 비교용 — 평균 1개보다 자세 변화에 훨씬 강함."""
    embs = [e for e in embs if e]
    if len(embs) <= k:
        return embs
    idx = np.linspace(0, len(embs) - 1, k).round().astype(int)
    return [embs[i] for i in idx]


def _avg_color(colors):
    if not colors:
        return {}
    out = {}
    for k in ("top_hist", "bot_hist", "top_bgr", "bot_bgr"):
        out[k] = np.mean(np.asarray([c[k] for c in colors], np.float32), axis=0).tolist()
    return out


def largest_bbox(bboxes):
    return max(bboxes, key=lambda b: (b[2] - b[0]) * (b[3] - b[1])) if bboxes else None


def save_profile(profile):
    PROFILE_PATH.write_text(json.dumps(profile, ensure_ascii=False, indent=2))
    print(f"[profile] 저장: {PROFILE_PATH}")


def load_profile():
    if PROFILE_PATH.exists():
        return json.loads(PROFILE_PATH.read_text())
    return None


# ══════════════════════════════════════════════════════════════════════════════
# 등록 (앞/뒤 촬영) — VM 디스플레이(cv2.imshow)로 안내
# ══════════════════════════════════════════════════════════════════════════════

def speak_on_pi(pi_ip, text):
    if not pi_ip:
        return
    def run():
        try:
            import urllib.parse
            import urllib.request
            encoded_text = urllib.parse.quote(text)
            # [07-15 백포트] "IP" 또는 "IP:포트" 허용 — 키오스크 음성 이관용 (주행 로직 무변경)
            host = pi_ip if ":" in str(pi_ip) else f"{pi_ip}:5000"
            url = f"http://{host}/speak?text={encoded_text}"
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=1.5) as response:
                pass
        except Exception as e:
            print(f"[speak_on_pi] 소리 출력 실패: {e}")
            
    import threading
    threading.Thread(target=run, daemon=True).start()


last_led_status = None

def set_robot_led(esp_ip, status, blocking=False):
    global last_led_status
    if not esp_ip or status == last_led_status:
        return
    last_led_status = status
    print(f"[set_robot_led] 아두이노({esp_ip})로 LED 상태 변경 전송: {status}")
    
    def run():
        try:
            import urllib.request
            import urllib.parse
            url = f"http://{esp_ip}/led?status={status}"
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=1.5) as response:
                pass
        except Exception as e:
            print(f"[set_robot_led] LED 제어 실패 ({status}): {e}")
            
    if blocking:
        run()
    else:
        import threading
        threading.Thread(target=run, daemon=True).start()


def _show(frame):
    cv2.imshow(WINDOW, frame)
    cv2.waitKey(1)


def register(cam, yolo, reid, user_id, grace_sec: float = 5.0, pi_ip: str = None):
    # [기능 2] 재촬영 시 기존 프로필 삭제 → 기록 누적 방지(항상 새 1개만 유지)
    if PROFILE_PATH.exists():
        PROFILE_PATH.unlink()
        print(f"[profile] 기존 프로필 삭제: {PROFILE_PATH.name}")

    speak_on_pi(pi_ip, "촬영을 시작합니다.")

    phases = [("front", "FRONT: face the camera"),
              ("back",  "BACK: turn around")]
    profile = {"user_id": user_id,
               "registered_at": datetime.now().isoformat(timespec="seconds"),
               "reid_model": REID_MODEL_NAME,   # 모델이 다르면 임베딩 호환 안 됨
               "phases": {}}

    # 위치 잡을 시간(grace) 카운트다운
    t_end = time.time() + grace_sec
    while time.time() < t_end:
        frame = cam.read()
        if frame is None:
            time.sleep(0.02); continue
        left = int(t_end - time.time()) + 1
        cv2.putText(frame, "STAND in view", (20, 50),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 255, 255), 2)
        cv2.putText(frame, f"capture starts in {left}s", (20, 95),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 200, 0), 2)
        _show(frame)

    for pname, instruct in phases:
        if pname == "back":
            speak_on_pi(pi_ip, "뒤돌아 주세요.")

        for sec in (3, 2, 1):
            t_end = time.time() + 1.0
            while time.time() < t_end:
                frame = cam.read()
                if frame is None:
                    time.sleep(0.02); continue
                cv2.putText(frame, instruct, (20, 50),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 255, 255), 2)
                cv2.putText(frame, f"start in {sec}", (20, 95),
                            cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 200, 0), 3)
                _show(frame)

        # ~3초간 샘플 수집. YOLO/ReID 는 워커 스레드에서 돌려 화면 멈춤 방지.
        embs, cols = [], []
        shared = {"bbox": None, "n": 0}
        stop_flag = {"v": False}
        lock = threading.Lock()

        def _worker():
            # 등록 중엔 대상이 제자리에 서 있으므로 무거운 YOLO 검출은
            # REG_DETECT_EVERY 샘플마다 한 번만 하고, 그 사이엔 직전 bbox를
            # 재사용해 가벼운 ReID 임베딩만 수행 → 샘플 수집 속도 수 배 향상
            last_bb = None
            since_det = REG_DETECT_EVERY   # 첫 프레임은 반드시 검출
            det_fails = 0
            last_rx = -1
            while not stop_flag["v"]:
                # 새 프레임이 도착했을 때만 처리 (같은 프레임 중복 샘플 방지)
                if hasattr(cam, "rx_count"):
                    rx = cam.rx_count()
                    if rx == last_rx:
                        time.sleep(0.005); continue
                    last_rx = rx
                f = cam.read()
                if f is None:
                    time.sleep(0.01); continue
                det_ms = 0.0
                if last_bb is None or since_det >= REG_DETECT_EVERY:
                    t0 = time.time()
                    bb = largest_bbox(yolo.detect(f))
                    det_ms = (time.time() - t0) * 1000
                    since_det = 0
                    if bb is None:
                        det_fails += 1
                        print(f"[register/{pname}] det={det_ms:.0f}ms 사람검출 실패 {det_fails}회 "
                              f"(frame {f.shape[1]}x{f.shape[0]})")
                        # 등록 중엔 대상이 제자리 → 일시적 검출 실패(블러/조명)는
                        # 직전 bbox로 계속 샘플 수집. 3연속 실패 시에만 bbox 폐기.
                        if last_bb is not None and det_fails < 3:
                            bb = last_bb
                        else:
                            last_bb = None
                            with lock:
                                shared["bbox"] = None
                            continue
                    else:
                        det_fails = 0
                        last_bb = bb
                else:
                    bb = last_bb
                since_det += 1
                x1, y1, x2, y2 = bb
                crop = f[max(0, y1):y2, max(0, x1):x2]
                if crop.size > 0:
                    t1 = time.time()
                    feat = extract_features(crop, reid)
                    emb_ms = (time.time() - t1) * 1000
                    if feat["reid_emb"]:
                        with lock:
                            embs.append(feat["reid_emb"]); cols.append(feat["color"])
                            shared["bbox"] = bb; shared["n"] = len(embs)
                        print(f"[register/{pname}] det={det_ms:.0f}ms emb={emb_ms:.0f}ms "
                              f"샘플 {len(embs)}개")

        th = threading.Thread(target=_worker, daemon=True)
        th.start()
        # 기본 3초 수집하되, 샘플이 REG_MIN_SAMPLES 미만이면 REG_MAX_SEC까지 연장
        # (추론이 느리거나 검출이 늦으면 3초 안에 1~2개만 모여 프로필이 부실해짐)
        t_start = time.time()
        rx_start = cam.rx_count() if hasattr(cam, "rx_count") else 0
        while True:
            elapsed = time.time() - t_start
            with lock:
                bb, n = shared["bbox"], shared["n"]
            if elapsed >= 3.0 and (n >= REG_MIN_SAMPLES or elapsed >= REG_MAX_SEC):
                break
            frame = cam.read()
            if frame is None:
                time.sleep(0.02); continue
            if bb is not None:
                cv2.rectangle(frame, (bb[0], bb[1]), (bb[2], bb[3]), (0, 255, 0), 2)
            cv2.putText(frame, f"{pname} capturing... {n}", (20, 50),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 255, 255), 2)
            _show(frame)
            time.sleep(0.01)   # 표시 루프 CPU 양보 (추론 스레드 우선)
        stop_flag["v"] = True
        th.join(timeout=1.5)
        profile["phases"][pname] = {"reid_emb": _avg_embed(embs),
                                    # 대표 표본 8→12: 매칭은 512-dim 코사인 12회(µs 단위)라 부하 무시 가능,
                                    # 자세/각도 커버리지 증가로 재획득 ReID 점수 상승 기대 (이슈 #48)
                                    "reid_embs": _pick_diverse(embs, 12),
                                    "color": _avg_color(cols)}
        dur = time.time() - t_start
        rx_fps = ((cam.rx_count() - rx_start) / dur) if hasattr(cam, "rx_count") else -1
        print(f"[register] {pname}: {len(embs)} 샘플 수집 ({dur:.1f}초, 카메라 수신 {rx_fps:.1f}fps)")
        DBG.log("register", phase=pname, n=len(embs), sec=round(dur, 1), rx_fps=round(rx_fps, 1))
        if len(embs) < REG_MIN_SAMPLES:
            print(f"[register] 경고: {pname} 샘플 {len(embs)}개뿐 — 인식률이 낮을 수 있습니다. "
                  f"조명/거리(1~2m)를 확인하고 재촬영을 권장합니다.")

    speak_on_pi(pi_ip, "촬영이 끝났습니다.")
    save_profile(profile)
    return profile


# ══════════════════════════════════════════════════════════════════════════════
# 보간 트래커 — MOSSE (실측: KCF 168~547ms/frame → MOSSE 17~66ms, 8배 빠름)
# 추적 중 루프 fps 붕괴(2~9fps)의 원인이 KCF 비용이라 보간 용도로는 MOSSE로 교체.
# ══════════════════════════════════════════════════════════════════════════════

class MosseBoxTracker(LF.BoxTracker):
    SCALE = 0.5   # 0.5x 축소 프레임에서 추적 (실측 66→26ms, 보간 정밀도 충분)

    @staticmethod
    def _create():
        if hasattr(cv2, "legacy") and hasattr(cv2.legacy, "TrackerMOSSE_create"):
            return cv2.legacy.TrackerMOSSE_create()
        return LF.BoxTracker._create()   # MOSSE 없으면 KCF 폴백

    def init(self, frame, bbox):
        small = cv2.resize(frame, None, fx=self.SCALE, fy=self.SCALE)
        return super().init(small, tuple(int(v * self.SCALE) for v in bbox))

    def update(self, frame):
        small = cv2.resize(frame, None, fx=self.SCALE, fy=self.SCALE)
        kb = super().update(small)
        if kb is None:
            return None
        return tuple(int(v / self.SCALE) for v in kb)


def score_multi_emb(pref, cand, last_bbox, cand_bbox, frame_shape):
    """LF.score_against_profile + ReID 다중 임베딩 매칭.

    평균 임베딩 1개 대신 등록 때 저장한 원본 임베딩들(reid_embs, 최대 8개)과
    개별 비교해 최고값을 사용 — 자세/각도 변화 시 본인 점수 하락을 줄인다.
    (타인은 어떤 임베딩과도 낮게 나와 오인식 위험 증가는 미미. 임계값 유지 목적)
    """
    total, det = LF.score_against_profile(pref, cand, last_bbox, cand_bbox, frame_shape)
    # 등록 원본(불변) + 주행 중 수확분(reid_embs_live) 합쳐 max 비교 — 최대 12+8=20회 코사인
    embs = (pref.get("reid_embs") or []) + (pref.get("reid_embs_live") or [])
    if embs:
        best = max(LF.cosine(e, cand.get("reid_emb")) for e in embs)
        if best > det["reid"]:
            total += LF.W_REID * (best - det["reid"])
            det = dict(det, reid=best)
    return total, det


# ══════════════════════════════════════════════════════════════════════════════
# 비동기 검출 워커 (YOLO+ReID+색상)
# ══════════════════════════════════════════════════════════════════════════════

class DetectionWorker(threading.Thread):
    def __init__(self, yolo, reid, face, profile, use_face):
        super().__init__(daemon=True)
        self._yolo, self._reid, self._face = yolo, reid, face
        self._phases = profile.get("phases", {})
        self._use_face = use_face
        self._in_lock = threading.Lock()
        self._in_frame = None
        self._in_lbbox = None
        self._out_lock = threading.Lock()
        self._out = {"bboxes": [], "scores": {}, "best_bbox": None,
                     "best_total": 0.0, "best_detail": None, "best_ori": "unknown",
                     "best_emb": None, "det_ms": 0.0, "reid_ms": 0.0, "seq": 0}
        self._seq = 0
        self._stop_flag = False

    def update_profile(self, profile):
        self._phases = profile.get("phases", {})

    def submit(self, frame, last_bbox):
        with self._in_lock:
            self._in_frame = frame
            self._in_lbbox = last_bbox

    def result(self):
        with self._out_lock:
            return dict(self._out)

    def stop(self):
        self._stop_flag = True

    def run(self):
        tm_det, tm_reid = cv2.TickMeter(), cv2.TickMeter()
        while not self._stop_flag:
            frame = last_bbox = None
            with self._in_lock:
                if self._in_frame is not None:
                    frame, last_bbox = self._in_frame, self._in_lbbox
                    self._in_frame = None
            if frame is None:
                time.sleep(0.003); continue

            h_f, w_f = frame.shape[:2]
            tm_det.reset(); tm_det.start()
            bboxes = self._yolo.detect(frame)
            tm_det.stop()

            best_bbox, best_total, best_detail, best_ori = None, -1.0, None, "unknown"
            best_emb = None
            scores = {}
            tm_reid.reset(); tm_reid.start()
            for bb in bboxes:
                x1, y1, x2, y2 = bb
                crop = frame[max(0, y1):min(h_f, y2), max(0, x1):min(w_f, x2)]
                if crop.size == 0:
                    continue
                feat = extract_features(crop, self._reid)
                ori = self._face.orient(crop) if self._use_face else "unknown"
                ph_best, ph_det, ph_name = -1.0, None, "front"
                for pn, pref in self._phases.items():
                    if not pref or not pref.get("reid_emb"):
                        continue
                    sc, det_sc = score_multi_emb(
                        pref, feat, last_bbox, bb, frame.shape)
                    if self._use_face and ori != "unknown" and ori == pn:
                        sc += 0.03
                    if sc > ph_best:
                        ph_best, ph_det, ph_name = sc, det_sc, pn
                scores[bb] = ph_best
                if ph_best > best_total:
                    best_total, best_bbox, best_detail, best_ori = ph_best, bb, ph_det, ph_name
                    best_emb = feat["reid_emb"]   # 온라인 수확용 — 이미 계산된 값 재사용
            tm_reid.stop()

            self._seq += 1
            with self._out_lock:
                self._out = {"bboxes": bboxes, "scores": scores,
                             "best_bbox": best_bbox, "best_total": best_total,
                             "best_detail": best_detail, "best_ori": best_ori,
                             "best_emb": best_emb,
                             "det_ms": tm_det.getTimeMilli(),
                             "reid_ms": tm_reid.getTimeMilli(), "seq": self._seq}
            # 검출 사이클 사이 CPU 양보 — 코어 적은 VM에서 표시/주행 스레드 멈춤 방지
            time.sleep(0.03)


# ══════════════════════════════════════════════════════════════════════════════
# 추종 루프 (cv2.imshow 표시 + 인식률 % + 주행 연동)
# ══════════════════════════════════════════════════════════════════════════════

def run_tracking(cam, yolo, reid, face, profile, use_face=True, follower=None,
                 just_registered=False):
    tracker = LF.TrackingState()
    last_harvest = {}   # 온라인 프로필 보강 — phase별 마지막 수확 시각
    # [sh 인식] 촬영 직후 빠른 진입(warm_start) 미사용 — sh 원본대로 진입도 동일 기준(from_search) 적용
    kcf = MosseBoxTracker()   # 보간 트래커 (MOSSE — KCF 대비 8배 경량)
    kcf_age = 0
    rx_last = -1              # 새 카메라 프레임에서만 트래커 업데이트 (동일 프레임 반복 연산 방지)
    frame_count = 0
    none_n = 0        # 연속 프레임 미수신 카운터 (스트림 끊김 안전 정지용)
    perf_t = time.time()          # 주기적 성능 스냅샷 타이머
    perf_frames = 0
    perf_rx0 = cam.rx_count() if hasattr(cam, "rx_count") else 0
    pred_vx = 0.0                 # 등록자 수평 이동 속도 추정 (px/s, 예측 조향용)
    prev_cx, prev_match_t = None, 0.0
    last_seen_t = time.time()     # 등록자 마지막 확인 시각 — 유실 후 SEARCH_START_DELAY 지나야 탐색 회전
    fps_t, fps_n, fps_val = time.time(), 0, 0.0

    avg = {"det": 0.0, "reid": 0.0}
    last_seq = 0
    cur_label = "-"
    cur_pct = 0
    last_bboxes, last_scores = [], {}
    reg_det_bbox = None

    worker = DetectionWorker(yolo, reid, face, profile, use_face)
    worker.start()

    # KCF 보간 추적기 가용성 확인 (opencv-contrib 없으면 조용히 죽어 있던 문제 가시화)
    try:
        MosseBoxTracker._create()
        kcf_env = True
    except Exception:
        kcf_env = False
        print("[경고] OpenCV KCF 추적기 없음 → 검출 사이 bbox 보간 비활성 (마지막 위치 조향으로 대체 동작). "
              "개선하려면 VM에서: pip install opencv-contrib-python")
    DBG.log("env", kcf=kcf_env)

    print("=== 추종 시작 ===  (화면 'q' 종료 / 터미널 '복귀'·'추종' 입력으로 모드 전환)")
    prev_state = follower.state if follower is not None else "FOLLOW"
    while True:
        if follower is not None and getattr(follower, 'trigger_register', False):
            follower.trigger_register = False
            worker.stop()
            worker.join()
            new_profile = register(cam, yolo, reid, "user", grace_sec=3.0, pi_ip=follower.pi_ip)
            profile = new_profile
            worker = DetectionWorker(yolo, reid, face, profile, use_face)
            worker.start()
            follower.is_registered = True
            follower.state = "FOLLOW"
            set_robot_led(follower.esp_ip, "STANDBY")
            tracker.reset(); kcf.deinit(); reg_det_bbox = None
            # [sh 인식] warm_start 미사용 — sh 원본대로 재획득도 동일 기준(from_search) 적용
            last_bboxes, last_scores = [], {}
            follower.reset_search()
            last_seen_t = time.time()   # 촬영 직후 = 대상이 바로 앞 → 유실 탐색 대기 타이머 리셋
            continue

        frame = cam.read()
        if frame is None:
            # 스트림 끊김: 라이다 브리징 시도, 안 되면 정지 명령 (마지막 속도 유지 방지)
            none_n += 1
            if none_n == 5:
                DBG.log("gap_start")
            if follower is not None and none_n >= 5 and none_n % 5 == 0:
                br = follower.lidar_bridge() if follower.state == "FOLLOW" else None
                if br is not None:
                    follower.send_velocity(*br)
                else:
                    follower.send_velocity(0.0, 0.0)
            time.sleep(0.02); continue
        if none_n >= 5:
            DBG.log("gap_end", n=none_n)
        none_n = 0
        frame_count += 1
        perf_frames += 1
        h_f, w_f = frame.shape[:2]
        # 카메라 수신(≈9fps)보다 루프(수십fps)가 훨씬 빨라 같은 프레임이 반복 처리됨 —
        # 트래커 업데이트는 새 프레임에서만 수행 (동일 프레임에 MOSSE/KCF 재실행 낭비 제거)
        rx_now = cam.rx_count() if hasattr(cam, "rx_count") else frame_count
        new_frame = (rx_now != rx_last)
        rx_last = rx_now

        # 5초마다 성능 스냅샷 (루프 fps / 카메라 수신 fps / 추론 시간 이동평균)
        now = time.time()
        if now - perf_t >= 5.0:
            rx = cam.rx_count() if hasattr(cam, "rx_count") else 0
            DBG.log("perf", loop_fps=round(perf_frames / (now - perf_t), 1),
                    rx_fps=round((rx - perf_rx0) / (now - perf_t), 1),
                    det_ms=round(avg["det"], 1), reid_ms=round(avg["reid"], 1))
            perf_t, perf_frames, perf_rx0 = now, 0, rx

        # [기능 2] 복귀(RETURN) 중엔 추종 연산 정지 (SLAM/Nav2 전용). FOLLOW→RETURN 전환 시 추적 리셋.
        cur_state = follower.state if follower is not None else "FOLLOW"
        
        # 1분(60초) 이상 사람 미인식 시 자동 원점 복귀 트리거
        if (follower is not None 
                and cur_state == "FOLLOW" 
                and follower.is_registered 
                and last_seen_t is not None 
                and (time.time() - last_seen_t > 60.0)):
            
            follower.get_logger().info("1분 동안 사람 미인식 -> 자동 원점 복귀를 수행합니다.")
            DBG.log("ros_cmd", cmd="auto_return_60s", prev_state="FOLLOW")
            follower.state = "RETURN"
            follower.is_registered = False  # 다음 사용자를 위해 등록 리셋
            follower.send_stop()
            set_robot_led(follower.esp_ip, "RUNNING")
            if not follower.has_start_pose:
                follower.get_logger().warn("AMCL 시작 위치 미저장 → (0,0) 복귀 시도.")
            follower.send_nav_goal(follower.start_x, follower.start_y, follower.start_yaw)
            
            # 상태 변수 업데이트 및 추적 리셋
            tracker.reset(); kcf.deinit(); reg_det_bbox = None
            last_bboxes, last_scores = [], {}
            follower.reset_search()
            prev_state = "RETURN"
            cur_state = "RETURN"
            continue
            
        if cur_state != "FOLLOW" and prev_state == "FOLLOW":
            tracker.reset(); kcf.deinit(); reg_det_bbox = None
            last_bboxes, last_scores = [], {}
            if follower is not None:
                follower.reset_search()
        elif cur_state == "FOLLOW" and prev_state != "FOLLOW":
            last_seen_t = time.time()   # FOLLOW 재진입 → 유실 탐색 대기 타이머 리셋
        prev_state = cur_state
        follow_active = (cur_state == "FOLLOW")

        interp_alive = follow_active and tracker.is_tracking and kcf.ok
        if follow_active and ((not interp_alive) or kcf_age >= KCF_MAX_AGE
                              or frame_count % DETECT_INTERVAL == 0):
            worker.submit(frame.copy(), tracker.last_bbox)

        det = worker.result()
        fresh = det["seq"] != last_seq
        last_seq = det["seq"]

        draw_bbox = None
        interp = False

        if fresh:
            last_bboxes, last_scores = det["bboxes"], det["scores"]
            avg["det"] = 0.8 * avg["det"] + 0.2 * det["det_ms"]
            avg["reid"] = 0.8 * avg["reid"] + 0.2 * det["reid_ms"]
            bb, total, detail, ori = (det["best_bbox"], det["best_total"],
                                      det["best_detail"], det["best_ori"])
            # [히스테리시스] 진입 엄격 / 유지 느슨: 상태별로 임계값·하드게이트를 다르게 적용
            #   추적 유지 = KEEP(0.56) + ReID 하한 완화(0.45) + 색상 게이트 생략
            #   유실 후 재획득 = SEARCH(0.65), 최초 진입 = MATCH(0.74) + 진입 게이트(0.55/0.15)
            if tracker.is_tracking:
                thr = LF.KEEP_THRESHOLD
                reid_floor, color_floor = LF.KEEP_REID_FLOOR, 0.0
            else:
                # 탐색·확정(confirm) 공통 임계 — 확정 프레임에만 MATCH(0.74)를 적용하면
                # 본인 점수가 71~74%일 때 68↔74 핑퐁으로 진입이 영구 불가(실측 확인).
                # 연속 매칭(SEARCH_CONFIRM_FRAMES) 요구가 타인 차단을 담당한다.
                thr = LF.SEARCH_MATCH_THR
                reid_floor, color_floor = LF.REID_FLOOR, LF.COLOR_FLOOR
            reid_ok = detail is not None and detail.get("reid", 0) >= reid_floor
            color_ok = detail is not None and detail.get("color", 0) >= color_floor
            matched = (bb is not None and total >= thr and reid_ok and color_ok)
            # [이슈 #48] 유실 재획득 구제: 탐색 중 color 붕괴로 total 미달이어도
            # ReID가 충분히 높으면(0.62↑) 재획득 허용. 최초 진입에는 미적용(had_track).
            # SEARCH_CONFIRM_FRAMES(3연속)가 그대로 적용되어 타인 오인식을 이중 차단.
            rescued = False
            if (not matched and bb is not None
                    and not tracker.is_tracking and tracker.had_track
                    and detail is not None
                    and detail.get("reid", 0) >= LF.SEARCH_REID_RESCUE
                    and detail.get("color", 0) >= LF.COLOR_FLOOR):
                matched = rescued = True
            if matched:
                tracker.update(True, bb, total)
                cur_pct = int(round(total * 100))
                cur_label = f"{profile['user_id']} [{ori}] {cur_pct}%"
                kcf.init(frame, bb); kcf_age = 0
                draw_bbox = bb; reg_det_bbox = bb
                # 예측 조향용 수평 속도 추정 (연속 매칭 간 cx 변화율, 지수평활)
                t_m = time.time()
                cx_m = (bb[0] + bb[2]) / 2.0
                if prev_cx is not None and 0.05 < t_m - prev_match_t < 1.5:
                    vx_now = (cx_m - prev_cx) / (t_m - prev_match_t)
                    pred_vx = 0.6 * pred_vx + 0.4 * _clamp(vx_now, -PRED_MAX_VX, PRED_MAX_VX)
                prev_cx, prev_match_t = cx_m, t_m
                # [온라인 프로필 보강] 고신뢰 프레임 임베딩 자동 수확.
                # 가드: ①ReID≥0.75(유지 임계보다 훨씬 엄격) ②추적 성립 상태만(confirm/rescue 제외)
                #       ③2초 간격 ④등록 원본 불변, 수확 풀만 오래된 것부터 교체
                if (tracker.status == "tracking" and not rescued
                        and detail.get("reid", 0) >= LF.HARVEST_REID_MIN
                        and det.get("best_emb")
                        and t_m - last_harvest.get(ori, 0.0) >= LF.HARVEST_INTERVAL_S):
                    ph = profile.get("phases", {}).get(ori)
                    if ph is not None:
                        live = ph.setdefault("reid_embs_live", [])
                        live.append(det["best_emb"])
                        if len(live) > LF.HARVEST_EXTRA_MAX:
                            live.pop(0)
                        last_harvest[ori] = t_m
                        DBG.log("harvest", ori=ori, reid=round(detail["reid"], 3),
                                n_live=len(live))
            else:
                tracker.update(False)
                reg_det_bbox = None
                # [유지 느슨] 한 프레임 리젝됐다고 KCF를 버리지 않는다. 추적이 살아 있으면
                # (lost N/LOST_MAX 유예 중) KCF 보간으로 초록 박스를 유지하고,
                # 실제로 추적이 끊겼을 때(is_tracking=False)만 폐기 → "잠깐 유실→주황/탐색" 방지.
                if tracker.is_tracking and kcf.ok:
                    if new_frame:
                        kb = kcf.update(frame); kcf_age += 1
                    else:
                        kb = tracker.last_bbox   # 같은 프레임 → 직전 보간 박스 재사용
                    if kb is not None:
                        tracker.last_bbox = kb
                        draw_bbox = kb; interp = True
                else:
                    kcf.deinit()
            # [기능 3] 인식률 % 터미널 로그 (임계값 튜닝 근거)
            if detail is not None:
                print(f"[score] match={total*100:5.1f}%  "
                      f"reid={detail['reid']*100:4.0f}% color={detail['color']*100:4.0f}% "
                      f"pos={detail['position']*100:4.0f}%  thr={thr*100:.0f}% "
                      f"=> {'RESCUE' if rescued else ('MATCH' if matched else 'reject')} "
                      f"(cand={len(last_bboxes)})")
            DBG.log("det", det_ms=round(det["det_ms"], 1), reid_ms=round(det["reid_ms"], 1),
                    cand=len(last_bboxes), thr=thr, ok=matched, rescue=rescued,
                    trk=tracker.is_tracking, st=tracker.status,
                    total=round(total, 3) if detail is not None else None,
                    reid=round(detail["reid"], 3) if detail is not None else None,
                    color=round(detail["color"], 3) if detail is not None else None)
        elif interp_alive:
            if new_frame:
                kb = kcf.update(frame); kcf_age += 1
            else:
                kb = tracker.last_bbox   # 같은 프레임 → 직전 보간 박스 재사용
            if kb is not None:
                tracker.last_bbox = kb
                draw_bbox = kb; interp = True

        if draw_bbox is not None:
            last_seen_t = time.time()   # 등록자 확인 → 유실 탐색 대기 타이머 갱신

        # 비등록자(회색) — % 표시
        for bb in last_bboxes:
            if bb == reg_det_bbox:
                continue
            x1, y1, x2, y2 = bb
            cv2.rectangle(frame, (x1, y1), (x2, y2), (95, 95, 95), 1)
            cv2.putText(frame, f"{int(last_scores.get(bb, 0) * 100)}%", (x1, max(15, y1 - 4)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.45, (95, 95, 95), 1)

        # 등록자(초록) — 라벨에 인식률 %
        if draw_bbox is not None:
            x1, y1, x2, y2 = draw_bbox
            cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 3)
            mark = "~" if interp else ""
            cv2.putText(frame, cur_label + mark, (x1, max(18, y1 - 8)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
        elif tracker.status.startswith("lost") and tracker.last_bbox:
            x1, y1, x2, y2 = tracker.last_bbox
            cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 140, 255), 2)
            cv2.putText(frame, tracker.status, (x1, max(18, y1 - 8)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 140, 255), 2)

        fps_n += 1
        _now = time.time()
        if _now - fps_t >= 0.5:
            fps_val = fps_n / (_now - fps_t)
            fps_t, fps_n = _now, 0
        mode = "DET" if fresh else ("KCF" if interp else "-")
        state_tag = follower.state if follower is not None else "NO-DRIVE"
        # [기능 3] HUD 에 현재 추종 대상 인식률 % 상시 표시
        match_tag = f"MATCH:{cur_pct}%" if tracker.is_tracking else "MATCH:--"
        hud = (f"FPS:{fps_val:.1f} {mode} det:{avg['det']:.0f} reid:{avg['reid']:.0f}ms "
               f"{match_tag} Cand:{len(last_bboxes)} {tracker.status.upper()} [{state_tag}]")
        cv2.rectangle(frame, (0, 0), (w_f, 24), (0, 0, 0), -1)
        cv2.putText(frame, hud, (6, 17), cv2.FONT_HERSHEY_SIMPLEX, 0.5,
                    (0, 255, 0) if tracker.is_tracking else (160, 160, 255), 1)

        # ── 주행 ──
        if follower is not None:
            if follower.state == "FOLLOW":
                if tracker.is_tracking and draw_bbox is not None:
                    # 검출 또는 KCF 보간 박스가 실제로 있음 = 화면에 보임 → 추종 주행
                    # (점수가 낮아 주황이어도 KCF가 살아 있으면 주행 유지 → 멈칫 방지)
                    v, w = follower.compute(draw_bbox, w_f, h_f, True)
                    follower.reset_search()      # 추종 중 → 탐색 종료
                elif tracker.is_tracking:
                    # [유실 시 정지] KCF도 놓침 = 진짜 시야에서 사라짐 → 즉시 정지.
                    # 기존엔 마지막 위치+외삽(pred_vx)으로 계속 전진했는데, 방향이 틀리면
                    # 불안정 전진이 되므로 제거. 재매칭되면 위 분기로 복귀해 그 방향 전진.
                    v, w = 0.0, 0.0
                elif draw_bbox is not None:      # 재확인(confirm) 중 → 회전 말고 정지 대기
                    v, w = 0.0, 0.0
                    follower.reset_search()
                else:                            # 완전 유실 → 좌우 탐색 회전 (sh 방식)
                    # 소프트 매치(후보 스코어 0.63↑): 회전 멈추고 confirm 기회 부여
                    if fresh and det["best_total"] > 0.63 and det["best_bbox"] is not None:
                        v, w = 0.0, 0.0
                        follower.reset_search()
                    elif time.time() - last_seen_t < SEARCH_START_DELAY:
                        v, w = 0.0, 0.0          # 유실 5초 미만 → 정지 대기 (재등장 기대, 회전이 재인식 방해 방지)
                        follower.reset_search()
                    else:
                        v, w = follower.search_rotate()
                
                # 사람이 인식되면 초록불(RUNNING), 인식되지 않으면(유실/재확인 포함) 즉시 노란불(STANDBY)
                if draw_bbox is not None:
                    set_robot_led(follower.esp_ip, "RUNNING")
                else:
                    set_robot_led(follower.esp_ip, "STANDBY")
                    
                # 매 루프 발행(~15-20Hz) — 가속도 필터가 있어 급변 없이 촘촘하게 갱신
                follower.send_velocity(v, w)
                if frame_count % 3 == 0:        # 로그는 ≈5-7Hz로 샘플링
                    err_c = (((draw_bbox[0] + draw_bbox[2]) / 2 - w_f / 2) / (w_f / 2)
                             if draw_bbox is not None else None)
                    DBG.log("cmd", v=round(follower.last_v, 3), w=round(follower.last_w, 3),
                            dist=round(follower.last_dist_cm, 1),
                            mode=getattr(follower, "_dist_mode", "?"),
                            err=round(err_c, 3) if err_c is not None else None,
                            trk=tracker.is_tracking)
                dist_mode = getattr(follower, "_dist_mode", "?")
                cv2.putText(frame,
                            f"WHEEL v={v:+.2f} w={w:+.2f} dist={follower.last_dist_cm:.0f}cm [{dist_mode}]",
                            (6, h_f - 12), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 1)
            else:  # RETURN / IDLE — Nav2 가 /cmd_vel 통제
                cv2.putText(frame, f"[{follower.state}] Nav2 controlling. type '추종' to follow.",
                            (6, h_f - 12), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 200, 255), 1)
                
                # Nav2 복귀 동작 중에는 초록불(RUNNING)
                if follower.state == "RETURN":
                    set_robot_led(follower.esp_ip, "RUNNING")
                elif follower.state == "STOPPED":
                    set_robot_led(follower.esp_ip, "STOPPED")

        # ── 화면 녹화 (--record-sec) : HUD 포함 프레임을 mp4로 저장, 시간 경과 시 자동 종료 ──
        global _REC
        if RECORD_SEC > 0:
            now_r = time.time()
            if _REC is None:
                path = str(HERE / "debug" / f"record_{time.strftime('%Y%m%d_%H%M%S')}.mp4")
                _REC = {"vw": cv2.VideoWriter(path, cv2.VideoWriter_fourcc(*"mp4v"),
                                              15.0, (w_f, h_f)),
                        "path": path, "t0": now_r, "last": 0.0}
                print(f"[record] 녹화 시작: {path} ({RECORD_SEC:.0f}초)")
            if now_r - _REC["last"] >= 1.0 / 15.0:
                _REC["vw"].write(frame)
                _REC["last"] = now_r
            if now_r - _REC["t0"] >= RECORD_SEC:
                _REC["vw"].release()
                print(f"[record] 녹화 완료({RECORD_SEC:.0f}초) → {_REC['path']} — 자동 종료")
                break

        cv2.imshow(WINDOW, frame)
        if (cv2.waitKey(1) & 0xFF) == ord("q"):
            break

        if frame_count % 30 == 0:
            print(f"[perf] {hud}")


# ══════════════════════════════════════════════════════════════════════════════
# 콘솔 입력 스레드 ('복귀' / '추종')
# ══════════════════════════════════════════════════════════════════════════════

def console_input_thread(follower):
    print("  - '복귀' 입력 → 시작 위치(AMCL 기록)로 Nav2 복귀")
    print("  - '추종' 입력 → 다시 FOLLOW 모드")
    print("  - '정지' 입력 → 비상 정지 및 빨간불")
    while True:
        try:
            cmd = input().strip()
        except (EOFError, KeyboardInterrupt):
            break
        if cmd == "복귀":
            if follower.state != "RETURN":
                follower.state = "RETURN"
                follower.send_stop()
                set_robot_led(follower.esp_ip, "RUNNING")
                if not follower.has_start_pose:
                    follower.get_logger().warn(
                        "AMCL 시작 위치 미저장 → (0,0) 으로 복귀 시도. RViz 2D Pose Estimate 권장.")
                follower.send_nav_goal(follower.start_x, follower.start_y, follower.start_yaw)
        elif cmd == "추종":
            if follower.state != "FOLLOW":
                follower.cancel_nav()          # Nav2 목표 취소 → /cmd_vel 충돌 방지
                if not follower.is_registered:
                    follower.trigger_register = True
                    follower.get_logger().info("FOLLOW 요청 수신 -> 신규 사용자 등록을 시작합니다.")
                else:
                    follower.state = "FOLLOW"
                    follower.send_stop()           # 잔여 속도 정지 후 추종 재개
                    set_robot_led(follower.esp_ip, "STANDBY")
                    follower.get_logger().info("FOLLOW 모드로 전환 (기등록 사용자).")
        elif cmd == "정지":
            follower.cancel_nav()
            follower.state = "STOPPED"
            follower.send_stop()
            set_robot_led(follower.esp_ip, "STOPPED")
            follower.get_logger().info("정지(STOPPED) 모드로 전환. LED 빨간불.")


# ══════════════════════════════════════════════════════════════════════════════
# main
# ══════════════════════════════════════════════════════════════════════════════

def parse_args():
    p = argparse.ArgumentParser(description="등록 사용자 추종 + Nav2 복귀 (분산)")
    p.add_argument("--pi-ip", default="192.168.0.35", help="라즈베리파이 IP (MJPEG :5000)")
    p.add_argument("--speak-ip", default=None,
                   help="음성 안내 수신 서버 — 'IP' 또는 'IP:포트' (예: 192.168.0.22:5001). 미지정 시 pi-ip")
    p.add_argument("--esp-ip", default=None, help="ESP8266 (RFID & LED) IP 주소 (예: 192.168.0.xx)")
    p.add_argument("--stream-url", default=None,
                   help="직접 지정 시 우선 (기본: http://<pi-ip>:5000/video_feed)")
    p.add_argument("--imgsz", type=int, default=256,
                   help="YOLO 입력 크기(192/256/320). 기본 256 — 실측상 192는 사람이 "
                        "작게 잡혀 검출 실패(606회 중 17회만 검출), 320은 447ms로 느림")
    p.add_argument("--reid-model", choices=["x0_25", "x1_0"], default="x1_0",
                   help="ReID 모델. 기본 x1_0(변별력 우수). 4코어+192px 기준 감당 가능. "
                        "너무 느리면 x0_25. 모델을 바꾸면 프로필 재등록 필요")
    p.add_argument("--threads", type=int, default=0,
                   help="onnxruntime 스레드 수. 0=자동(코어수-1, 최대 4) — "
                        "코어보다 크게 주면 스레드 경합으로 화면이 멈춤")
    p.add_argument("--register", action="store_true", help="등록(앞/뒤) 후 추종")
    p.add_argument("--reset", action="store_true", help="기존 프로필 삭제 후 등록")
    p.add_argument("--user-id", default="owner_001")
    p.add_argument("--no-face", action="store_true", help="얼굴 방향 보조 비활성화")
    p.add_argument("--grace", type=float, default=5.0, help="촬영 시작 전 준비 시간(초)")
    p.add_argument("--no-drive", action="store_true",
                   help="ROS2 주행 비활성(인식만 확인). cmd_vel/Nav2 미사용")
    p.add_argument("--invert-turn", action="store_true",
                   help="회전 방향 반전 (모터가 반대로 돌 때). --mirror 와 동시 사용 금지")
    p.add_argument("--mirror", action="store_true",
                   help="카메라 영상 좌우반전 보정 (영상이 거울상일 때). "
                        "라이다 방위까지 일관되게 맞음 — 반대 회전의 근본 해결책")
    p.add_argument("--no-debug-log", action="store_true",
                   help="디버그 로그(debug_logs/run_*.jsonl) 기록 비활성화")
    p.add_argument("--record-sec", type=float, default=0.0,
                   help="지정 시 HUD 포함 화면을 mp4로 녹화하고 해당 초 경과 후 자동 종료 (0=끔)")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    stream_url = args.stream_url or f"http://{args.pi_ip}:5000/video_feed"
    speak_ip = args.speak_ip or args.pi_ip

    global DBG, RECORD_SEC
    RECORD_SEC = args.record_sec
    DBG = DebugLog(enabled=not args.no_debug_log)
    if DBG.path:
        print(f"[debug] 로그 기록: {DBG.path} (분석: python3 analyze_debug.py)")
    DBG.log("start", imgsz=args.imgsz, reid_model=args.reid_model,
            mirror=args.mirror, invert_turn=args.invert_turn,
            cpu=os.cpu_count())

    print("[init] 모델 로딩...")
    if args.threads <= 0:
        # 코어 수보다 많은 스레드는 경합만 유발 (특히 코어 적은 VM에서 화면 멈춤)
        args.threads = max(1, min(4, (os.cpu_count() or 2) - 1))
    print(f"[init] CPU 코어={os.cpu_count()}, onnx threads={args.threads}")
    yolo_path, yolo_sz = pick_yolo_onnx(args.imgsz)
    print(f"[init] YOLO={yolo_path.name} imgsz={yolo_sz}")
    yolo = OnnxYolo(str(yolo_path), imgsz=yolo_sz, threads=args.threads)
    global REID_MODEL_NAME
    REID_MODEL_NAME = args.reid_model
    reid_path = MODELS_DIR / f"osnet_{args.reid_model}.onnx"
    reid = OnnxReID(str(reid_path), threads=args.threads)
    face = FaceOrient(str(YUNET_ONNX) if not args.no_face else None)
    print(f"[init] YOLO/ReID OK (ReID={reid_path.name}), face={face.mode}")

    print(f"[cam] 분산 MJPEG 연결: {stream_url}")
    cam = MjpegCamera(stream_url, mirror=args.mirror)
    time.sleep(1.0)
    if cam.read() is None:
        print(f"[오류] 스트림({stream_url}) 프레임 수신 실패. "
              f"라파의 pi_camera_streamer.py 실행/ IP 확인.")
        cam.stop()
        return 1

    # ── ROS2 주행 준비 ──
    follower = None
    if not args.no_drive:
        if not _ROS2_OK:
            print("[경고] rclpy 없음 → 주행 비활성(인식만). "
                  "source /opt/ros/humble/setup.bash 후 재실행하면 주행됩니다.")
        else:
            rclpy.init()
            follower = RobotController(esp_ip=args.esp_ip, pi_ip=speak_ip,
                                       ang_sign=-1.0 if args.invert_turn else 1.0)
            ex = rclpy.executors.MultiThreadedExecutor()
            ex.add_node(follower)
            threading.Thread(target=ex.spin, daemon=True).start()
            threading.Thread(target=console_input_thread, args=(follower,), daemon=True).start()

    # ── 프로필 / 등록 ──
    if args.reset and PROFILE_PATH.exists():
        PROFILE_PATH.unlink()
    profile = load_profile()

    # 다른 ReID 모델로 만든 프로필은 임베딩 공간이 달라 매칭 불가 → 폐기
    if profile and profile.get("reid_model", "x1_0") != args.reid_model:
        print(f"[profile] ReID 모델 불일치(프로필={profile.get('reid_model', 'x1_0')}, "
              f"현재={args.reid_model}) → 기존 프로필 폐기. 재등록이 필요합니다.")
        profile = None

    if args.register:
        # 즉시 촬영하지 않고, 앱에서 QR 인식(→ cmd_server RESUME → /robocart/resume) 신호를
        # 받으면 그때 등록을 시작한다. (등록 트리거: RobotController._resume_cb → trigger_register)
        if PROFILE_PATH.exists():
            PROFILE_PATH.unlink()
            print(f"[profile] 기존 프로필 삭제: {PROFILE_PATH.name}")
        if follower is not None:
            profile = {"user_id": args.user_id, "phases": {}}
            follower.is_registered = False    # 미등록 → 앱 RESUME 수신 시 촬영 시작
            print("[register] 앱에서 QR 인식(시작 명령) 후 촬영을 시작합니다. 대기 중...")
        else:
            # --no-drive 등 ROS2 비활성이면 앱 신호를 받을 수 없어 즉시 촬영으로 폴백
            print("[register] 경고: 주행(ROS2) 비활성 상태라 앱 QR 신호를 받을 수 없어 즉시 촬영합니다.")
            profile = register(cam, yolo, reid, args.user_id, grace_sec=args.grace, pi_ip=speak_ip)
    elif profile is None:
        # 프로필 파일이 아예 없으면 빈 프로필로 대기
        profile = {"user_id": args.user_id, "phases": {}}

    if profile and profile.get("phases"):
        if follower is not None:
            follower.is_registered = True

    try:
        run_tracking(cam, yolo, reid, face, profile,
                     use_face=not args.no_face, follower=follower,
                     just_registered=False)
    except KeyboardInterrupt:
        print("\n[종료]")
    finally:
        if follower is not None:
            set_robot_led(follower.esp_ip, "STOPPED", blocking=True)
            follower.send_stop()
            follower.destroy_node()
            if rclpy.ok():
                rclpy.shutdown()
        if _REC is not None:
            _REC["vw"].release()   # 중복 release 무해 — q 종료 등 조기 종료 시 파일 보존
        cam.stop()
        cv2.destroyAllWindows()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
