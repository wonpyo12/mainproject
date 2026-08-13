#!/usr/bin/env python3
"""
ros_person_follower_nav2_v5 — 등록 사용자 인식 + 추종 + Nav2 원점 복귀 (분산 처리판)

버전 이력
  - v3 : ReID 모델 OSNet-x0.25 → OSNet-x1.0 교체 (임베딩 품질↑).
         ※ x0.25↔x1.0 임베딩은 비호환 → 프로필 분리(robocart_profile_v3.json), 재등록 필요.
  - v4 : 앱/웹 연동(정지·재개·복귀 토픽), ESP8266 LED 상태 표시, 라파 TTS 음성 안내,
         라이다 브리징·예측 조향·가속도 제한 등 주행 안정화.
  - v5 : 최종 확정본. 촬영 후 5초 무음 대기 출발, 백엔드 복귀 Nav2 goal을 RPi
         return_controller로 단일화(선점 경쟁 제거), /robocart/reset 구독,
         유실 재획득 구제(ReID 단독 0.62) + 온라인 프로필 보강.

설계
  - 인식부: robocart_light(YOLOv8n-ONNX + OSNet-ONNX + 색상) 파이프라인을 그대로 이식.
            DetectionWorker(비동기 검출) + MOSSE 보간 + 등록(앞/뒤) + ReID/색상/위치 가중 스코어링.
            → "아무나"가 아니라 '등록된 1명'만 추종한다.
  - 영상부: 라즈베리파이 pi_camera_streamer.py 의 MJPEG(:5000)을 VM이 받아 추론(분산 처리).
  - 주행부: 주행/복귀 기능을 RobotController 한 노드로 통합.
            FOLLOW = 인식 bbox → /cmd_vel(Twist) P제어,  RETURN = Nav2 navigate_to_pose 복귀.
            터미널에 '복귀'/'추종' 입력으로 모드 전환.

추가 기능
  - 재등록 시 기존 프로필 파일을 먼저 삭제(기록 누적 방지).
  - 판정 인식률(%)을 화면 박스 라벨 / 상단 HUD / 터미널 로그에 표시.

실행(VM)
  source /opt/ros/humble/setup.bash
  export TURTLEBOT3_MODEL=burger
  # (선택) Nav2 복귀를 쓰려면 별도 터미널에서 navigation2 + rviz 먼저 기동
  python3 ros_person_follower_nav2_v5.py --pi-ip <라파IP> --esp-ip <ESP IP> \
      --speak-ip <키오스크IP>:5001 --register

  q : 종료 / 터미널에 '복귀' 또는 '추종' 입력 : 모드 전환

의존(같은 폴더): light_features.py, light_models.py, models_light/
"""
from __future__ import annotations

import argparse
import os
import threading
import time

import cv2

from light_models import FaceOrient, OnnxReID, OnnxYolo

from follower import config, tracking
from follower.camera import MjpegCamera
from follower.config import MODELS_DIR, PROFILE_PATH, YUNET_ONNX, pick_yolo_onnx
from follower.console import console_input_thread
from follower.debug_log import DBG
from follower.notify import set_robot_led
from follower.profile import load_profile
from follower.registration import register
from follower.robot import _ROS2_OK, RobotController
from follower.tracking import run_tracking

try:                      # 주행 없이(인식만) 돌릴 수 있게 graceful
    import rclpy
except Exception:
    rclpy = None


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

    config.RECORD_SEC = args.record_sec
    if not args.no_debug_log:
        DBG.enable()
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
    config.REID_MODEL_NAME = args.reid_model
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
        tracking.close_recorder()   # 녹화 중이면 파일 저장 (조기 종료 시 보존)
        cam.stop()
        cv2.destroyAllWindows()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
