"""robocart_light — 순수 특징/점수/추적 유틸 (torch 무관, cv2+numpy 만 사용).

기존 robocart_main.py 의 색상·점수·추적 로직을 경량 파이프라인용으로 분리.
- 체형(MediaPipe) 제거 → 가중치 재배분 (ReID 0.65 / 색상 0.30 / 위치 0.05)
- RPi4 의 apt cv2(4.5.4) / numpy(1.21) 에서 동작하도록 표준 API 만 사용
"""
from __future__ import annotations

import collections
import math
from typing import Any

import cv2
import numpy as np

# ── 규격 ──────────────────────────────────────────────────────────────────────
CROP_SIZE = (128, 256)   # (width, height) — ReID/색상 공통 정규화 크기
HIST_BINS = (16, 16)     # H, S 채널 bins

# ── 가중치 (체형 제거 반영) ────────────────────────────────────────────────────
# 색상(0.30)이 높으면 같은 색 옷 입은 타인이 등록자로 오인식됨 → ReID 비중↑, 색상↓
W_REID     = 0.70
W_COLOR    = 0.25
W_POSITION = 0.05

# ── 임계값 ────────────────────────────────────────────────────────────────────
# REID_FLOOR 가 타인 차단의 핵심 하드게이트(색상과 무관하게 ReID 낮으면 즉시 탈락).
# [히스테리시스] 진입 엄격 / 유지 느슨: 초록 켜기는 어렵게, 한번 켜지면 오래 유지.
MATCH_THRESHOLD    = 0.74   # 추적 시작 (진입 엄격: 원본 0.72→0.74)
SEARCH_MATCH_THR   = 0.68   # 완전 유실 탐색 중 재인식 (원본 0.70→1차 0.65→2차 0.60→3차 0.68)
KEEP_THRESHOLD     = 0.60   # 추적 유지 (원본 0.62→1차 0.56→2차 0.60→4차 0.58→5차 0.60 복귀)
REID_FLOOR         = 0.55   # ReID 하한(진입/탐색용) — 미만이면 무조건 비등록자
KEEP_REID_FLOOR    = 0.52   # ReID 하한(추적 유지 중) — 1차 0.45→2차 0.52 강화, 타인 오인식(drift) 차단
COLOR_FLOOR        = 0.15   # 색상 하한(진입/탐색용) — 추적 유지 중엔 생략(조명/자세 변화 허용)
LOST_MAX           = 60     # 유실 허용 프레임 (30에서 60으로 연장해 유실 유예시간 연장)
SCORE_WINDOW       = 10     # 이동 평균 창
MIN_CONFIRM_FRAMES    = 4   # 추종 시작 전 연속 매칭 프레임 (진입 엄격: 원본 3→4)
SEARCH_CONFIRM_FRAMES = 3   # 완전 유실 후 재인식 시 연속 매칭 프레임 (5→3: 촬영 직후 바로 탐색모드 진입 방지)
# [이슈 #48] 유실 후 재획득 실패 대책 — 탐색 중 color 히스토그램이 붕괴(조명/각도/뒷모습)해
# total이 SEARCH_MATCH_THR에 영구 미달하는 문제. 재획득에 한해 ReID 단독으로 구제한다.
# 근거(07-13 주행 로그): 탐색 중 본인 ReID p50=0.611/p90=0.683, 타인 차단선(REID_FLOOR)=0.55,
# 추적 중 본인 p10=0.627 → 그 사이 0.62 선택. SEARCH_CONFIRM_FRAMES 연속 요구가 오인식을 이중 차단.
SEARCH_REID_RESCUE = 0.62   # 재획득 전용 ReID 단독 임계 (had_track=True 인 탐색에만 적용)


# ══════════════════════════════════════════════════════════════════════════════
# 색상 특징 (상/하의 HSV 히스토그램)
# ══════════════════════════════════════════════════════════════════════════════

def _hs_hist(roi: np.ndarray) -> np.ndarray:
    hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)        # V채널 제외 → 조명 강건
    hist = cv2.calcHist([hsv], [0, 1], None, list(HIST_BINS), [0, 180, 0, 256])
    return cv2.normalize(hist, hist).flatten().astype(np.float32)


def extract_color(crop: np.ndarray) -> dict[str, Any]:
    """상의(15~55%) / 하의(55~90%) HSV 히스토그램 + 평균 BGR."""
    r = cv2.resize(crop, CROP_SIZE)
    h = r.shape[0]
    top_roi = r[int(h * 0.15):int(h * 0.55), :]
    bot_roi = r[int(h * 0.55):int(h * 0.90), :]

    def safe(roi):
        if roi.size == 0:
            return ([0.0] * (HIST_BINS[0] * HIST_BINS[1]), [128.0, 128.0, 128.0])
        return (_hs_hist(roi).tolist(), np.mean(roi.reshape(-1, 3), axis=0).tolist())

    top_hist, top_bgr = safe(top_roi)
    bot_hist, bot_bgr = safe(bot_roi)
    return {"top_hist": top_hist, "bot_hist": bot_hist,
            "top_bgr": top_bgr, "bot_bgr": bot_bgr}


# ══════════════════════════════════════════════════════════════════════════════
# 유사도
# ══════════════════════════════════════════════════════════════════════════════

