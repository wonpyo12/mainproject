#!/usr/bin/env python3
"""
ESP32 + MG996R 카메라 팬 서보 시리얼 컨트롤러

펌웨어: Arduino/camera_servo/camera_servo.ino (115200bps)

명령 프로토콜:
  A<각도>\n  지정 각도로 이동 (추적)
  S\n        탐색 스윕 시작 (ESP32 자체 왕복)
  H\n        스윕 정지 (현재 각도 유지)
  C\n        중앙(90도) 복귀

수신:
  P<각도>    ESP32가 100ms마다 보고하는 현재 각도
"""

from __future__ import annotations

import threading
import time

try:
    import serial
    import serial.tools.list_ports
    SERIAL_AVAILABLE = True
except ImportError:
    SERIAL_AVAILABLE = False
    print("[경고] pyserial 없음 → 서보 제어 비활성화")
    print("       pip install pyserial")

BAUD_RATE        = 115200
ANGLE_MIN        = 0
ANGLE_MAX        = 180
ANGLE_CENTER     = 90
SEND_INTERVAL    = 0.10   # 각도 명령 최소 전송 간격 (초) — 시리얼 폭주 방지
ANGLE_DEADBAND   = 1      # 목표각 변화가 이 값 이하면 전송 생략

# ESP32 USB-UART 칩 식별용 (CP210x, CH340 등)
_ESP32_KEYWORDS = ("CP210", "CH340", "CH910", "USB-SERIAL", "USB SERIAL", "SILICON LABS")


def find_esp32_port() -> str | None:
    """연결된 포트 중 ESP32로 추정되는 COM 포트를 반환합니다."""
    if not SERIAL_AVAILABLE:
        return None
    ports = serial.tools.list_ports.comports()
    for p in ports:
        desc = (p.description or "").upper()
        if any(k in desc for k in _ESP32_KEYWORDS):
            return p.device
    # 못 찾으면 포트가 1개뿐일 때 그것을 사용
    if len(ports) == 1:
        return ports[0].device
    return None


class ServoController:
    """카메라 팬 서보 제어 (스레드 안전, 미연결 시 no-op으로 동작)."""

    def __init__(self, port: str | None = None, enabled: bool = True) -> None:
        self._lock = threading.Lock()
        self._ser = None
        self.current_angle = ANGLE_CENTER   # ESP32가 보고하는 실제 각도
        self._last_sent_angle: int | None = None
        self._last_send_time = 0.0
        self._mode = "hold"                 # hold | track | sweep
        self._stop_flag = False

        if not enabled or not SERIAL_AVAILABLE:
            print("[서보] 비활성화 모드 (시뮬레이션)")
            return

        if port is None:
            port = find_esp32_port()
        if port is None:
            print("[서보] ESP32 포트를 찾지 못함 → 서보 없이 동작")
            return

        try:
            self._ser = serial.Serial(port, BAUD_RATE, timeout=0.1)
            time.sleep(2.0)   # ESP32 리셋 대기
            self._ser.reset_input_buffer()
            print(f"[서보] 연결 완료: {port}")
        except Exception as e:
            print(f"[서보] 연결 실패 ({port}): {e} → 서보 없이 동작")
            self._ser = None
            return

        # 백그라운드에서 각도 보고(P<n>) 수신
        self._reader = threading.Thread(target=self._read_loop, daemon=True)
        self._reader.start()

    # ── 내부 ────────────────────────────────────────────────────────────────

    @property
    def connected(self) -> bool:
        return self._ser is not None

    def _read_loop(self) -> None:
        while not self._stop_flag and self._ser is not None:
            try:
                line = self._ser.readline().decode(errors="ignore").strip()
            except Exception:
                break
            if line.startswith("P"):
                try:
                    self.current_angle = int(line[1:])
                except ValueError:
                    pass

    def _send(self, cmd: str) -> None:
        if self._ser is None:
            return
        with self._lock:
            try:
                self._ser.write((cmd + "\n").encode())
            except Exception as e:
                print(f"[서보] 전송 오류: {e}")

    # ── 공개 API ────────────────────────────────────────────────────────────

    @property
    def mode(self) -> str:
        return self._mode

    def move_to(self, angle: float) -> None:
        """지정 각도로 이동 (추적 모드). 전송 레이트 제한 적용."""
        angle = int(max(ANGLE_MIN, min(ANGLE_MAX, round(angle))))
        now = time.time()
        if (self._last_sent_angle is not None
                and abs(angle - self._last_sent_angle) <= ANGLE_DEADBAND
                and self._mode == "track"):
            return
        if now - self._last_send_time < SEND_INTERVAL:
            return
        self._last_send_time = now
        self._last_sent_angle = angle
        self._mode = "track"
        self._send(f"A{angle}")
        if self._ser is None:               # 시뮬레이션 모드에서도 각도 추적
            self.current_angle = angle

    def start_sweep(self) -> None:
        """탐색 스윕 시작 (이미 스윕 중이면 무시)."""
        if self._mode == "sweep":
            return
        self._mode = "sweep"
        self._last_sent_angle = None
        self._send("S")
        print("[서보] 탐색 스윕 시작")

    def hold(self) -> None:
        """스윕 정지, 현재 각도 유지."""
        if self._mode == "hold":
            return
        self._mode = "hold"
        self._last_sent_angle = None
        self._send("H")

    def center(self) -> None:
        """중앙(90도) 복귀."""
        self._mode = "track"
        self._last_sent_angle = ANGLE_CENTER
        self._send("C")

    def close(self) -> None:
        self._stop_flag = True
        if self._ser is not None:
            try:
                self._send("C")   # 종료 시 중앙 복귀
                time.sleep(0.1)
                self._ser.close()
            except Exception:
                pass
            self._ser = None


if __name__ == "__main__":
    # 단독 테스트: 연결 → 좌우 이동 → 스윕 5초 → 중앙 복귀
    sc = ServoController()
    if not sc.connected:
        print("ESP32 미연결 — 테스트 종료")
    else:
        print("45도 이동");  sc.move_to(45);  time.sleep(2)
        print("135도 이동"); time.sleep(0.2); sc.move_to(135); time.sleep(2)
        print("스윕 5초");   sc.start_sweep(); time.sleep(5)
        print("정지 후 중앙 복귀"); sc.hold(); time.sleep(1); sc.center(); time.sleep(2)
    sc.close()
