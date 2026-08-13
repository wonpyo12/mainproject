"""인식 — MOSSE 보간 트래커, 다중 임베딩 스코어링, 비동기 검출 워커."""
import threading
import time

import cv2

import light_features as LF

from .profile import extract_features


# ══════════════════════════════════════════════════════════════════════════════
# 보간 트래커 — MOSSE (실측: KCF 168~547ms/frame → MOSSE 17~66ms, 8배 빠름)
# 추적 중 루프 fps 붕괴(2~9fps)의 원인이 KCF 비용이라 보간 용도로는 MOSSE로 교체.
# ══════════════════════════════════════════════════════════════════════════════

class MosseBoxTracker(LF.BoxTracker):
    SCALE = 0.5   # 0.5x 축소 프레임에서 추적 (실측 66→26ms, 보간 정밀도 충분)

    @staticmethod
    def _create():
        if hasattr(cv2, "legacy") and hasattr(cv2.legacy, "TrackerMOSSE_create"):
            return cv2.legacy.TrackerMOSSE_create()
        return LF.BoxTracker._create()   # MOSSE 없으면 KCF 폴백

    def init(self, frame, bbox):
        small = cv2.resize(frame, None, fx=self.SCALE, fy=self.SCALE)
        return super().init(small, tuple(int(v * self.SCALE) for v in bbox))

    def update(self, frame):
        small = cv2.resize(frame, None, fx=self.SCALE, fy=self.SCALE)
        kb = super().update(small)
        if kb is None:
            return None
        return tuple(int(v / self.SCALE) for v in kb)


def score_multi_emb(pref, cand, last_bbox, cand_bbox, frame_shape):
    """LF.score_against_profile + ReID 다중 임베딩 매칭.

    평균 임베딩 1개 대신 등록 때 저장한 원본 임베딩들(reid_embs, 최대 8개)과
    개별 비교해 최고값을 사용 — 자세/각도 변화 시 본인 점수 하락을 줄인다.
    (타인은 어떤 임베딩과도 낮게 나와 오인식 위험 증가는 미미. 임계값 유지 목적)
    """
    total, det = LF.score_against_profile(pref, cand, last_bbox, cand_bbox, frame_shape)
    # 등록 원본(불변) + 주행 중 수확분(reid_embs_live) 합쳐 max 비교 — 최대 12+8=20회 코사인
    embs = (pref.get("reid_embs") or []) + (pref.get("reid_embs_live") or [])
    if embs:
        best = max(LF.cosine(e, cand.get("reid_emb")) for e in embs)
        if best > det["reid"]:
            total += LF.W_REID * (best - det["reid"])
            det = dict(det, reid=best)
    return total, det


# ══════════════════════════════════════════════════════════════════════════════
# 비동기 검출 워커 (YOLO+ReID+색상)
# ══════════════════════════════════════════════════════════════════════════════

class DetectionWorker(threading.Thread):
    def __init__(self, yolo, reid, face, profile, use_face):
        super().__init__(daemon=True)
        self._yolo, self._reid, self._face = yolo, reid, face
        self._phases = profile.get("phases", {})
        self._use_face = use_face
        self._in_lock = threading.Lock()
        self._in_frame = None
        self._in_lbbox = None
        self._out_lock = threading.Lock()
        self._out = {"bboxes": [], "scores": {}, "best_bbox": None,
                     "best_total": 0.0, "best_detail": None, "best_ori": "unknown",
                     "best_emb": None, "det_ms": 0.0, "reid_ms": 0.0, "seq": 0}
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
                time.sleep(0.003); continue

            h_f, w_f = frame.shape[:2]
            tm_det.reset(); tm_det.start()
            bboxes = self._yolo.detect(frame)
            tm_det.stop()

            best_bbox, best_total, best_detail, best_ori = None, -1.0, None, "unknown"
            best_emb = None
            scores = {}
            tm_reid.reset(); tm_reid.start()
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
                        pref, feat, last_bbox, bb, frame.shape)
                    if self._use_face and ori != "unknown" and ori == pn:
                        sc += 0.03
                    if sc > ph_best:
                        ph_best, ph_det, ph_name = sc, det_sc, pn
                scores[bb] = ph_best
                if ph_best > best_total:
                    best_total, best_bbox, best_detail, best_ori = ph_best, bb, ph_det, ph_name
                    best_emb = feat["reid_emb"]   # 온라인 수확용 — 이미 계산된 값 재사용
            tm_reid.stop()

            self._seq += 1
            with self._out_lock:
                self._out = {"bboxes": bboxes, "scores": scores,
                             "best_bbox": best_bbox, "best_total": best_total,
                             "best_detail": best_detail, "best_ori": best_ori,
                             "best_emb": best_emb,
                             "det_ms": tm_det.getTimeMilli(),
                             "reid_ms": tm_reid.getTimeMilli(), "seq": self._seq}
            # 검출 사이클 사이 CPU 양보 — 코어 적은 VM에서 표시/주행 스레드 멈춤 방지
            time.sleep(0.03)


