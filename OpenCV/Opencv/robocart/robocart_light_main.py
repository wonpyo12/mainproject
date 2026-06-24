#!/usr/bin/env python3
"""robocart_light — RPi4 단독 경량 인식 (YOLOv8n-ONNX + OSNet-ONNX + 색상).

실행(라파):
    python3 robocart_light_main.py --register      # 정면/뒷면 등록 후 추종
    python3 robocart_light_main.py                 # 기존 프로필로 추종
출력: http://<pi-ip>:8080  (MJPEG 라이브)

torch/ultralytics/mediapipe 불필요. onnxruntime + apt cv2/numpy 만 사용.
모델 파일은 VM 의 export_models.py 로 만들어 models_light/ 에 둔다.
"""
from __future__ import annotations

import argparse
import json
import threading
import time
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np

import light_features as LF
from light_models import OnnxYolo, OnnxReID, FaceOrient

try:
    from wheel_control import WheelFollower   # 기존 파일 재사용 (robocart_main 비의존, 그대로 가져다 씀)
    _WHEEL_AVAILABLE = True
except ImportError:
    _WHEEL_AVAILABLE = False

HERE = Path(__file__).resolve().parent
MODELS_DIR   = HERE / "models_light"
PROFILE_PATH = HERE / "robocart_light_profile.json"

REID_ONNX = MODELS_DIR / "osnet_x0_25.onnx"
YUNET_ONNX = MODELS_DIR / "face_detection_yunet.onnx"

# imgsz 별 YOLO onnx (모델 입력은 고정 크기라 imgsz 와 파일이 일치해야 함)
YOLO_ONNX_BY_SZ = {320: MODELS_DIR / "yolov8n.onnx",
                   256: MODELS_DIR / "yolov8n_256.onnx",
                   192: MODELS_DIR / "yolov8n_192.onnx"}


def pick_yolo_onnx(imgsz: int):
    p = YOLO_ONNX_BY_SZ.get(imgsz)
    if p and p.exists():
        return p, imgsz
    # 폴백: 320 기본 모델
    return MODELS_DIR / "yolov8n.onnx", 320

DETECT_INTERVAL = 5     # 검출 사이 KCF 보간 프레임 수
KCF_MAX_AGE     = 40     # KCF 단독 보간 허용 최대 (초과 시 강제 재검출)


# ══════════════════════════════════════════════════════════════════════════════
# MJPEG 웹 출력 (:8080)
# ══════════════════════════════════════════════════════════════════════════════

_web_cond = threading.Condition()
_web_jpeg: bytes | None = None
_web_seq: int = 0
_web_last_t: float = 0.0


def web_push(frame: np.ndarray) -> None:
    global _web_jpeg, _web_seq, _web_last_t
    now = time.time()
    if now - _web_last_t < 1.0 / 15:   # 인코딩을 15fps로 제한(메인 루프 CPU 절약)
        return
    _web_last_t = now
    small = cv2.resize(frame, (320, 240))     # 640×480→320×240: JPEG 크기 1/4로 절감
    ok, jpeg = cv2.imencode(".jpg", small, [cv2.IMWRITE_JPEG_QUALITY, 65])
    if ok:
        with _web_cond:
            _web_jpeg = jpeg.tobytes()
            _web_seq += 1
            _web_cond.notify_all()


