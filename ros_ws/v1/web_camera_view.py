#!/usr/bin/env python3
"""
라즈베리파이 카메라 영상 — 웹 브라우저 확인 서버

cv2.imshow 가 VMware 에서 검은 창만 뜨는 환경을 위해, ROS2 토픽
(/robocart/image_raw/compressed) 을 구독해 MJPEG 로 HTTP 스트리밍한다.
브라우저에서 영상을 바로 확인할 수 있다.

실행:
  source /opt/ros/humble/setup.bash
  export ROS_DOMAIN_ID=42
  python3 web_camera_view.py                  # http://localhost:8080
  python3 web_camera_view.py --port 8000

확인: 같은 VMware 의 브라우저에서  http://localhost:8080  접속
종료: Ctrl+C

의존성: rclpy(ROS2 Humble). cv2 는 디코드/재인코드에만 사용(창 안 띄움).
"""
import argparse
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import rclpy
from rclpy.node import Node
from sensor_msgs.msg import CompressedImage
import cv2
import numpy as np

TOPIC = '/robocart/image_raw/compressed'

# 최신 JPEG 프레임을 보관(스레드 공유)
_latest_jpeg: bytes | None = None
_lock = threading.Lock()
_frame_count = 0


class CameraSub(Node):
    def __init__(self):
        super().__init__('web_camera_view')
        self.create_subscription(CompressedImage, TOPIC, self.cb, 10)
        self.get_logger().info(f'구독 시작: {TOPIC}')

    def cb(self, msg):
        global _latest_jpeg, _frame_count
        arr = np.frombuffer(bytes(msg.data), np.uint8)
        frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if frame is None:
            return
        _frame_count += 1
        cv2.putText(frame, f'Frame: {_frame_count}', (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
        ok, jpeg = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
        if ok:
            with _lock:
                _latest_jpeg = jpeg.tobytes()


PAGE = """<!doctype html><html><head><meta charset="utf-8">
<title>SmartCart Camera</title>
<style>body{background:#111;color:#eee;font-family:sans-serif;text-align:center}
img{max-width:95vw;border:1px solid #444;margin-top:12px}</style></head>
<body><h2>SmartCart - 라즈베리파이 카메라</h2>
<img src="/stream"><p>토픽: /robocart/image_raw/compressed</p></body></html>""".encode('utf-8')


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):  # 콘솔 로그 억제
        pass

    def do_GET(self):
        if self.path in ('/', '/index.html'):
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.end_headers()
            self.wfile.write(PAGE)
            return

        if self.path == '/stream':
            self.send_response(200)
            self.send_header(
                'Content-Type',
                'multipart/x-mixed-replace; boundary=frame')
            self.end_headers()
            try:
                while True:
                    with _lock:
                        jpeg = _latest_jpeg
                    if jpeg is None:
                        time.sleep(0.05)
                        continue
                    self.wfile.write(b'--frame\r\n')
                    self.wfile.write(b'Content-Type: image/jpeg\r\n')
                    self.wfile.write(
                        f'Content-Length: {len(jpeg)}\r\n\r\n'.encode())
                    self.wfile.write(jpeg)
                    self.wfile.write(b'\r\n')
                    time.sleep(1 / 30)
            except (BrokenPipeError, ConnectionResetError):
                pass
            return

        self.send_error(404)


def main():
    ap = argparse.ArgumentParser(description='ROS2 카메라 → 웹 MJPEG 뷰어')
    ap.add_argument('--port', type=int, default=8080)
    ap.add_argument('--host', default='0.0.0.0',
                    help='0.0.0.0 이면 다른 PC(같은 네트워크)에서도 접속 가능')
    args = ap.parse_args()

    rclpy.init()
    node = CameraSub()
    spin = threading.Thread(target=rclpy.spin, args=(node,), daemon=True)
    spin.start()

    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print('=' * 50)
    print('  SmartCart 웹 카메라 뷰어')
    print(f'  브라우저에서 접속:  http://localhost:{args.port}')
    print('  종료: Ctrl+C')
    print('=' * 50, flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.shutdown()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
