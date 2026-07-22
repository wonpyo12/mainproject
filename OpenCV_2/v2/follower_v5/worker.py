# -*- coding: utf-8 -*-
"""[비전 연산 워커 모듈] worker.py
- 주요 역할: YOLOv8 인물 검출, OSNet ReID 임베딩 및 HSV 색상 추출을 비동기 스레드로 실행하여 화면 멈춤 방지.
- 주요 구성:
  1. DetectionWorker (YOLO/ReID 비동기 처리 스레드)
  2. extract_features (이미지 크롭 영역 특징 추출 함수)
  3. score_multi_emb (등록 프로필과 후보군 간 다각도 가중 일치율 산출)
"""

from __future__ import annotations

import threading
import time
from typing import Any

import cv2

import light_features as LF
from light_models import OnnxReID


def extract_features(crop, reid: OnnxReID) -> dict[str, Any]:
    return {"reid_emb": reid.embed(crop), "color": LF.extract_color(crop)}


def score_multi_emb(pref, cand, last_bbox, cand_bbox, frame_shape):
    total, det = LF.score_against_profile(pref, cand, last_bbox, cand_bbox, frame_shape)
    embs = (pref.get("reid_embs") or []) + (pref.get("reid_embs_live") or [])
    if embs:
        best = max(LF.cosine(e, cand.get("reid_emb")) for e in embs)
        if best > det["reid"]:
            total += LF.W_REID * (best - det["reid"])
            det = dict(det, reid=best)
    return total, det


class DetectionWorker(threading.Thread):
    """비동기 검출 워커 (YOLO+ReID+색상 스레드)."""

    def __init__(self, yolo, reid, face, profile, use_face):
        super().__init__(daemon=True)
        self._yolo, self._reid, self._face = yolo, reid, face
        self._phases = profile.get("phases", {})
        self._use_face = use_face
        self._in_lock = threading.Lock()
        self._in_frame = None
        self._in_lbbox = None
        self._out_lock = threading.Lock()
        self._out = {
            "bboxes": [], "scores": {}, "best_bbox": None,
            "best_total": 0.0, "best_detail": None, "best_ori": "unknown",
            "best_emb": None, "det_ms": 0.0, "reid_ms": 0.0, "seq": 0
        }
        self._seq = 0
        self._stop_flag = False

    def update_profile(self, profile):
        self._phases = profile.get("phases", {})

    def submit(self, frame, last_bbox):
        with self._in_lock:
            self._in_frame = frame
            self._in_lbbox = last_bbox

    def result(self):
        with self._out_lock:
            return dict(self._out)

    def stop(self):
        self._stop_flag = True

    def run(self):
        tm_det, tm_reid = cv2.TickMeter(), cv2.TickMeter()
        while not self._stop_flag:
            frame = last_bbox = None
            with self._in_lock:
                if self._in_frame is not None:
                    frame, last_bbox = self._in_frame, self._in_lbbox
                    self._in_frame = None
            if frame is None:
                time.sleep(0.003)
                continue

            h_f, w_f = frame.shape[:2]
            tm_det.reset()
            tm_det.start()
            bboxes = self._yolo.detect(frame)
            tm_det.stop()

            best_bbox, best_total, best_detail, best_ori = None, -1.0, None, "unknown"
            best_emb = None
            scores = {}
            tm_reid.reset()
            tm_reid.start()
            for bb in bboxes:
                x1, y1, x2, y2 = bb
                crop = frame[max(0, y1):min(h_f, y2), max(0, x1):min(w_f, x2)]
                if crop.size == 0:
                    continue
                feat = extract_features(crop, self._reid)
                ori = self._face.orient(crop) if self._use_face else "unknown"
                ph_best, ph_det, ph_name = -1.0, None, "front"
                for pn, pref in self._phases.items():
                    if not pref or not pref.get("reid_emb"):
                        continue
                    sc, det_sc = score_multi_emb(
                        pref, feat, last_bbox, bb, frame.shape
                    )
                    if self._use_face and ori != "unknown" and ori == pn:
                        sc += 0.03
                    if sc > ph_best:
                        ph_best, ph_det, ph_name = sc, det_sc, pn
                scores[bb] = ph_best
                if ph_best > best_total:
                    best_total, best_bbox, best_detail, best_ori = ph_best, bb, ph_det, ph_name
                    best_emb = feat["reid_emb"]
            tm_reid.stop()

            self._seq += 1
            with self._out_lock:
                self._out = {
                    "bboxes": bboxes, "scores": scores,
                    "best_bbox": best_bbox, "best_total": best_total,
                    "best_detail": best_detail, "best_ori": best_ori,
                    "best_emb": best_emb,
                    "det_ms": tm_det.getTimeMilli(),
                    "reid_ms": tm_reid.getTimeMilli(), "seq": self._seq
                }
            time.sleep(0.03)
