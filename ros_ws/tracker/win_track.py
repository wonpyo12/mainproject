#!/usr/bin/env python3
"""
[Windows · WSL 불필요] 세션 추적 — 라파 카메라(TCP) → 인식 → 모터 명령(TCP)

WSL/ROS2 없이 Windows 파이썬으로 통째로 돈다.
  카메라 입력 : 라파 web_stream(MJPEG/HTTP) ← HttpCamera (TCP)
  인식        : smart_cart_core (YOLO/MediaPipe/ReID) — 순수 파이썬
  화면        : cv2.imshow (Windows 네이티브 창)
  모터 명령   : 라파 cmd_server(TCP 9998) → 라파 ROS2 → ESP32/바퀴
  세션        : 시작 시 자동 등록 → 종료 시 등록 데이터 삭제

라파 쪽 필요 노드: camera_node + web_stream(:8090) + cmd_server(:9998)
                  + esp32_motor_node (+ cmd_vel_relay/turtlebot3 — 바퀴 쓸 때)

실행 (Windows, smart_cart venv):
  d:\\YH\\OpenCV\\smart_cart\\.venv\\Scripts\\python.exe win_track.py --pi YOUR_PI_IP
  # 바퀴까지 구동하려면 (주의: 로봇이 움직임):
  ...win_track.py --pi YOUR_PI_IP --wheels
"""
import argparse
import os
import shutil
import socket
import threading
import time
import urllib.request

# 인식이 CPU 전체를 점유해 화면 루프가 멈추는 것(FPS:0) 방지 —
# 추론 스레드를 제한해 화면/카메라용 코어를 남긴다. (cv2/torch import 전에 설정)
os.environ.setdefault("OMP_NUM_THREADS", "3")

import cv2
import numpy as np

import smart_cart_core as core

cv2.setNumThreads(2)
try:
    import torch
    torch.set_num_threads(3)
except Exception:
    pass


# ── 라파 카메라 (TCP, MJPEG) ────────────────────────────────────────────────
class HttpCamera:
    def __init__(self, url):
        self._url = url
        self._frame = None
        self._event = threading.Event()
        self._stop = False
        threading.Thread(target=self._reader, daemon=True).start()

    def _reader(self):
        while not self._stop:
            try:
                stream = urllib.request.urlopen(self._url, timeout=5)
                buf = b""
                while not self._stop:
                    chunk = stream.read(16384)
                    if not chunk:
                        break
                    buf += chunk
                    # 딜레이 감소: 버퍼에 쌓인 것 중 '가장 최신' JPEG 만 사용 (오래된 프레임 버림)
                    last_b = buf.rfind(b"\xff\xd9")
                    if last_b != -1:
                        last_a = buf.rfind(b"\xff\xd8", 0, last_b)
                        if last_a != -1:
                            jpg = buf[last_a:last_b + 2]
                            buf = buf[last_b + 2:]          # 그 뒤만 남김(최신만)
                            fr = cv2.imdecode(np.frombuffer(jpg, np.uint8),
                                              cv2.IMREAD_COLOR)
                            if fr is not None:
                                self._frame = fr
                                self._event.set()
                    if len(buf) > 4_000_000:
                        buf = b""
            except Exception as e:
                print(f"[win] TCP 카메라 재연결... ({e})")
                time.sleep(0.5)

    def read(self):
        # 새 프레임을 짧게 대기. WiFi 가 잠깐 끊겨도 마지막 프레임으로 버텨
        # 세션이 죽지 않게 함 (한 번 연결되면 종료 안 됨).
        if self._event.wait(timeout=2.0):
            self._event.clear()
            return True, self._frame
        if self._frame is not None:
            time.sleep(0.03)              # 끊김 중 — 마지막 프레임 유지
            return True, self._frame
        return False, None               # 최초 연결 전이면 실패

    def release(self):
        self._stop = True


