#!/usr/bin/env python3
import cv2
from ultralytics import YOLO
import numpy as np
import time
import threading
import urllib.request
import os
import math

# ROS2 관련 라이브러리 임포트
import rclpy
from rclpy.node import Node
from rclpy.action import ActionClient
from geometry_msgs.msg import Twist, PoseWithCovarianceStamped
from nav2_msgs.action import NavigateToPose

class RobotController(Node):
    """
    터틀봇3 속도 명령(/cmd_vel) 및 Nav2 네비게이션을 수행하는 ROS2 노드
    """
    def __init__(self):
        super().__init__('person_follower_nav2')
        # /cmd_vel 토픽으로 Twist 메시지 퍼블리셔 생성
        self.cmd_vel_pub = self.create_publisher(Twist, 'cmd_vel', 10)
        
        # Nav2 NavigateToPose 액션 클라이언트 생성
        self.nav_to_pose_client = ActionClient(self, NavigateToPose, 'navigate_to_pose')
        
        # AMCL 포즈 구독자 생성 (시작 위치 자동 저장용)
        self.amcl_pose_sub = self.create_subscription(
            PoseWithCovarianceStamped,
            'amcl_pose',
            self.amcl_pose_callback,
            10
        )
        
        # 시작 위치 저장 변수 (기본값은 0, 0, 0)
        self.start_x = 0.0
        self.start_y = 0.0
        self.start_yaw = 0.0
        self.has_start_pose = False
        
        # 상태 변수: FOLLOW (추종), RETURN (복귀)
        self.state = "FOLLOW"
        self.nav_goal_sent = False
        
        self.get_logger().info("ROS2 Robot Controller Node Initialized (Nav2 Support).")

    def amcl_pose_callback(self, msg):
        """AMCL로부터 현재 로봇 위치를 받아 최초 위치를 시작 위치로 자동 저장"""
        if not self.has_start_pose:
            self.start_x = msg.pose.pose.position.x
            self.start_y = msg.pose.pose.position.y
            
            # 쿼터니언을 Yaw(각도)로 변환
            q = msg.pose.pose.orientation
            siny_cosp = 2.0 * (q.w * q.z + q.x * q.y)
            cosy_cosp = 1.0 - 2.0 * (q.y * q.y + q.z * q.z)
            self.start_yaw = math.atan2(siny_cosp, cosy_cosp)
            
            self.has_start_pose = True
            self.get_logger().info(
                f"★★ 시작 위치 자동 저장 완료! (AMCL 수신) -> x={self.start_x:.2f}, y={self.start_y:.2f}, yaw={self.start_yaw:.2f} ★★"
            )

    def send_stop(self):
        """로봇 정지 명령 발행"""
        msg = Twist()
        msg.linear.x = 0.0
        msg.angular.z = 0.0
        self.cmd_vel_pub.publish(msg)
        self.get_logger().info("Sent STOP command to robot.")

    def send_velocity(self, linear, angular):
        """계산된 선속도 및 각속도 명령 발행 (FOLLOW 모드일 때만 동작)"""
        if self.state == "FOLLOW":
            msg = Twist()
            msg.linear.x = float(linear)
            msg.angular.z = float(angular)
            self.cmd_vel_pub.publish(msg)
            sub_count = self.cmd_vel_pub.get_subscription_count()
            # self.get_logger().info(f"Publishing -> Lin: {linear:.2f}, Ang: {angular:.2f} (Subs: {sub_count})")

    def send_nav_goal(self, x, y, yaw):
        """Nav2 복귀 목표 좌표 전송"""
        if self.nav_goal_sent:
            return
            
        self.get_logger().info(f"Sending Nav2 goal to starting position (x={x:.2f}, y={y:.2f})")
        self.nav_to_pose_client.wait_for_server()
        
        goal_msg = NavigateToPose.Goal()
        goal_msg.pose.header.frame_id = 'map'
        goal_msg.pose.header.stamp = self.get_clock().now().to_msg()
        
        # Position 설정
        goal_msg.pose.pose.position.x = float(x)
        goal_msg.pose.pose.position.y = float(y)
        goal_msg.pose.pose.position.z = 0.0
        
        # Orientation 설정 (yaw -> quaternion)
        q_z = math.sin(yaw / 2.0)
        q_w = math.cos(yaw / 2.0)
        goal_msg.pose.pose.orientation.x = 0.0
        goal_msg.pose.pose.orientation.y = 0.0
        goal_msg.pose.pose.orientation.z = q_z
        goal_msg.pose.pose.orientation.w = q_w
        
        self.nav_goal_sent = True
        self._send_goal_future = self.nav_to_pose_client.send_goal_async(
            goal_msg, 
            feedback_callback=self.nav_feedback_callback
        )
        self._send_goal_future.add_done_callback(self.nav_goal_response_callback)
        
    def nav_feedback_callback(self, feedback_msg):
        # 복귀 진행 도중 남은 거리 피드백을 디버깅용으로 수신할 수 있습니다.
        # dist = feedback_msg.feedback.distance_remaining
        # self.get_logger().info(f"Distance remaining: {dist:.2f} m")
        pass
        
    def nav_goal_response_callback(self, future):
        goal_handle = future.result()
        if not goal_handle.accepted:
            self.get_logger().info('Goal rejected by Nav2 server. Staying IDLE.')
            self.nav_goal_sent = False
            self.state = "IDLE"
            return
            
        self.get_logger().info('Goal accepted by Nav2 server. Navigating...')
        self._get_result_future = goal_handle.get_result_async()
        self._get_result_future.add_done_callback(self.nav_get_result_callback)
        
    def nav_get_result_callback(self, future):
        status = future.result().status
        self.get_logger().info(f'Navigation finished with status code: {status}. Staying at base (IDLE).')
        self.nav_goal_sent = False
        self.state = "IDLE"
        self.send_stop()  # 안전하게 모터 속도 0으로 최종 정지 명령 발행


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
        hist = cv2.calcHist([hsv], [0, 1], None, [32, 32], [0, 180, 0, 256])
        cv2.normalize(hist, hist, 0, 1, cv2.NORM_MINMAX)
        return hist
    except Exception as e:
        return None


