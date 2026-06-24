#!/usr/bin/env python3
import cv2
from ultralytics import YOLO
import numpy as np
import time
import threading
import urllib.request

# ROS2 관련 라이브러리 임포트
import rclpy
from rclpy.node import Node
from geometry_msgs.msg import Twist

class RobotController(Node):
    """
    터틀봇3 속도 명령(/cmd_vel)을 발행하는 ROS2 노드
    """
    def __init__(self):
        super().__init__('person_follower')
        # /cmd_vel 토픽으로 Twist 메시지 퍼블리셔 생성
        self.cmd_vel_pub = self.create_publisher(Twist, 'cmd_vel', 10)
        self.get_logger().info("ROS2 Robot Controller Node Initialized.")

    def send_stop(self):
        """로봇 정지 명령 발행"""
        msg = Twist()
        msg.linear.x = 0.0
        msg.angular.z = 0.0
        self.cmd_vel_pub.publish(msg)
        self.get_logger().info("Sent STOP command to robot.")

    def send_velocity(self, linear, angular):
        """계산된 선속도 및 각속도 명령 발행"""
        msg = Twist()
        msg.linear.x = float(linear)
        msg.angular.z = float(angular)
        self.cmd_vel_pub.publish(msg)
        # self.get_logger().info(f"Publishing -> Lin: {linear:.2f}, Ang: {angular:.2f}")

class VideoCaptureThreaded:
    """
    HTTP MJPEG 스트림을 직접 파싱하여 OpenCV FFMPEG 크래시(Segfault, Abort)를 원천 차단하고
    안전하게 프레임을 읽어오는 재연결 지원 클래스
    """
    def __init__(self, src):
        self.src = src
        self.frame = None
        self.ret = False
        self.running = True
        self.thread = threading.Thread(target=self.update, args=())
        self.thread.daemon = True
        self.thread.start()

    def update(self):
        while self.running:
            stream = None
            try:
                # HTTP 요청 타임아웃 3초 설정으로 무한 대기 방지
                stream = urllib.request.urlopen(self.src, timeout=3.0)
                bytes_buffer = bytes()
                
                # MJPEG 스트림 읽기 루프
                while self.running:
                    chunk = stream.read(8192)  # 버퍼 크기 확장 (더 빠른 처리)
                    if not chunk:
                        break
                    bytes_buffer += chunk
                    
                    # JPEG 이미지의 시작(\xff\xd8)과 끝(\xff\xd9) 지점을 버퍼에서 검색
                    a = bytes_buffer.find(b'\xff\xd8')
                    b = bytes_buffer.find(b'\xff\xd9')
                    
                    if a != -1 and b != -1 and a < b:
                        jpg_data = bytes_buffer[a:b+2]
                        bytes_buffer = bytes_buffer[b+2:]
                        
                        # JPEG 바이너리를 OpenCV 이미지 형식으로 디코딩
                        frame = cv2.imdecode(np.frombuffer(jpg_data, dtype=np.uint8), cv2.IMREAD_COLOR)
                        if frame is not None:
                            self.frame = frame
                            self.ret = True
                            
            except Exception as e:
                # 연결 실패 시 디버그를 위한 미세 프린트 제거 (터미널 스팸 방지)
                self.ret = False
                self.frame = None
            finally:
                if stream is not None:
                    try:
                        stream.close()
                    except:
                        pass
            
            # 재연결 전 1초 대기
            if self.running:
                time.sleep(1.0)

    def read(self):
        return self.ret, self.frame

    def isOpened(self):
        return self.running

    def release(self):
        self.running = False

