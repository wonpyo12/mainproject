#!/usr/bin/env python3
"""
ros_person_follower_nav2_v2 — 등록 사용자 인식 + 추종 + Nav2 원점 복귀 (분산 처리판)

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
  python3 ros_person_follower_nav2_v2.py --pi-ip 192.168.0.23 --register

  q : 종료 / 터미널에 '복귀' 또는 '추종' 입력 : 모드 전환

의존(같은 폴더): light_features.py, light_models.py, models_light/
"""
from __future__ import annotations

import argparse
import json
import math
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
    from geometry_msgs.msg import Twist, PoseStamped, PoseWithCovarianceStamped
    from sensor_msgs.msg import LaserScan
    from nav2_msgs.action import NavigateToPose
    _ROS2_OK = True
except Exception:
    _ROS2_OK = False


HERE = Path(__file__).resolve().parent
MODELS_DIR   = HERE / "models_light"
PROFILE_PATH = HERE / "robocart_profile_v2.json"

REID_ONNX  = MODELS_DIR / "osnet_x0_25.onnx"
YUNET_ONNX = MODELS_DIR / "face_detection_yunet.onnx"
YOLO_ONNX_BY_SZ = {320: MODELS_DIR / "yolov8n.onnx",
                   256: MODELS_DIR / "yolov8n_256.onnx",
                   192: MODELS_DIR / "yolov8n_192.onnx"}

DETECT_INTERVAL = 5      # 검출 사이 KCF 보간 프레임 수
KCF_MAX_AGE     = 40     # KCF 단독 보간 허용 최대 (초과 시 강제 재검출)

WINDOW = "robocart v2 - Registered User Follow + Nav2"


def pick_yolo_onnx(imgsz: int):
    p = YOLO_ONNX_BY_SZ.get(imgsz)
    if p and p.exists():
        return p, imgsz
    return MODELS_DIR / "yolov8n.onnx", 320


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

    def __init__(self, url: str):
        self.url = url
        self._frame: np.ndarray | None = None
        self._running = True
        self._th = threading.Thread(target=self._loop, daemon=True)
        self._th.start()

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
                    a = buf.find(b"\xff\xd8")     # JPEG SOI
                    b = buf.find(b"\xff\xd9")     # JPEG EOI
                    if a != -1 and b != -1 and a < b:
                        jpg = buf[a:b + 2]
                        buf = buf[b + 2:]
                        f = cv2.imdecode(np.frombuffer(jpg, np.uint8), cv2.IMREAD_COLOR)
                        if f is not None:
                            self._frame = f
            except Exception:
                self._frame = None
            finally:
                if stream is not None:
                    try:
                        stream.close()
                    except Exception:
                        pass
            if self._running:
                time.sleep(1.0)               # 재연결 대기

    def read(self):
        f = self._frame
        return f.copy() if f is not None else None

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
TARGET_DIST_CM = 70.0
DIST_NEAR_CM   = 60.0
DIST_FAR_CM    = 80.0
CENTER_DEADBAND = 0.12

KP_LIN_DIST = 0.004
KP_ANG      = 0.5
MAX_LIN     = 0.12
MAX_LIN_REV = 0.08
MAX_ANG     = 0.5
ALLOW_REVERSE = True

FRONT_STOP_M = 0.35      # 전방 라이다 이 거리 이내 장애물이면 전진 0 (안전)


def _clamp(x, lo, hi):
    return max(lo, min(hi, x))


def _yaw_to_quat(yaw: float):
    return (0.0, 0.0, math.sin(yaw / 2.0), math.cos(yaw / 2.0))


def _quat_to_yaw(x, y, z, w):
    return math.atan2(2.0 * (w * z + x * y), 1.0 - 2.0 * (y * y + z * z))


