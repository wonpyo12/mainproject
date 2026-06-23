"""robocart_light — ONNX 추론 래퍼 (onnxruntime + cv2).

RPi4 런타임에서 torch 없이 동작.
- OnnxYolo   : YOLOv8n-ONNX 사람 검출
- OnnxReID   : OSNet-x0.25-ONNX 512-dim 임베딩
- FaceOrient : YuNet(or Haar) 얼굴 검출로 앞/뒤 보조 판별 (없으면 graceful degrade)
"""
from __future__ import annotations

import os

import cv2
import numpy as np

try:
    import onnxruntime as ort
    ORT_OK = True
except Exception:
    ORT_OK = False


def _session(path: str, threads: int = 4):
    so = ort.SessionOptions()
    so.intra_op_num_threads = threads
    so.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
    return ort.InferenceSession(path, sess_options=so, providers=["CPUExecutionProvider"])


# ══════════════════════════════════════════════════════════════════════════════
# YOLOv8n — 사람 검출
# ══════════════════════════════════════════════════════════════════════════════

class OnnxYolo:
    def __init__(self, onnx_path: str, imgsz: int = 320,
                 conf_thr: float = 0.40, iou_thr: float = 0.45, threads: int = 4):
        if not ORT_OK:
            raise RuntimeError("onnxruntime 미설치")
        if not os.path.exists(onnx_path):
            raise FileNotFoundError(onnx_path)
        self.sess = _session(onnx_path, threads)
        self.inp = self.sess.get_inputs()[0].name
        self.imgsz = imgsz
        self.conf_thr = conf_thr
        self.iou_thr = iou_thr

    def _letterbox(self, img):
        h, w = img.shape[:2]
        r = min(self.imgsz / h, self.imgsz / w)
        nh, nw = int(round(h * r)), int(round(w * r))
        resized = cv2.resize(img, (nw, nh))
        canvas = np.full((self.imgsz, self.imgsz, 3), 114, np.uint8)
        dh, dw = (self.imgsz - nh) // 2, (self.imgsz - nw) // 2
        canvas[dh:dh + nh, dw:dw + nw] = resized
        return canvas, r, dw, dh

    def detect(self, frame):
        """사람 bbox 목록 (x1,y1,x2,y2) 반환."""
        h_f, w_f = frame.shape[:2]
        lb, r, dw, dh = self._letterbox(frame)
        blob = cv2.cvtColor(lb, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
        blob = np.transpose(blob, (2, 0, 1))[None]   # (1,3,H,W)
        out = self.sess.run(None, {self.inp: blob})[0]   # (1,84,8400)
        out = np.squeeze(out, 0).T                        # (8400,84)

        boxes_xywh = out[:, :4]
        cls_scores = out[:, 4:]
        cls = np.argmax(cls_scores, axis=1)
        conf = cls_scores[np.arange(cls_scores.shape[0]), cls]
        mask = (cls == 0) & (conf > self.conf_thr)       # class 0 = person
        if not np.any(mask):
            return []
        bx = boxes_xywh[mask]
        cf = conf[mask]

        # cx,cy,w,h (letterbox space) → x1y1x2y2 (원본 space)
        x1 = (bx[:, 0] - bx[:, 2] / 2 - dw) / r
        y1 = (bx[:, 1] - bx[:, 3] / 2 - dh) / r
        x2 = (bx[:, 0] + bx[:, 2] / 2 - dw) / r
        y2 = (bx[:, 1] + bx[:, 3] / 2 - dh) / r
        rects = np.stack([x1, y1, x2 - x1, y2 - y1], axis=1)  # NMS는 x,y,w,h

        idxs = cv2.dnn.NMSBoxes(rects.tolist(), cf.tolist(),
                                self.conf_thr, self.iou_thr)
        if len(idxs) == 0:
            return []
        idxs = np.array(idxs).flatten()

        out_boxes = []
        for i in idxs:
            ix1 = max(0, int(x1[i])); iy1 = max(0, int(y1[i]))
            ix2 = min(w_f, int(x2[i])); iy2 = min(h_f, int(y2[i]))
            if (ix2 - ix1) < 40 or (iy2 - iy1) < 80:   # 너무 작은 박스 제외
                continue
            out_boxes.append((ix1, iy1, ix2, iy2))
        return out_boxes


# ══════════════════════════════════════════════════════════════════════════════
# OSNet-x0.25 — ReID 임베딩
# ══════════════════════════════════════════════════════════════════════════════

_MEAN = np.array([0.485, 0.456, 0.406], np.float32).reshape(3, 1, 1)
_STD  = np.array([0.229, 0.224, 0.225], np.float32).reshape(3, 1, 1)


class OnnxReID:
    def __init__(self, onnx_path: str, threads: int = 4):
        if not ORT_OK:
            raise RuntimeError("onnxruntime 미설치")
        if not os.path.exists(onnx_path):
            raise FileNotFoundError(onnx_path)
        self.sess = _session(onnx_path, threads)
        self.inp = self.sess.get_inputs()[0].name

    def embed(self, crop) -> list[float]:
        """사람 crop → 정규화된 임베딩 벡터 (list[float])."""
        if crop is None or crop.size == 0:
            return []
        img = cv2.resize(crop, (128, 256))               # (W,H)=(128,256)
        img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
        img = np.transpose(img, (2, 0, 1))               # (3,256,128)
        img = (img - _MEAN) / _STD
        emb = self.sess.run(None, {self.inp: img[None]})[0].squeeze()
        n = float(np.linalg.norm(emb))
        return (emb / n).tolist() if n > 0 else emb.tolist()


# ══════════════════════════════════════════════════════════════════════════════
# 얼굴 검출 → 앞/뒤 보조 판별 (선택적, 없으면 'unknown')
# ══════════════════════════════════════════════════════════════════════════════

class FaceOrient:
    def __init__(self, yunet_path: str | None = None):
        self.mode = "none"
        self.det = None
        # 1순위: YuNet — create 가 되더라도 구버전 OpenCV(예: 4.5.4)에서는 최신 YuNet
        # onnx 의 Eltwise 형상 불일치로 detect() 가 터진다. 더미 프레임으로 실제
        # detect 까지 검증해 통과할 때만 채택하고, 실패하면 Haar 로 폴백한다.
        if yunet_path and os.path.exists(yunet_path) and hasattr(cv2, "FaceDetectorYN"):
            try:
                det = cv2.FaceDetectorYN.create(yunet_path, "", (160, 160))
                dummy = np.zeros((160, 160, 3), np.uint8)
                det.setInputSize((160, 160))
                det.detect(dummy)          # 여기서 터지면 폴백
                self.det = det
                self.mode = "yunet"
                return
            except Exception:
                self.det = None
        # 2순위: Haar cascade (cv2 기본 동봉)
        try:
            cascade = os.path.join(cv2.data.haarcascades,
                                   "haarcascade_frontalface_default.xml")
            if os.path.exists(cascade):
                self.det = cv2.CascadeClassifier(cascade)
                self.mode = "haar"
        except Exception:
            self.det = None

    def orient(self, crop) -> str:
        """앞(front)/뒤(back)/unknown. crop 상단부에 얼굴 있으면 front."""
        if self.det is None or crop is None or crop.size == 0:
            return "unknown"
        h = crop.shape[0]
        upper = crop[:int(h * 0.45), :]            # 상단 45%만 검사
        if upper.size == 0:
            return "unknown"
        try:
            if self.mode == "yunet":
                hh, ww = upper.shape[:2]
                self.det.setInputSize((ww, hh))
                _, faces = self.det.detect(upper)
                return "front" if faces is not None and len(faces) > 0 else "back"
            else:  # haar
                gray = cv2.cvtColor(upper, cv2.COLOR_BGR2GRAY)
                faces = self.det.detectMultiScale(gray, 1.2, 4, minSize=(24, 24))
                return "front" if len(faces) > 0 else "back"
        except Exception:
            return "unknown"
