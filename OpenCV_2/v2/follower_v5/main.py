# -*- coding: utf-8 -*-
"""[프로그램 진입점 모듈] main.py
- 주요 역할: 인자 파싱, 딥러닝 모델(YOLO/ReID) 로딩, 카메라 및 ROS2 노드 연결 후 추종 루프 기동.
- 주요 함수:
  - main(): 전체 하드웨어/소프트웨어 세션 초기화 및 예외 처리 안전 종료 총괄
"""

from __future__ import annotations

import os
import threading
import time

import cv2
from light_models import FaceOrient, OnnxReID, OnnxYolo

from .config import MODELS_DIR, PROFILE_PATH, YUNET_ONNX, parse_args, pick_yolo_onnx
from .camera import MjpegCamera
from .ros_node import RobotController, _ROS2_OK
from .tracker_loop import console_input_thread, load_profile, register, run_tracking
from .utils import DBG, DebugLog, set_robot_led

try:
    import rclpy
except ImportError:
    pass


def main() -> int:
    args = parse_args()
    stream_url = args.stream_url or f"http://{args.pi_ip}:5000/video_feed"
    speak_ip = args.speak_ip or args.pi_ip

    global DBG
    DBG = DebugLog(enabled=not args.no_debug_log)
    if DBG.path:
        print(f"[debug] 로그 기록: {DBG.path} (분석: python3 analyze_debug.py)")
    DBG.log("start", imgsz=args.imgsz, reid_model=args.reid_model,
            mirror=args.mirror, invert_turn=args.invert_turn,
            cpu=os.cpu_count())

    print("[init] 모델 로딩...")
    if args.threads <= 0:
        args.threads = max(1, min(4, (os.cpu_count() or 2) - 1))
    print(f"[init] CPU 코어={os.cpu_count()}, onnx threads={args.threads}")
    yolo_path, yolo_sz = pick_yolo_onnx(args.imgsz)
    print(f"[init] YOLO={yolo_path.name} imgsz={yolo_sz}")
    yolo = OnnxYolo(str(yolo_path), imgsz=yolo_sz, threads=args.threads)

    reid_path = MODELS_DIR / f"osnet_{args.reid_model}.onnx"
    reid = OnnxReID(str(reid_path), threads=args.threads)
    face = FaceOrient(str(YUNET_ONNX) if not args.no_face else None)
    print(f"[init] YOLO/ReID OK (ReID={reid_path.name}), face={face.mode}")

    print(f"[cam] 분산 MJPEG 연결: {stream_url}")
    cam = MjpegCamera(stream_url, mirror=args.mirror)
    time.sleep(1.0)
    if cam.read() is None:
        print(f"[오류] 스트림({stream_url}) 프레임 수신 실패. 라파의 pi_camera_streamer.py 실행 확인.")
        cam.stop()
        return 1

    follower = None
    if not args.no_drive:
        if not _ROS2_OK:
            print("[경고] rclpy 없음 → 주행 비활성(인식만). source /opt/ros/humble/setup.bash 필요")
        else:
            rclpy.init()
            follower = RobotController(esp_ip=args.esp_ip, pi_ip=speak_ip,
                                       ang_sign=-1.0 if args.invert_turn else 1.0)
            ex = rclpy.executors.MultiThreadedExecutor()
            ex.add_node(follower)
            threading.Thread(target=ex.spin, daemon=True).start()
            threading.Thread(target=console_input_thread, args=(follower,), daemon=True).start()

    if args.reset and PROFILE_PATH.exists():
        PROFILE_PATH.unlink()
    profile = load_profile()

    if profile and profile.get("reid_model", "x1_0") != args.reid_model:
        print(f"[profile] ReID 모델 불일치(프로필={profile.get('reid_model', 'x1_0')}, "
              f"현재={args.reid_model}) → 기존 프로필 폐기. 재등록 필요.")
        profile = None

    if args.register:
        if PROFILE_PATH.exists():
            PROFILE_PATH.unlink()
            print(f"[profile] 기존 프로필 삭제: {PROFILE_PATH.name}")
        if follower is not None:
            profile = {"user_id": args.user_id, "phases": {}}
            follower.is_registered = False
            print("[register] 앱에서 QR 인식(시작 명령) 후 촬영을 시작합니다. 대기 중...")
        else:
            print("[register] 경고: 주행(ROS2) 비활성 상태라 즉시 촬영합니다.")
            profile = register(cam, yolo, reid, args.user_id, grace_sec=args.grace, pi_ip=speak_ip)
    elif profile is None:
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
        cam.stop()
        cv2.destroyAllWindows()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
