"""
사람 특징 추출 및 매칭 모듈 (경량)

OpenCV HSV 히스토그램 + OSNet ReID 딥러닝 임베딩 조합.

특징 가중치 (합 = 1.0):
  - ReID 임베딩 (256차원)     60%
  - HSV 색상 (상/하의)        20%
  - 위치 연속성               15%
  - bbox 가로/세로 비율        5%
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import cv2
import numpy as np

# ── 매칭 임계값 (튜닝 가능) ─────────────────────────────────
MATCH_THRESHOLD     = 0.72   # 최초 획득: 새 사람을 추종 대상으로 잠금
KEEP_THRESHOLD      = 0.60   # FOLLOW 유지 (이 아래로 떨어지면 lost)
REACQUIRE_THRESHOLD = 0.58   # SEARCH 재획득: color 붕괴 대응 (이슈 #48)

# FOLLOW/최초획득 가중치 (합 = 1.0) — ReID 중심 (60%) + HSV 보조 (20%) + 위치(15%) + 체형(5%)
W_REID     = 0.60
W_COLOR    = 0.20
W_POSITION = 0.15
W_SHAPE    = 0.05

# SEARCH 재획득 전용 가중치 — color 의존도 최소화 (조명/각도 변화 대응)
W_REID_SEARCH     = 0.80
W_COLOR_SEARCH    = 0.07
W_POSITION_SEARCH = 0.08
W_SHAPE_SEARCH    = 0.05

# 색상 히스토그램 bin 수 (작을수록 빠르지만 거칠어짐)
HIST_BINS_H = 16   # Hue
HIST_BINS_S = 16   # Saturation


def _safe_crop(image: np.ndarray, x1: int, y1: int, x2: int, y2: int) -> np.ndarray | None:
    """이미지 경계를 벗어나지 않게 잘라내기."""
    h, w = image.shape[:2]
    x1, y1 = max(0, x1), max(0, y1)
    x2, y2 = min(w, x2), min(h, y2)
    if x2 <= x1 or y2 <= y1:
        return None
    return image[y1:y2, x1:x2]


def _hsv_hist(bgr_crop: np.ndarray) -> np.ndarray:
    """HSV 2D 히스토그램 (Hue+Saturation). 조명 변화에 강함."""
    hsv = cv2.cvtColor(bgr_crop, cv2.COLOR_BGR2HSV)
    hist = cv2.calcHist(
        [hsv], [0, 1], None,
        [HIST_BINS_H, HIST_BINS_S],
        [0, 180, 0, 256],
    )
    cv2.normalize(hist, hist, 0, 1, cv2.NORM_MINMAX)
    return hist.flatten()


def extract_features(image: np.ndarray, bbox: tuple[int, int, int, int], reid_model=None) -> dict | None:
    """
    한 사람 bbox에서 특징 추출 (HSV + ReID 임베딩).

    bbox: (x1, y1, x2, y2) 픽셀 좌표
    reid_model: osnet_x0_25 모델 (None이면 HSV만 추출)
    반환: 특징 dict (없으면 None)
    """
    x1, y1, x2, y2 = bbox
    person = _safe_crop(image, x1, y1, x2, y2)
    if person is None:
        return None

    bh, bw = person.shape[:2]
    if bh < 40 or bw < 20:   # 너무 작은 박스는 무시
        return None

    # 사람 영역 2분할: 상의(상단 55%) / 하의(55~100%)
    upper_y2 = int(bh * 0.55)
    upper_crop = person[0:upper_y2, :]
    lower_crop = person[upper_y2:bh, :]

    # ReID 임베딩 추출
    reid_emb = None
    if reid_model is not None:
        try:
            import torch
            person_rgb = cv2.cvtColor(person, cv2.COLOR_BGR2RGB)
            person_resized = cv2.resize(person_rgb, (128, 256))
            person_norm = (person_resized.astype(np.float32) / 255.0 -
                          np.array([0.485, 0.456, 0.406])) / np.array([0.229, 0.224, 0.225])
            x = torch.from_numpy(person_norm.transpose(2, 0, 1)).unsqueeze(0).float()
            with torch.no_grad():
                feat_vec = reid_model(x)
            reid_emb = feat_vec.squeeze(0).cpu().numpy().tolist()
        except Exception:
            reid_emb = None

    feat = {
        "reid_emb":   reid_emb,
        "hist_upper": _hsv_hist(upper_crop).tolist() if upper_crop.size else None,
        "hist_lower": _hsv_hist(lower_crop).tolist() if lower_crop.size else None,
        "aspect":     bw / bh,
        "cx":         (x1 + x2) / 2,
        "cy":         (y1 + y2) / 2,
        "timestamp":  time.time(),
    }
    return feat


def _hist_similarity(h1: list | None, h2: list | None) -> float:
    """두 히스토그램 코사인 유사도 (0~1)."""
    if h1 is None or h2 is None:
        return 0.0
    a = np.array(h1, dtype=np.float32)
    b = np.array(h2, dtype=np.float32)
    denom = (np.linalg.norm(a) * np.linalg.norm(b))
    if denom < 1e-6:
        return 0.0
    return float(np.dot(a, b) / denom)


def compare_features(saved: dict, current: dict, prev_cx: float | None = None) -> float:
    """
    저장된 특징과 현재 후보의 매칭 점수 (0~1).
    ReID 임베딩이 주 식별 수단 (W_REID 60%).

    prev_cx: 이전 프레임의 추종 대상 중심 x (위치 연속성 계산용)
    """
    # 1) ReID 임베딩 코사인 유사도 (신규)
    sim_reid = 0.0
    saved_emb = saved.get("reid_emb")
    curr_emb = current.get("reid_emb")
    if saved_emb is not None and curr_emb is not None:
        a = np.array(saved_emb, dtype=np.float32)
        b = np.array(curr_emb, dtype=np.float32)
        denom = np.linalg.norm(a) * np.linalg.norm(b)
        if denom > 1e-6:
            sim_reid = float(np.dot(a, b) / denom)

    # 2) 상의 색상
    sim_upper = _hist_similarity(saved.get("hist_upper"), current.get("hist_upper"))
    # 3) 하의 색상
    sim_lower = _hist_similarity(saved.get("hist_lower"), current.get("hist_lower"))
    # 4) 체형 비율 (차이가 작을수록 점수 ↑)
    a_saved, a_curr = saved.get("aspect", 0.5), current.get("aspect", 0.5)
    sim_shape = max(0.0, 1.0 - abs(a_saved - a_curr) / max(a_saved, 0.1))
    # 5) 위치 연속성 (이전 프레임 중심과 가까울수록 ↑)
    if prev_cx is None:
        sim_pos = 0.5
    else:
        dx = abs(current.get("cx", prev_cx) - prev_cx)
        sim_pos = max(0.0, 1.0 - dx / 300.0)

    # 상/하의 평균을 색상 점수로
    sim_color = (sim_upper + sim_lower) / 2

    score = (
        W_REID     * sim_reid +
        W_COLOR    * sim_color +
        W_SHAPE    * sim_shape +
        W_POSITION * sim_pos
    )
    return float(np.clip(score, 0.0, 1.0))


def save_features(feat: dict, path: str | Path) -> None:
    """등록된 사용자 특징을 JSON 파일로 저장."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(feat, f, ensure_ascii=False, indent=2)


def load_features(path: str | Path) -> dict | None:
    """저장된 특징 불러오기. 파일 없으면 None."""
    path = Path(path)
    if not path.exists():
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


# ── 자체 점검 (개발 중 수동 테스트용) ─────────────────────────
if __name__ == "__main__":
    print("[features.py] 자체 점검")
    # 더미 이미지 (640x480) 가운데에 가짜 사람 박스
    img = np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8)
    bbox = (200, 100, 440, 460)

    f1 = extract_features(img, bbox)
    print(f"  [OK] 특징 추출 → 키: {list(f1.keys())}")

    f2 = extract_features(img, bbox)
    score = compare_features(f1, f2, prev_cx=320)
    print(f"  [OK] 동일 박스 매칭 점수: {score:.3f} (1.0에 가까워야 정상)")

    # 다른 박스
    f3 = extract_features(img, (50, 50, 200, 400))
    score2 = compare_features(f1, f3, prev_cx=320)
    print(f"  [OK] 다른 박스 매칭 점수: {score2:.3f}")
    print("[features.py] 점검 완료")
