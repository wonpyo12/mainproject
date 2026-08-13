"""등록 프로필 저장/로드 + 특징 추출·집계 유틸."""
import json

import numpy as np

import light_features as LF
from light_models import OnnxReID

from .config import (PROFILE_PATH)


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


def _pick_diverse(embs, k=8):
    """수집 시간축에서 고르게 k개 대표 샘플 선택 (자세 다양성 확보).
    매칭 시 max 비교용 — 평균 1개보다 자세 변화에 훨씬 강함."""
    embs = [e for e in embs if e]
    if len(embs) <= k:
        return embs
    idx = np.linspace(0, len(embs) - 1, k).round().astype(int)
    return [embs[i] for i in idx]


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


