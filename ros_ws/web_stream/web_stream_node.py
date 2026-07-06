#!/usr/bin/env python3
"""
web_stream_node — ROS2 영상 토픽을 웹 브라우저용 MJPEG 스트림으로 변환

  /image/annotated (tracker 인식 결과) 또는 /image/compressed (원본 카메라)
    → multipart/x-mixed-replace MJPEG HTTP 스트림 (포트 8090)

브라우저에서 보기:
  http://localhost:8090/            단독 뷰어 페이지
  http://localhost:8090/stream      <img src> 로 임베드할 MJPEG 스트림
  http://localhost:8090/snapshot    현재 프레임 1장 (JPEG)

mirrored 네트워킹이면 WSL에서 띄워도 Windows 브라우저에서 localhost 로 접속됩니다.

실행 (WSL):
  source /opt/ros/humble/setup.bash
  export ROS_DOMAIN_ID=30
  python3 web_stream_node.py
  # 원본 카메라를 보고 싶으면:
  python3 web_stream_node.py --ros-args -p topic:=/image/compressed
"""
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy
from sensor_msgs.msg import CompressedImage

PORT = 8090

_latest = {"jpg": None, "ts": 0.0}
_anno = {"ts": 0.0}   # /image/annotated 마지막 수신 시각 (폴백 판단용)
_lock = threading.Lock()

PAGE = ("""<!doctype html>
<html lang="ko"><head><meta charset="utf-8">
<title>RoboCart 카메라</title>
<style>
  body{margin:0;background:#111;color:#eee;font-family:sans-serif;text-align:center}
  h2{padding:14px;margin:0;font-weight:600}
  img{max-width:100%;height:auto;border-top:1px solid #333}
  .hint{color:#888;font-size:13px;padding:10px}
</style></head><body>
<h2>RoboCart 실시간 카메라</h2>
<img src="/stream" alt="카메라 연결 대기 중...">
<div class="hint">tracker_node 가 실행 중이면 인식 박스가 함께 보입니다.</div>
</body></html>""").encode("utf-8")


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass  # 접속 로그 끔

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(PAGE)))
            self.end_headers()
            self.wfile.write(PAGE)

        elif self.path == "/snapshot":
            with _lock:
                jpg = _latest["jpg"]
            if jpg is None:
                self.send_error(503, "no frame yet")
                return
            self.send_response(200)
            self.send_header("Content-Type", "image/jpeg")
            self.send_header("Content-Length", str(len(jpg)))
            self.end_headers()
            self.wfile.write(jpg)

        elif self.path == "/stream":
            self.send_response(200)
            self.send_header("Age", "0")
            self.send_header("Cache-Control", "no-cache, private")
            self.send_header("Pragma", "no-cache")
            self.send_header(
                "Content-Type", "multipart/x-mixed-replace; boundary=frame")
            self.end_headers()
            last_ts = 0.0
            try:
                while True:
                    with _lock:
                        jpg = _latest["jpg"]
                        ts = _latest["ts"]
                    if jpg is not None and ts != last_ts:
                        last_ts = ts
                        self.wfile.write(b"--frame\r\n")
                        self.wfile.write(b"Content-Type: image/jpeg\r\n")
                        self.wfile.write(
                            f"Content-Length: {len(jpg)}\r\n\r\n".encode())
                        self.wfile.write(jpg)
                        self.wfile.write(b"\r\n")
                    time.sleep(0.03)
            except (BrokenPipeError, ConnectionResetError):
                pass  # 브라우저 탭 닫힘
        else:
            self.send_error(404)


class WebStreamNode(Node):
    def __init__(self):
        super().__init__("web_stream_node")
        topic = self.declare_parameter("topic", "/image/annotated").value
        qos = QoSProfile(depth=1, reliability=ReliabilityPolicy.BEST_EFFORT)
        self.create_subscription(CompressedImage, topic, self._on_image, qos)
        # annotated 가 없을 때를 대비해 원본도 함께 구독(있으면 annotated 가 우선)
        if topic == "/image/annotated":
            self.create_subscription(
                CompressedImage, "/image/compressed", self._on_fallback, qos)
        self.get_logger().info(f"구독: {topic}  →  http://localhost:{PORT}/")

    def _on_image(self, msg: CompressedImage):
        with _lock:
            _latest["jpg"] = bytes(msg.data)
            _latest["ts"] = time.time()
            _anno["ts"] = time.time()   # annotated 수신 기록

    def _on_fallback(self, msg: CompressedImage):
        # annotated 가 최근 0.5초간 없을 때만 원본 사용 — 단 풀레이트로 갱신
        # (이전 버그: _latest["ts"] 기준이라 원본이 0.5초당 1프레임으로 제한됐음)
        with _lock:
            if time.time() - _anno["ts"] > 0.5:
                _latest["jpg"] = bytes(msg.data)
                _latest["ts"] = time.time()


def main():
    rclpy.init()
    node = WebStreamNode()

    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    print(f"[web_stream] http://localhost:{PORT}/  열림")

    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        server.shutdown()
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
