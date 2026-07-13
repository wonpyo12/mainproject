import cv2
import sys
import time
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from socketserver import ThreadingMixIn

# 스트리밍을 위한 카메라 프레임 공유 클래스
class CameraState:
    def __init__(self):
        self.frame = None

camera_state = CameraState()

class CamHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/video_feed':
            try:
                self.send_response(200)
                self.send_header('Content-type', 'multipart/x-mixed-replace; boundary=frame')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
            except Exception as e:
                print(f"[CamServer Headers Error] {e}")
                return

            while True:
                img_frame = camera_state.frame
                if img_frame is None:
                    time.sleep(0.03)
                    continue
                try:
                    # JPEG 포맷으로 프레임 압축 (퀄리티를 50으로 낮춰 네트워크 전송 속도 극대화)
                    ret, jpeg = cv2.imencode('.jpg', img_frame, [int(cv2.IMWRITE_JPEG_QUALITY), 50])
                    if not ret:
                        time.sleep(0.01)
                        continue
                    
                    # MJPEG 바이트 전송
                    self.wfile.write(b'--frame\r\n')
                    self.wfile.write(b'Content-Type: image/jpeg\r\n')
                    self.wfile.write(f'Content-Length: {len(jpeg)}\r\n\r\n'.encode('utf-8'))
                    self.wfile.write(jpeg.tobytes())
                    self.wfile.write(b'\r\n')
                    self.wfile.flush()
                    time.sleep(0.07)  # 약 15fps로 대역폭 제한 (무선 네트워크 대역폭 부족에 의한 순간적인 렉 방지)
                except (ConnectionResetError, BrokenPipeError):
                    break
                except Exception as e:
                    print(f"[CamServer Error] {e}")
                    break
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        return

class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True

def start_camera_server(port=5000):
    try:
        server = ThreadedHTTPServer(('0.0.0.0', port), CamHandler)
        print(f"[CamServer] 실시간 영상 스트리밍 서버가 포트 {port}에서 시작되었습니다.")
        server.serve_forever()
    except Exception as e:
        print(f"[CamServer] 서버 기동 실패: {e}")

def main():
    # 스트리밍 서버 백그라운드 스레드 기동
    threading.Thread(target=start_camera_server, daemon=True).start()

    # 카메라 초기화 (0번 기본 카메라 연결)
    cap = cv2.VideoCapture(0)
    
    # 해상도 설정 (모든 카메라가 지원하는 표준 640x480 해상도로 설정)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

    if not cap.isOpened():
        print("[Error] 카메라를 열 수 없습니다. 카메라 연결 상태를 확인해 주세요.")
        sys.exit(1)

    print("==================================================")
    print("  라즈베리파이 카메라 스트리머 기동 완료 (초저지연 모드).")
    print("  서버 접속 경로: http://<라즈베리파이_IP>:5000/video_feed")
    print("  종료하려면 Ctrl+C를 누르세요.")
    print("==================================================")

    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                time.sleep(0.01)
                continue
            
            # 가상 서버가 전송할 최신 프레임 업데이트
            camera_state.frame = frame
            # cap.read() 자체가 카메라 프레임레이트(30fps)에 맞춰 대기하므로 추가 sleep 제거로 지연 최소화
    except KeyboardInterrupt:
        print("\n스트리머 종료 중...")
    finally:
        cap.release()
        print("카메라 연결이 해제되었습니다.")

if __name__ == '__main__':
    main()
