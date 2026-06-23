#!/usr/bin/env python3
import cv2
import mediapipe as mp
import numpy as np
import time

# MediaPipe Pose 모듈 초기화
mp_pose = mp.solutions.pose
mp_drawing = mp.solutions.drawing_utils

def main():
    # ── 카메라 소스 설정 ──
    # 라즈베리파이 4 IP 주소 (192.168.0.67)
    # 노트북 내장 카메라로 로컬 테스트 하려면 주소 대신 0을 적으시면 됩니다.
    PI_IP = "192.168.0.67" 
    stream_url = f"http://{PI_IP}:5000/video_feed"
    
    print(f"[연동] 카메라 스트림 연결 중: {stream_url}")
    cap = cv2.VideoCapture(stream_url)
    if not cap.isOpened():
        print(f"[Error] 비디오 피드({stream_url})에 연결할 수 없습니다.")
        print("라즈베리파이의 'pi_camera_streamer.py'가 실행 중인지, IP 주소가 맞는지 확인하세요.")
        return

    print("==================================================")
    print("  [사람 인식 및 가상 제어 테스트 모드 - 뒷모습 인식 강화형]")
    print("  - 코(Nose)를 배제하고 어깨~골반 거리로 인식하여 뒤돌아도 상시 트래킹 유지")
    print("  - MediaPipe model_complexity=2 (정밀형 모델) 탑재")
    print("  - 종료하려면 카메라 창에서 'q' 키를 누르세요.")
    print("==================================================")

    # 제어 계산용 기준 상수
    # 어깨~골반 기준으로 거리를 측정하므로 목표 세로 비율을 0.35로 조정 (약 1.2m~1.5m 유지 거리)
    TARGET_HEIGHT_RATIO = 0.35  
    
    # 최적화 관련 변수
    SKIP_FRAMES = 1             # 1프레임당 1번 검출 (지연 최소화)
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

    # FPS 계산용 변수
    prev_time = time.time()

    # MediaPipe Pose 감지 세팅 (model_complexity=0 으로 속도 극대화)
    with mp_pose.Pose(
        static_image_mode=False,
        model_complexity=0,       # 0:빠름, 1:보통, 2:정밀
        min_detection_confidence=0.5,
        min_tracking_confidence=0.5
    ) as pose:
        while cap.isOpened():
            ret, frame = cap.read()
            if not ret:
                print("[Warning] 프레임을 읽어올 수 없습니다. 재연결 시도 중...")
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
                    
                    # 어깨 검출 신뢰도 0.3으로 기준 완화 (뒷모습은 반사가 심해 점수가 낮게 측정될 수 있음)
                    if left_shoulder.visibility > 0.3 and right_shoulder.visibility > 0.3:
                        person_detected = True
                        last_person_cx = (left_shoulder.x + right_shoulder.x) / 2.0
                        last_person_cy = (left_shoulder.y + right_shoulder.y) / 2.0
                        
                        # ── [핵심 개선] 코 대신 어깨 평균 Y좌표에서 골반 평균 Y좌표까지의 거리로 높이 측정 ──
                        shoulder_y = (left_shoulder.y + right_shoulder.y) / 2.0
                        hip_y = (left_hip.y + right_hip.y) / 2.0
                        last_body_height_ratio = hip_y - shoulder_y
                        
                        last_pose_landmarks = results.pose_landmarks
                    else:
                        person_detected = False
                else:
                    person_detected = False

            # 화면 출력 및 가상 제어 연산
            if person_detected and last_person_cx is not None:
                angular_error = 0.5 - last_person_cx
                linear_error = TARGET_HEIGHT_RATIO - last_body_height_ratio
                
                virtual_linear = max(-0.15, min(0.15, linear_error * 1.5)) # 가중치 소폭 조정
                virtual_angular = max(-0.6, min(0.6, angular_error * 2.2))
                
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

            # 상태 표시 및 연산 속도 표시
            if person_detected:
                cv2.putText(frame, "STATUS: PERSON TRACKING", (20, 40),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
            else:
                cv2.putText(frame, "STATUS: SEARCHING...", (20, 40),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)

            # 실시간 FPS 및 측정된 Inference Time 화면에 표시
            cv2.putText(frame, f"FPS: {fps:.1f}", (w_img - 110, 40),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
            cv2.putText(frame, f"Inference: {inference_time_ms:.1f} ms", (w_img - 220, h_img - 20),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.55, (100, 255, 100), 2)

            # 디스플레이 출력
            cv2.imshow('Turtlebot 3 Human Follower Simulation', frame)
            
            # 'q' 키 입력 시 종료
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break

    # 리소스 정리
    cap.release()
    cv2.destroyAllWindows()
    print("인식 테스트 시뮬레이션이 종료되었습니다.")

if __name__ == '__main__':
    main()
