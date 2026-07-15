#!/usr/bin/env python3
"""
SmartCart 등록 사용자 실시간 인식 시스템 (단일 실행 파일)

기술 스택:
  YOLO (ultralytics)        : 사람 검출
  MediaPipe PoseLandmarker  : 체형 측정 + 앞/뒤 방향 판별
  ResNet50 (torchvision)    : Person ReID 임베딩
  HSV 히스토그램             : 상하의 색상 프로파일

4가지 구분 요소 (가중치 합 = 1.0):
  1. ReID 임베딩   50%  — ResNet50 2048차원 전신 특징
  2. 의상 색상     25%  — 상하의 HSV 히스토그램
  3. 체형 비율     15%  — MediaPipe 12차원 골격 비율 벡터
  4. 위치 연속성   10%  — 이전 프레임 bbox 중심 거리

실행 방법:
  python smart_cart_main.py            # 기존 등록 데이터로 추종
  python smart_cart_main.py --register # 새로 등록 후 추종
  python smart_cart_main.py --reset    # 기존 데이터 삭제 후 재등록
"""

from __future__ import annotations

import argparse
import collections
import json
import math
import os
import shutil
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import cv2
import mediapipe as mp
import numpy as np
from mediapipe.tasks.python import BaseOptions
from mediapipe.tasks.python.vision import PoseLandmarker, PoseLandmarkerOptions, RunningMode
try:
    # mediapipe <= 0.10.x legacy 경로
    from mediapipe.python.solutions.pose import PoseLandmark   # enum: NOSE, LEFT_SHOULDER …
except ImportError:
    # mediapipe 0.10.30+ 에서 legacy solutions 제거됨 → 동일 인덱스 자체 정의
    # (tasks API PoseLandmarker도 같은 33개 랜드마크 인덱스를 사용)
    from enum import IntEnum

    class PoseLandmark(IntEnum):
        NOSE           = 0
        LEFT_EYE       = 2
        RIGHT_EYE      = 5
        LEFT_EAR       = 7
        RIGHT_EAR      = 8
        LEFT_SHOULDER  = 11
        RIGHT_SHOULDER = 12
        LEFT_ELBOW     = 13
        RIGHT_ELBOW    = 14
        LEFT_WRIST     = 15
        RIGHT_WRIST    = 16
        LEFT_HIP       = 23
        RIGHT_HIP      = 24
        LEFT_KNEE      = 25
        RIGHT_KNEE     = 26
        LEFT_ANKLE     = 27
        RIGHT_ANKLE    = 28

from servo_controller import ServoController

# ── YOLO ─────────────────────────────────────────────────────────────────────
try:
    from ultralytics import YOLO as _YOLO
    YOLO_AVAILABLE = True
except ImportError:
    YOLO_AVAILABLE = False
    print("[경고] ultralytics 없음 → HOG 폴백 사용")
    print("       pip install ultralytics")

# ── ReID (ResNet50) ───────────────────────────────────────────────────────────
try:
    import torch
    import torchvision.transforms as T
    from torchvision import models as tv_models
    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False
    print("[경고] PyTorch/torchvision 없음 → HOG 폴백 사용")
    print("       pip install torch torchvision")

# ── 한글 텍스트 렌더링 (PIL) ─────────────────────────────────────────────────
try:
    from PIL import ImageFont, ImageDraw, Image as _PILImage
    _PIL_OK = True
except ImportError:
    _PIL_OK = False

_KR_FONT_CANDIDATES = [
    "C:/Windows/Fonts/malgun.ttf",   # 맑은 고딕
    "C:/Windows/Fonts/gulim.ttc",    # 굴림
    "C:/Windows/Fonts/batang.ttc",   # 바탕
    "C:/Windows/Fonts/NanumGothic.ttf",
    # WSL에서 실행 시 (Windows 폰트는 /mnt/c 로 마운트됨)
    "/mnt/c/Windows/Fonts/malgun.ttf",
    "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
]
_KR_FONT_PATH = next((p for p in _KR_FONT_CANDIDATES if os.path.exists(p)), None)
_FONT_CACHE: dict = {}


def _pil_font(size: int):
    if size not in _FONT_CACHE:
        _FONT_CACHE[size] = (
            ImageFont.truetype(_KR_FONT_PATH, size)
            if (_PIL_OK and _KR_FONT_PATH) else None
        )
    return _FONT_CACHE[size]


def put_texts(frame: np.ndarray, items: list) -> None:
    """
    한 프레임의 텍스트를 PIL로 일괄 렌더링합니다 (변환 1회).
    items: [((x, y), text, pil_font_size, bgr_color), ...]
    (x, y): PIL 기준 좌측 상단 좌표
    """
    if not items:
        return
    if _PIL_OK and _KR_FONT_PATH:
        img = _PILImage.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
        draw = ImageDraw.Draw(img)
        for (x, y), text, size, bgr in items:
            f = _pil_font(size)
            draw.text((x, y), text, font=f, fill=(bgr[2], bgr[1], bgr[0]))
        frame[:] = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)
    else:
        # PIL 없음: cv2 폴백 (한글 깨짐)
        for (x, y), text, size, bgr in items:
            cv2_y = y + size  # PIL top → cv2 baseline 보정
            cv2.putText(frame, text, (x, cv2_y),
                        cv2.FONT_HERSHEY_SIMPLEX, max(0.3, size / 36.0), bgr, 1)


# ══════════════════════════════════════════════════════════════════════════════
# 설정 상수
# ══════════════════════════════════════════════════════════════════════════════

DATA_DIR     = Path(__file__).resolve().parent / "data"
SAMPLES_DIR  = DATA_DIR / "samples"
PROFILE_PATH = DATA_DIR / "smart_cart_profile.json"

_MODEL_NAME       = "pose_landmarker_lite.task"
_MODEL_SRC        = DATA_DIR / _MODEL_NAME
_MODEL_CACHE_DIR  = Path(os.environ.get("LOCALAPPDATA", os.path.expanduser("~"))) / "mediapipe_models"
_MODEL_CACHE_PATH = _MODEL_CACHE_DIR / _MODEL_NAME

YOLO_MODEL_FILE = "yolov8n.pt"
CROP_SIZE       = (128, 256)   # (width, height)
HIST_BINS       = (16, 16)     # H, S 채널 bins

# ── 가중치 ───────────────────────────────────────────────────────────────────
W_REID     = 0.55   # 위치 비중 줄이고 ReID 비중 증가
W_COLOR    = 0.25
W_SHAPE    = 0.15
W_POSITION = 0.05   # 위치 연속성 의존도 낮춤 (위치 오탐 방지)

# ── 임계값 ───────────────────────────────────────────────────────────────────
MATCH_THRESHOLD    = 0.77   # 추적 시작 (강화)
KEEP_THRESHOLD     = 0.67   # 추적 유지 (강화)
LOST_MAX           = 20     # 유실 허용 프레임
SCORE_WINDOW       = 10     # 이동 평균 창
REID_FLOOR         = 0.50   # ReID 최소 하한 (이 미만이면 무조건 비등록자)
COLOR_FLOOR        = 0.35   # 색상 최소 하한 (옷 색상이 전혀 안 맞으면 거부)
MIN_CONFIRM_FRAMES = 3      # 추종 시작 전 연속 매칭 프레임 수

# ── 서보 (카메라 팬) ──────────────────────────────────────────────────────────
SERVO_HFOV_DEG   = 60.0   # 카메라 수평 화각 (대략값, 실측 후 조정)
SERVO_GAIN       = 0.5    # P제어 게인 — 클수록 빠르게 따라가지만 오버슈트 위험
SERVO_DIRECTION  = 1      # 사용자가 화면 오른쪽일 때 서보 각도가 증가해야 하면 1, 반대면 -1
SERVO_DEAD_ZONE  = 40     # 화면 중앙 ±N px 이내면 서보 정지 (떨림 방지)
SEARCH_GRACE_SEC = 2.0    # searching 상태가 이 시간 이상 지속되면 탐색 스윕 시작