if _ROS2_OK:

    class RobotController(Node):
        """추종 속도 발행 + Nav2 원점 복귀 + 상태(FOLLOW/RETURN/IDLE/STOPPED) 관리."""

        def __init__(self, topic: str = "cmd_vel", esp_ip: str = None):
            super().__init__("person_follower_nav2_v2")
            self.esp_ip = esp_ip
            self.cmd_vel_pub = self.create_publisher(Twist, topic, 10)
            self.nav_client = ActionClient(self, NavigateToPose, "navigate_to_pose")
            self.create_subscription(PoseWithCovarianceStamped, "amcl_pose",
                                     self._amcl_cb, 10)
            self.create_subscription(LaserScan, "scan", self._scan_cb, 10)

            self.latest_scan = None
            self.start_x = 0.0
            self.start_y = 0.0
            self.start_yaw = 0.0
            self.has_start_pose = False

            self.state = "FOLLOW"          # FOLLOW / RETURN / IDLE
            self.last_v = 0.0
            self.last_w = 0.0
            self.last_dist_cm = 0.0
            self.get_logger().info(f"RobotController v2 준비 (FOLLOW + Nav2 RETURN). ESP_IP: {self.esp_ip}")
            
            # 구동 시작 시 대기 상태(노란불)로 초기화
            set_robot_led(self.esp_ip, "STANDBY")

        # ── 구독 콜백 ──
        def _amcl_cb(self, msg):
            if not self.has_start_pose:
                p = msg.pose.pose
                self.start_x = p.position.x
                self.start_y = p.position.y
                self.start_yaw = _quat_to_yaw(p.orientation.x, p.orientation.y,
                                              p.orientation.z, p.orientation.w)
                self.has_start_pose = True
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

        # ── FOLLOW: bbox → (v, w) ──
        def compute(self, bbox, frame_w, frame_h, is_tracking):
            if not is_tracking or bbox is None or frame_w <= 0:
                self.last_dist_cm = 0.0
                return 0.0, 0.0
            x1, y1, x2, y2 = bbox
            bbox_w = max(1, x2 - x1)
            cx = (x1 + x2) / 2.0

            dist_cm = CALIB_K / bbox_w
            self.last_dist_cm = dist_cm
            if DIST_NEAR_CM <= dist_cm <= DIST_FAR_CM:
                v = 0.0
            else:
                err = dist_cm - TARGET_DIST_CM
                v = _clamp(KP_LIN_DIST * err, -MAX_LIN, MAX_LIN)
                if v < 0:
                    v = 0.0 if not ALLOW_REVERSE else max(v, -MAX_LIN_REV)

            err_c = (cx - frame_w / 2.0) / (frame_w / 2.0)
            w = 0.0 if abs(err_c) < CENTER_DEADBAND else _clamp(-KP_ANG * err_c, -MAX_ANG, MAX_ANG)
            return v, w

        def send_velocity(self, v, w):
            """FOLLOW 상태에서만 실제 발행 (RETURN 중엔 Nav2가 /cmd_vel 통제)."""
            if self.state != "FOLLOW":
                return
            if v > 0 and self.front_blocked():       # 안전: 전방 막히면 전진 취소
                v = 0.0
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
            fut = self.nav_client.send_goal_async(goal)
            fut.add_done_callback(self._nav_resp_cb)

        def _nav_resp_cb(self, future):
            gh = future.result()
            if not gh.accepted:
                self.get_logger().warn("복귀 목표 거부됨 → FOLLOW 복귀.")
                self.state = "FOLLOW"
                return
            gh.get_result_async().add_done_callback(self._nav_done_cb)

        def _nav_done_cb(self, future):
            self.get_logger().info("원점 도착 → FOLLOW 모드 자동 전환.")
            self.state = "FOLLOW"

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
            url = f"http://{pi_ip}:5000/speak?text={encoded_text}"
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
            while not stop_flag["v"]:
                f = cam.read()
                if f is None:
                    time.sleep(0.01); continue
                bb = largest_bbox(yolo.detect(f))
                if bb is None:
                    with lock:
                        shared["bbox"] = None
                    continue
                x1, y1, x2, y2 = bb
                crop = f[max(0, y1):y2, max(0, x1):x2]
                if crop.size > 0:
                    feat = extract_features(crop, reid)
                    if feat["reid_emb"]:
                        with lock:
                            embs.append(feat["reid_emb"]); cols.append(feat["color"])
                            shared["bbox"] = bb; shared["n"] = len(embs)

        th = threading.Thread(target=_worker, daemon=True)
        th.start()
        t_end = time.time() + 3.0
        while time.time() < t_end:
            frame = cam.read()
            if frame is None:
                time.sleep(0.02); continue
            with lock:
                bb, n = shared["bbox"], shared["n"]
            if bb is not None:
                cv2.rectangle(frame, (bb[0], bb[1]), (bb[2], bb[3]), (0, 255, 0), 2)
            cv2.putText(frame, f"{pname} capturing... {n}", (20, 50),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 255, 255), 2)
            _show(frame)
        stop_flag["v"] = True
        th.join(timeout=1.5)
        profile["phases"][pname] = {"reid_emb": _avg_embed(embs),
                                    "color": _avg_color(cols)}
        print(f"[register] {pname}: {len(embs)} 샘플 수집")

    speak_on_pi(pi_ip, "촬영이 끝났습니다.")
    save_profile(profile)
    return profile


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
                     "det_ms": 0.0, "reid_ms": 0.0, "seq": 0}
        self._seq = 0
        self._stop = False

    def submit(self, frame, last_bbox):
        with self._in_lock:
            self._in_frame = frame
            self._in_lbbox = last_bbox

    def result(self):
        with self._out_lock:
            return dict(self._out)

    def stop(self):
        self._stop = True

    def run(self):
        tm_det, tm_reid = cv2.TickMeter(), cv2.TickMeter()
        while not self._stop:
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
                    sc, det_sc = LF.score_against_profile(
                        pref, feat, last_bbox, bb, frame.shape)
                    if self._use_face and ori != "unknown" and ori == pn:
                        sc += 0.03
                    if sc > ph_best:
                        ph_best, ph_det, ph_name = sc, det_sc, pn
                scores[bb] = ph_best
                if ph_best > best_total:
                    best_total, best_bbox, best_detail, best_ori = ph_best, bb, ph_det, ph_name
            tm_reid.stop()

            self._seq += 1
            with self._out_lock:
                self._out = {"bboxes": bboxes, "scores": scores,
                             "best_bbox": best_bbox, "best_total": best_total,
                             "best_detail": best_detail, "best_ori": best_ori,
                             "det_ms": tm_det.getTimeMilli(),
                             "reid_ms": tm_reid.getTimeMilli(), "seq": self._seq}


