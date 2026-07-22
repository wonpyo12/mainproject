# -*- coding: utf-8 -*-
"""[설정 모듈] config.py
- 주요 역할: 시스템 전반의 상수, ONNX 모델 경로, 주행 제어 게인값 설정 및 CLI 터미널 인자 파싱(parse_args).
- 주요 구성:
  1. 딥러닝 모델(YOLO, ReID, YuNet) 파일 경로 및 프로필 저장 경로
  2. 로봇 제어 한계(최대 속도, P제어 게인, 데드밴드, 안전 정지 거리 등)
  3. 터미널 명령행 옵션 파서 (parse_args)
"""

from __future__ import annotations

import argparse
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
MODELS_DIR = HERE / "models_light"
PROFILE_PATH = HERE / "robocart_profile_v3.json"

RECORD_SEC = 0.0

REID_ONNX = MODELS_DIR / "osnet_x1_0.onnx"
REID_MODEL_NAME = "x1_0"
YUNET_ONNX = MODELS_DIR / "face_detection_yunet.onnx"

YOLO_ONNX_BY_SZ = {
    320: MODELS_DIR / "yolov8n.onnx",
    256: MODELS_DIR / "yolov8n_256.onnx",
    192: MODELS_DIR / "yolov8n_192.onnx",
}

DETECT_INTERVAL = 8      # 검출 사이 KCF 보간 프레임 수
KCF_MAX_AGE     = 40     # KCF 단독 보간 허용 최대 (초과 시 강제 재검출)

WINDOW = "robocart v3 - Registered User Follow + Nav2"

# ── 로봇 구동 한계 및 제어 상수 ──
BURGER_MAX_LIN = 0.22
BURGER_MAX_ANG = 2.84

CALIB_K        = 22000.0
TARGET_DIST_CM = 35.0
DIST_NEAR_CM   = 30.0
DIST_FAR_CM    = 40.0
CENTER_DEADBAND = 0.05
CENTER_HOLD_GAIN = 1.5

KP_LIN_DIST = 0.006
KP_ANG      = 0.8
MAX_LIN     = 0.16
MAX_LIN_REV = 0.08
MAX_ANG     = 0.9
ALLOW_REVERSE = True

FRONT_STOP_M = 0.25

SEARCH_ANG         = 0.20
SEARCH_HALF_PERIOD = 15.7
SEARCH_START_DELAY = 5.0

REG_MIN_SAMPLES = 20
REG_MAX_SEC     = 15.0

BRIDGE_MAX_SEC  = 2.0
BRIDGE_CONE_DEG = 20
BRIDGE_MIN_M    = 0.2
BRIDGE_MAX_M    = 1.5
BRIDGE_MAX_LIN  = 0.10
REG_DETECT_EVERY = 5

ACC_LIN_UP   = 0.25
ACC_LIN_DOWN = 0.80
ACC_ANG      = 2.5

PRED_MAX_SEC = 0.8
PRED_MAX_VX  = 400.0


def pick_yolo_onnx(imgsz: int) -> tuple[Path, int]:
    p = YOLO_ONNX_BY_SZ.get(imgsz)
    if p and p.exists():
        return p, imgsz
    return MODELS_DIR / "yolov8n.onnx", 320


def parse_args():
    p = argparse.ArgumentParser(description="등록 사용자 추종 + Nav2 복귀 (분산)")
    p.add_argument("--pi-ip", default="192.168.0.35", help="라즈베리파이 IP (MJPEG :5000)")
    p.add_argument("--speak-ip", default=None,
                   help="음성 안내 수신 서버 - 'IP' 또는 'IP:포트' (예: 192.168.0.22:5001). 미지정 시 pi-ip")
    p.add_argument("--esp-ip", default=None, help="ESP8266 (RFID & LED) IP 주소 (예: 192.168.0.xx)")
    p.add_argument("--stream-url", default=None,
                   help="직접 지정 시 우선 (기본: http://<pi-ip>:5000/video_feed)")
    p.add_argument("--imgsz", type=int, default=256,
                   help="YOLO 입력 크기(192/256/320). 기본 256")
    p.add_argument("--reid-model", choices=["x0_25", "x1_0"], default="x1_0",
                   help="ReID 모델. 기본 x1_0(변별력 우수)")
    p.add_argument("--threads", type=int, default=0,
                   help="onnxruntime 스레드 수. 0=자동")
    p.add_argument("--register", action="store_true", help="등록(앞/뒤) 후 추종")
    p.add_argument("--reset", action="store_true", help="기존 프로필 삭제 후 등록")
    p.add_argument("--user-id", default="owner_001")
    p.add_argument("--no-face", action="store_true", help="얼굴 방향 보조 비활성화")
    p.add_argument("--grace", type=float, default=5.0, help="촬영 시작 전 준비 시간(초)")
    p.add_argument("--no-drive", action="store_true",
                   help="ROS2 주행 비활성(인식만 확인). cmd_vel/Nav2 미사용")
    p.add_argument("--invert-turn", action="store_true",
                   help="회전 방향 반전 (모터가 반대로 돌 때)")
    p.add_argument("--mirror", action="store_true",
                   help="카메라 영상 좌우반전 보정 (영상이 거울상일 때)")
    p.add_argument("--no-debug-log", action="store_true",
                   help="디버그 로그(debug_logs/run_*.jsonl) 기록 비활성화")
    p.add_argument("--record-sec", type=float, default=0.0,
                   help="지정 시 HUD 포함 화면을 mp4로 녹화 (0=끔)")
    return p.parse_args()