_PoseLM = PoseLandmark


# ══════════════════════════════════════════════════════════════════════════════
# 모델 초기화
# ══════════════════════════════════════════════════════════════════════════════

def _resolve_model_path() -> str:
    """pose_landmarker_lite.task 파일의 ASCII 경로를 반환합니다."""
    _MODEL_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    if not _MODEL_CACHE_PATH.exists() and _MODEL_SRC.exists():
        shutil.copy2(_MODEL_SRC, _MODEL_CACHE_PATH)
    if _MODEL_CACHE_PATH.exists():
        return str(_MODEL_CACHE_PATH)
    if _MODEL_SRC.exists():
        return str(_MODEL_SRC)
    raise FileNotFoundError(
        f"MediaPipe 모델 파일 없음: {_MODEL_NAME}\n"
        f"  필요 경로: {_MODEL_SRC}\n"
        f"  다운로드: https://storage.googleapis.com/mediapipe-models/"
        f"pose_landmarker/pose_landmarker_lite/float16/1/pose_landmarker_lite.task"
    )


def create_pose_estimator(num_poses: int = 2) -> PoseLandmarker:  # 경량화: 6→2명
    opts = PoseLandmarkerOptions(
        base_options=BaseOptions(model_asset_path=_resolve_model_path()),
        running_mode=RunningMode.IMAGE,
        num_poses=num_poses,
        min_pose_detection_confidence=0.5,
        min_pose_presence_confidence=0.5,
        min_tracking_confidence=0.5,
    )
    return PoseLandmarker.create_from_options(opts)


def create_yolo():
    if not YOLO_AVAILABLE:
        return None
    return _YOLO(YOLO_MODEL_FILE)


# OSNet(Person-ReID 전용) 가중치 경로 — market1501 학습본
OSNET_WEIGHTS = DATA_DIR / "osnet_x1_0_market1501.pth"


def create_reid_model():
    if not TORCH_AVAILABLE:
        return None

    # 1순위: OSNet (Person-ReID 전용, market1501 학습) — 사람 구분 정확도 높음
    if OSNET_WEIGHTS.exists():
        try:
            import torchreid
            model = torchreid.models.build_model(
                "osnet_x1_0", num_classes=1000, loss="softmax", pretrained=False)
            torchreid.utils.load_pretrained_weights(model, str(OSNET_WEIGHTS))
            model.eval()   # eval 모드에서 forward 는 512차원 임베딩 반환
            print("  → OSNet x1_0 (market1501) ReID 모델 사용")
            return model
        except Exception as e:
            print(f"  → OSNet 로드 실패({e}) — ResNet50 폴백")

    # 폴백: ImageNet ResNet50 (ReID 전용 아님)
    weights = tv_models.ResNet50_Weights.IMAGENET1K_V1
    model = tv_models.resnet50(weights=weights)
    model.fc = torch.nn.Identity()   # 2048-dim 출력
    model.eval()
    print("  → ResNet50(ImageNet) ReID 모델 사용")
    return model


# torchvision 전처리 파이프라인 (ResNet50 입력 규격)
_REID_TRANSFORM = (
    T.Compose([
        T.ToPILImage(),
        T.Resize((256, 128)),
        T.ToTensor(),
        T.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
    ])
    if TORCH_AVAILABLE else None
)


# ══════════════════════════════════════════════════════════════════════════════
# 사람 검출
# ══════════════════════════════════════════════════════════════════════════════

YOLO_IMGSZ = 256   # 입력 해상도 축소 → 검출 속도 향상 (경량화: 320 → 256)


def detect_yolo(frame: np.ndarray, yolo) -> list[tuple[int, int, int, int]]:
    """YOLO로 사람 bbox 목록을 반환합니다."""
    results = yolo(frame, classes=[0], verbose=False, imgsz=YOLO_IMGSZ)
    bboxes = []
    for r in results:
        for box in r.boxes:
            if float(box.conf[0]) < 0.40:
                continue
            x1, y1, x2, y2 = map(int, box.xyxy[0])
            if (x2 - x1) < 40 or (y2 - y1) < 80:
                continue
            bboxes.append((x1, y1, x2, y2))
    return bboxes


def _nms(boxes, scores, iou_thr=0.45):
    order = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)
    suppressed = set()
    keep = []
    for i in order:
        if i in suppressed:
            continue
        keep.append(i)
        a = boxes[i]
        for j in order:
            if j in suppressed or j == i:
                continue
            b = boxes[j]
            ix1, iy1 = max(a[0], b[0]), max(a[1], b[1])
            ix2, iy2 = min(a[2], b[2]), min(a[3], b[3])
            inter = max(0, ix2 - ix1) * max(0, iy2 - iy1)
            if inter > 0:
                union = (a[2]-a[0])*(a[3]-a[1]) + (b[2]-b[0])*(b[3]-b[1]) - inter
                if inter / max(union, 1) > iou_thr:
                    suppressed.add(j)
    return keep


def detect_hog(frame: np.ndarray, hog) -> list[tuple[int, int, int, int]]:
    """HOG 폴백 사람 검출."""
    h_f, w_f = frame.shape[:2]
    rects, weights = hog.detectMultiScale(
        frame, winStride=(8, 8), padding=(8, 8), scale=1.1
    )
    if len(rects) == 0:
        return []
    boxes, scores = [], []
    for (x, y, bw, bh), w in zip(rects, weights):
        wv = float(w) if np.ndim(w) == 0 else float(w[0])
        if wv < 0.1:
            continue
        boxes.append((max(0, x), max(0, y), min(w_f, x+bw), min(h_f, y+bh)))
        scores.append(wv)
    keep = _nms(boxes, scores)
    return [boxes[i] for i in keep]


def detect_people(frame, yolo, hog_fallback) -> list[tuple[int, int, int, int]]:
    if yolo is not None:
        return detect_yolo(frame, yolo)
    return detect_hog(frame, hog_fallback)


# ══════════════════════════════════════════════════════════════════════════════
# 특징 추출 1 — ReID 임베딩 (전신 외형)
# ══════════════════════════════════════════════════════════════════════════════

def extract_reid(reid_model, crop: np.ndarray) -> list[float]:
    """ResNet50 → 2048차원 임베딩. torch 없으면 HOG 폴백."""
    resized = cv2.resize(crop, CROP_SIZE)
    if TORCH_AVAILABLE and reid_model is not None and _REID_TRANSFORM is not None:
        rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
        tensor = _REID_TRANSFORM(rgb).unsqueeze(0)
        with torch.no_grad():
            emb = reid_model(tensor).squeeze().numpy()
        return emb.tolist()

    # HOG 폴백 (3780차원)
    gray = cv2.cvtColor(cv2.resize(resized, (64, 128)), cv2.COLOR_BGR2GRAY)
    hog_desc = cv2.HOGDescriptor((64, 128), (16, 16), (8, 8), (8, 8), 9)
    vec = hog_desc.compute(gray)
    return vec.flatten().tolist() if vec is not None else []


# ══════════════════════════════════════════════════════════════════════════════
# 특징 추출 2 — 색상 (상하의 HSV 히스토그램)
# ══════════════════════════════════════════════════════════════════════════════

def _hs_hist(roi: np.ndarray) -> np.ndarray:
    hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
    # V채널(명도) 제외 → 조명 변화에 강건
    hist = cv2.calcHist([hsv], [0, 1], None, list(HIST_BINS), [0, 180, 0, 256])
    return cv2.normalize(hist, hist).flatten().astype(np.float32)


def extract_color(crop: np.ndarray) -> dict[str, Any]:
    """
    상의: 상단 15~55% 영역
    하의: 55~90% 영역  (머리·발목 제외)
    """
    r = cv2.resize(crop, CROP_SIZE)
    h = r.shape[0]
    top_roi = r[int(h * 0.15):int(h * 0.55), :]
    bot_roi = r[int(h * 0.55):int(h * 0.90), :]

    def safe_extract(roi):
        if roi.size == 0:
            return np.zeros(HIST_BINS[0] * HIST_BINS[1], np.float32).tolist(), [128.0, 128.0, 128.0]
        return _hs_hist(roi).tolist(), np.mean(roi.reshape(-1, 3), axis=0).tolist()

    top_hist, top_bgr = safe_extract(top_roi)
    bot_hist, bot_bgr = safe_extract(bot_roi)
    return {"top_hist": top_hist, "bot_hist": bot_hist,
            "top_bgr": top_bgr, "bot_bgr": bot_bgr}