# ══════════════════════════════════════════════════════════════════════════════
# 추종 루프 (cv2.imshow 표시 + 인식률 % + 주행 연동)
# ══════════════════════════════════════════════════════════════════════════════

def run_tracking(cam, yolo, reid, face, profile, use_face=True, follower=None):
    tracker = LF.TrackingState()
    kcf = LF.BoxTracker()
    kcf_age = 0
    frame_count = 0
    fps_t, fps_n, fps_val = time.time(), 0, 0.0

    avg = {"det": 0.0, "reid": 0.0}
    last_seq = 0
    cur_label = "-"
    cur_pct = 0
    last_bboxes, last_scores = [], {}
    reg_det_bbox = None

    worker = DetectionWorker(yolo, reid, face, profile, use_face)
    worker.start()

    print("=== 추종 시작 ===  (화면 'q' 종료 / 터미널 '복귀'·'추종' 입력으로 모드 전환)")
    while True:
        frame = cam.read()
        if frame is None:
            time.sleep(0.02); continue
        frame_count += 1
        h_f, w_f = frame.shape[:2]

        interp_alive = tracker.is_tracking and kcf.ok
        if (not interp_alive) or kcf_age >= KCF_MAX_AGE or frame_count % DETECT_INTERVAL == 0:
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
            reid_ok = detail is not None and detail.get("reid", 0) >= LF.REID_FLOOR
            color_ok = detail is not None and detail.get("color", 0) >= LF.COLOR_FLOOR
            thr = LF.KEEP_THRESHOLD if tracker.is_tracking else LF.MATCH_THRESHOLD
            matched = (bb is not None and total >= thr and reid_ok and color_ok)
            if matched:
                tracker.update(True, bb, total)
                cur_pct = int(round(total * 100))
                cur_label = f"{profile['user_id']} [{ori}] {cur_pct}%"
                kcf.init(frame, bb); kcf_age = 0
                draw_bbox = bb; reg_det_bbox = bb
            else:
                tracker.update(False)
                kcf.deinit(); reg_det_bbox = None
            # [기능 3] 인식률 % 터미널 로그 (임계값 튜닝 근거)
            if detail is not None:
                print(f"[score] match={total*100:5.1f}%  "
                      f"reid={detail['reid']*100:4.0f}% color={detail['color']*100:4.0f}% "
                      f"pos={detail['position']*100:4.0f}%  thr={thr*100:.0f}% "
                      f"=> {'MATCH' if matched else 'reject'} (cand={len(last_bboxes)})")
        elif interp_alive:
            kb = kcf.update(frame); kcf_age += 1
            if kb is not None:
                tracker.last_bbox = kb
                draw_bbox = kb; interp = True

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
                v, w = follower.compute(draw_bbox, w_f, h_f, tracker.is_tracking)
                if frame_count % 3 == 0:        # ≈10Hz publish (매프레임 publish 오버헤드 방지)
                    follower.send_velocity(v, w)
                
                # 사람이 인식되면 초록불(RUNNING), 인식되지 않으면(유실/재확인 포함) 즉시 노란불(STANDBY)
                if draw_bbox is not None:
                    set_robot_led(follower.esp_ip, "RUNNING")
                else:
                    set_robot_led(follower.esp_ip, "STANDBY")

                cv2.putText(frame,
                            f"WHEEL v={v:+.2f} w={w:+.2f} dist={follower.last_dist_cm:.0f}cm",
                            (6, h_f - 12), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 1)
            else:  # RETURN / IDLE — Nav2 가 /cmd_vel 통제
                cv2.putText(frame, f"[{follower.state}] Nav2 controlling. type '추종' to follow.",
                            (6, h_f - 12), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 200, 255), 1)
                
                # Nav2 복귀 동작 중에는 초록불(RUNNING)
                if follower.state == "RETURN":
                    set_robot_led(follower.esp_ip, "RUNNING")
                elif follower.state == "STOPPED":
                    set_robot_led(follower.esp_ip, "STOPPED")

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
                follower.state = "FOLLOW"
                follower.send_stop()
                set_robot_led(follower.esp_ip, "STANDBY")
                follower.get_logger().info("FOLLOW 모드로 전환.")
        elif cmd == "정지":
            follower.state = "STOPPED"
            follower.send_stop()
            set_robot_led(follower.esp_ip, "STOPPED")
            follower.get_logger().info("정지(STOPPED) 모드로 전환. LED 빨간불.")


