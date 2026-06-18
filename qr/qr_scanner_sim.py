import cv2
import requests
import time

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
SERVER_URL = "http://localhost:3000/api/hardware/qr-scan"
ROBOT_SERIAL = "CartMe-ROS2-08"

# 웹캠 초기화 (0번 기본 카메라)
cap = cv2.VideoCapture(0)
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

while True:
    ret, frame = cap.read()
    if not ret:
        print("[Error] 프레임을 읽어올 수 없습니다.")
        break

    # 이미지 좌우 반전 (거울 모드, 시각적으로 편함)
    frame = cv2.flip(frame, 1)
    
    # ── 중앙 스캔 영역 (ROI) 설정 ──
    h, w, _ = frame.shape
    box_size = 240  # 240x240 정사각 스캔 영역
    x1 = int((w - box_size) / 2)
    y1 = int((h - box_size) / 2)
    x2 = x1 + box_size
    y2 = y1 + box_size

    # 해당 중앙 영역(ROI)만 크롭하여 QR 코드 스캔용으로 사용
    roi = frame[y1:y2, x1:x2]

    # QR 코드 검출 및 디코딩 (크롭된 영역 내에서만 검출)
    try:
        data, bbox, _ = detector.detectAndDecode(roi)
    except Exception as e:
        data, bbox = "", None

    # QR 코드가 인식되었고 이전에 인식했던 토큰과 다르거나 성공 후 대기 상태인 경우
    if data and data != last_scanned_token:
        print(f"\n[QR 감지] 읽어온 데이터: {data}")
        last_scanned_token = data
        auth_status = "SENDING"
        status_text = "Sending Auth Request..."
        status_color = (0, 165, 255)  # 주황색

        # 백엔드 서버로 POST 요청 전송
        try:
            payload = {
                "qrToken": data,
                "robotSerialNumber": ROBOT_SERIAL
            }
            response = requests.post(SERVER_URL, json=payload, timeout=3)
            res_json = response.json()

            if response.status_code == 200 and res_json.get("success"):
                print(f"[성공] 인증 완료! 유저 ID: {res_json.get('userId')}와 매칭되었습니다.")
                auth_status = "SUCCESS"
                status_text = f"SUCCESS: Matched with User {res_json.get('userId')}"
                status_color = (0, 255, 0)  # 초록색
            else:
                print(f"[실패] 백엔드 응답 에러: {res_json.get('message')}")
                auth_status = "FAILED"
                status_text = f"FAILED: {res_json.get('message')}"
                status_color = (0, 0, 255)  # 빨간색
        except requests.exceptions.RequestException as e:
            print(f"[실패] 서버 연결 실패: {e}")
            auth_status = "FAILED"
            status_text = "FAILED: Server Connection Error"
            status_color = (0, 0, 255)  # 빨간색
            
        status_timer = time.time()  # 타이머 리셋

    # ── 중앙 가이드 박스 테두리 (가벼운 흰색 실선 하나만 표시) ──
    cv2.rectangle(frame, (x1, y1), (x2, y2), (255, 255, 255), 2)



    # 3초 동안 성공/실패 메시지를 보여준 뒤 다시 대기 상태로 복원
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

    # 'q' 키를 누르면 루프 탈출 및 종료
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

# 리소스 해제
cap.release()
cv2.destroyAllWindows()
print("\n[종료] 카메라 스캐너 시뮬레이터가 종료되었습니다.")