def get_upper_body_hist(frame, bbox):
    """
    바운딩 박스로부터 상체 영역(상의)을 Crop하여 HSV 2D 히스토그램을 반환하는 함수
    """
    try:
        h, w, _ = frame.shape
        bx1, by1, bx2, by2 = bbox
        
        # 픽셀 좌표로 변환 및 경계 클리핑
        x1 = max(0, int(bx1 * w))
        y1 = max(0, int(by1 * h))
        x2 = min(w - 1, int(bx2 * w))
        y2 = min(h - 1, int(by2 * h))
        
        box_h = y2 - y1
        if box_h <= 0 or (x2 - x1) <= 0:
            return None
            
        # 상의 영역 계산: 바운딩 박스의 위쪽 15% ~ 50% 지점
        upper_y1 = y1 + int(box_h * 0.15)
        upper_y2 = y1 + int(box_h * 0.50)
        
        # 상의 픽셀 추출
        upper_body_crop = frame[upper_y1:upper_y2, x1:x2]
        if upper_body_crop.size == 0:
            return None
            
        # HSV 변환 (조명 변화 방어)
        hsv = cv2.cvtColor(upper_body_crop, cv2.COLOR_BGR2HSV)
        
        # Hue(색상)와 Saturation(채도) 채널의 2D 히스토그램 계산
        # H bins=32, S bins=32로 설정하여 노이즈 방지
        hist = cv2.calcHist([hsv], [0, 1], None, [32, 32], [0, 180, 0, 256])
        cv2.normalize(hist, hist, 0, 1, cv2.NORM_MINMAX)
        return hist
    except Exception as e:
        return None

def ros_spin_thread(node):
    """ROS2 콜백 처리를 위한 스핀 스레드"""
    rclpy.spin(node)