def ros_spin_thread(node):
    """ROS2 콜백 처리를 위한 스핀 스레드"""
    rclpy.spin(node)


def console_input_thread(node):
    """터미널 사용자 입력을 감시하여 모드를 제어하는 스레드"""
    print("\n" + "="*50)
    print("  [터미널 제어 명령어 목록]")
    print("  - '복귀' 입력 시: 제자리를 찾아 최초 시작한 위치(AMCL 기록값)로 복귀합니다.")
    print("  - '추종' 입력 시: 다시 사람을 추종(FOLLOW) 모드로 전환합니다.")
    print("="*50 + "\n")
    
    while rclpy.ok():
        try:
            cmd = input().strip()
            if cmd == "복귀":
                if node.state != "RETURN":
                    node.state = "RETURN"
                    node.send_stop()  # 즉시 카메라 추종 속도를 멈춤
                    if not node.has_start_pose:
                        node.get_logger().warn("AMCL 시작 위치가 아직 저장되지 않았습니다! 기본값 (0.0, 0.0)으로 복귀를 시도합니다.")
                    node.send_nav_goal(node.start_x, node.start_y, node.start_yaw) # 저장된 시작 위치로 복귀 목표 전송
            elif cmd == "추종":
                if node.state != "FOLLOW":
                    node.get_logger().info("추종 모드로 수동 복귀합니다.")
                    node.state = "FOLLOW"
                    node.nav_goal_sent = False
        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f"[입력 에러] {e}")


