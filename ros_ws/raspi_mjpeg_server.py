#!/usr/bin/env python3
"""
SmartCart 라즈베리파이4 — C920 네이티브 MJPEG HTTP 송출 (디코드 없음, CPU≈0)

목적:
  DDS(ROS2 image) 전송이 WiFi에서 불안정하고, usb_cam(mjpeg2rgb)이 RPi에서
  디코드→재압축 이중 변환으로 CPU를 포화시켜 영상이 "멈췄다 몰아보기" 되는 문제를
  근본 회피한다. ffmpeg가 카메라의 네이티브 MJPEG 프레임을 -c:v copy(재인코딩 없음)
  로 그대로 받아 stdout으로 흘리고, 이 서버가 프레임 단위로 잘라
  multipart/x-mixed-replace 로 여러 클라이언트에 송출한다.

  C920 → ffmpeg(copy, 디코드X) → 이 서버 → HTTP MJPEG → (WiFi) → VMware robocart_main

전송 경로 분리(하이브리드):
  영상 = 이 HTTP MJPEG (ROS2 안 거침)
  명령 = ROS2 /robocart/cmd (raspi_cmd_bridge.py 그대로)

실행:
  python3 raspi_mjpeg_server.py                       # http://<RPI_IP>:8090/stream
  python3 raspi_mjpeg_server.py --port 8090 --device /dev/video0 \
          --width 640 --height 480 --fps 15

의존성: ffmpeg (sudo apt install ffmpeg). OpenCV/ROS2 불필요 → RPi 가볍게 유지.
종료: Ctrl+C
"""
import argparse
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

_latest: bytes | None = None       # 최신 완성 JPEG 프레임
_lock = threading.Lock()
_running = True

_SOI = b"\xff\xd8"   # JPEG 시작 마커
_EOI = b"\xff\xd9"   # JPEG 끝 마커


def _reader(proc: subprocess.Popen) -> None:
    """ffmpeg stdout(연속 MJPEG)에서 프레임을 잘라 최신본만 보관."""
    global _latest
    buf = b""
    while _running:
        chunk = proc.stdout.read(8192)
        if not chunk:
            break
        buf += chunk
        # 버퍼에 완성된 프레임이 여러 개면 가장 마지막(최신)만 남기고 소비
        while True:
            s = buf.find(_SOI)
            if s < 0:
                if len(buf) > 4_000_000:    # 비정상 누적 방지
                    buf = b""
                break
            e = buf.find(_EOI, s + 2)
            if e < 0:
                buf = buf[s:]               # 미완성 프레임은 보존
                break
            frame = buf[s:e + 2]
            buf = buf[e + 2:]
            with _lock:
                _latest = frame


PAGE = ("""<!doctype html><html><head><meta charset="utf-8">
<title>RPi Camera (MJPEG passthrough)</title>
<style>body{background:#111;color:#eee;font-family:sans-serif;text-align:center}
img{max-width:97vw;border:1px solid #444;margin-top:10px}</style></head>
<body><h3>SmartCart - 라즈베리파이 카메라 (MJPEG 패스스루)</h3>
<img src="/stream"></body></html>""").encode("utf-8")


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):  # 접근 로그 억제
        pass

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(PAGE)
            return
        if self.path == "/stream":
            self.send_response(200)
            self.send_header(
                "Content-Type", "multipart/x-mixed-replace; boundary=frame")
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            last_id = None
            try:
                while True:
                    with _lock:
                        f = _latest
                    if f is None or f is last_id:
                        time.sleep(0.005)
                        continue
                    last_id = f
                    self.wfile.write(b"--frame\r\nContent-Type: image/jpeg\r\n")
                    self.wfile.write(f"Content-Length: {len(f)}\r\n\r\n".encode())
                    self.wfile.write(f)
                    self.wfile.write(b"\r\n")
            except (BrokenPipeError, ConnectionResetError):
                pass
            return
        self.send_error(404)


def main() -> None:
    ap = argparse.ArgumentParser(description="RPi C920 MJPEG HTTP 패스스루 송출")
    ap.add_argument("--port", type=int, default=8090)
    ap.add_argument("--device", default="/dev/video0")
    ap.add_argument("--width", type=int, default=640)
    ap.add_argument("--height", type=int, default=480)
    ap.add_argument("--fps", type=int, default=15)
    a = ap.parse_args()

    cmd = [
        "ffmpeg", "-nostdin", "-loglevel", "error",
        "-f", "v4l2", "-input_format", "mjpeg",
        "-video_size", f"{a.width}x{a.height}", "-framerate", str(a.fps),
        "-i", a.device,
        "-c:v", "copy",          # 재인코딩 없음 (디코드/인코드 안 함 → CPU≈0)
        "-f", "mjpeg", "pipe:1",
    ]
    print("[ffmpeg]", " ".join(cmd), flush=True)
    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=sys.stderr,
                                bufsize=0)
    except FileNotFoundError:
        print("[오류] ffmpeg 없음 → sudo apt install ffmpeg", file=sys.stderr)
        sys.exit(1)

    threading.Thread(target=_reader, args=(proc,), daemon=True).start()

    server = ThreadingHTTPServer(("0.0.0.0", a.port), Handler)
    print("=" * 56, flush=True)
    print("  SmartCart 라즈베리파이 MJPEG 패스스루 송출", flush=True)
    print(f"  스트림 URL:  http://<RPI_IP>:{a.port}/stream", flush=True)
    print(f"  해상도/FPS:  {a.width}x{a.height} @ {a.fps}fps  (디코드 없음)", flush=True)
    print("  종료: Ctrl+C", flush=True)
    print("=" * 56, flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        global _running
        _running = False
        try:
            proc.terminate()
        except Exception:
            pass


if __name__ == "__main__":
    main()
