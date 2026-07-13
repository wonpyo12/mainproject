#!/usr/bin/env python3
"""
[Windows 쪽] 카메라·서보 하드웨어 브리지 — "로봇 역할"

웹캠과 ESP32(서보)가 Windows에 물려 있으므로, 이 스크립트가 로봇인 척하며
WSL 안의 ROS2와 TCP로 데이터를 주고받는다. (로봇이 준비되면 이 스크립트가
로봇의 카메라 노드 + 모터 노드로 대체된다)

  웹캠 → JPEG → TCP ──→ [WSL] cam_bridge_node → /image/compressed
  ESP32 서보 ← 시리얼 ← TCP ←─ [WSL] cam_bridge_node ← /servo_cmd

패킷 (양방향 공통):  type(1B) + length(4B BE) + payload
  Windows → WSL : 'F' = JPEG 프레임, 'S' = 서보 상태("P95")
  WSL → Windows : 'C' = 서보 명령("A95"/"S"/"H"/"C"),
                  'V' = 추적 결과 JPEG (이 창을 Windows에서 표시)

실행 (Windows, smart_cart venv):
  d:\\YH\\OpenCV\\smart_cart\\.venv\\Scripts\\python.exe win_cam_servo_bridge.py
"""
import socket
import struct
import sys
import threading
import time

import cv2
import serial
import serial.tools.list_ports

HOST = "127.0.0.1"     # WSL2는 Windows에서 localhost로 접근 가능
PORT = 5005
JPEG_QUALITY = 80
TARGET_FPS = 20
BAUD = 115200


def find_esp32_port() -> str | None:
    for p in serial.tools.list_ports.comports():
        desc = (p.description or "").lower()
        if any(k in desc for k in ("cp210", "ch340", "ch910", "usb serial", "silicon labs")):
            return p.device
    return None


def open_camera():
    for backend in (cv2.CAP_DSHOW, cv2.CAP_MSMF, cv2.CAP_ANY):
        cap = cv2.VideoCapture(0, backend)
        if cap.isOpened():
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
            return cap
        cap.release()
    return None


def main() -> int:
    # ── 시리얼 (없어도 영상은 전송) ──────────────────────────────
    ser = None
    port = find_esp32_port()
    if port:
        try:
            ser = serial.Serial(port, BAUD, timeout=0.1)
            time.sleep(2)  # ESP32 리셋 대기
            print(f"[브리지] 서보 연결: {port}")
        except serial.SerialException as e:
            print(f"[브리지] 서보 연결 실패({e}) → 영상만 전송")
    else:
        print("[브리지] ESP32 미발견 → 영상만 전송")

    cap = open_camera()
    if cap is None:
        print("[브리지] 카메라를 열 수 없습니다")
        return 1

    # ── TCP 연결 (WSL의 cam_bridge_node가 먼저 떠 있어야 함) ────
    while True:
        try:
            sock = socket.create_connection((HOST, PORT), timeout=3)
            sock.settimeout(None)   # 연결 후엔 블로킹 모드 (recv 타임아웃 방지)
            break
        except OSError:
            print("[브리지] WSL 노드 대기 중... (cam_bridge_node 먼저 실행)")
            time.sleep(2)
    sock_lock = threading.Lock()
    print(f"[브리지] WSL 연결 완료 {HOST}:{PORT}")

    def send_packet(ptype: bytes, payload: bytes):
        with sock_lock:
            sock.sendall(ptype + struct.pack(">I", len(payload)) + payload)

    # ── WSL → Windows 패킷 수신 스레드 (서보 명령 + 추적 화면) ──
    view_holder = {"frame": None}

    def _recv_exact(n: int) -> bytes:
        buf = b""
        while len(buf) < n:
            chunk = sock.recv(n - len(buf))
            if not chunk:
                raise OSError("closed")
            buf += chunk
        return buf

    def packet_reader():
        import numpy as np
        while True:
            try:
                head = _recv_exact(5)
            except OSError:
                break
            ptype, length = head[:1], struct.unpack(">I", head[1:])[0]
            payload = _recv_exact(length)
            if ptype == b"C":
                cmd = payload.decode(errors="ignore").strip()
                if cmd:
                    print(f"[브리지] 서보 명령 ← ROS2: {cmd}")
                    if ser:
                        ser.write((cmd + "\n").encode())
            elif ptype == b"V":
                img = cv2.imdecode(np.frombuffer(payload, np.uint8),
                                   cv2.IMREAD_COLOR)
                if img is not None:
                    view_holder["frame"] = img

    threading.Thread(target=packet_reader, daemon=True).start()

    # ── 시리얼 → WSL 상태 전달 스레드 (P각도 보고) ──────────────
    def serial_reader():
        while ser:
            try:
                line = ser.readline().decode(errors="ignore").strip()
            except serial.SerialException:
                break
            if line.startswith("P"):
                try:
                    send_packet(b"S", line.encode())
                except OSError:
                    break

    if ser:
        threading.Thread(target=serial_reader, daemon=True).start()

    # ── 메인 루프: 프레임 전송 ──────────────────────────────────
    interval = 1.0 / TARGET_FPS
    n, t0 = 0, time.time()
    try:
        while True:
            t = time.time()
            ok, frame = cap.read()
            if not ok:
                print("[브리지] 프레임 읽기 실패")
                break
            ok, jpg = cv2.imencode(".jpg", frame,
                                   [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY])
            if ok:
                try:
                    send_packet(b"F", jpg.tobytes())
                except OSError:
                    print("[브리지] WSL 연결 끊김")
                    break
            n += 1
            if n % 100 == 0:
                print(f"[브리지] 전송 {n}프레임  ({n/(time.time()-t0):.1f}fps)")

            # WSL에서 돌아온 추적 결과 화면 표시 (ESC: 종료)
            view = view_holder["frame"]
            if view is not None:
                cv2.imshow("SmartCart - ROS2 실시간 추종", view)
                if cv2.waitKey(1) & 0xFF == 27:
                    print("[브리지] ESC — 종료")
                    break

            wait = interval - (time.time() - t)
            if wait > 0:
                time.sleep(wait)
    except KeyboardInterrupt:
        pass
    finally:
        cap.release()
        if ser:
            ser.write(b"C\n")   # 종료 시 중앙 복귀
            ser.close()
        sock.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