# ══════════════════════════════════════════════════════════════════════════════
# 특징 추출 3 — 체형 비율 (MediaPipe 12차원 벡터)
# ══════════════════════════════════════════════════════════════════════════════

def _lm(lms, idx) -> tuple[np.ndarray, float]:
    pt = lms[int(idx)]
    return np.array([pt.x, pt.y], np.float32), float(getattr(pt, "visibility", 0.0) or 0.0)


def infer_orientation(lms: list) -> str:
    """랜드마크 가시성으로 앞(front) / 뒤(back) / 측면(side) 판별."""
    _, nose_v = _lm(lms, _PoseLM.NOSE)
    _, leye_v = _lm(lms, _PoseLM.LEFT_EYE)
    _, reye_v = _lm(lms, _PoseLM.RIGHT_EYE)
    _, lsh_v  = _lm(lms, _PoseLM.LEFT_SHOULDER)
    _, rsh_v  = _lm(lms, _PoseLM.RIGHT_SHOULDER)
    _, lear_v = _lm(lms, _PoseLM.LEFT_EAR)
    _, rear_v = _lm(lms, _PoseLM.RIGHT_EAR)

    face_score  = nose_v + leye_v + reye_v
    sh_score    = lsh_v + rsh_v
    ear_balance = abs(lear_v - rear_v)

    if face_score > 1.2 and sh_score > 0.8:
        return "front"
    if face_score < 0.6 and sh_score > 0.8:
        return "back"
    if ear_balance > 0.35:
        return "side"
    return "unknown"


def compute_body_vector(lms: list, world_lms: list | None) -> list[float]:
    """12차원 체형 비율 벡터. world_landmarks 사용 시 3D 거리 기반."""
    try:
        if world_lms and len(world_lms) > 0:
            def d3(a, b):
                pa, pb = world_lms[int(a)], world_lms[int(b)]
                return math.sqrt((pa.x-pb.x)**2 + (pa.y-pb.y)**2 + (pa.z-pb.z)**2)

            sh_w = d3(_PoseLM.LEFT_SHOULDER, _PoseLM.RIGHT_SHOULDER)
            hip_w = d3(_PoseLM.LEFT_HIP, _PoseLM.RIGHT_HIP)

            ls, rs = world_lms[int(_PoseLM.LEFT_SHOULDER)], world_lms[int(_PoseLM.RIGHT_SHOULDER)]
            lh, rh = world_lms[int(_PoseLM.LEFT_HIP)],      world_lms[int(_PoseLM.RIGHT_HIP)]
            sh_c  = np.array([(ls.x+rs.x)/2, (ls.y+rs.y)/2, (ls.z+rs.z)/2])
            hip_c = np.array([(lh.x+rh.x)/2, (lh.y+rh.y)/2, (lh.z+rh.z)/2])
            torso = float(np.linalg.norm(sh_c - hip_c))

            l_arm = d3(_PoseLM.LEFT_SHOULDER, _PoseLM.LEFT_ELBOW)   + d3(_PoseLM.LEFT_ELBOW,  _PoseLM.LEFT_WRIST)
            r_arm = d3(_PoseLM.RIGHT_SHOULDER, _PoseLM.RIGHT_ELBOW) + d3(_PoseLM.RIGHT_ELBOW, _PoseLM.RIGHT_WRIST)
            l_leg = d3(_PoseLM.LEFT_HIP, _PoseLM.LEFT_KNEE)   + d3(_PoseLM.LEFT_KNEE,  _PoseLM.LEFT_ANKLE)
            r_leg = d3(_PoseLM.RIGHT_HIP, _PoseLM.RIGHT_KNEE) + d3(_PoseLM.RIGHT_KNEE, _PoseLM.RIGHT_ANKLE)
            avg_leg = (l_leg + r_leg) / 2

            nose_pt = world_lms[int(_PoseLM.NOSE)]
            head = float(np.linalg.norm(np.array([nose_pt.x, nose_pt.y, nose_pt.z]) - sh_c))
            H = max(head + torso + avg_leg, 0.5)

            l_ua = d3(_PoseLM.LEFT_SHOULDER,  _PoseLM.LEFT_ELBOW)
            l_la = max(d3(_PoseLM.LEFT_ELBOW, _PoseLM.LEFT_WRIST),  1e-3)
            r_ua = d3(_PoseLM.RIGHT_SHOULDER, _PoseLM.RIGHT_ELBOW)
            r_la = max(d3(_PoseLM.RIGHT_ELBOW,_PoseLM.RIGHT_WRIST), 1e-3)

        else:
            # 2D 좌표 폴백
            nose_p, _ = _lm(lms, _PoseLM.NOSE)
            la_p, _   = _lm(lms, _PoseLM.LEFT_ANKLE)
            ra_p, _   = _lm(lms, _PoseLM.RIGHT_ANKLE)
            H = max(abs(((la_p[1]+ra_p[1])/2) - nose_p[1]), 1e-6)

            def d2(a, b):
                pa, _ = _lm(lms, a)
                pb, _ = _lm(lms, b)
                return float(np.linalg.norm(pa - pb))

            sh_w  = d2(_PoseLM.LEFT_SHOULDER, _PoseLM.RIGHT_SHOULDER)
            hip_w = d2(_PoseLM.LEFT_HIP,      _PoseLM.RIGHT_HIP)
            lsh_p, _ = _lm(lms, _PoseLM.LEFT_SHOULDER)
            rsh_p, _ = _lm(lms, _PoseLM.RIGHT_SHOULDER)
            lhp, _   = _lm(lms, _PoseLM.LEFT_HIP)
            rhp, _   = _lm(lms, _PoseLM.RIGHT_HIP)
            sh_c  = (lsh_p + rsh_p) / 2
            hip_c = (lhp + rhp) / 2
            torso = float(np.linalg.norm(sh_c - hip_c))

            l_arm = d2(_PoseLM.LEFT_SHOULDER,  _PoseLM.LEFT_ELBOW)   + d2(_PoseLM.LEFT_ELBOW,  _PoseLM.LEFT_WRIST)
            r_arm = d2(_PoseLM.RIGHT_SHOULDER, _PoseLM.RIGHT_ELBOW)  + d2(_PoseLM.RIGHT_ELBOW, _PoseLM.RIGHT_WRIST)
            l_leg = d2(_PoseLM.LEFT_HIP,  _PoseLM.LEFT_KNEE)   + d2(_PoseLM.LEFT_KNEE,  _PoseLM.LEFT_ANKLE)
            r_leg = d2(_PoseLM.RIGHT_HIP, _PoseLM.RIGHT_KNEE)  + d2(_PoseLM.RIGHT_KNEE, _PoseLM.RIGHT_ANKLE)
            avg_leg = (l_leg + r_leg) / 2

            ankle_c = (la_p + ra_p) / 2
            head = float(np.linalg.norm(nose_p - sh_c))

            l_ua = d2(_PoseLM.LEFT_SHOULDER,  _PoseLM.LEFT_ELBOW)
            l_la = max(d2(_PoseLM.LEFT_ELBOW, _PoseLM.LEFT_WRIST),  1e-6)
            r_ua = d2(_PoseLM.RIGHT_SHOULDER, _PoseLM.RIGHT_ELBOW)
            r_la = max(d2(_PoseLM.RIGHT_ELBOW,_PoseLM.RIGHT_WRIST), 1e-6)

        return [
            sh_w  / H,                     # [0]  어깨 너비 비율
            hip_w / H,                     # [1]  골반 너비 비율
            torso / H,                     # [2]  몸통 길이 비율
            l_arm / H,                     # [3]  왼팔 비율
            r_arm / H,                     # [4]  오른팔 비율
            l_leg / H,                     # [5]  왼다리 비율
            r_leg / H,                     # [6]  오른다리 비율
            sh_w  / max(hip_w, 1e-3),      # [7]  어깨/골반 비율
            torso / max(avg_leg, 1e-3),    # [8]  상체/하체 비율
            head  / H,                     # [9]  머리 비율
            l_ua  / l_la,                  # [10] 왼쪽 상완/전완
            r_ua  / r_la,                  # [11] 오른쪽 상완/전완
        ]
    except Exception:
        return []


