# -*- coding: utf-8 -*-
"""[카메라 스트리밍 모듈] camera.py
- 주요 역할: 라즈베리파이 5000번 포트의 MJPEG 비디오 스트림을 비동기 수신하여 최신 프레임 큐 보관.
- 주요 클래스:
  - MjpegCamera: HTTP 바이트 버퍼 기반 파싱 (FFMPEG 백엔드 크래시 방지 및 최신 프레임 갱신)
"""

from __future__ import annotations

import threading
import time
import urllib.request

import cv2
import numpy as np


class MjpegCamera:
    """HTTP MJPEG 스트림을 직접 파싱해 최신 프레임만 보관."""

    def __init__(self, url: str, mirror: bool = False):
        self.url = url
        self._mirror = mirror
        self._frame: np.ndarray | None = None
        self._frame_at = 0.0
        self._rx_n = 0
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
                    b = buf.rfind(b"\xff\xd9")
                    if b == -1:
                        continue
                    a = buf.rfind(b"\xff\xd8", 0, b)
                    if a == -1:
                        buf = buf[b + 2:]
                        continue
                    jpg = buf[a:b + 2]
                    buf = buf[b + 2:]
                    f = cv2.imdecode(np.frombuffer(jpg, np.uint8), cv2.IMREAD_COLOR)
                    if f is not None:
                        if self._mirror:
                            f = cv2.flip(f, 1)
                        self._frame = f
                        self._frame_at = time.time()
                        self._rx_n += 1
            except Exception:
                pass
            finally:
                if stream is not None:
                    try:
                        stream.close()
                    except Exception:
                        pass
            if self._running:
                time.sleep(0.3)

    def read(self) -> np.ndarray | None:
        f = self._frame
        if f is None or time.time() - self._frame_at > 2.0:
            return None
        return f.copy()

    def opened(self) -> bool:
        return self._running

    def stop(self):
        self._running = False
