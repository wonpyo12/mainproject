#!/usr/bin/env python3
"""
motor_node — RPi4용 모터 제어 노드 (소켓 서버 + ESP32 시리얼)

역할:
  - TCP 소켓 서버 (포트 9999) → VM inference_node 로부터 명령 수신
  - 수신 명령을 ESP32 시리얼 프로토콜로 변환하여 송신
  - dry_run=True 면 시리얼 미연결도 동작 (콘솔 출력만)

소켓 입력 (JSON, 줄바꿈 종료):
  {"type":"track","x":320,"y":240,"score":0.83}    # 카메라 서보 추적
  {"type":"lost"}                                   # 사람 놓침 → 서보 탐색
  {"type":"center"}                                 # 서보 중앙 복귀
  {"type":"drive","linear":0.2,"angular":0.0}      # 바퀴 주행 (m/s, rad/s)
  {"type":"stop"}                                   # 바퀴 정지

ESP32 시리얼 명령 (115200bps, 줄바꿈 종료):
  A<각도>            — 서보 지정 각도로 이동
  S                  — 서보 좌우 탐색 시작
  H                  — 서보 탐색 정지
  C                  — 서보 중앙 복귀
  D<linear>,<angular> — 바퀴 주행 (cm/s, deg/s 단위로 ×100 정수 송신)
  X                  — 바퀴 정지
"""
from __future__ import annotations

import json
import socket
import threading
import time

import rclpy
from rclpy.node import Node

try:
    import serial   # pyserial
    SERIAL_OK = True
except ImportError:
    SERIAL_OK = False