# ══════════════════════════════════════════════════════════════════════════════
# MediaPipe 포즈 실행 + bbox 매칭
# ══════════════════════════════════════════════════════════════════════════════

def run_pose(frame: np.ndarray, pose: PoseLandmarker):
    """전체 프레임에서 MediaPipe PoseLandmarker를 1회 실행합니다."""
    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    mp_img = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
    return pose.detect(mp_img)


def match_pose_idx(results, bbox: tuple, frame_shape: tuple) -> int | None:
    """bbox 내에 속하는 포즈 인덱스를 반환합니다 (없으면 None)."""
    if not results or not results.pose_landmarks:
        return None
    h, w = frame_shape[:2]
    x1, y1, x2, y2 = bbox
    cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
    bbox_diag = math.sqrt((x2-x1)**2 + (y2-y1)**2)

    best_idx, best_dist = None, float("inf")
    for i, lms in enumerate(results.pose_landmarks):
        nose_v = getattr(lms[int(_PoseLM.NOSE)], "visibility", 0.0) or 0.0
        if nose_v > 0.4:
            pt = lms[int(_PoseLM.NOSE)]
            px, py = pt.x * w, pt.y * h
        else:
            ls = lms[int(_PoseLM.LEFT_SHOULDER)]
            rs = lms[int(_PoseLM.RIGHT_SHOULDER)]
            px, py = (ls.x + rs.x) / 2 * w, (ls.y + rs.y) / 2 * h

        dist = math.sqrt((px - cx)**2 + (py - cy)**2)
        if dist < bbox_diag * 0.65 and dist < best_dist:
            best_dist = dist
            best_idx = i
    return best_idx


# ══════════════════════════════════════════════════════════════════════════════
# 통합 특징 추출
# ══════════════════════════════════════════════════════════════════════════════

def extract_features(
    crop: np.ndarray,
    reid_model,
    pose_results=None,
    pose_idx: int | None = None,
) -> dict[str, Any]:
    """한 사람 crop의 4가지 특징을 모두 추출합니다."""
    feat = {
        "reid_emb":    extract_reid(reid_model, crop),
        "color":       extract_color(crop),
        "body_vector": [],
        "orientation": "unknown",
        "pose_ok":     False,
    }
    if pose_results and pose_results.pose_landmarks and pose_idx is not None:
        lms = pose_results.pose_landmarks[pose_idx]
        w_lms = (
            pose_results.pose_world_landmarks[pose_idx]
            if pose_results.pose_world_landmarks and pose_idx < len(pose_results.pose_world_landmarks)
            else None
        )
        try:
            feat["body_vector"] = compute_body_vector(lms, w_lms)
            feat["orientation"] = infer_orientation(lms)
            feat["pose_ok"]     = True
        except Exception:
            pass
    return feat


# ══════════════════════════════════════════════════════════════════════════════
# 유사도 함수
# ══════════════════════════════════════════════════════════════════════════════

def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    va, vb = np.array(a, np.float32), np.array(b, np.float32)
    denom = np.linalg.norm(va) * np.linalg.norm(vb)
    return float(np.clip(np.dot(va, vb) / denom, 0.0, 1.0)) if denom > 0 else 0.0


