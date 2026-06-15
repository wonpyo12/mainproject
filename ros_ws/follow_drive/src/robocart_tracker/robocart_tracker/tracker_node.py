#!/usr/bin/env python3
"""
[노트북] 사용자 추적 노드 — smart_cart_core(인식/매칭 1400줄)를 그대로 재사용

핵심: core.run_tracking() 은 카메라(open_camera)와 서보(servo) 객체만 쓰므로
      그 둘만 ROS2 백엔드로 바꿔 끼운다. 인식/매칭 로직은 무수정.

  /image/compressed 구독 → cv2.imdecode → core.run_tracking 에 프레임 공급
  결과 동작 →  FollowActuator
       추적 → /robocart/cmd_vel (TurtleBot3 바퀴) + /robocart/servo "CENTER"
       검색 → /robocart/servo "SCAN_START" (ESP32) + cmd_vel 0
  추적 결과 화면(cv2.imshow 가로채기) → /image/annotated 발행(디버그)

준비물(노트북, 이 파일과 같은 PYTHONPATH 에 둘 것):
  smart_cart_core.py            ← 저장소 ros_ws/tracker/ 에서 복사
  data/ (등록된 사용자 프로필)   ← Windows에서 등록 후 복사, 또는 --register 로 생성
  yolov8n.pt                    ← 저장소 OpenCV/Opencv/ 에서 복사

실행 (노트북, Pi와 같은 Wi-Fi · 같은 ROS_DOMAIN_ID=30):
  source /opt/ros/humble/setup.bash
  export ROS_DOMAIN_ID=30
  cd <smart_cart_core.py 있는 폴더>
  ros2 run robocart_tracker tracker_node
  # 회전 방향이 반대면:
  ros2 run robocart_tracker tracker_node --ros-args -p k_rot:=-1.0 -p forward_speed:=0.12
"""
import threading
import time

import cv2
import numpy as np
import rclpy
from rclpy.qos import QoSProfile, ReliabilityPolicy
from sensor_msgs.msg import CompressedImage

import smart_cart_core as core

from robocart_tracker.follow_actuator import FollowActuator


# ══════════════════════════════════════════════════════════════════════════
# ROS 백엔드 카메라 — cv2.VideoCapture 와 같은 인터페이스 (.read/.release)
# ══════════════════════════════════════════════════════════════════════════
class RosCamera:
    def __init__(self, node):
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
            print("[tracker] 10초간 프레임 없음 — Pi camera_node / 네트워크 확인")
            return False, None
        self._event.clear()
        return True, self._frame

    def release(self):
        pass


def main() -> int:
    rclpy.init()
    node = rclpy.create_node('tracker_node')

    cam = RosCamera(node)
    actuator = FollowActuator(node)

    # rclpy 콜백은 백그라운드 스레드에서 처리
    spin_th = threading.Thread(target=rclpy.spin, args=(node,), daemon=True)
    spin_th.start()

    # core 의 카메라 열기를 ROS 카메라로 대체
    core.open_camera = lambda index=0: cam

    # ── cv2 GUI 호출 가로채기 ───────────────────────────────────
    # 노트북에 화면이 있으면 그대로 imshow 해도 되지만, 헤드리스/원격을 위해
    # imshow 프레임을 /image/annotated 로도 발행한다.
    qos_view = QoSProfile(depth=1, reliability=ReliabilityPolicy.BEST_EFFORT)
    pub_view = node.create_publisher(CompressedImage, '/image/annotated', qos_view)
    view_state = {"last": 0.0}
    _orig_imshow = cv2.imshow

    def ros_imshow(title, frame):
        now = time.time()
        if now - view_state["last"] >= 1 / 15:   # 최대 15fps 로 송출
            view_state["last"] = now
            ok, jpg = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 75])
            if ok:
                m = CompressedImage()
                m.format = "jpeg"
                m.data = jpg.tobytes()
                pub_view.publish(m)
        # 로컬 화면이 가능하면 같이 표시(없으면 예외 무시)
        try:
            _orig_imshow(title, frame)
        except cv2.error:
            pass

    cv2.imshow = ros_imshow

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

    print("[tracker] 추적 시작 — Pi 영상 수신 중 (cmd_vel→TurtleBot3, servo→ESP32)")
    try:
        core.run_tracking(yolo, hog, pose, reid, profile, servo=actuator)
    finally:
        actuator.close()
        rclpy.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
