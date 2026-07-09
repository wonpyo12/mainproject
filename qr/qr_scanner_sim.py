import sys
import cv2
import requests
import time
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from socketserver import ThreadingMixIn

# 윈도우 cp949 콘솔에서 한글/특수문자 print 크래시 방지
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')

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
                    # 스트림용은 640폭으로 줄여 인코딩 (대역폭·CPU 절약, 원본 화질은 유지)
                    if img_frame.shape[1] > 640:
                        scale = 640 / img_frame.shape[1]
                        img_frame = cv2.resize(img_frame, (640, int(img_frame.shape[0] * scale)))
                    ret, jpeg = cv2.imencode('.jpg', img_frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
                    if not ret:
                        time.sleep(0.01)
                        continue
                    
                    # MJPEG 프레임 전송 (직접 바이트 출력으로 형식 정합성 준수)
                    self.wfile.write(b'--frame\r\n')
                    self.wfile.write(b'Content-Type: image/jpeg\r\n')
                    self.wfile.write(f'Content-Length: {len(jpeg)}\r\n\r\n'.encode('utf-8'))
                    self.wfile.write(jpeg.tobytes())
                    self.wfile.write(b'\r\n')
                    self.wfile.flush()  # 소켓 버퍼를 즉시 비워 프레임 송출
                    time.sleep(0.05)  # 약 20fps 대역폭 제한
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

def start_camera_server():
    try:
        server = ThreadedHTTPServer(('0.0.0.0', 5000), CamHandler)
        print("[CamServer] 실시간 영상 스트리밍 서버가 포트 5000에서 시작되었습니다.")
        server.serve_forever()
    except Exception as e:
        print(f"[CamServer] 서버 기동 실패: {e}")

# 스트리밍 서버 백그라운드 스레드 기동
threading.Thread(target=start_camera_server, daemon=True).start()


# ===================================================================
# [로봇 QR 스캐너 시뮬레이터]
# 이 스크립트는 로봇의 카메라를 시뮬레이션하여, 웹캠으로 유저 앱의 QR 코드를 스캔하고
# 백엔드 서버로 인증 요청을 전송하여 로봇과 유저를 매칭합니다.
#
# 실행 전에 필수 라이브러리를 설치해 주세요:
#   pip install opencv-python requests
# ===================================================================

# 백엔드 서버 URL 및 로봇 시리얼 넘버 설정
# (모바일 기기와 PC가 동일한 와이파이에 있는 경우 localhost 대신 PC의 사설 IP를 적어주세요. 예: 192.168.0.X)
SERVER_URL = "http://192.168.0.17:3000/api/hardware/qr-scan"
ROBOT_SERIAL = "CartMe-ROS2-08"

# 웹캠 초기화 (0번 기본 카메라)
# CAP_DSHOW: 윈도우 MSMF 백엔드의 초기화 지연·랙 회피 / MJPG + 720p 로 화질·프레임 확보
# 카메라 프로파일: 720p MJPG 우선, 끊기면 640x480 기본 모드로 강등
CAM_PROFILES = [
    {"name": "1280x720 MJPG", "w": 1280, "h": 720, "mjpg": True},
    {"name": "640x480 기본",   "w": 640,  "h": 480, "mjpg": False},
]
cam_profile = 0  # 현재 프로파일 인덱스 (실패 누적 시 다음 프로파일로)


def open_camera():
    p = CAM_PROFILES[cam_profile]
    c = cv2.VideoCapture(0, cv2.CAP_DSHOW)
    if p["mjpg"]:
        c.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'MJPG'))
    c.set(cv2.CAP_PROP_FRAME_WIDTH, p["w"])
    c.set(cv2.CAP_PROP_FRAME_HEIGHT, p["h"])
    c.set(cv2.CAP_PROP_FPS, 30)
    c.set(cv2.CAP_PROP_BUFFERSIZE, 1)   # 오래된 프레임 버퍼링으로 인한 지연 방지
    # 실제 프레임이 나오는지 테스트 (모드는 열리는데 read 가 실패하는 캠이 있음)
    ok = c.isOpened() and c.read()[0]
    if ok:
        print(f"[카메라] {p['name']} → {int(c.get(cv2.CAP_PROP_FRAME_WIDTH))}x{int(c.get(cv2.CAP_PROP_FRAME_HEIGHT))}")
    return c


cap = open_camera()
if not cap.isOpened():
    print("[Error] 카메라를 열 수 없습니다. 웹캠 연결을 확인하세요.")
    exit()

# OpenCV 내장 QR 코드 디텍터 초기화
detector = cv2.QRCodeDetector()

print("==================================================")
print("  로봇 QR 카메라 시뮬레이터가 실행되었습니다.")
print(f"  - 연동 대상 로봇 시리얼: {ROBOT_SERIAL}")
print(f"  - 백엔드 서버 주소: {SERVER_URL}")
print("  앱에서 생성된 QR 코드를 카메라에 비춰주세요.")
print("  종료하려면 카메라 창에서 'q' 키를 누르세요.")
print("==================================================")