def _hist_corr(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    va, vb = np.array(a, np.float32), np.array(b, np.float32)
    return max(0.0, float(cv2.compareHist(va, vb, cv2.HISTCMP_CORREL)))


def _body_sim(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dist = float(np.linalg.norm(np.array(a, np.float32) - np.array(b, np.float32)))
    return max(0.0, 1.0 - dist / 4.5)


def score_against_profile(
    ref: dict[str, Any],
    cand: dict[str, Any],
    last_bbox: tuple | None,
    cand_bbox: tuple,
    frame_shape: tuple,
) -> tuple[float, dict[str, float]]:
    """
    등록 특징(ref)과 후보 특징(cand)을 비교하여
    가중 합산 점수와 세부 점수를 반환합니다.
    """
    # 1. ReID 임베딩 코사인 유사도
    reid_sc = _cosine(ref["reid_emb"], cand["reid_emb"])

    # 2. 색상 (상/하의 히스토그램 평균)
    color_sc = (
        _hist_corr(ref["color"]["top_hist"], cand["color"]["top_hist"]) +
        _hist_corr(ref["color"]["bot_hist"], cand["color"]["bot_hist"])
    ) / 2.0

    # 3. 체형 비율 벡터 (12차원)
    shape_sc = _body_sim(ref["body_vector"], cand["body_vector"])
    if not ref["body_vector"] or not cand["body_vector"]:
        shape_sc = 0.5   # 정보 없으면 중립값

    # 4. 위치 연속성 (이전 위치와의 거리)
    if last_bbox is not None:
        cx = (cand_bbox[0] + cand_bbox[2]) / 2
        cy = (cand_bbox[1] + cand_bbox[3]) / 2
        lx = (last_bbox[0] + last_bbox[2]) / 2
        ly = (last_bbox[1] + last_bbox[3]) / 2
        diag = math.sqrt(frame_shape[0]**2 + frame_shape[1]**2)
        dist_r = math.sqrt((cx-lx)**2 + (cy-ly)**2) / max(diag, 1)
        pos_sc = max(0.0, 1.0 - dist_r * 4.0)
    else:
        pos_sc = 0.5

    total = W_REID * reid_sc + W_COLOR * color_sc + W_SHAPE * shape_sc + W_POSITION * pos_sc
    return total, {"reid": reid_sc, "color": color_sc, "shape": shape_sc, "position": pos_sc}


# ══════════════════════════════════════════════════════════════════════════════
# 추적 상태 관리 (히스테리시스 + 유실 대응)
# ══════════════════════════════════════════════════════════════════════════════

class TrackingState:
    def __init__(self) -> None:
        self.is_tracking = False
        self.last_bbox: tuple | None = None
        self.lost_count = 0
        self._history: collections.deque = collections.deque(maxlen=SCORE_WINDOW)
        self._confirm_count = 0   # 연속 임계값 초과 프레임 수
        self.status = "searching"

    @property
    def avg_score(self) -> float:
        return float(np.mean(list(self._history))) if self._history else 0.0

    def update(self, matched: bool, bbox=None, score: float = 0.0) -> None:
        if matched and bbox is not None:
            self._history.append(score)
            self.last_bbox = bbox
            self.lost_count = 0
            s = self.avg_score
            if self.is_tracking:
                if s < KEEP_THRESHOLD:
                    self.is_tracking = False
                    self._confirm_count = 0
                    self.status = "searching"
                else:
                    self.status = "tracking"
            else:
                # 연속 N프레임이 임계값을 넘어야 추종 시작 (단발성 오탐 방지)
                if score >= MATCH_THRESHOLD:
                    self._confirm_count += 1
                else:
                    self._confirm_count = max(0, self._confirm_count - 1)

                if self._confirm_count >= MIN_CONFIRM_FRAMES and s >= MATCH_THRESHOLD:
                    self.is_tracking = True
                    self.status = "tracking"
                else:
                    self.status = f"confirming({self._confirm_count}/{MIN_CONFIRM_FRAMES})"
        else:
            self._confirm_count = 0
            if self.is_tracking:
                self.lost_count += 1
                if self.lost_count > LOST_MAX:
                    self.is_tracking = False
                    self.last_bbox = None
                    self._history.clear()
                    self.status = "searching"
                else:
                    self.status = f"lost({self.lost_count}/{LOST_MAX})"
            else:
                self.status = "searching"

    def reset(self) -> None:
        self.__init__()


# ══════════════════════════════════════════════════════════════════════════════
# JSON 프로필 저장 / 로드
# ══════════════════════════════════════════════════════════════════════════════

def _avg_vecs(vecs: list) -> list[float]:
    valid = [v for v in vecs if v]
    if not valid:
        return []
    return np.mean([np.array(v, np.float32) for v in valid], axis=0).tolist()


def summarise(samples: list[dict]) -> dict[str, Any]:
    """여러 샘플의 특징을 평균으로 요약합니다."""
    return {
        "reid_emb":    _avg_vecs([s["reid_emb"]             for s in samples]),
        "body_vector": _avg_vecs([s["body_vector"]           for s in samples if s["body_vector"]]),
        "color": {
            "top_hist": _avg_vecs([s["color"]["top_hist"] for s in samples]),
            "bot_hist": _avg_vecs([s["color"]["bot_hist"] for s in samples]),
            "top_bgr":  _avg_vecs([s["color"]["top_bgr"]  for s in samples]),
            "bot_bgr":  _avg_vecs([s["color"]["bot_bgr"]  for s in samples]),
        },
    }


def save_profile(profile: dict, path: Path = PROFILE_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(profile, indent=2, ensure_ascii=False), encoding="utf-8")


def load_profile(path: Path = PROFILE_PATH) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def update_profile_ema(phase_ref: dict, new_feat: dict, alpha: float = 0.05) -> None:
    """EMA로 프로필을 서서히 갱신합니다 (색상·ReID 드리프트 보정)."""
    def ema(old, new):
        if not old or not new or len(old) != len(new):
            return old
        o, n = np.array(old, np.float32), np.array(new, np.float32)
        return (o * (1 - alpha) + n * alpha).tolist()

    phase_ref["reid_emb"]    = ema(phase_ref.get("reid_emb", []),    new_feat.get("reid_emb", []))
    phase_ref["body_vector"] = ema(phase_ref.get("body_vector", []), new_feat.get("body_vector", []))
    for k in ("top_hist", "bot_hist", "top_bgr", "bot_bgr"):
        phase_ref["color"][k] = ema(phase_ref["color"].get(k, []), new_feat["color"].get(k, []))


# ══════════════════════════════════════════════════════════════════════════════
# 카메라
# ══════════════════════════════════════════════════════════════════════════════

def open_camera(index: int = 0):
    for backend in [cv2.CAP_ANY, cv2.CAP_DSHOW, cv2.CAP_MSMF]:
        cap = cv2.VideoCapture(index, backend)
        if cap.isOpened():
            return cap
        cap.release()
    return None


# ══════════════════════════════════════════════════════════════════════════════
# 시각화 헬퍼
# ══════════════════════════════════════════════════════════════════════════════

def _score_bar(frame, x, y, label, score, bw=110, bh=13):
    cv2.rectangle(frame, (x, y), (x+bw, y+bh), (45, 45, 45), -1)
    fill = int(bw * min(max(score, 0.0), 1.0))
    c = (0, 220, 60) if score >= MATCH_THRESHOLD else \
        (0, 180, 255) if score >= KEEP_THRESHOLD else (80, 80, 200)
    if fill > 0:
        cv2.rectangle(frame, (x, y), (x+fill, y+bh), c, -1)
    cv2.rectangle(frame, (x, y), (x+bw, y+bh), (130, 130, 130), 1)
    cv2.putText(frame, f"{label}:{score:.2f}", (x+bw+4, y+bh-1),
                cv2.FONT_HERSHEY_SIMPLEX, 0.36, (200, 200, 200), 1)
    return y + bh + 4


def _swatch(frame, x, y, bgr, label, sz=20):
    col = tuple(int(c) for c in bgr[:3])
    cv2.rectangle(frame, (x, y), (x+sz, y+sz), col, -1)
    cv2.rectangle(frame, (x, y), (x+sz, y+sz), (170, 170, 170), 1)
    cv2.putText(frame, label, (x+sz+4, y+sz-3),
                cv2.FONT_HERSHEY_SIMPLEX, 0.37, (200, 200, 200), 1)
    return y + sz + 5


def draw_panel(frame, panel_x, profile, scores, orientation, tracker):
    h, w = frame.shape[:2]
    overlay = frame.copy()
    cv2.rectangle(overlay, (panel_x, 0), (w, h), (22, 22, 22), -1)
    cv2.addWeighted(overlay, 0.80, frame, 0.20, 0, frame)
    cv2.line(frame, (panel_x, 0), (panel_x, h), (80, 80, 80), 1)

    x = panel_x + 8
    y = 8          # PIL top 기준 시작
    bw = min(w - panel_x - 70, 115)

    # ── PIL 텍스트 아이템 수집 ──────────────────────────────────────────────
    txt = []

    txt.append(((x, y), "SmartCart Info", 16, (100, 200, 255)))
    y += 26

    txt.append(((x, y), f"ID: {profile.get('user_id', 'N/A')}", 14, (220, 220, 220)))
    y += 21

    ori_c = {"front": (0, 255, 0), "back": (0, 180, 255)}.get(orientation, (150, 150, 150))
    txt.append(((x, y), f"방향: {orientation}", 14, ori_c))
    y += 21

    s_c = (0, 255, 0) if tracker.is_tracking else (100, 100, 200)
    txt.append(((x, y), f"상태: {tracker.status}", 14, s_c))
    y += 26

    if scores:
        txt.append(((x, y), "[ 4가지 구분 요소 ]", 13, (100, 200, 255)))
        y += 17
        # 점수 바는 cv2로 그린 후 레이블 put_texts로 처리
        y = _score_bar(frame, x, y, "TOTAL", scores.get("total", 0), bw)
        y = _score_bar(frame, x, y, "ReID",  scores.get("reid",  0), bw)
        y = _score_bar(frame, x, y, "Color", scores.get("color", 0), bw)
        y = _score_bar(frame, x, y, "Shape", scores.get("shape", 0), bw)
        y = _score_bar(frame, x, y, "Pos",   scores.get("position", 0), bw)
        y += 8

    # 등록 색상 견본
    phases = profile.get("phases", {})
    col = phases.get("front", {}).get("color", {})
    top_bgr = col.get("top_bgr", [128, 128, 128])
    bot_bgr = col.get("bot_bgr",  [64,  64,  64])
    txt.append(((x, y), "등록 색상", 13, (100, 200, 255)))
    y += 17
    y = _swatch(frame, x, y, top_bgr, "Top")
    y = _swatch(frame, x, y, bot_bgr, "Bot")

    y += 5
    txt.append(((x, y), f"Avg: {tracker.avg_score:.3f}", 13, (170, 170, 170)))

    # PIL 일괄 렌더링 (한 번만 변환)
    put_texts(frame, txt)


# ══════════════════════════════════════════════════════════════════════════════
# 등록 단계 (앞모습 1장 + 뒷모습 1장)
# ══════════════════════════════════════════════════════════════════════════════

COUNTDOWN_SEC   = 3      # 자동 촬영 카운트다운 (초)
TRANSITION_SEC  = 2      # 단계 전환 대기 (초)
CAPTURE_FLASH   = 1.2    # 촬영 완료 표시 시간 (초)


def register_user(yolo, hog_fallback, pose: PoseLandmarker, reid_model,
                  user_id: str = "owner_001", announce=None) -> bool:
    """앞/뒤 자동 촬영 후 등록 프로필(JSON)을 저장합니다.

    흐름: 사람 감지 → 3초 카운트다운 → 자동 촬영 → 뒤로 돌기 안내 → 반복
    announce: 단계별 음성 안내 콜백 (텍스트 1개 인자, 예: 라파 TTS)
    """
    DATA_DIR.mkdir(exist_ok=True)
    (SAMPLES_DIR / "front").mkdir(parents=True, exist_ok=True)
    (SAMPLES_DIR / "back").mkdir(parents=True, exist_ok=True)

    cap = open_camera()
    if cap is None:
        print("[오류] 카메라를 열 수 없습니다.")
        return False

    stages = [
        ("front", "정면을 바라보세요"),
        ("back",  "뒤로 돌아서세요"),
    ]
    samples: dict[str, list] = {"front": [], "back": []}

    print("\n=== 사용자 등록 (자동 촬영) ===  Q: 취소\n")

    def _read() -> tuple[bool, np.ndarray | None]:
        ok, f = cap.read()
        return ok, f if ok else None

    def _check_q() -> bool:
        return cv2.waitKey(1) & 0xFF == ord("q")

    def _best_person(frame: np.ndarray):
        """화면 중앙에 가장 가까운 사람 bbox를 반환합니다."""
        h, w = frame.shape[:2]
        bboxes = detect_people(frame, yolo, hog_fallback)
        if not bboxes:
            return None
        bboxes.sort(key=lambda b: math.sqrt(
            ((b[0]+b[2])/2 - w/2)**2 + ((b[1]+b[3])/2 - h/2)**2))
        return bboxes[0]

    def _draw_base(disp: np.ndarray, stage_idx: int, slabel: str) -> None:
        """공통 상단 바 + 완료 단계 표시."""
        w = disp.shape[1]
        cv2.rectangle(disp, (0, 0), (w, 60), (0, 0, 0), -1)
        items = [((10, 8), f"[{stage_idx+1}/{len(stages)}]  {slabel}", 22, (255, 255, 255))]
        for i in range(stage_idx):
            items.append(((10, 64 + i * 22), f"  [완료] {stages[i][1]}", 18, (0, 220, 0)))
        put_texts(disp, items)

    def _draw_progress_bar(disp: np.ndarray, ratio: float) -> None:
        """하단 카운트다운 진행 바."""
        h, w = disp.shape[:2]
        bw = int(w * 0.7)
        bh = 16
        bx = (w - bw) // 2
        by = h - 40
        cv2.rectangle(disp, (bx, by), (bx+bw, by+bh), (40, 40, 40), -1)
        fill = int(bw * min(ratio, 1.0))
        if fill > 0:
            g = int(180 + 75 * ratio)
            cv2.rectangle(disp, (bx, by), (bx+fill, by+bh), (0, g, 80), -1)
        cv2.rectangle(disp, (bx, by), (bx+bw, by+bh), (140, 140, 140), 1)

    def _draw_countdown(disp: np.ndarray, remaining: float) -> None:
        """중앙 대형 카운트다운 숫자."""
        h, w = disp.shape[:2]
        cnt = str(int(remaining) + 1)
        fs = 5.5
        th = 7
        (tw, tht), _ = cv2.getTextSize(cnt, cv2.FONT_HERSHEY_SIMPLEX, fs, th)
        cx = (w - tw) // 2
        cy = (h + tht) // 2 + 20
        # 반투명 배경
        overlay = disp.copy()
        cv2.circle(overlay, (w//2, h//2 + 20), max(tw, tht)//2 + 30, (0, 0, 0), -1)
        cv2.addWeighted(overlay, 0.45, disp, 0.55, 0, disp)
        # 숫자
        ratio = remaining / COUNTDOWN_SEC
        g = int(255 * (1 - ratio))
        r = int(255 * ratio)
        cv2.putText(disp, cnt, (cx, cy), cv2.FONT_HERSHEY_SIMPLEX, fs, (0, g, r), th)

    try:
        for stage_idx, (sname, slabel) in enumerate(stages):
            countdown_start: float | None = None
            print(f"[{stage_idx+1}/{len(stages)}] {slabel}")
            if announce:
                announce("사진을 촬영합니다. 정면을 바라봐 주세요." if sname == "front"
                         else "뒤돌아 주세요.")

            # ── 카운트다운 & 자동 촬영 ────────────────────────────────────────
            captured = False
            while not captured:
                ok, frame = _read()
                if not ok:
                    return False
                disp = frame.copy()
                h_f, w_f = frame.shape[:2]

                best_box = _best_person(frame)

                # ── 방향 검증: 해당 단계 방향(front/back)과 일치할 때만 촬영 ──
                # (뒷모습이 front 로 잘못 등록되던 문제 방지)
                cur_dir = None
                dir_ok = False
                if best_box is not None:
                    pose_live = run_pose(frame, pose)
                    pidx_live = match_pose_idx(pose_live, best_box, frame.shape)
                    if pidx_live is not None:
                        cur_dir = infer_orientation(pose_live.pose_landmarks[pidx_live])
                    # front: 정면이 확실할 때만 (정면 인식은 신뢰도 높음)
                    # back : 방향 제한 없음 — 사람만 잡히면 촬영 (뒤에선 포즈 인식이
                    #        약해 제한 두면 등록이 막힘. 화면 보며 직접 돌면 됨)
                    if sname == "front":
                        dir_ok = (cur_dir == "front")
                    else:
                        dir_ok = True

                if best_box is not None and dir_ok:
                    if countdown_start is None:
                        countdown_start = time.time()
                    elapsed   = time.time() - countdown_start
                    remaining = max(0.0, COUNTDOWN_SEC - elapsed)
                    ratio     = elapsed / COUNTDOWN_SEC

                    # 박스 색상: 빨강 → 초록 (진행에 따라)
                    g = int(255 * ratio)
                    r = int(255 * (1 - ratio))
                    x1, y1, x2, y2 = best_box
                    cv2.rectangle(disp, (x1, y1), (x2, y2), (0, g, r), 2)

                    _draw_progress_bar(disp, ratio)
                    if remaining > 0:
                        _draw_countdown(disp, remaining)
                elif best_box is not None and not dir_ok:
                    # 사람은 있지만 방향이 안 맞음 → 카운트다운 보류 + 안내
                    countdown_start = None
                    elapsed = 0.0
                    remaining = float(COUNTDOWN_SEC)
                    x1, y1, x2, y2 = best_box
                    cv2.rectangle(disp, (x1, y1), (x2, y2), (0, 140, 255), 2)
                    hint = ("뒤로 완전히 돌아주세요" if sname == "back"
                            else "정면을 바라봐 주세요")
                    put_texts(disp, [
                        ((20, 80), hint, 24, (0, 140, 255)),
                        ((20, 112), f"(현재 인식: {cur_dir or '불명'})", 16, (180, 180, 180)),
                    ])
                else:
                    countdown_start = None
                    elapsed = 0.0
                    remaining = float(COUNTDOWN_SEC)
                    put_texts(disp, [((20, 80), "사람을 찾는 중...", 22, (0, 80, 220))])

                _draw_base(disp, stage_idx, slabel)
                cv2.imshow("SmartCart - 사용자 등록", disp)
                if _check_q():
                    print("등록 취소")
                    return False

                # 촬영 실행
                if best_box is not None and elapsed >= COUNTDOWN_SEC:
                    x1, y1, x2, y2 = best_box
                    pad  = 10
                    crop = frame[max(0, y1-pad):min(h_f, y2+pad),
                                 max(0, x1-pad):min(w_f, x2+pad)]
                    pose_res = run_pose(frame, pose)
                    pidx     = match_pose_idx(pose_res, best_box, frame.shape)
                    feat     = extract_features(crop, reid_model, pose_res, pidx)
                    samples[sname].append(feat)

                    img_path = SAMPLES_DIR / sname / f"{user_id}_001.jpg"
                    cv2.imwrite(str(img_path), crop)
                    print(f"  [{sname}] 촬영 완료  방향={feat['orientation']}")
                    captured = True

                    # ── 촬영 완료 플래시 ────────────────────────────────────
                    flash_end = time.time() + CAPTURE_FLASH
                    while time.time() < flash_end:
                        ok2, f2 = _read()
                        if not ok2:
                            break
                        flash = f2.copy()
                        _draw_base(flash, stage_idx, slabel)
                        hf, wf = flash.shape[:2]
                        put_texts(flash, [
                            ((wf//2 - 90, hf//2 - 20), "촬영 완료!", 46, (0, 255, 80)),
                        ])
                        cv2.imshow("SmartCart - 사용자 등록", flash)
                        if _check_q():
                            return False

            # ── 다음 단계 전환 안내 ───────────────────────────────────────────
            if stage_idx + 1 < len(stages):
                next_label = stages[stage_idx + 1][1]
                trans_end  = time.time() + TRANSITION_SEC
                print(f"  → 다음: {next_label}")
                while time.time() < trans_end:
                    ok2, f2 = _read()
                    if not ok2:
                        break
                    trans = f2.copy()
                    _draw_base(trans, stage_idx + 1, next_label)
                    ht, wt = trans.shape[:2]
                    left = trans_end - time.time()
                    put_texts(trans, [
                        ((wt//2 - 120, ht//2 - 20), next_label, 34, (0, 220, 255)),
                        ((wt//2 - 70,  ht//2 + 26), f"{left:.1f}초 후 시작", 22, (200, 200, 200)),
                    ])
                    cv2.imshow("SmartCart - 사용자 등록", trans)
                    if _check_q():
                        return False

    finally:
        cap.release()
        cv2.destroyAllWindows()

    if not all(samples[s] for s, _ in stages):
        print("등록 실패: 앞/뒤 촬영이 모두 필요합니다.")
        return False

    profile = {
        "user_id":       user_id,
        "registered_at": datetime.now().isoformat(timespec="seconds"),
        "phases": {
            "front": summarise(samples["front"]),
            "back":  summarise(samples["back"]),
        },
    }
    save_profile(profile, PROFILE_PATH)
    print(f"\n등록 완료  →  {PROFILE_PATH}\n")
    return True


# ══════════════════════════════════════════════════════════════════════════════
# 백그라운드 검출 워커 (YOLO + Pose + ReID 비동기 처리)
# ══════════════════════════════════════════════════════════════════════════════

class DetectionWorker(threading.Thread):
    """검출·특징 추출을 백그라운드 스레드에서 실행합니다.

    메인 루프는 카메라 FPS 속도로 프레임을 표시하고,
    검출 결과는 워커가 완료될 때마다 비동기로 갱신됩니다.
    submit()으로 최신 프레임을 제출하면 이전 대기 프레임을 덮어씁니다.
    """

    _EMPTY: dict = {
        "bboxes":      [],
        "bbox_scores": {},
        "best_bbox":   None,
        "best_total":  0.0,
        "best_detail": None,
        "best_ori":    "unknown",
        "feat":        None,
    }

    def __init__(self, yolo, hog_fallback, pose, reid_model, profile) -> None:
        super().__init__(daemon=True)
        self._yolo    = yolo
        self._hog     = hog_fallback
        self._pose    = pose
        self._reid    = reid_model
        self._profile = profile

        self._in_lock  = threading.Lock()
        self._in_frame = None
        self._in_lbbox = None

        self._out_lock = threading.Lock()
        self._out      = dict(self._EMPTY)

        self._stop_flag = False

    def submit(self, frame: np.ndarray, last_bbox) -> None:
        """새 프레임 제출 — 이전 대기 프레임을 덮어써 항상 최신 프레임만 처리."""
        with self._in_lock:
            self._in_frame = frame.copy()   # 메인스레드 드로우와 충돌 방지
            self._in_lbbox = last_bbox

    def get_result(self) -> dict:
        """최신 검출 결과를 반환 (논블로킹)."""
        with self._out_lock:
            return dict(self._out)

    def stop(self) -> None:
        self._stop_flag = True

    def run(self) -> None:
        while not self._stop_flag:
            frame = last_bbox = None
            with self._in_lock:
                if self._in_frame is not None:
                    frame      = self._in_frame
                    last_bbox  = self._in_lbbox
                    self._in_frame = None
            if frame is None:
                time.sleep(0.005)
                continue
            result = self._process(frame, last_bbox)
            with self._out_lock:
                self._out = result
            # CPU 양보: 인식이 100% 점유해 화면 루프가 굶는 것 방지 (박스는 ~6fps 갱신)
            time.sleep(0.04)

    def _process(self, frame: np.ndarray, last_bbox) -> dict:
        h_f, w_f    = frame.shape[:2]
        bboxes      = detect_people(frame, self._yolo, self._hog)
        pose_res    = run_pose(frame, self._pose)
        phases      = self._profile.get("phases", {})

        best_bbox   = None
        best_total  = -1.0
        best_detail = None
        best_ori    = "unknown"
        best_feat   = None
        bbox_scores: dict = {}

        for bbox in bboxes:
            x1, y1, x2, y2 = bbox
            pad  = 5
            crop = frame[max(0, y1-pad):min(h_f, y2+pad),
                         max(0, x1-pad):min(w_f, x2+pad)]
            if crop.size == 0:
                continue

            pidx = match_pose_idx(pose_res, bbox, frame.shape)
            feat = extract_features(crop, self._reid, pose_res, pidx)

            ph_best = -1.0
            ph_det  = None
            ph_ori  = "front"
            for pname, pref in phases.items():
                if not pref:
                    continue
                sc, det_sc = score_against_profile(
                    pref, feat, last_bbox, bbox, frame.shape)
                if sc > ph_best:
                    ph_best = sc
                    ph_det  = det_sc
                    ph_ori  = pname

            bbox_scores[bbox] = ph_best
            if ph_best > best_total:
                best_total  = ph_best
                best_bbox   = bbox
                best_detail = ph_det
                best_ori    = ph_ori
                best_feat   = feat

        return {
            "bboxes":      bboxes,
            "bbox_scores": bbox_scores,
            "best_bbox":   best_bbox,
            "best_total":  best_total,
            "best_detail": best_detail,
            "best_ori":    best_ori,
            "feat":        best_feat,
        }


# ══════════════════════════════════════════════════════════════════════════════
# 실시간 추종
# ══════════════════════════════════════════════════════════════════════════════

def run_tracking(yolo, hog_fallback, pose: PoseLandmarker,
                 reid_model, profile: dict, panel_width: int = 240,
                 servo: ServoController | None = None) -> None:
    cap = open_camera()
    if cap is None:
        print("[오류] 카메라를 열 수 없습니다.")
        return

    tracker    = TrackingState()
    frame_count = 0
    t0         = time.time()
    cur_scores: dict | None = None
    cur_ori    = "unknown"
    phases     = profile.get("phases", {})
    search_since: float | None = None   # searching 상태 진입 시각

    print("=== 실시간 추종 ===  ESC: 종료\n")

    # 백그라운드 검출 워커 시작
    worker = DetectionWorker(yolo, hog_fallback, pose, reid_model, profile)
    worker.start()

    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                break

            frame_count += 1
            fps = frame_count / max(time.time() - t0, 1e-6)
            w_f     = frame.shape[1]
            panel_x = w_f - panel_width

            # 현재 프레임을 워커에 제출 (논블로킹 — 이전 대기 프레임 덮어씀)
            worker.submit(frame, tracker.last_bbox)

            # 최신 검출 결과 가져오기 (논블로킹)
            det         = worker.get_result()
            bboxes      = det["bboxes"]
            bbox_scores = det["bbox_scores"]
            best_bbox   = det["best_bbox"]
            best_total  = det["best_total"]
            best_detail = det["best_detail"]
            best_ori    = det["best_ori"]
            feat        = det["feat"]

            # 비등록자 차단: ReID + 색상 둘 다 하한을 충족해야 매칭
            reid_ok  = best_detail is not None and best_detail.get("reid",  0) >= REID_FLOOR
            color_ok = best_detail is not None and best_detail.get("color", 0) >= COLOR_FLOOR
            matched  = (best_bbox is not None and best_total >= MATCH_THRESHOLD
                        and reid_ok and color_ok)

            # ── 점수 진단 로그 (1초 간격) — 왜 인식이 되고/안 되는지 ──────────
            if best_detail is not None and frame_count % 15 == 0:
                why = "" if matched else (
                    " [차단:" +
                    ("total<%.2f " % MATCH_THRESHOLD if best_total < MATCH_THRESHOLD else "") +
                    ("reid<%.2f " % REID_FLOOR if not reid_ok else "") +
                    ("color<%.2f" % COLOR_FLOOR if not color_ok else "") + "]")
                print("[score] total=%.2f reid=%.2f color=%.2f shape=%.2f pos=%.2f ori=%s %s"
                      % (best_total, best_detail.get("reid", 0), best_detail.get("color", 0),
                         best_detail.get("shape", 0), best_detail.get("position", 0),
                         best_ori, ("MATCH" if matched else why)), flush=True)

            if matched:
                tracker.update(True, best_bbox, best_total)
                cur_scores = {**best_detail, "total": best_total}
                cur_ori    = best_ori

                x1, y1, x2, y2 = best_bbox
                cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 3)
                label = f"{profile['user_id']} [{best_ori}] {best_total:.2f}"
                (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.55, 2)
                ty = max(th + 6, y1 - 8)
                cv2.rectangle(frame, (x1, ty-th-4), (x1+tw+6, ty+2), (0, 200, 0), -1)
                cv2.putText(frame, label, (x1+3, ty-2),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 0, 0), 2)

                # 매우 높은 확신 구간에서만 EMA 프로필 갱신 (비등록자 드리프트 방지)
                if tracker.status == "tracking" and best_total >= 0.90 and feat is not None:
                    update_profile_ema(phases[best_ori], feat, alpha=0.04)
                    save_profile(profile, PROFILE_PATH)

            else:
                tracker.update(False)
                if tracker.status.startswith("lost") and tracker.last_bbox:
                    x1, y1, x2, y2 = tracker.last_bbox
                    cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 140, 255), 2)
                    cv2.putText(frame, tracker.status, (x1, max(18, y1-8)),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.48, (0, 140, 255), 2)

            # ── 서보 제어 ────────────────────────────────────────────────────
            # matched      → 사용자를 화면 중앙에 유지 (P제어)
            # lost(n/20)   → 잠깐 가려진 것일 수 있으니 그 자리에서 대기
            # searching    → 유예 시간 경과 후 탐색 스윕 시작
            if servo is not None:
                if matched:
                    search_since = None
                    if servo.mode == "sweep":
                        servo.hold()   # 탐색 중 발견 → 즉시 정지
                    cx = (best_bbox[0] + best_bbox[2]) / 2
                    err_px = cx - w_f / 2
                    if abs(err_px) > SERVO_DEAD_ZONE:
                        err_deg = err_px / w_f * SERVO_HFOV_DEG
                        servo.move_to(servo.current_angle
                                      + SERVO_DIRECTION * SERVO_GAIN * err_deg)
                elif tracker.status.startswith("lost"):
                    search_since = None
                    servo.hold()
                else:   # searching
                    now_t = time.time()
                    if search_since is None:
                        search_since = now_t
                    elif now_t - search_since >= SEARCH_GRACE_SEC:
                        servo.start_sweep()

            # 비등록자 박스 (회색) — 등록자 박스와 중복 방지
            for bbox in bboxes:
                if bbox == best_bbox and matched:
                    continue
                x1, y1, x2, y2 = bbox
                sc = bbox_scores.get(bbox, 0.0)
                cv2.rectangle(frame, (x1, y1), (x2, y2), (95, 95, 95), 1)
                cv2.putText(frame, f"{sc:.2f}", (x1, max(18, y1-5)),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.38, (95, 95, 95), 1)

            # HUD
            hud_c = (0, 255, 0) if tracker.is_tracking else (100, 100, 200)
            cv2.rectangle(frame, (0, 0), (panel_x, 34), (0, 0, 0), -1)
            servo_info = (f"  Servo:{servo.current_angle} {servo.mode}"
                          if servo is not None and servo.connected else "")
            cv2.putText(frame,
                        f"FPS:{fps:.0f}  Cand:{len(bboxes)}  {tracker.status.upper()}{servo_info}",
                        (8, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.56, hud_c, 2)
            put_texts(frame, [((8, 36), "ESC: 종료", 14, (160, 160, 160))])

            # 정보 패널
            draw_panel(frame, panel_x, profile, cur_scores, cur_ori, tracker)

            cv2.imshow("SmartCart - 실시간 추종", frame)
            if cv2.waitKey(1) & 0xFF == 27:
                break
    finally:
        worker.stop()
        cap.release()
        cv2.destroyAllWindows()


# ══════════════════════════════════════════════════════════════════════════════
# 메인
# ══════════════════════════════════════════════════════════════════════════════

def parse_args():
    p = argparse.ArgumentParser(description="SmartCart 등록 사용자 실시간 인식")
    p.add_argument("--register", action="store_true", help="새로 등록 후 추종")
    p.add_argument("--reset",    action="store_true", help="기존 데이터 삭제 후 재등록")
    p.add_argument("--camera",   type=int, default=0, help="카메라 인덱스 (기본값: 0)")
    p.add_argument("--user-id",  default="owner_001",  help="등록 사용자 ID")
    p.add_argument("--serial-port", default=None,
                   help="ESP32 시리얼 포트 (예: COM3). 생략 시 자동 탐지")
    p.add_argument("--no-servo", action="store_true", help="서보 제어 비활성화")
    return p.parse_args()


def main() -> int:
    args = parse_args()

    # Windows 콘솔 UTF-8 설정 (한글 print 깨짐 방지)
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass

    print("=" * 58)
    print("  SmartCart 등록 사용자 실시간 인식 시스템")
    print("  YOLO + MediaPipe PoseLandmarker + ResNet50 ReID")
    print("=" * 58)

    # ── 모델 로드 ─────────────────────────────────────────────────────────────
    print("\n[1/3] YOLO (yolov8n) 로드...")
    yolo = create_yolo()
    hog_fallback = None
    if yolo is None:
        hog_fallback = cv2.HOGDescriptor()
        hog_fallback.setSVMDetector(cv2.HOGDescriptor_getDefaultPeopleDetector())
        print("  → HOG 폴백 사용")

    print("[2/3] MediaPipe PoseLandmarker 로드...")
    pose = create_pose_estimator()

    print("[3/3] ResNet50 ReID 모델 로드...")
    reid_model = create_reid_model()
    if reid_model is None:
        print("  → HOG 폴백 사용")

    print("\n모델 준비 완료!\n")

    # ── 등록 초기화 ───────────────────────────────────────────────────────────
    if args.reset and PROFILE_PATH.exists():
        PROFILE_PATH.unlink()
        print("기존 등록 데이터 삭제\n")

    need_reg = args.register or args.reset or not PROFILE_PATH.exists()

    if not need_reg:
        print(f"기존 등록 데이터: {PROFILE_PATH}")
        print("  1) 기존 데이터로 추종 시작")
        print("  2) 새로 등록")
        print("  3) 종료")
        choice = input("선택 (1/2/3): ").strip()
        if choice == "2":
            need_reg = True
        elif choice != "1":
            pose.close()
            return 0

    if need_reg:
        ok = register_user(yolo, hog_fallback, pose, reid_model, args.user_id)
        if not ok:
            pose.close()
            return 1

    # ── 프로필 로드 ───────────────────────────────────────────────────────────
    try:
        profile = load_profile(PROFILE_PATH)
    except Exception as e:
        print(f"[오류] 프로필 로드 실패: {e}")
        pose.close()
        return 1

    print(f"사용자 [{profile['user_id']}] 로드 완료")
    print(f"등록 일시: {profile.get('registered_at', 'N/A')}\n")

    # ── 서보 연결 (ESP32 + MG996R) ───────────────────────────────────────────
    servo = ServoController(port=args.serial_port, enabled=not args.no_servo)

    # ── 실시간 추종 ───────────────────────────────────────────────────────────
    try:
        run_tracking(yolo, hog_fallback, pose, reid_model, profile, servo=servo)
    finally:
        servo.close()

    pose.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
