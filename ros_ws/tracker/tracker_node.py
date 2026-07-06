#!/usr/bin/env python3
"""
[WSL 쪽] 사용자 추적 노드 — smart_cart_core(1400줄)를 그대로 재사용

핵심: run_tracking()은 카메라(open_camera)와 서보 객체만 쓰므로
      그 둘만 ROS2 백엔드로 바꿔 끼운다. 인식/매칭 로직은 무수정.

  /image/compressed 구독 → cv2.imdecode → core.run_tracking 에 프레임 공급
  서보 명령(move_to/start_sweep/hold) → /servo_cmd 발행
  /servo_state ("P95") 구독 → 현재 각도 갱신
  추적 결과 화면(cv2.imshow 호출 가로채기) → /image/annotated 발행
    → Windows 브리지가 받아서 네이티브 창으로 표시 (WSLg 불필요)

실행 (WSL):
  source /opt/ros/humble/setup.bash
  cd /mnt/d/YH/ros_ws/tracker
  python3 tracker_node.py
"""
import threading
import time

import cv2
import numpy as np
import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy
from sensor_msgs.msg import CompressedImage
from std_msgs.msg import String

import smart_cart_core as core


# ══════════════════════════════════════════════════════════════════════════
# ROS 백엔드 카메라 — cv2.VideoCapture 와 같은 인터페이스 (.read/.release)
# ══════════════════════════════════════════════════════════════════════════
class RosCamera:
    def __init__(self, node: Node):
        self._node = node
        self._frame = None
        self._event = threading.Event()
        qos = QoSProfile(depth=1, reliability=ReliabilityPolicy.BEST_EFFORT)
        node.create_subscription(CompressedImage, '/image/compressed',
                                 self._on_image, qos)

    def _on_image(self, msg: CompressedImage):
        arr = np.frombuffer(bytes(msg.data), dtype=np.uint8)
        frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if frame is not None:
            self._frame = frame
            self._event.set()

    def read(self):
        # 새 프레임이 올 때까지 대기 (최신 프레임만 사용 — 지연 누적 방지)
        if not self._event.wait(timeout=10.0):
            print("[tracker] 10초간 프레임 없음 — 브리지 연결 확인")
            return False, None
        self._event.clear()
        return True, self._frame

    def release(self):
        pass


# ══════════════════════════════════════════════════════════════════════════
# ROS 백엔드 서보 — ServoController 와 같은 인터페이스
# (mode / current_angle / connected / move_to / start_sweep / hold / center)
# ══════════════════════════════════════════════════════════════════════════
class RosServo:
    SEND_INTERVAL = 0.1   # 명령 최소 간격(초) — 시리얼 과부하 방지

    def __init__(self, node: Node):
        self.connected = True
        self.mode = "hold"
        self.current_angle = 75   # 시작값(보정된 중앙각)
        self._pub = node.create_publisher(String, '/servo_cmd', 10)
        self._last_send = 0.0
        node.create_subscription(String, '/servo_state', self._on_state, 10)

    def _on_state(self, msg: String):
        s = msg.data.strip()
        if s.startswith("P"):
            try:
                self.current_angle = int(s[1:])
            except ValueError:
                pass

    def _send(self, cmd: str):
        m = String()
        m.data = cmd
        self._pub.publish(m)

    def move_to(self, angle: float):
        now = time.time()
        if now - self._last_send < self.SEND_INTERVAL:
            return
        self._last_send = now
        a = int(max(0, min(180, round(angle))))
        self.mode = "track"
        self._send(f"A{a}")

    def start_sweep(self):
        if self.mode != "sweep":
            self.mode = "sweep"
            self._send("S")

    def hold(self):
        if self.mode != "hold":
            self.mode = "hold"
            self._send("H")

    def center(self):
        self.mode = "track"
        self._send("C")

    def close(self):
        self._send("C")


def main() -> int:
    rclpy.init()
    node = rclpy.create_node('tracker_node')

    cam = RosCamera(node)
    servo = RosServo(node)

    # rclpy 콜백은 백그라운드 스레드에서 처리
    spin_th = threading.Thread(target=rclpy.spin, args=(node,), daemon=True)
    spin_th.start()

    # core의 카메라 열기를 ROS 카메라로 대체
    core.open_camera = lambda index=0: cam

    # ── cv2 GUI 호출 가로채기 ───────────────────────────────────
    # WSL에는 화면이 없을 수 있으므로 imshow 프레임을 /image/annotated 로
    # 발행하고, Windows 브리지가 네이티브 창으로 표시한다.
    qos_view = QoSProfile(depth=1, reliability=ReliabilityPolicy.BEST_EFFORT)
    pub_view = node.create_publisher(CompressedImage, '/image/annotated', qos_view)
    view_state = {"last": 0.0}

    def ros_imshow(_title, frame):
        now = time.time()
        if now - view_state["last"] < 1 / 15:   # 최대 15fps로 송출
            return
        view_state["last"] = now
        ok, jpg = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 75])
        if ok:
            m = CompressedImage()
            m.format = "jpeg"
            m.data = jpg.tobytes()
            pub_view.publish(m)

    cv2.imshow = ros_imshow
    cv2.waitKey = lambda *_a, **_k: -1          # 키 입력 없음 (Windows 창에서 ESC)
    cv2.destroyAllWindows = lambda *_a, **_k: None

    print("[tracker] 프로필 로드...")
    try:
        profile = core.load_profile()
    except FileNotFoundError:
        print(f"[tracker] 프로필 없음: {core.PROFILE_PATH}")
        print("          Windows에서 먼저 사용자 등록을 하거나 data/ 를 복사하세요")
        return 1
    print(f"[tracker] 사용자 [{profile['user_id']}] 로드 완료")

    print("[tracker] 모델 로드 (YOLO/MediaPipe/ReID)...")
    yolo = core.create_yolo()
    hog = None
    if yolo is None:
        hog = cv2.HOGDescriptor()
        hog.setSVMDetector(cv2.HOGDescriptor_getDefaultPeopleDetector())
        print("[tracker] YOLO 불가 → HOG 폴백")
    pose = core.create_pose_estimator()
    reid = core.create_reid_model()

    print("[tracker] 추적 시작 — ROS2 토픽으로 영상 수신 중")
    try:
        core.run_tracking(yolo, hog, pose, reid, profile, servo=servo)
    finally:
        servo.close()
        rclpy.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