def cosine(a, b) -> float:
    if a is None or b is None or len(a) == 0 or len(a) != len(b):
        return 0.0
    va, vb = np.asarray(a, np.float32), np.asarray(b, np.float32)
    denom = float(np.linalg.norm(va) * np.linalg.norm(vb))
    return float(np.clip(np.dot(va, vb) / denom, 0.0, 1.0)) if denom > 0 else 0.0


def hist_corr(a, b) -> float:
    if a is None or b is None or len(a) == 0 or len(a) != len(b):
        return 0.0
    va, vb = np.asarray(a, np.float32), np.asarray(b, np.float32)
    return max(0.0, float(cv2.compareHist(va, vb, cv2.HISTCMP_CORREL)))


def score_against_profile(ref, cand, last_bbox, cand_bbox, frame_shape):
    """등록 특징(ref) vs 후보(cand) → (총점, 세부점수)."""
    reid_sc = cosine(ref.get("reid_emb"), cand.get("reid_emb"))
    color_sc = (
        hist_corr(ref["color"]["top_hist"], cand["color"]["top_hist"]) +
        hist_corr(ref["color"]["bot_hist"], cand["color"]["bot_hist"])
    ) / 2.0

    if last_bbox is not None:
        cx, cy = (cand_bbox[0] + cand_bbox[2]) / 2, (cand_bbox[1] + cand_bbox[3]) / 2
        lx, ly = (last_bbox[0] + last_bbox[2]) / 2, (last_bbox[1] + last_bbox[3]) / 2
        diag = math.sqrt(frame_shape[0] ** 2 + frame_shape[1] ** 2)
        dist_r = math.sqrt((cx - lx) ** 2 + (cy - ly) ** 2) / max(diag, 1)
        pos_sc = max(0.0, 1.0 - dist_r * 4.0)
    else:
        pos_sc = 0.5

    total = W_REID * reid_sc + W_COLOR * color_sc + W_POSITION * pos_sc
    return total, {"reid": reid_sc, "color": color_sc, "position": pos_sc}


# ══════════════════════════════════════════════════════════════════════════════
# 추적 상태 (히스테리시스 + 유실 대응)
# ══════════════════════════════════════════════════════════════════════════════

class TrackingState:
    def __init__(self) -> None:
        self.is_tracking = False
        self.last_bbox: tuple | None = None
        self.lost_count = 0
        self._history: collections.deque = collections.deque(maxlen=SCORE_WINDOW)
        self._confirm = 0
        self.status = "searching"
        self._from_search = True   # 탐색 후 재인식 여부 (confirm 프레임 수 결정)
        self.had_track = False     # 이번 세션에서 한 번이라도 추적 성립 여부 — ReID 구제는 재획득에만 허용

    @property
    def avg_score(self) -> float:
        return float(np.mean(list(self._history))) if self._history else 0.0

    def reset(self) -> None:
        """추적 상태 즉시 초기화 (모드 전환 등에서 잔류 추적 제거)."""
        self.is_tracking = False
        self.last_bbox = None
        self.lost_count = 0
        self._confirm = 0
        self._history.clear()
        self.status = "searching"
        self._from_search = True
        self.had_track = False

    def update(self, matched: bool, bbox=None, score: float = 0.0) -> None:
        if matched and bbox is not None:
            self._history.append(score)
            self.last_bbox = bbox
            self.lost_count = 0
            if not self.is_tracking:
                req = SEARCH_CONFIRM_FRAMES if self._from_search else MIN_CONFIRM_FRAMES
                self._confirm += 1
                if self._confirm >= req:
                    self.is_tracking = True
                    self.had_track = True
                    self._from_search = False
                    self.status = "tracking"
                else:
                    self.status = f"confirm {self._confirm}/{req}"
            else:
                self.status = "tracking"
        else:
            self._confirm = 0
            if self.is_tracking:
                self.lost_count += 1
                if self.lost_count <= LOST_MAX:
                    self.status = f"lost {self.lost_count}/{LOST_MAX}"
                else:
                    self.is_tracking = False
                    self.last_bbox = None
                    self._history.clear()
                    self.status = "searching"
                    self._from_search = True
            else:
                self.status = "searching"


# ══════════════════════════════════════════════════════════════════════════════
# KCF 경량 보간 추적기 (검출 사이 프레임 bbox 보간)
# ══════════════════════════════════════════════════════════════════════════════

class BoxTracker:
    def __init__(self) -> None:
        self._t = None
        self.ok = False

    @staticmethod
    def _create():
        if hasattr(cv2, "TrackerKCF_create"):
            return cv2.TrackerKCF_create()
        return cv2.legacy.TrackerKCF_create()   # 일부 빌드 legacy 네임스페이스

    def init(self, frame, bbox) -> bool:
        x1, y1, x2, y2 = bbox
        w, h = int(x2 - x1), int(y2 - y1)
        if w <= 0 or h <= 0:
            self.ok = False
            return False
        try:
            self._t = self._create()
            self._t.init(frame, (int(x1), int(y1), w, h))
            self.ok = True
        except Exception:
            self._t, self.ok = None, False
        return self.ok

    def update(self, frame):
        if not self.ok or self._t is None:
            return None
        try:
            ok, box = self._t.update(frame)
        except Exception:
            ok = False
        if not ok:
            self.ok = False
            return None
        x, y, w, h = box
        return (int(x), int(y), int(x + w), int(y + h))

    def deinit(self) -> None:
        self._t, self.ok = None, False
