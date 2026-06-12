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
    
    # QR 코드 검출 및 디코딩
    # 거울 모드로 뒤집힌 프레임에서도 OpenCV는 디코딩이 가능합니다.
    try:
        data, bbox, _ = detector.detectAndDecode(frame)
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

    # Bounding Box가 검출되었을 경우 화면에 테두리 그리기
    if bbox is not None and len(bbox) > 0:
        # bbox의 자료형에 맞춰 좌표 파싱
        pts = bbox[0].astype(int)
        for i in range(len(pts)):
            pt1 = tuple(pts[i])
            pt2 = tuple(pts[(i + 1) % len(pts)])
            cv2.line(frame, pt1, pt2, status_color, 3)

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