# ══════════════════════════════════════════════════════════════════════════════
# main
# ══════════════════════════════════════════════════════════════════════════════

def parse_args():
    p = argparse.ArgumentParser(description="등록 사용자 추종 + Nav2 복귀 (분산)")
    p.add_argument("--pi-ip", default="192.168.0.25", help="라즈베리파이 IP (MJPEG :5000)")
    p.add_argument("--esp-ip", default=None, help="ESP8266 (RFID & LED) IP 주소 (예: 192.168.0.xx)")
    p.add_argument("--stream-url", default=None,
                   help="직접 지정 시 우선 (기본: http://<pi-ip>:5000/video_feed)")
    p.add_argument("--imgsz", type=int, default=320,
                   help="YOLO 입력 크기(192/256/320). VM 추론이라 320 권장")
    p.add_argument("--threads", type=int, default=4)
    p.add_argument("--register", action="store_true", help="등록(앞/뒤) 후 추종")
    p.add_argument("--reset", action="store_true", help="기존 프로필 삭제 후 등록")
    p.add_argument("--user-id", default="owner_001")
    p.add_argument("--no-face", action="store_true", help="얼굴 방향 보조 비활성화")
    p.add_argument("--grace", type=float, default=5.0, help="촬영 시작 전 준비 시간(초)")
    p.add_argument("--no-drive", action="store_true",
                   help="ROS2 주행 비활성(인식만 확인). cmd_vel/Nav2 미사용")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    stream_url = args.stream_url or f"http://{args.pi_ip}:5000/video_feed"

    print("[init] 모델 로딩...")
    yolo_path, yolo_sz = pick_yolo_onnx(args.imgsz)
    print(f"[init] YOLO={yolo_path.name} imgsz={yolo_sz}")
    yolo = OnnxYolo(str(yolo_path), imgsz=yolo_sz, threads=args.threads)
    reid = OnnxReID(str(REID_ONNX), threads=args.threads)
    face = FaceOrient(str(YUNET_ONNX) if not args.no_face else None)
    print(f"[init] YOLO/ReID OK, face={face.mode}")

    print(f"[cam] 분산 MJPEG 연결: {stream_url}")
    cam = MjpegCamera(stream_url)
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
            follower = RobotController(esp_ip=args.esp_ip)
            ex = rclpy.executors.MultiThreadedExecutor()
            ex.add_node(follower)
            threading.Thread(target=ex.spin, daemon=True).start()
            threading.Thread(target=console_input_thread, args=(follower,), daemon=True).start()

    # ── 프로필 / 등록 ──
    if args.reset and PROFILE_PATH.exists():
        PROFILE_PATH.unlink()
    profile = load_profile()
    if args.register or args.reset or profile is None:
        if profile is None and not (args.register or args.reset):
            print("[안내] 프로필 없음 → 등록 진행")
        profile = register(cam, yolo, reid, args.user_id, grace_sec=args.grace, pi_ip=args.pi_ip)

    try:
        run_tracking(cam, yolo, reid, face, profile,
                     use_face=not args.no_face, follower=follower)
    except KeyboardInterrupt:
        print("\n[종료]")
    finally:
        if follower is not None:
            set_robot_led(follower.esp_ip, "STOPPED", blocking=True)
            follower.send_stop()
            follower.destroy_node()
            if rclpy.ok():
                rclpy.shutdown()
        cam.stop()
        cv2.destroyAllWindows()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