def start_web_server(port: int = 8080, host: str = "0.0.0.0"):
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    page = (b"""<!doctype html><html><head><meta charset="utf-8"><title>robocart_light</title>
<style>body{background:#111;color:#eee;font-family:sans-serif;text-align:center}
img{max-width:97vw;border:1px solid #444;margin-top:10px}</style></head>
<body><h3>robocart_light - RPi4</h3><img src="/stream"></body></html>""")

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_GET(self):
            if self.path in ("/", "/index.html"):
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(page)
                return
            if self.path == "/stream":
                self.send_response(200)
                self.send_header("Content-Type",
                                 "multipart/x-mixed-replace; boundary=frame")
                self.end_headers()
                try:
                    last_seq = -1
                    last_send_t = 0.0
                    while True:
                        with _web_cond:
                            _web_cond.wait_for(
                                lambda: _web_seq != last_seq, timeout=1.0)
                            jpeg = _web_jpeg
                            cur_seq = _web_seq
                        if jpeg is None or cur_seq == last_seq:
                            continue
                        last_seq = cur_seq          # seq 항상 소비 → 이전 프레임 재전송 없음
                        now = time.time()
                        if now - last_send_t < 1.0 / 15:
                            continue               # 15fps 초과 시 전송 생략(최신 프레임 유지)
                        last_send_t = now
                        self.wfile.write(b"--frame\r\n")
                        self.wfile.write(b"Content-Type: image/jpeg\r\n")
                        self.wfile.write(f"Content-Length: {len(jpeg)}\r\n\r\n".encode())
                        self.wfile.write(jpeg)
                        self.wfile.write(b"\r\n")
                        self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError):
                    pass
                return
            self.send_error(404)

    srv = ThreadingHTTPServer((host, port), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    print(f"[web] http://0.0.0.0:{port}  (/stream MJPEG)")
    return srv


# ══════════════════════════════════════════════════════════════════════════════
# 카메라 (latest-only 캡처 스레드)
# ══════════════════════════════════════════════════════════════════════════════

class Camera:
    def __init__(self, index: int = 0, width: int = 640, height: int = 480):
        self.cap = cv2.VideoCapture(index)
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
        try:
            self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        except Exception:
            pass
        self._frame = None
        self._lock = threading.Lock()
        self._stop = False
        self._th = threading.Thread(target=self._loop, daemon=True)
        self._th.start()

    def _loop(self):
        while not self._stop:
            ok, f = self.cap.read()
            if ok and f is not None:
                with self._lock:
                    self._frame = f
            else:
                time.sleep(0.01)

    def read(self):
        with self._lock:
            return None if self._frame is None else self._frame.copy()

    def opened(self):
        return self.cap.isOpened()

    def stop(self):
        self._stop = True
        try:
            self.cap.release()
        except Exception:
            pass


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


def _avg_color(colors):
    if not colors:
        return {}
    keys = ["top_hist", "bot_hist", "top_bgr", "bot_bgr"]
    out = {}
    for k in keys:
        out[k] = np.mean(np.asarray([c[k] for c in colors], np.float32), axis=0).tolist()
    return out


def largest_bbox(bboxes):
    if not bboxes:
        return None
    return max(bboxes, key=lambda b: (b[2] - b[0]) * (b[3] - b[1]))


def save_profile(profile):
    PROFILE_PATH.write_text(json.dumps(profile, ensure_ascii=False, indent=2))
    print(f"[profile] 저장: {PROFILE_PATH}")


def load_profile():
    if PROFILE_PATH.exists():
        return json.loads(PROFILE_PATH.read_text())
    return None


# ══════════════════════════════════════════════════════════════════════════════
# 등록 (시간 기반, 8080 화면 지시 따라가기)
# ══════════════════════════════════════════════════════════════════════════════

def register(cam, yolo, reid, user_id, grace_sec: float = 15.0):
    phases = [("front", "FRONT: face the camera"),
              ("back",  "BACK: turn around")]
    profile = {"user_id": user_id,
               "registered_at": datetime.now().isoformat(timespec="seconds"),
               "phases": {}}

    # ── 준비 대기: 브라우저(:8080) 접속 + 위치 잡을 시간 ──
    t_end = time.time() + grace_sec
    while time.time() < t_end:
        frame = cam.read()
        if frame is None:
            time.sleep(0.02); continue
        left = int(t_end - time.time()) + 1
        cv2.putText(frame, "OPEN :8080 and STAND in view", (20, 50),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2)
        cv2.putText(frame, f"registration starts in {left}s", (20, 90),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 200, 0), 2)
        # 미리보기는 YOLO 없이 카메라 원본만 → 부드러운 스트림(검출은 느려서 제외)
        web_push(frame)

    for pname, instruct in phases:
        # 3초 카운트다운
        for sec in (3, 2, 1):
            t_end = time.time() + 1.0
            while time.time() < t_end:
                frame = cam.read()
                if frame is None:
                    time.sleep(0.02); continue
                cv2.putText(frame, instruct, (20, 50),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 255, 255), 2)
                cv2.putText(frame, f"start in {sec}", (20, 95),
                            cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 200, 0), 3)
                web_push(frame)
        # ~4초 동안 샘플 수집. YOLO(880ms)를 백그라운드 스레드에서 돌려 메인은
        # 카메라 속도로 영상만 갱신 → 캡처 중에도 화면이 멈추지 않는다.
        embs, cols = [], []
        shared = {"bbox": None, "n": 0}
        stop_flag = {"v": False}
        lock = threading.Lock()

        def _capture_worker():
            while not stop_flag["v"]:
                f = cam.read()
                if f is None:
                    time.sleep(0.01); continue
                bb = largest_bbox(yolo.detect(f))
                if bb is None:
                    with lock:
                        shared["bbox"] = None
                    continue
                x1, y1, x2, y2 = bb
                crop = f[max(0, y1):y2, max(0, x1):x2]
                if crop.size > 0:
                    feat = extract_features(crop, reid)
                    if feat["reid_emb"]:
                        with lock:
                            embs.append(feat["reid_emb"]); cols.append(feat["color"])
                            shared["bbox"] = bb; shared["n"] = len(embs)

        th = threading.Thread(target=_capture_worker, daemon=True)
        th.start()
        t_end = time.time() + 4.0
        while time.time() < t_end:
            frame = cam.read()
            if frame is None:
                time.sleep(0.02); continue
            with lock:
                bb, n = shared["bbox"], shared["n"]
            if bb is not None:
                cv2.rectangle(frame, (bb[0], bb[1]), (bb[2], bb[3]), (0, 255, 0), 2)
            cv2.putText(frame, f"{pname} capturing... {n}", (20, 50),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 255, 255), 2)
            web_push(frame)
            time.sleep(0.01)
        stop_flag["v"] = True
        th.join(timeout=1.5)
        profile["phases"][pname] = {"reid_emb": _avg_embed(embs),
                                    "color": _avg_color(cols)}
        print(f"[register] {pname}: {len(embs)} 샘플 수집")

    save_profile(profile)
    return profile