# ── 라파 모터 (TCP → cmd_server) ───────────────────────────────────────────
# smart_cart_core.run_tracking 이 쓰는 servo 인터페이스를 구현.
class TcpServo:
    SEND_INTERVAL = 0.1
    CENTER = 75          # 카메라 정면 보정각

    def __init__(self, host, port=9998, wheels=False,
                 k_turn=1.2, forward=0.12, max_ang=1.0):
        self.connected = True
        self.mode = "hold"
        self.current_angle = self.CENTER
        self._wheels = wheels
        self._k = k_turn; self._fwd = forward; self._maxang = max_ang
        self._last = 0.0
        self._sock = None
        self._lock = threading.Lock()
        self._connect(host, port)

    def _connect(self, host, port):
        try:
            self._sock = socket.create_connection((host, port), timeout=5)
            print(f"[win] 모터 명령 서버 연결: {host}:{port}")
        except OSError as e:
            print(f"[win] 모터 서버 연결 실패({e}) — 명령 없이 동작")
            self.connected = False

    def _send(self, line):
        if not self._sock:
            return
        try:
            with self._lock:
                self._sock.sendall((line + "\n").encode())
        except OSError:
            pass

    def _clamp(self, v, m):
        return max(-m, min(m, v))

    def move_to(self, angle):                 # 사람 추적: 카메라 + (옵션)바퀴
        now = time.time()
        if now - self._last < self.SEND_INTERVAL:
            return
        self._last = now
        a = int(max(0, min(180, round(angle))))
        self.current_angle = a
        self.mode = "track"
        self._send(f"S:A{a}")
        if self._wheels:
            err = (a - self.CENTER) / self.CENTER         # -1~1
            ang = self._clamp(-self._k * err, self._maxang)
            self._send(f"V:{self._fwd:.2f},{ang:.2f}")

    def start_sweep(self):                    # 사람 없음: 서보 스캔, 바퀴 정지
        if self.mode != "sweep":
            self.mode = "sweep"
            self._send("S:SCAN_START")
            if self._wheels:
                self._send("V:0,0")

    def hold(self):                           # 잠깐 유실: 정지
        if self.mode != "hold":
            self.mode = "hold"
            self._send("S:SCAN_STOP")
            if self._wheels:
                self._send("V:0,0")

    def center(self):
        self.mode = "track"
        self._send("S:CENTER")

    def close(self):
        if self._wheels:
            self._send("V:0,0")
        self._send("S:CENTER")
        if self._sock:
            try:
                self._sock.close()
            except OSError:
                pass


def cleanup_session():
    """세션 종료 — 일회용 등록 데이터 삭제."""
    try:
        if core.PROFILE_PATH.exists():
            core.PROFILE_PATH.unlink()
            print(f"[session] 프로필 삭제: {core.PROFILE_PATH}")
    except Exception as e:
        print(f"[session] 프로필 삭제 실패: {e}")
    try:
        if core.SAMPLES_DIR.exists():
            shutil.rmtree(core.SAMPLES_DIR, ignore_errors=True)
    except Exception:
        pass


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pi", default=os.environ.get("PI_HOST", "YOUR_PI_IP"), help="라파 IP")
    ap.add_argument("--cam-port", type=int, default=8090)
    ap.add_argument("--cmd-port", type=int, default=9998)
    ap.add_argument("--wheels", action="store_true", help="바퀴 구동 활성화(주의)")
    ap.add_argument("--user-id", default="owner_001")
    args = ap.parse_args()

    cam_url = f"http://{args.pi}:{args.cam_port}/stream"
    print(f"[win] 카메라: {cam_url}")
    cam = HttpCamera(cam_url)
    servo = TcpServo(args.pi, args.cmd_port, wheels=args.wheels)

    core.open_camera = lambda index=0: cam

    print("[win] 모델 로드 (YOLO/MediaPipe/ReID)...")
    yolo = core.create_yolo()
    hog = None
    if yolo is None:
        hog = cv2.HOGDescriptor()
        hog.setSVMDetector(cv2.HOGDescriptor_getDefaultPeopleDetector())
    pose = core.create_pose_estimator()
    reid = core.create_reid_model()

    # 세션 시작: 초기화 → 자동 등록
    cleanup_session()
    for _ in range(3):
        servo.center(); time.sleep(0.15)
    print("[session] 자동 등록 — 화면 보며 정면→뒤돌기")
    if not core.register_user(yolo, hog, pose, reid, user_id=args.user_id):
        print("[session] 등록 실패 — 종료")
        cleanup_session(); servo.close(); return 1
    profile = core.load_profile()
    print(f"[session] 등록 완료 [{profile['user_id']}] → 추적 시작")

    try:
        core.run_tracking(yolo, hog, pose, reid, profile, servo=servo)
    finally:
        servo.close()
        cam.release()
        cleanup_session()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
