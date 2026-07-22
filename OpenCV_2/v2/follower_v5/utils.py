# -*- coding: utf-8 -*-
"""[유틸리티 모듈] utils.py
- 주요 역할: 시스템 디버그 이력 저장, 외부 기기(라파 음성/ESP8266 LED) 연동 통신 및 수학 보정 유틸.
- 주요 구성:
  1. DebugLog (JSONL 형태의 디버그 이력 기록 클래스)
  2. speak_on_pi (라즈베리파이 스피커 HTTP 음성 안내 호출)
  3. set_robot_led (ESP8266 아두이노 LED 상태 변경 HTTP 요청)
  4. _clamp, _yaw_to_quat, _quat_to_yaw (수학 및 오일러-쿼터니언 각도 변환)
"""

from __future__ import annotations

import json
import math
import threading
import time
import urllib.parse
import urllib.request
from datetime import datetime

from .config import HERE

last_led_status = None


class DebugLog:
    """인식/주행 이벤트를 debug_logs/run_*.jsonl 에 기록."""

    def __init__(self, enabled: bool = False):
        self.f = None
        self.path = None
        if enabled:
            d = HERE / "debug" / "debug_logs"
            d.mkdir(parents=True, exist_ok=True)
            self.path = d / f"run_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jsonl"
            self.f = open(self.path, "w", encoding="utf-8", buffering=1)

    def log(self, ev: str, **kw):
        if self.f is None:
            return
        kw["ev"] = ev
        kw["t"] = round(time.time(), 3)
        try:
            self.f.write(json.dumps(kw, ensure_ascii=False) + "\n")
        except Exception:
            pass


DBG = DebugLog(enabled=False)


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def _yaw_to_quat(yaw: float) -> tuple[float, float, float, float]:
    return (0.0, 0.0, math.sin(yaw / 2.0), math.cos(yaw / 2.0))


def _quat_to_yaw(x: float, y: float, z: float, w: float) -> float:
    return math.atan2(2.0 * (w * z + x * y), 1.0 - 2.0 * (y * y + z * z))


def speak_on_pi(pi_ip: str | None, text: str):
    if not pi_ip:
        return

    def run():
        try:
            encoded_text = urllib.parse.quote(text)
            host = pi_ip if ":" in str(pi_ip) else f"{pi_ip}:5000"
            url = f"http://{host}/speak?text={encoded_text}"
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=1.5):
                pass
        except Exception as e:
            print(f"[speak_on_pi] 소리 출력 실패: {e}")

    threading.Thread(target=run, daemon=True).start()


def set_robot_led(esp_ip: str | None, status: str, blocking: bool = False):
    global last_led_status
    if not esp_ip or status == last_led_status:
        return
    last_led_status = status
    print(f"[set_robot_led] 아두이노({esp_ip})로 LED 상태 변경 전송: {status}")

    def run():
        try:
            url = f"http://{esp_ip}/led?status={status}"
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=1.5):
                pass
        except Exception as e:
            print(f"[set_robot_led] LED 제어 실패 ({status}): {e}")

    if blocking:
        run()
    else:
        threading.Thread(target=run, daemon=True).start()