# ══════════════════════════════════════════════════════════════════════════════
# 추종 루프
# ══════════════════════════════════════════════════════════════════════════════

class DetectionWorker(threading.Thread):
    """무거운 검출(YOLO+ReID+색상)을 백그라운드에서 처리.

    메인 루프는 카메라 FPS 로 계속 돌며 KCF 로 박스를 보간하고,
    이 워커가 완료될 때마다 결과(seq 증가)를 비동기로 반영한다.
    submit() 은 항상 최신 프레임만 남겨 밀린 프레임을 버린다 → 지연 누적 방지.
    """

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
                     "det_ms": 0.0, "reid_ms": 0.0, "seq": 0}
        self._seq = 0
        self._stop = False

    def submit(self, frame, last_bbox):
        with self._in_lock:
            self._in_frame = frame          # 캡처 스레드가 매번 copy 본을 주므로 안전
            self._in_lbbox = last_bbox

    def result(self):
        with self._out_lock:
            return dict(self._out)

    def stop(self):
        self._stop = True

    def run(self):
        tm_det, tm_reid = cv2.TickMeter(), cv2.TickMeter()
        while not self._stop:
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
                    sc, det_sc = LF.score_against_profile(
                        pref, feat, last_bbox, bb, frame.shape)
                    if self._use_face and ori != "unknown" and ori == pn:
                        sc += 0.03
                    if sc > ph_best:
                        ph_best, ph_det, ph_name = sc, det_sc, pn
                scores[bb] = ph_best
                if ph_best > best_total:
                    best_total, best_bbox, best_detail, best_ori = ph_best, bb, ph_det, ph_name
            tm_reid.stop()

            self._seq += 1
            with self._out_lock:
                self._out = {"bboxes": bboxes, "scores": scores,
                             "best_bbox": best_bbox, "best_total": best_total,
                             "best_detail": best_detail, "best_ori": best_ori,
                             "det_ms": tm_det.getTimeMilli(),
                             "reid_ms": tm_reid.getTimeMilli(), "seq": self._seq}