def main():
    # ── ROS2 초기화 ──
    rclpy.init()
    node = RobotController()
    
    # ROS2 스레드 실행
    spin_thread = threading.Thread(target=ros_spin_thread, args=(node,), daemon=True)
    spin_thread.start()

    # 터미널 명령어 감시 스레드 실행
    input_thread = threading.Thread(target=console_input_thread, args=(node,), daemon=True)
    input_thread.start()

    # ── 카메라 소스 설정 ──
    PI_IP = "192.168.0.23" 
    stream_url = f"http://{PI_IP}:5000/video_feed"
    
    print(f"[연동] 카메라 스트림 연결 중: {stream_url}")
    cap = VideoCaptureThreaded(stream_url)
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
    print("  [사람 인식 및 터틀봇 3 하이브리드 제어 노드 (SLAM/Nav2 연동)]")
    print("  - '복귀' 키워드로 자율 원점 복귀 가동")
    print("  - 종료하려면 카메라 창에서 'q' 키를 누르세요.")
    print("==================================================")

    # 제어 계산용 기준 상수
    TARGET_HEIGHT_RATIO = 0.52
    
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
    shared_last_pose_landmarks = None
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
            
            # FOLLOW 모드일 때만 욜로 연산 수행 (자원 절약 및 중복 동작 방지)
            if img_to_process is not None and node.state == "FOLLOW":
                try:
                    tm_local.reset()
                    tm_local.start()
                    results = model(img_to_process, conf=0.15, verbose=False)
                    tm_local.stop()
                    
                    detected = False
                    final_cx, final_cy = None, None
                    final_body_height = None
                    final_annotated = None
                    
                    valid_candidates = []
                    
                    if results and len(results) > 0:
                        r = results[0]
                        if r.boxes is not None and len(r.boxes.xyxyn) > 0:
                            for idx, bbox_tensor in enumerate(r.boxes.xyxyn):
                                bbox = bbox_tensor.cpu().numpy()
                                bx1, by1, bx2, by2 = bbox
                                
                                cx = float((bx1 + bx2) / 2.0)
                                cy = float((by1 + by2) / 2.0)
                                
                                bbox_height = by2 - by1
                                body_height = float(bbox_height * 0.35)
                                keypoints = None
                                
                                if r.keypoints is not None and len(r.keypoints.xyn) > idx:
                                    xyn_data = r.keypoints.xyn[idx]
                                    if hasattr(xyn_data, 'cpu'):
                                        keypoints = xyn_data.cpu().numpy()
                                    elif hasattr(xyn_data, 'numpy'):
                                        keypoints = xyn_data.numpy()
                                    else:
                                        keypoints = xyn_data
                                    
                                    if keypoints is not None and len(keypoints) > 12:
                                        l_shoulder = keypoints[5]
                                        r_shoulder = keypoints[6]
                                        l_hip = keypoints[11]
                                        r_hip = keypoints[12]
                                        
                                        if not (l_shoulder[0] == 0.0 and l_shoulder[1] == 0.0) and \
                                           not (r_shoulder[0] == 0.0 and r_shoulder[1] == 0.0):
                                            cx = float((l_shoulder[0] + r_shoulder[0]) / 2.0)
                                            cy = float((l_shoulder[1] + r_shoulder[1]) / 2.0)
                                            
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
                    
                    if len(valid_candidates) > 0:
                        target_candidate = None
                        
                        for cand in valid_candidates:
                            if cand['annotated'][1] is not None:
                                cand['hist'] = get_upper_body_hist(img_to_process, cand['annotated'][1])
                            else:
                                cand['hist'] = None
                        
                        if tracked_cx is None or tracked_color_hist is None:
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
                            best_idx = -1
                            max_score = -999.0
                            for idx, cand in enumerate(valid_candidates):
                                dist = np.sqrt((cand['cx'] - tracked_cx)**2 + (cand['cy'] - tracked_cy)**2)
                                score_dist = max(0.0, 1.0 - dist)
                                
                                score_color = 0.5
                                if cand['hist'] is not None and tracked_color_hist is not None:
                                    sim_color = cv2.compareHist(cand['hist'], tracked_color_hist, cv2.HISTCMP_CORREL)
                                    score_color = max(0.0, sim_color)
                                
                                hybrid_score = 0.6 * score_dist + 0.4 * score_color
                                
                                if hybrid_score > max_score:
                                    max_score = hybrid_score
                                    best_idx = idx
                            
                            if best_idx != -1 and max_score > 0.40:
                                target_candidate = valid_candidates[best_idx]
                                if target_candidate['hist'] is not None:
                                    tracked_color_hist = 0.8 * tracked_color_hist + 0.2 * target_candidate['hist']
                                    cv2.normalize(tracked_color_hist, tracked_color_hist, 0, 1, cv2.NORM_MINMAX)
                        
                        if target_candidate is not None:
                            detected = True
                            final_cx = target_candidate['cx']
                            final_cy = target_candidate['cy']
                            final_body_height = target_candidate['body_height']
                            final_annotated = target_candidate['annotated']
                            
                            tracked_cx = final_cx
                            tracked_cy = final_cy
                            yolo_lost_count = 0
                    
                    if not detected:
                        yolo_lost_count += 1
                        if yolo_lost_count >= 30:
                            tracked_cx = None
                            tracked_cy = None
                            tracked_color_hist = None
                    
                    with frame_lock:
                        shared_person_detected = detected
                        shared_last_person_cx = final_cx
                        shared_last_person_cy = final_cy
                        shared_last_body_height_ratio = final_body_height
                        shared_last_pose_landmarks = final_annotated
                        shared_inference_time_ms = tm_local.getTimeMilli()
                        
                except Exception as e:
                    print(f"[YOLO 스레드 에러] {e}")
            else:
                # RETURN 모드이거나 프레임이 대기상태가 아니면 대기
                time.sleep(0.03)

    # ── 백그라운드 스레드 시작 ──
    inference_thread = threading.Thread(target=yolo_inference_thread, daemon=True)
    inference_thread.start()

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

            with frame_lock:
                latest_frame = frame
                new_frame_ready = True
            
            h_img, w_img, _ = frame.shape

            current_time = time.time()
            time_diff = current_time - prev_time
            fps = 1.0 / time_diff if time_diff > 0 else 0.0
            prev_time = current_time

            display_frame = frame.copy()

            if node.state == "FOLLOW":
                # ── [FOLLOW 모드] 실시간 카메라 기반 제어 및 발행 ──
                with frame_lock:
                    person_detected = shared_person_detected
                    last_person_cx = shared_last_person_cx
                    last_person_cy = shared_last_person_cy
                    last_body_height_ratio = shared_last_body_height_ratio
                    annotated_frame = shared_last_pose_landmarks
                    inference_time_ms = shared_inference_time_ms

                if person_detected and last_person_cx is not None and last_person_cy is not None and last_body_height_ratio is not None:
                    lost_frame_count = 0
                    cached_cx = last_person_cx
                    cached_cy = last_person_cy
                    cached_body_height_ratio = last_body_height_ratio
                else:
                    lost_frame_count += 1
                    if lost_frame_count < 15 and cached_cx is not None and cached_cy is not None and cached_body_height_ratio is not None:
                        person_detected = True
                        last_person_cx = cached_cx
                        last_person_cy = cached_cy
                        last_body_height_ratio = cached_body_height_ratio
                    else:
                        person_detected = False

                if person_detected and last_person_cx is not None and last_person_cy is not None and last_body_height_ratio is not None:
                    angular_error = 0.5 - last_person_cx
                    linear_error = TARGET_HEIGHT_RATIO - last_body_height_ratio
                    
                    # 속도를 낮추고 게인값을 줄여 바퀴 슬립과 급회전을 방지합니다.
                    raw_linear = linear_error * 0.6
                    virtual_linear = max(-0.05, min(0.08, raw_linear)) 
                    
                    raw_angular = angular_error * 0.8
                    virtual_angular_target = max(-0.2, min(0.2, raw_angular))
                    
                    if abs(linear_error) < 0.03:
                        virtual_linear = 0.0
                    if abs(angular_error) < 0.04:
                        virtual_angular_target = 0.0

                    virtual_angular = 0.4 * virtual_angular_target + 0.6 * prev_virtual_angular
                    prev_virtual_angular = virtual_angular

                    scale_factor = max(0.3, 1.0 - abs(angular_error) * 1.5)
                    virtual_linear *= scale_factor

                    # 속도 명령 전송
                    node.send_velocity(virtual_linear, virtual_angular)
                    
                    # 오버레이 정보
                    cv2.putText(display_frame, f"Person Center X: {last_person_cx:.2f}", (20, 80),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 0), 2)
                    cv2.putText(display_frame, f"Ang Error: {angular_error:.2f} (Speed: {virtual_angular:.2f})", (20, 110),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)
                    cv2.putText(display_frame, f"Body Height (S-H): {last_body_height_ratio:.2f}", (20, 140),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 0), 2)
                    cv2.putText(display_frame, f"Lin Error: {linear_error:.2f} (Speed: {virtual_linear:.2f})", (20, 170),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)
                    
                    cv2.circle(display_frame, (int(last_person_cx * w_img), int(last_person_cy * h_img)), 8, (0, 255, 0), -1)

                    if annotated_frame is not None:
                        keypoints, bbox = annotated_frame
                        if bbox is not None:
                            bx1, by1, bx2, by2 = bbox
                            cv2.rectangle(display_frame, 
                                          (int(bx1 * w_img), int(by1 * h_img)), 
                                          (int(bx2 * w_img), int(by2 * h_img)), 
                                          (0, 255, 0), 2)
                            cv2.putText(display_frame, "Person", 
                                        (int(bx1 * w_img), int(by1 * h_img) - 10),
                                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)

                        if keypoints is not None and len(keypoints) > 12:
                            pt_l_shoulder = (int(keypoints[5][0] * w_img), int(keypoints[5][1] * h_img))
                            pt_r_shoulder = (int(keypoints[6][0] * w_img), int(keypoints[6][1] * h_img))
                            pt_l_hip = (int(keypoints[11][0] * w_img), int(keypoints[11][1] * h_img))
                            pt_r_hip = (int(keypoints[12][0] * w_img), int(keypoints[12][1] * h_img))

                            cv2.line(display_frame, pt_l_shoulder, pt_r_shoulder, (255, 0, 0), 2)
                            cv2.line(display_frame, pt_l_hip, pt_r_hip, (255, 0, 0), 2)
                            cv2.line(display_frame, pt_l_shoulder, pt_l_hip, (255, 0, 0), 2)
                            cv2.line(display_frame, pt_r_shoulder, pt_r_hip, (255, 0, 0), 2)

                            for pt in [pt_l_shoulder, pt_r_shoulder, pt_l_hip, pt_r_hip]:
                                cv2.circle(display_frame, pt, 5, (0, 0, 255), -1)
                else:
                    prev_virtual_angular = 0.0
                    node.send_stop()

                if person_detected:
                    cv2.putText(display_frame, "STATUS: TRACKING ACTIVE", (20, 40),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
                else:
                    cv2.putText(display_frame, "STATUS: STOP & SEARCHING", (20, 40),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)

                cv2.putText(display_frame, f"Inference: {inference_time_ms:.1f} ms", (w_img - 220, h_img - 20),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.55, (100, 255, 100), 2)

            elif node.state == "RETURN":
                # ── [RETURN 모드] 네비게이션 복귀 (속도는 Nav2가 /cmd_vel로 직접 통제함) ──
                cv2.putText(display_frame, "STATUS: RETURNING TO HOME (Nav2)", (20, 40),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
                cv2.putText(display_frame, f"Target: x={node.start_x:.2f}, y={node.start_y:.2f}, yaw={node.start_yaw:.2f}", (20, 80),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
                cv2.putText(display_frame, "Type '추종' in Terminal to resume following.", (20, 110),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (100, 255, 255), 2)

            elif node.state == "IDLE":
                # ── [IDLE 모드] 대기 상태 (복귀 완료 후 또는 수동 대기) ──
                cv2.putText(display_frame, "STATUS: IDLE (Waiting at Base)", (20, 40),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (150, 150, 150), 2)
                cv2.putText(display_frame, "Type '추종' in Terminal to start following.", (20, 80),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 2)

            cv2.putText(display_frame, f"FPS: {fps:.1f}", (w_img - 110, 40),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)

            cv2.imshow('Turtlebot 3 Hybrid Follower & Nav2 Base', display_frame)
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break
    except KeyboardInterrupt:
        print("\n키보드 인터럽트로 종료합니다.")
    except Exception as e:
        print(f"\n[메인 루프 에러] {e}")
        import traceback
        traceback.print_exc()
    finally:
        node.send_stop()
        cap.release()
        cv2.destroyAllWindows()
        node.destroy_node()
        rclpy.shutdown()
        print("사람 추종 및 네비게이션 노드가 안전하게 종료되었습니다.")

if __name__ == '__main__':
    main()
