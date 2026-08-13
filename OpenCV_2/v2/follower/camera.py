"""라즈베리파이 MJPEG(:5000) 수신 카메라."""
import threading
import time
import urllib.request

import cv2
import numpy as np

from .config import (FRAME_STALE_SEC)


# ══════════════════════════════════════════════════════════════════════════════
# 분산 카메라 — 라즈베리파이 MJPEG(:5000) 수신 (작업순서 1번)
# ══════════════════════════════════════════════════════════════════════════════

class MjpegCamera:
    """HTTP MJPEG 스트림을 직접 파싱해 최신 프레임만 보관.

    OpenCV FFMPEG 백엔드의 네트워크 스트림 크래시(Segfault/Abort)를 피하려고
    urllib 로 바이트를 받아 JPEG 경계(FFD8..FFD9)로 직접 잘라 디코드한다.
    (ros_person_follower_nav2.py 의 VideoCaptureThreaded 와 동일 전략)

    인터페이스는 robocart_light 의 Camera 와 동일: read()->frame|None / opened() / stop()
    """

    def __init__(self, url: str, mirror: bool = False):
        self.url = url
        self._mirror = mirror          # True: 좌우반전 보정 (카메라가 거울상일 때)
        self._frame: np.ndarray | None = None
        self._frame_at = 0.0           # 마지막 프레임 수신 시각 (신선도 판정)
        self._rx_n = 0                 # 수신 프레임 카운터 (fps 진단용)
        self._running = True
        self._th = threading.Thread(target=self._loop, daemon=True)
        self._th.start()

    def rx_count(self) -> int:
        return self._rx_n

    def _loop(self):
        while self._running:
            stream = None
            try:
                stream = urllib.request.urlopen(self.url, timeout=3.0)
                buf = b""
                while self._running:
                    chunk = stream.read(8192)
                    if not chunk:
                        break
                    buf += chunk
                    # 최신 프레임만 디코드: 버퍼에 완성 JPEG이 여러 장 쌓여 있으면
                    # 마지막 한 장만 취하고 이전 것은 폐기 (디코드가 수신을 못 따라갈 때
                    # 지연이 계속 누적되는 것을 방지)
                    b = buf.rfind(b"\xff\xd9")    # 마지막 JPEG EOI
                    if b == -1:
                        continue
                    a = buf.rfind(b"\xff\xd8", 0, b)   # 그 앞의 SOI
                    if a == -1:
                        buf = buf[b + 2:]
                        continue
                    jpg = buf[a:b + 2]
                    buf = buf[b + 2:]
                    f = cv2.imdecode(np.frombuffer(jpg, np.uint8), cv2.IMREAD_COLOR)
                    if f is not None:
                        if self._mirror:
                            f = cv2.flip(f, 1)   # 좌우반전 보정 (인식·라이다 방위 일관)
                        self._frame = f
                        self._frame_at = time.time()
                        self._rx_n += 1
            except Exception:
                # 프레임은 지우지 않음 — read()의 신선도 검사가 오래된 프레임을 걸러줌.
                # (여기서 None 으로 지우면 잠깐의 끊김에도 화면이 검게 멈춤)
                pass
            finally:
                if stream is not None:
                    try:
                        stream.close()
                    except Exception:
                        pass
            if self._running:
                time.sleep(0.3)               # 재연결 대기 (1.0→0.3: 끊김 시 공백 단축)

    def read(self):
        # 오래된 프레임(FRAME_STALE_SEC 초과)은 없는 것으로 처리 (끊긴 스트림으로 주행 판단 방지)
        f = self._frame
        if f is None or time.time() - self._frame_at > FRAME_STALE_SEC:
            return None
        return f.copy()

    def opened(self):
        return self._running

    def stop(self):
        self._running = False


