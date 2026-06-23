#!/usr/bin/env python3
import cv2
import mediapipe as mp
import numpy as np
import time
import threading

# ROS2 관련 라이브러리 임포트
import rclpy
from rclpy.node import Node
from geometry_msgs.msg import Twist

# MediaPipe Pose 모듈 초기화
mp_pose = mp.solutions.pose
mp_drawing = mp.solutions.drawing_utils

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
    PI_IP = "192.168.0.67" 
    stream_url = f"http://{PI_IP}:5000/video_feed"
    
    print(f"[연동] 카메라 스트림 연결 중: {stream_url}")
    cap = cv2.VideoCapture(stream_url)
    if not cap.isOpened():
        print(f"[Error] 비디오 피드({stream_url})에 연결할 수 없습니다.")
        print("라즈베리파이의 'pi_camera_streamer.py'가 실행 중인지 확인하세요.")
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
    TARGET_HEIGHT_RATIO = 0.35  # 어깨~골반 목표 세로 비율 (약 1.2m~1.5m 유지 거리)
    
    # 최적화 관련 변수
    SKIP_FRAMES = 1             # 실시간성 극대화를 위해 매 프레임 검출 (지연 극소화)
    frame_counter = 0
    
    # 이전 검출 좌표 저장용 캐시
    last_person_cx = None
    last_person_cy = None
    last_body_height_ratio = None
    last_pose_landmarks = None
    person_detected = False
    
    # OpenCV 연산 속도 측정 객체
    tm = cv2.TickMeter()
    inference_time_ms = 0.0
    prev_time = time.time()

    # MediaPipe Pose 감지 세팅 (model_complexity=0 으로 초고속 처리)
    with mp_pose.Pose(
        static_image_mode=False,
        model_complexity=0,       # 0:빠름(초고속 모드), 1:보통, 2:정밀
        min_detection_confidence=0.5,
        min_tracking_confidence=0.5
    ) as pose:
        try:
            while cap.isOpened() and rclpy.ok():
                ret, frame = cap.read()
                if not ret:
                    print("[Warning] 프레임을 읽어올 수 없습니다. 정지 명령을 보내고 대기합니다.")
                    node.send_stop()
                    time.sleep(0.5)
                    continue

                frame_counter += 1
                h_img, w_img, _ = frame.shape

                # FPS 계산
                current_time = time.time()
                fps = 1.0 / (current_time - prev_time)
                prev_time = current_time

                # 설정된 프레임 주기마다 검출 수행
                if frame_counter % SKIP_FRAMES == 0 or last_person_cx is None:
                    image_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    
                    tm.reset()
                    tm.start()
                    results = pose.process(image_rgb)
                    tm.stop()
                    inference_time_ms = tm.getTimeMilli()
                    
                    if results.pose_landmarks:
                        landmarks = results.pose_landmarks.landmark
                        left_shoulder = landmarks[mp_pose.PoseLandmark.LEFT_SHOULDER]
                        right_shoulder = landmarks[mp_pose.PoseLandmark.RIGHT_SHOULDER]
                        left_hip = landmarks[mp_pose.PoseLandmark.LEFT_HIP]
                        right_hip = landmarks[mp_pose.PoseLandmark.RIGHT_HIP]
                        
                        # 어깨 신뢰도 0.3으로 기준 완화
                        if left_shoulder.visibility > 0.3 and right_shoulder.visibility > 0.3:
                            person_detected = True
                            last_person_cx = (left_shoulder.x + right_shoulder.x) / 2.0
                            last_person_cy = (left_shoulder.y + right_shoulder.y) / 2.0
                            
                            # 어깨 평균 Y좌표에서 골반 평균 Y좌표까지의 거리로 높이 측정
                            shoulder_y = (left_shoulder.y + right_shoulder.y) / 2.0
                            hip_y = (left_hip.y + right_hip.y) / 2.0
                            last_body_height_ratio = hip_y - shoulder_y
                            
                            last_pose_landmarks = results.pose_landmarks
                        else:
                            person_detected = False
                    else:
                        person_detected = False

                # ── 제어 및 속도 명령 발행 ──
                if person_detected and last_person_cx is not None:
                    angular_error = 0.5 - last_person_cx
                    linear_error = TARGET_HEIGHT_RATIO - last_body_height_ratio
                    
                    # 실전 주행을 위한 속도 제한 및 비례 제어 (P-Control)
                    # 선속도 (Linear): 최대 0.15 m/s, 후진 최대 -0.08 m/s (안전을 위해 후진 속도 최소화)
                    raw_linear = linear_error * 1.5
                    virtual_linear = max(-0.08, min(0.15, raw_linear)) 
                    
                    # 각속도 (Angular): 최대 0.5 rad/s
                    raw_angular = angular_error * 2.2
                    virtual_angular = max(-0.5, min(0.5, raw_angular))
                    
                    # 불감대 (Deadzone) 적용: 미세한 진동 방지
                    if abs(linear_error) < 0.03:
                        virtual_linear = 0.0
                    if abs(angular_error) < 0.04:
                        virtual_angular = 0.0

                    # 실제 로봇에 속도 전달!
                    node.send_velocity(virtual_linear, virtual_angular)
                    
                    # 디버그 정보 화면 드로잉
                    cv2.putText(frame, f"Person Center X: {last_person_cx:.2f}", (20, 80),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 0), 2)
                    cv2.putText(frame, f"Ang Error: {angular_error:.2f} (Speed: {virtual_angular:.2f})", (20, 110),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)
                    cv2.putText(frame, f"Body Height (S-H): {last_body_height_ratio:.2f}", (20, 140),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 0), 2)
                    cv2.putText(frame, f"Lin Error: {linear_error:.2f} (Speed: {virtual_linear:.2f})", (20, 170),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)
                    
                    # 이미지에 사람의 어깨 중심 표시 (초록색 원)
                    cv2.circle(frame, (int(last_person_cx * w_img), int(last_person_cy * h_img)), 8, (0, 255, 0), -1)

                    # 포즈 스켈레톤 라인 그리기
                    if last_pose_landmarks:
                        mp_drawing.draw_landmarks(frame, last_pose_landmarks, mp_pose.POSE_CONNECTIONS)
                else:
                    # 사람이 없으면 즉시 정지시킵니다.
                    node.send_stop()

                # 상태 표시 및 연산 속도 표시
                if person_detected:
                    cv2.putText(frame, "STATUS: TRACKING ACTIVE", (20, 40),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
                else:
                    cv2.putText(frame, "STATUS: STOP & SEARCHING", (20, 40),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)

                # 실시간 FPS 및 측정된 Inference Time 화면에 표시
                cv2.putText(frame, f"FPS: {fps:.1f}", (w_img - 110, 40),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
                cv2.putText(frame, f"Inference: {inference_time_ms:.1f} ms", (w_img - 220, h_img - 20),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.55, (100, 255, 100), 2)

                # 디스플레이 출력
                cv2.imshow('Turtlebot 3 Real-time Human Follower', frame)
                
                # 'q' 키 입력 시 종료
                if cv2.waitKey(1) & 0xFF == ord('q'):
                    break
        except KeyboardInterrupt:
            print("\n키보드 인터럽트로 종료합니다.")
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
