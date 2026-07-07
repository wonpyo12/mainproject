#!/usr/bin/env python3
"""
[WSL] 사용자 등록 노드 — 라파 카메라(ROS)로 새 사용자를 등록

  /image/compressed (라파 카메라) 구독 → core.register_user() 의 입력으로 공급
  등록 UI(정면/뒤돌기 안내 + 3초 카운트다운) → /image/annotated 발행
    → 브라우저 http://localhost:8090/ 에서 보며 따라하면 됨
  완료 시 data/smart_cart_profile.json 저장 → tracker_node 가 다음 실행부터 사용

키보드 입력이 없으므로(헤드리스) 'q' 취소는 동작하지 않고, 사람을 비추면
3초 뒤 자동 촬영 → 뒤돌기 안내 → 자동 촬영 순으로 진행된다.

실행 (WSL):
  source /opt/ros/humble/setup.bash
  source ~/robocart_ws/install/setup.bash   # 불필요(코어만 쓰면) 하지만 무해
  export ROS_DOMAIN_ID=0
  cd ~/robocart_run
  python3 register_node.py                   # 기본 ID: owner_001 (덮어씀)
  python3 register_node.py --user-id owner_002
"""
import argparse
import threading
import time

import cv2
import numpy as np
import rclpy
from rclpy.qos import QoSProfile, ReliabilityPolicy
from sensor_msgs.msg import CompressedImage
from std_msgs.msg import String

import smart_cart_core as core


class RosCamera:
    """cv2.VideoCapture 인터페이스(.read/.release)로 /image/compressed 를 공급."""
    def __init__(self, node):
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
        if not self._event.wait(timeout=15.0):
            print("[register] 라파 영상 없음 — camera_node/네트워크 확인")
            return False, None
        self._event.clear()
        return True, self._frame

    def release(self):
        pass


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--user-id", default="owner_001")
    args = ap.parse_args()

    rclpy.init()
    node = rclpy.create_node('register_node')
    cam = RosCamera(node)
    threading.Thread(target=rclpy.spin, args=(node,), daemon=True).start()

    # core 의 카메라 입력을 ROS 카메라로 대체
    core.open_camera = lambda index=0: cam

    # ── 등록 중 카메라 고정 ─────────────────────────────────────
    # 이전 tracker 가 스캔(SCAN_START) 상태로 두고 갔을 수 있으므로,
    # 등록 동안 서보가 움직이지 않도록 중앙 고정 명령을 보낸다.
    servo_pub = node.create_publisher(String, '/robocart/servo', 10)

    def hold_camera_center():
        for cmd in ("SCAN_STOP", "CENTER"):
            m = String(); m.data = cmd
            servo_pub.publish(m)
            time.sleep(0.2)

    # 발행 직후엔 구독자 연결이 안 됐을 수 있어 잠깐 대기 후 수 회 전송
    time.sleep(1.0)
    for _ in range(3):
        hold_camera_center()
    print("[register] 서보 중앙 고정 — 등록 중 카메라 움직임 없음")

    # 등록 UI(cv2.imshow) 를 /image/annotated 로 발행 → 브라우저 표시
    qos = QoSProfile(depth=1, reliability=ReliabilityPolicy.BEST_EFFORT)
    pub_view = node.create_publisher(CompressedImage, '/image/annotated', qos)
    vstate = {"last": 0.0}

    def ros_imshow(_title, frame):
        now = time.time()
        if now - vstate["last"] >= 1 / 20:
            vstate["last"] = now
            ok, jpg = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
            if ok:
                m = CompressedImage()
                m.format = "jpeg"
                m.data = jpg.tobytes()
                pub_view.publish(m)

    cv2.imshow = ros_imshow
    cv2.waitKey = lambda *_a, **_k: -1          # 키 입력 없음(취소 비활성)
    cv2.destroyAllWindows = lambda *_a, **_k: None

    print("[register] 모델 로드 (YOLO/MediaPipe/ReID)...")
    yolo = core.create_yolo()
    hog = None
    if yolo is None:
        hog = cv2.HOGDescriptor()
        hog.setSVMDetector(cv2.HOGDescriptor_getDefaultPeopleDetector())
    pose = core.create_pose_estimator()
    reid = core.create_reid_model()

    print(f"[register] 등록 시작 — 브라우저(localhost:8090)를 보며 따라하세요")
    print("           1) 정면으로 서기 → 3초 후 자동 촬영")
    print("           2) 뒤로 돌기 → 자동 촬영")
    ok = core.register_user(yolo, hog, pose, reid, user_id=args.user_id)
    if ok:
        print(f"[register] 등록 완료 → {core.PROFILE_PATH}")
        print("           이제 tracker_node 를 실행하면 새 사용자를 추종합니다.")
    else:
        print("[register] 등록 실패(앞/뒤 촬영 미완료)")

    rclpy.shutdown()
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