def run_tracking(cam, yolo, reid, face, profile, use_face=True, follower=None):
    tracker = LF.TrackingState()
    kcf = LF.BoxTracker()
    kcf_age = 0
    frame_count = 0
    t0 = time.time()
    fps_t, fps_n, fps_val = t0, 0, 0.0   # 최근 구간 FPS(누적 평균이 아니라 실시간 체감값)

    avg = {"det": 0.0, "reid": 0.0}
    last_seq = 0
    cur_label = "-"
    last_bboxes, last_scores = [], {}
    reg_det_bbox = None

    worker = DetectionWorker(yolo, reid, face, profile, use_face)
    worker.start()

    print("=== 추종 시작 (비동기 검출) ===  (Ctrl+C 종료)")
    while True:
        frame = cam.read()
        if frame is None:
            time.sleep(0.02); continue
        frame_count += 1
        h_f, w_f = frame.shape[:2]

        # ── 검출 제출 (항상 최신 프레임만; 워커가 바쁘면 자연히 스킵됨) ──
        interp_alive = tracker.is_tracking and kcf.ok
        if (not interp_alive) or kcf_age >= KCF_MAX_AGE or frame_count % DETECT_INTERVAL == 0:
            worker.submit(frame.copy(), tracker.last_bbox)

        det = worker.result()
        fresh = det["seq"] != last_seq
        last_seq = det["seq"]

        draw_bbox = None
        interp = False

        if fresh:
            # ── 새 검출 결과 도착 → 신원 확인 + KCF 재고정 ──
            last_bboxes, last_scores = det["bboxes"], det["scores"]
            avg["det"] = 0.8 * avg["det"] + 0.2 * det["det_ms"]
            avg["reid"] = 0.8 * avg["reid"] + 0.2 * det["reid_ms"]
            bb, total, detail, ori = (det["best_bbox"], det["best_total"],
                                      det["best_detail"], det["best_ori"])
            reid_ok = detail is not None and detail.get("reid", 0) >= LF.REID_FLOOR
            color_ok = detail is not None and detail.get("color", 0) >= LF.COLOR_FLOOR
            thr = LF.KEEP_THRESHOLD if tracker.is_tracking else LF.MATCH_THRESHOLD
            matched = (bb is not None and total >= thr and reid_ok and color_ok)
            if matched:
                tracker.update(True, bb, total)
                cur_label = f"{profile['user_id']} [{ori}] {total:.2f}"
                kcf.init(frame, bb); kcf_age = 0
                draw_bbox = bb; reg_det_bbox = bb
            else:
                tracker.update(False)
                kcf.deinit(); reg_det_bbox = None
            # ── 보정용 진단 로그: 최고 후보의 reid/color/total 실측 (임계값 튜닝 근거) ──
            if detail is not None:
                print(f"[score] reid={detail['reid']:.2f} color={detail['color']:.2f} "
                      f"pos={detail['position']:.2f} total={total:.2f} "
                      f"thr={thr:.2f} reidF={LF.REID_FLOOR:.2f} "
                      f"=> {'MATCH' if matched else 'reject'} (cand={len(last_bboxes)})")
        elif interp_alive:
            # ── 검출 사이 프레임 → KCF 보간 (수 ms) ──
            kb = kcf.update(frame); kcf_age += 1
            if kb is not None:
                tracker.last_bbox = kb
                draw_bbox = kb; interp = True

        # 비등록자(회색) — 마지막 검출 기준
        for bb in last_bboxes:
            if bb == reg_det_bbox:
                continue
            x1, y1, x2, y2 = bb
            cv2.rectangle(frame, (x1, y1), (x2, y2), (95, 95, 95), 1)
            cv2.putText(frame, f"{last_scores.get(bb, 0):.2f}", (x1, max(15, y1 - 4)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.4, (95, 95, 95), 1)

        # 등록자 박스
        if draw_bbox is not None:
            x1, y1, x2, y2 = draw_bbox
            cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 3)
            mark = "~" if interp else ""
            cv2.putText(frame, cur_label + mark, (x1, max(18, y1 - 8)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 255, 0), 2)
        elif tracker.status.startswith("lost") and tracker.last_bbox:
            x1, y1, x2, y2 = tracker.last_bbox
            cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 140, 255), 2)
            cv2.putText(frame, tracker.status, (x1, max(18, y1 - 8)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 140, 255), 2)

        fps_n += 1
        _now = time.time()
        if _now - fps_t >= 0.5:          # 0.5초 구간마다 실시간 FPS 갱신
            fps_val = fps_n / (_now - fps_t)
            fps_t, fps_n = _now, 0
        mode = "DET" if fresh else ("KCF" if interp else "-")
        hud = (f"FPS:{fps_val:.1f} {mode} det:{avg['det']:.0f} reid:{avg['reid']:.0f}ms "
               f"Cand:{len(last_bboxes)} {tracker.status.upper()}")
        cv2.rectangle(frame, (0, 0), (w_f, 22), (0, 0, 0), -1)
        cv2.putText(frame, hud, (6, 16), cv2.FONT_HERSHEY_SIMPLEX, 0.45,
                    (0, 255, 0) if tracker.is_tracking else (160, 160, 255), 1)

        # ── 바퀴 추종(--follow): 인식 bbox → /cmd_vel 발행 (wheel_control.py 재사용) ──
        # 추종 중이면 현재 박스로 속도 계산, 아니면 정지(안전). KCF 보간 프레임도 draw_bbox
        # 가 있으면 그 위치로 계속 추종(끊김 없는 제어).
        if follower is not None:
            v, w = follower.compute(draw_bbox, w_f, h_f, tracker.is_tracking)
            if frame_count % 3 == 0:   # ≈10Hz — 매 프레임 rclpy publish 호출 시 오버헤드로 FPS 저하 방지
                follower.publish(v, w)
            cv2.putText(frame, f"WHEEL v={v:+.2f} w={w:+.2f} dist={follower.last_dist_cm:.0f}cm",
                        (6, h_f - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 1)

        web_push(frame)
        if frame_count % 30 == 0:
            print(f"[perf] {hud}")


# ══════════════════════════════════════════════════════════════════════════════
# main
# ══════════════════════════════════════════════════════════════════════════════

def parse_args():
    p = argparse.ArgumentParser(description="robocart_light — RPi4 단독 경량 인식")
    p.add_argument("--camera", type=int, default=0)
    p.add_argument("--width", type=int, default=640)
    p.add_argument("--height", type=int, default=480)
    p.add_argument("--imgsz", type=int, default=192,
                   help="YOLO 입력 크기. 192=빠름(스로틀 환경 권장), 256=정확. "
                        "models_light/yolov8n_<크기>.onnx 필요")
    p.add_argument("--threads", type=int, default=4)
    p.add_argument("--register", action="store_true", help="등록 후 추종")
    p.add_argument("--reset", action="store_true", help="기존 프로필 삭제 후 등록")
    p.add_argument("--user-id", default="owner_001")
    p.add_argument("--web-port", type=int, default=8080)
    p.add_argument("--no-face", action="store_true", help="얼굴 방향 보조 비활성화")
    p.add_argument("--grace", type=float, default=15.0,
                   help="등록 시작 전 준비 대기 초 (브라우저 접속·위치)")
    p.add_argument("--follow", action="store_true",
                   help="바퀴 추종: 인식 결과(bbox)로 /cmd_vel(Twist) 발행 "
                        "(TurtleBot3 Burger). wheel_control.py 재사용 — ROS2 환경 필요")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    print("[init] 모델 로딩...")
    yolo_path, yolo_sz = pick_yolo_onnx(args.imgsz)
    print(f"[init] YOLO={yolo_path.name} imgsz={yolo_sz}")
    yolo = OnnxYolo(str(yolo_path), imgsz=yolo_sz, threads=args.threads)
    reid = OnnxReID(str(REID_ONNX), threads=args.threads)
    face = FaceOrient(str(YUNET_ONNX) if not args.no_face else None)
    print(f"[init] YOLO/ReID OK, face={face.mode}")

    cam = Camera(args.camera, args.width, args.height)
    time.sleep(1.0)
    if not cam.opened() or cam.read() is None:
        print(f"[오류] 카메라 {args.camera} 열기 실패")
        return 1

    start_web_server(args.web_port)

    if args.reset and PROFILE_PATH.exists():
        PROFILE_PATH.unlink()
    profile = load_profile()
    if args.register or args.reset or profile is None:
        if profile is None and not (args.register or args.reset):
            print("[안내] 프로필 없음 → 등록 진행")
        profile = register(cam, yolo, reid, args.user_id, grace_sec=args.grace)

    follower = None
    if args.follow:
        if not _WHEEL_AVAILABLE:
            print("[오류] --follow 사용 불가 — rclpy 없음 "
                  "(source /opt/ros/humble/setup.bash 후 실행하세요)")
            cam.stop()
            return 1
        follower = WheelFollower()

    try:
        run_tracking(cam, yolo, reid, face, profile,
                     use_face=not args.no_face, follower=follower)
    except KeyboardInterrupt:
        print("\n[종료]")
    finally:
        if follower is not None:
            follower.destroy()   # 정지 명령 발행 + 노드 정리
        cam.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