# 인증 상태 관리 변수
auth_status = "READY"  # READY, SENDING, SUCCESS, FAILED
status_text = "Scan QR Code on App"
status_color = (255, 255, 0)  # 하늘색/노란색 (BGR)
last_scanned_token = ""
status_timer = 0  # 상태 메시지 표시 타이머
frame_no = 0
state_lock = threading.Lock()


def send_auth(token):
    """백엔드 인증 POST — 영상 루프를 막지 않게 별도 스레드에서 실행"""
    global auth_status, status_text, status_color, status_timer
    try:
        response = requests.post(
            SERVER_URL,
            json={"qrToken": token, "robotSerialNumber": ROBOT_SERIAL},
            timeout=3)
        res_json = response.json()
        with state_lock:
            if response.status_code == 200 and res_json.get("success"):
                print(f"[성공] 인증 완료! 유저 ID: {res_json.get('userId')}와 매칭되었습니다.")
                auth_status = "SUCCESS"
                status_text = f"SUCCESS: Matched with User {res_json.get('userId')}"
                status_color = (0, 255, 0)
            else:
                print(f"[실패] 백엔드 응답 에러: {res_json.get('message')}")
                auth_status = "FAILED"
                status_text = f"FAILED: {res_json.get('message')}"
                status_color = (0, 0, 255)
            status_timer = time.time()
    except requests.exceptions.RequestException as e:
        print(f"[실패] 서버 연결 실패: {e}")
        with state_lock:
            auth_status = "FAILED"
            status_text = "FAILED: Server Connection Error"
            status_color = (0, 0, 255)
            status_timer = time.time()


read_fail = 0
while True:
    ret, frame = cap.read()
    if not ret:
        # 웹캠이 끊겨도 종료하지 않고 재연결 시도. 2회 연속 실패하면 저해상도 모드로 강등.
        read_fail += 1
        if read_fail == 2 and cam_profile < len(CAM_PROFILES) - 1:
            cam_profile += 1
            print(f"[경고] 프레임 끊김 반복 - {CAM_PROFILES[cam_profile]['name']} 모드로 전환")
        else:
            print(f"[경고] 프레임 읽기 실패 ({read_fail}/10) - 카메라 재연결 시도")
        cap.release()
        time.sleep(1.0)
        cap = open_camera()
        if read_fail >= 10:
            print("[Error] 카메라 재연결 실패 - 종료합니다.")
            break
        continue
    read_fail = 0
    frame_no += 1

    # ── 중앙 스캔 영역 (ROI) — 화면 짧은 변의 65% 크기 ──
    h, w, _ = frame.shape
    box_size = int(min(h, w) * 0.65)
    x1 = int((w - box_size) / 2)
    y1 = int((h - box_size) / 2)
    x2 = x1 + box_size
    y2 = y1 + box_size

    # QR 검출은 반전 전 원본에서! (거울상 QR 은 디코딩이 안 됨)
    # 매 3프레임마다 그레이스케일 ROI 에서 검출 — CPU 절약
    data = ""
    if frame_no % 3 == 0 and auth_status == "READY":
        roi = cv2.cvtColor(frame[y1:y2, x1:x2], cv2.COLOR_BGR2GRAY)
        try:
            data, bbox, _ = detector.detectAndDecode(roi)
        except Exception:
            data = ""

    # QR 인식 → 인증 요청은 스레드로 (영상 루프 안 멈춤)
    if data and data != last_scanned_token:
        print(f"\n[QR 감지] 읽어온 데이터: {data}")
        last_scanned_token = data
        with state_lock:
            auth_status = "SENDING"
            status_text = "Sending Auth Request..."
            status_color = (0, 165, 255)
        threading.Thread(target=send_auth, args=(data,), daemon=True).start()

    # 표시용은 좌우 반전 (거울 모드, 시각적으로 편함)
    frame = cv2.flip(frame, 1)

    # ── 중앙 가이드 박스 테두리 (가벼운 흰색 실선 하나만 표시) ──
    cv2.rectangle(frame, (x1, y1), (x2, y2), (255, 255, 255), 2)



    # 4초 동안 성공/실패 메시지를 보여준 뒤 다시 대기 상태로 복원
    with state_lock:
        if auth_status in ["SUCCESS", "FAILED"] and (time.time() - status_timer > 4.0):
            auth_status = "READY"
            status_text = "Scan QR Code on App"
            status_color = (255, 255, 0)
            last_scanned_token = ""  # 새로운 스캔을 허용하기 위해 리셋

    # 화면에 상태 텍스트 출력
    cv2.putText(frame, status_text, (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.7, status_color, 2, cv2.LINE_AA)
    cv2.putText(frame, f"Robot: {ROBOT_SERIAL}", (20, frame.shape[0] - 20), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1, cv2.LINE_AA)

    # 영상 출력 창 표시
    cv2.imshow("Robot QR Camera Scanner Sim", frame)

    # 실시간 공유 프레임 업데이트 (웹 스트리밍용)
    camera_state.frame = frame

    # 'q' 키를 누르면 루프 탈출 및 종료
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

# 리소스 해제
cap.release()
cv2.destroyAllWindows()
print("\n[종료] 카메라 스캐너 시뮬레이터가 종료되었습니다.")