class MotorNode(Node):

    def __init__(self) -> None:
        super().__init__("motor_node")

        # ── 파라미터 ─────────────────────────────────────
        self.declare_parameter("listen_host", "0.0.0.0")
        self.declare_parameter("listen_port", 9999)
        self.declare_parameter("serial_port", "/dev/ttyUSB0")
        self.declare_parameter("serial_baud", 115200)
        self.declare_parameter("dry_run",     False)        # 시리얼 없이 콘솔만
        self.declare_parameter("image_width", 640)          # 카메라 가로 (각도 계산용)
        self.declare_parameter("hfov_deg",    60.0)         # 카메라 수평 화각
        self.declare_parameter("center_deg",  90.0)         # 서보 중앙 각도
        self.declare_parameter("gain",        0.5)          # 반응 게인 (0~1)
        self.declare_parameter("dead_zone_px", 40)          # 중앙 ±N px 무시
        self.declare_parameter("min_deg",     10.0)
        self.declare_parameter("max_deg",     170.0)

        self.host    = self.get_parameter("listen_host").value
        self.port    = self.get_parameter("listen_port").value
        self.dry     = self.get_parameter("dry_run").value
        self.img_w   = self.get_parameter("image_width").value
        self.hfov    = self.get_parameter("hfov_deg").value
        self.center  = self.get_parameter("center_deg").value
        self.gain    = self.get_parameter("gain").value
        self.dead_px = self.get_parameter("dead_zone_px").value
        self.min_deg = self.get_parameter("min_deg").value
        self.max_deg = self.get_parameter("max_deg").value

        # ── 시리얼 ───────────────────────────────────────
        self.ser = None
        if self.dry:
            print("[motor_node] dry_run=True → 시리얼 미사용 (콘솔 출력)")
        elif not SERIAL_OK:
            print("[motor_node] [경고] pyserial 미설치 → dry_run 으로 폴백")
            self.dry = True
        else:
            port = self.get_parameter("serial_port").value
            baud = self.get_parameter("serial_baud").value
            try:
                self.ser = serial.Serial(port, baud, timeout=0.2)
                time.sleep(2.0)   # ESP32 리셋 대기
                print(f"[motor_node] 시리얼 연결 ✓ {port} @ {baud}")
            except Exception as e:
                print(f"[motor_node] [경고] 시리얼 열기 실패: {e} → dry_run 으로 폴백")
                self.dry = True

        # ── 현재 각도 ─────────────────────────────────
        self.cur_deg = self.center
        self._send_serial(f"C")     # 중앙 복귀로 시작

        # ── 소켓 서버 (별도 스레드) ─────────────────
        self._stop = False
        threading.Thread(target=self._socket_server_loop, daemon=True).start()
        print(f"[motor_node] 소켓 서버 대기: {self.host}:{self.port}")

    # ════════════════════════════════════════════════════
    # 시리얼 송신
    # ════════════════════════════════════════════════════
    def _send_serial(self, cmd: str) -> None:
        cmd = cmd.strip() + "\n"
        if self.dry or self.ser is None:
            print(f"  [DRY-SERIAL] → {cmd.strip()}")
            return
        try:
            self.ser.write(cmd.encode("ascii"))
        except Exception as e:
            print(f"[motor_node] 시리얼 송신 실패: {e}")

    # ════════════════════════════════════════════════════
    # 명령 처리
    # ════════════════════════════════════════════════════
    def _handle_command(self, payload: dict) -> None:
        t = payload.get("type", "")

        if t == "track":
            x = int(payload.get("x", self.img_w // 2))
            self._track(x)
        elif t == "lost":
            self._send_serial("S")     # 탐색 시작
            print("[motor_node] LOST → 탐색(S)")
        elif t == "center":
            self._send_serial("C")
            self.cur_deg = self.center
            print("[motor_node] CENTER → 90°")
        elif t == "drive":
            linear  = float(payload.get("linear", 0.0))
            angular = float(payload.get("angular", 0.0))
            # 정수 변환: m/s → cm/s 정수, rad/s → 0.01rad/s 단위 정수 (펌웨어 파싱 용이)
            self._send_serial(f"D{int(round(linear * 100))},{int(round(angular * 100))}")
        elif t == "stop":
            self._send_serial("X")
            print("[motor_node] STOP → 바퀴 정지(X)")
        else:
            print(f"[motor_node] 알 수 없는 명령: {payload}")

    def _track(self, target_x: int) -> None:
        """target_x (영상 픽셀) → 서보 각도 변환."""
        center_x = self.img_w / 2
        err = target_x - center_x

        # 데드존
        if abs(err) < self.dead_px:
            return

        # 픽셀 → 도 변환 (화각 기반)
        # 영상 가로 = hfov (도) 에 해당
        deg_per_px = self.hfov / self.img_w
        delta = -err * deg_per_px * self.gain   # 부호: 사람이 왼쪽이면 서보를 왼쪽으로

        new_deg = self.cur_deg + delta
        new_deg = max(self.min_deg, min(self.max_deg, new_deg))

        if abs(new_deg - self.cur_deg) < 0.5:
            return

        self.cur_deg = new_deg
        self._send_serial(f"A{int(round(new_deg))}")

    # ════════════════════════════════════════════════════
    # 소켓 서버
    # ════════════════════════════════════════════════════
    def _socket_server_loop(self) -> None:
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind((self.host, self.port))
        srv.listen(1)
        srv.settimeout(1.0)

        while not self._stop and rclpy.ok():
            try:
                conn, addr = srv.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            print(f"[motor_node] 클라이언트 접속 ✓ {addr}")
            self._serve_client(conn)
            print(f"[motor_node] 클라이언트 종료 ✗ {addr}")

        srv.close()

    def _serve_client(self, conn: socket.socket) -> None:
        buf = b""
        conn.settimeout(2.0)
        while not self._stop and rclpy.ok():
            try:
                chunk = conn.recv(4096)
            except socket.timeout:
                continue
            except OSError:
                break
            if not chunk:
                break
            buf += chunk
            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                line = line.strip()
                if not line:
                    continue
                try:
                    payload = json.loads(line.decode("utf-8"))
                except json.JSONDecodeError:
                    continue
                self._handle_command(payload)
        conn.close()

    # ════════════════════════════════════════════════════
    def destroy_node(self) -> bool:
        self._stop = True
        self._send_serial("X")   # 바퀴 정지
        self._send_serial("C")   # 서보 중앙 복귀
        if self.ser is not None:
            try:
                self.ser.close()
            except Exception:
                pass
        print("[motor_node] 종료")
        return super().destroy_node()


def main(args=None) -> None:
    rclpy.init(args=args)
    node = None
    try:
        node = MotorNode()
        rclpy.spin(node)
    except KeyboardInterrupt:
        print("\n[motor_node] Ctrl+C 종료")
    finally:
        if node is not None:
            node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