def main():
    # ── ROS2 초기화 ──
    rclpy.init()
    node = RobotController()
    
    # ROS2 스레드 실행 (OpenCV GUI 루프와 병렬 구동)
    spin_thread = threading.Thread(target=ros_spin_thread, args=(node,), daemon=True)
    spin_thread.start()

    # ── 카메라 소스 설정 ──
    # 라즈베리파이 4 IP 주소 (실제 세팅에 맞춰 수정 가능)
    PI_IP = "192.168.0.2" 
    stream_url = f"http://{PI_IP}:5000/video_feed"
    
    print(f"[연동] 카메라 스트림 연결 중: {stream_url}")
    # 버퍼 지연을 방지하기 위해 쓰레드 기반 비디오 캡처 사용
    cap = VideoCaptureThreaded(stream_url)
    # 초기 프레임 확인을 위해 잠시 대기
    time.sleep(0.5)
    ret, frame = cap.read()
    if not ret:
        print(f"[Error] 비디오 피드({stream_url})에 연결할 수 없습니다.")
        print("라즈베리파이의 'pi_camera_streamer.py'가 실행 중인지 확인하세요.")
        cap.release()
        node.destroy_node()
        rclpy.shutdown()
        return

    print("==================================================")
    print("  [사람 인식 및 터틀봇 3 실전 추종 구동 모드]")
    print("  - 코(Nose)를 배제하고 어깨~골반 거리로 인식하여 뒤돌아도 트래킹 유지")
    print("  - 가상 테스트가 아닌 실제 /cmd_vel 토픽을 발행하여 로봇을 움직입니다.")
    print("  - 종료하려면 카메라 창에서 'q' 키를 누르세요. (종료 시 자동 정지)")
    print("==================================================")

    # 제어 계산용 기준 상수
    TARGET_HEIGHT_RATIO = 0.52  # 어깨~골반 목표 세로 비율 (약 80cm 안팎의 쾌적하고 안정적인 추종 거리 유지)
    
    # 이전 검출 좌표 저장용 캐시
    last_person_cx = None
    last_person_cy = None
    last_body_height_ratio = None
    person_detected = False
    
    # OpenCV 연산 속도 측정 객체
    tm = cv2.TickMeter()
    inference_time_ms = 0.0
    prev_time = time.time()

    # ── 공유 데이터 정의 (스레드 간 동기화용) ──
    latest_frame = None
    new_frame_ready = False
    frame_lock = threading.Lock()
    
    # YOLO 검출 결과를 저장할 공유 변수들
    shared_person_detected = False
    shared_last_person_cx = None
    shared_last_person_cy = None
    shared_last_body_height_ratio = None
    shared_last_pose_landmarks = None  # 어노테이션된 이미지를 저장
    shared_inference_time_ms = 0.0
    
    # YOLOv8-Pose 실행을 위한 백그라운드 스레드 함수
    def yolo_inference_thread():
        nonlocal latest_frame, new_frame_ready, shared_person_detected, shared_last_person_cx, shared_last_person_cy
        nonlocal shared_last_body_height_ratio, shared_last_pose_landmarks, shared_inference_time_ms
        
        # YOLOv8 Nano Pose 모델 로드
        model = YOLO('yolov8n-pose.pt')
        tm_local = cv2.TickMeter()
        
        # Centroid + Color Hybrid Tracking 변수
        tracked_cx = None
        tracked_cy = None
        tracked_color_hist = None
        yolo_lost_count = 0
        
        while rclpy.ok() and cap.isOpened():
            # 1. 처리할 프레임 복사 (새 프레임이 왔을 때만 수행)
            img_to_process = None
            with frame_lock:
                if new_frame_ready and latest_frame is not None:
                    img_to_process = latest_frame.copy()
                    new_frame_ready = False
            
            if img_to_process is not None:
                try:
                    tm_local.reset()
                    tm_local.start()
                    results = model(img_to_process, conf=0.15, verbose=False)
                    tm_local.stop()
                    
                    detected = False
                    final_cx, final_cy = None, None
                    final_body_height = None
                    final_annotated = None
                    
                    # 감지된 유효한 사람들의 리스트를 수집
                    valid_candidates = []
                    
                    if results and len(results) > 0:
                        r = results[0]
                        # 검출된 객체(바운딩 박스)가 존재하는 경우
                        if r.boxes is not None and len(r.boxes.xyxyn) > 0:
                            for idx, bbox_tensor in enumerate(r.boxes.xyxyn):
                                bbox = bbox_tensor.cpu().numpy()
                                bx1, by1, bx2, by2 = bbox
                                
                                # 기본 바운딩 박스 기준 중심 좌표 설정 (추적 탈락 방지)
                                cx = float((bx1 + bx2) / 2.0)
                                cy = float((by1 + by2) / 2.0)
                                
                                # 기본 높이는 바운딩 박스 높이의 35%로 설정 (골반 미검출 대비 백업)
                                bbox_height = by2 - by1
                                body_height = float(bbox_height * 0.35)
                                keypoints = None
                                
                                # 포즈 키포인트가 유효한지 확인
                                if r.keypoints is not None and len(r.keypoints.xyn) > idx:
                                    xyn_data = r.keypoints.xyn[idx]
                                    if hasattr(xyn_data, 'cpu'):
                                        keypoints = xyn_data.cpu().numpy()
                                    elif hasattr(xyn_data, 'numpy'):
                                        keypoints = xyn_data.numpy()
                                    else:
                                        keypoints = xyn_data
                                    
                                    # 키포인트 개수 검증
                                    if keypoints is not None and len(keypoints) > 12:
                                        l_shoulder = keypoints[5]
                                        r_shoulder = keypoints[6]
                                        l_hip = keypoints[11]
                                        r_hip = keypoints[12]
                                        
                                        # 어깨가 둘 다 정상적으로 감지된 경우 중심 좌표를 어깨 기준 좌표로 더 정밀하게 세팅
                                        if not (l_shoulder[0] == 0.0 and l_shoulder[1] == 0.0) and \
                                           not (r_shoulder[0] == 0.0 and r_shoulder[1] == 0.0):
                                            cx = float((l_shoulder[0] + r_shoulder[0]) / 2.0)
                                            cy = float((l_shoulder[1] + r_shoulder[1]) / 2.0)
                                            
                                            # 골반까지 검출된 경우 더 정확한 골반-어깨 세로 비율 사용
                                            if not (l_hip[0] == 0.0 and l_hip[1] == 0.0) and \
                                               not (r_hip[0] == 0.0 and r_hip[1] == 0.0):
                                                shoulder_y = (l_shoulder[1] + r_shoulder[1]) / 2.0
                                                hip_y = (l_hip[1] + r_hip[1]) / 2.0
                                                body_height = float(hip_y - shoulder_y)
                                                
                                valid_candidates.append({
                                    'cx': cx,
                                    'cy': cy,
                                    'body_height': body_height,
                                    'annotated': (keypoints, bbox)
                                })
                    
                    # 수집된 후보군 중 타겟 매칭 (Color + Centroid Hybrid Tracking)
                    if len(valid_candidates) > 0:
                        target_candidate = None
                        
                        # 각 후보들의 상체 색상 히스토그램 연산
                        for cand in valid_candidates:
                            if cand['annotated'][1] is not None:
                                cand['hist'] = get_upper_body_hist(img_to_process, cand['annotated'][1])
                            else:
                                cand['hist'] = None
                        
                        if tracked_cx is None or tracked_color_hist is None:
                            # 1) 최초 감지 시: 화면 가로 중앙(0.5)에 가장 가깝고 색상이 추출된 사람 선택
                            best_idx = -1
                            min_dist_to_center = 999.0
                            for idx, cand in enumerate(valid_candidates):
                                dist = abs(cand['cx'] - 0.5)
                                if dist < min_dist_to_center:
                                    min_dist_to_center = dist
                                    best_idx = idx
                            if best_idx != -1:
                                target_candidate = valid_candidates[best_idx]
                                if target_candidate['hist'] is not None:
                                    tracked_color_hist = target_candidate['hist']
                        else:
                            # 2) 추적 중일 때: [거리 점수(60%) + 색상 유사도(40%)] 하이브리드 스코어링 매칭
                            best_idx = -1
                            max_score = -999.0
                            for idx, cand in enumerate(valid_candidates):
                                # 거리 점수 (가까울수록 1.0에 근접)
                                dist = np.sqrt((cand['cx'] - tracked_cx)**2 + (cand['cy'] - tracked_cy)**2)
                                score_dist = max(0.0, 1.0 - dist)
                                
                                # 색상 점수 (Correlation 유사도, 범위 0.0 ~ 1.0)
                                score_color = 0.5  # 비교 불가 시 중간 점수 부여
                                if cand['hist'] is not None and tracked_color_hist is not None:
                                    sim_color = cv2.compareHist(cand['hist'], tracked_color_hist, cv2.HISTCMP_CORREL)
                                    score_color = max(0.0, sim_color)
                                
                                # 하이브리드 점수 합산
                                hybrid_score = 0.6 * score_dist + 0.4 * score_color
                                
                                if hybrid_score > max_score:
                                    max_score = hybrid_score
                                    best_idx = idx
                            
                            # 점수가 임계 오차(0.40)를 넘는 최선 후보 매칭
                            if best_idx != -1 and max_score > 0.40:
                                target_candidate = valid_candidates[best_idx]
                                # 조명 변화에 부드럽게 대처하기 위해 누적 색상 학습 적용 (이전 80%, 신규 20%)
                                if target_candidate['hist'] is not None:
                                    tracked_color_hist = 0.8 * tracked_color_hist + 0.2 * target_candidate['hist']
                                    cv2.normalize(tracked_color_hist, tracked_color_hist, 0, 1, cv2.NORM_MINMAX)
                        
                        # 최종 매칭 성공 시 좌표 및 상태 업데이트
                        if target_candidate is not None:
                            detected = True
                            final_cx = target_candidate['cx']
                            final_cy = target_candidate['cy']
                            final_body_height = target_candidate['body_height']
                            final_annotated = target_candidate['annotated']
                            
                            tracked_cx = final_cx
                            tracked_cy = final_cy
                            yolo_lost_count = 0
                    
                    # 감지 실패 시 처리
                    if not detected:
                        yolo_lost_count += 1
                        # 30프레임 이상 연속 감지 실패 시 추적 대상 및 색상 정보 리셋 (다시 첫 사람 잡도록 함)
                        if yolo_lost_count >= 30:
                            tracked_cx = None
                            tracked_cy = None
                            tracked_color_hist = None
                    
                    # 공유 데이터 업데이트
                    with frame_lock:
                        shared_person_detected = detected
                        shared_last_person_cx = final_cx
                        shared_last_person_cy = final_cy
                        shared_last_body_height_ratio = final_body_height
                        shared_last_pose_landmarks = final_annotated
                        shared_inference_time_ms = tm_local.getTimeMilli()
                        
                except Exception as e:
                    print(f"[YOLO 스레드 루프 에러] {e}")
            
            # CPU 과부하 방지용 미세 대기
            time.sleep(0.02)

    # ── 백그라운드 스레드 시작 ──
    inference_thread = threading.Thread(target=yolo_inference_thread, daemon=True)
    inference_thread.start()

    # ── 디바운싱(인식 흔들림 방지) 및 제어 필터 변수 ──
    lost_frame_count = 0
    cached_cx = None
    cached_cy = None
    cached_body_height_ratio = None
    prev_virtual_angular = 0.0

    try:
        while cap.isOpened() and rclpy.ok():
            ret, frame = cap.read()
            if not ret:
                print("[Warning] 프레임을 읽어올 수 없습니다. 정지 명령을 보내고 대기합니다.")
                node.send_stop()
                time.sleep(0.5)
                continue

            # 백그라운드 스레드에 최신 프레임 제공
            with frame_lock:
                latest_frame = frame
                new_frame_ready = True
            
            h_img, w_img, _ = frame.shape

            # FPS 계산 (메인 스레드 화면 재생률)
            current_time = time.time()
            time_diff = current_time - prev_time
            fps = 1.0 / time_diff if time_diff > 0 else 0.0
            prev_time = current_time

            # ── 공유 변수 복사 (동기화) ──
            with frame_lock:
                person_detected = shared_person_detected
                last_person_cx = shared_last_person_cx
                last_person_cy = shared_last_person_cy
                last_body_height_ratio = shared_last_body_height_ratio
                annotated_frame = shared_last_pose_landmarks
                inference_time_ms = shared_inference_time_ms

            # 디바운스 필터링 적용 (일시적으로 인식을 유실해도 뚝뚝 끊기지 않게 유지)
            if person_detected and last_person_cx is not None and last_person_cy is not None and last_body_height_ratio is not None:
                lost_frame_count = 0
                cached_cx = last_person_cx
                cached_cy = last_person_cy
                cached_body_height_ratio = last_body_height_ratio
            else:
                lost_frame_count += 1
                # 만약 일시적인 인식 유실(15프레임 미만, 약 1.0초)이면 이전 데이터를 재사용하여 회전/전진 유지
                if lost_frame_count < 15 and cached_cx is not None and cached_cy is not None and cached_body_height_ratio is not None:
                    person_detected = True
                    last_person_cx = cached_cx
                    last_person_cy = cached_cy
                    last_body_height_ratio = cached_body_height_ratio

            # 디스플레이용 프레임 설정 (지연을 완전히 차단하기 위해 항상 생생한 최신 라이브 프레임 복제)
            display_frame = frame.copy()

            # ── 제어 및 속도 명령 발행 ──
            if person_detected and last_person_cx is not None and last_person_cy is not None and last_body_height_ratio is not None:
                angular_error = 0.5 - last_person_cx  # 사람이 있는 쪽으로 회전하도록 오차 계산 방향 설정
                linear_error = TARGET_HEIGHT_RATIO - last_body_height_ratio
                
                # 실전 주행을 위한 속도 제한 및 비례 제어 (P-Control)
                raw_linear = linear_error * 1.0
                virtual_linear = max(-0.08, min(0.15, raw_linear)) 
                
                # 회전 비례 게인(P-gain)을 2.5에서 1.2로 완화 및 최대 각속도를 0.3 rad/s로 제한
                raw_angular = angular_error * 1.2
                virtual_angular_target = max(-0.3, min(0.3, raw_angular))
                
                # 불감대 (Deadzone) 적용
                if abs(linear_error) < 0.03:
                    virtual_linear = 0.0
                if abs(angular_error) < 0.04:
                    virtual_angular_target = 0.0

                # 각속도 저역통과필터 (Low Pass Filter) 스무딩 적용
                # 새 각속도 가중치 40%, 이전 각속도 가중치 60%로 혼합하여 급가속/급감속 차단
                virtual_angular = 0.4 * virtual_angular_target + 0.6 * prev_virtual_angular
                prev_virtual_angular = virtual_angular

                # 뚝뚝 끊기는 회전 정렬 조건 완화 (부드러운 선회 비행 유도)
                # 각도 오차가 클수록 전진 속도를 부드럽게 감속시키되, 완전히 멈추지는 않음 (최소 30% 선속도 유지)
                scale_factor = max(0.3, 1.0 - abs(angular_error) * 1.5)
                virtual_linear *= scale_factor

                # 실제 로봇에 속도 전달!
                node.send_velocity(virtual_linear, virtual_angular)
                
                # 디버그 정보 화면 드로잉
                cv2.putText(display_frame, f"Person Center X: {last_person_cx:.2f}", (20, 80),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 0), 2)
                cv2.putText(display_frame, f"Ang Error: {angular_error:.2f} (Speed: {virtual_angular:.2f})", (20, 110),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)
                cv2.putText(display_frame, f"Body Height (S-H): {last_body_height_ratio:.2f}", (20, 140),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 0), 2)
                cv2.putText(display_frame, f"Lin Error: {linear_error:.2f} (Speed: {virtual_linear:.2f})", (20, 170),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)
                
                # 이미지에 사람의 어깨 중심 표시 (초록색 원)
                cv2.circle(display_frame, (int(last_person_cx * w_img), int(last_person_cy * h_img)), 8, (0, 255, 0), -1)

                # 사용자 정의 바운딩 박스 및 골격 선그리기 (렉 없이 OpenCV로 고속 드로잉)
                if annotated_frame is not None:
                    keypoints, bbox = annotated_frame
                    
                    # 1. 욜로 바운딩 박스 그리기
                    if bbox is not None:
                        bx1, by1, bx2, by2 = bbox
                        cv2.rectangle(display_frame, 
                                      (int(bx1 * w_img), int(by1 * h_img)), 
                                      (int(bx2 * w_img), int(by2 * h_img)), 
                                      (0, 255, 0), 2)
                        cv2.putText(display_frame, "Person", 
                                    (int(bx1 * w_img), int(by1 * h_img) - 10),
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)

                    # 2. 골격 (어깨, 골반) 관절 포인트 그리기 및 연결선 그리기
                    if keypoints is not None and len(keypoints) > 12:
                        pt_l_shoulder = (int(keypoints[5][0] * w_img), int(keypoints[5][1] * h_img))
                        pt_r_shoulder = (int(keypoints[6][0] * w_img), int(keypoints[6][1] * h_img))
                        pt_l_hip = (int(keypoints[11][0] * w_img), int(keypoints[11][1] * h_img))
                        pt_r_hip = (int(keypoints[12][0] * w_img), int(keypoints[12][1] * h_img))

                        # 어깨선, 골반선
                        cv2.line(display_frame, pt_l_shoulder, pt_r_shoulder, (255, 0, 0), 2)
                        cv2.line(display_frame, pt_l_hip, pt_r_hip, (255, 0, 0), 2)
                        # 몸통 양 옆선 (어깨-골반)
                        cv2.line(display_frame, pt_l_shoulder, pt_l_hip, (255, 0, 0), 2)
                        cv2.line(display_frame, pt_r_shoulder, pt_r_hip, (255, 0, 0), 2)

                        # 관절 점 표시
                        for pt in [pt_l_shoulder, pt_r_shoulder, pt_l_hip, pt_r_hip]:
                            cv2.circle(display_frame, pt, 5, (0, 0, 255), -1)
            else:
                prev_virtual_angular = 0.0
                node.send_stop()

            # 상태 표시 및 연산 속도 표시
            if person_detected:
                cv2.putText(display_frame, "STATUS: TRACKING ACTIVE", (20, 40),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
            else:
                cv2.putText(display_frame, "STATUS: STOP & SEARCHING", (20, 40),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)

            # 실시간 FPS 및 측정된 Inference Time 화면에 표시
            cv2.putText(display_frame, f"FPS: {fps:.1f}", (w_img - 110, 40),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
            cv2.putText(display_frame, f"Inference: {inference_time_ms:.1f} ms", (w_img - 220, h_img - 20),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.55, (100, 255, 100), 2)

            # 디스플레이 출력
            cv2.imshow('Turtlebot 3 Real-time Human Follower', display_frame)
            
            # 'q' 키 입력 시 종료
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break
    except KeyboardInterrupt:
        print("\n키보드 인터럽트로 종료합니다.")
    except Exception as e:
        print(f"\n[메인 루프 치명적 에러 발생] {e}")
        import traceback
        traceback.print_exc()
    finally:
        # ── 안전을 위한 리소스 정리 및 정지 ──
        node.send_stop()
        cap.release()
        cv2.destroyAllWindows()
        node.destroy_node()
        rclpy.shutdown()
        print("사람 추종 제어가 안전하게 종료되었습니다.")

if __name__ == '__main__':
    main()
