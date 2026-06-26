#!/usr/bin/env python3
import cv2
import mediapipe as mp
import numpy as np
import time
import pyrealsense2 as rs

# MediaPipe Pose 모듈 초기화
mp_pose = mp.solutions.pose
mp_drawing = mp.solutions.drawing_utils


def detect_usb3():
    """연결된 RealSense 가 USB 3.x 로 잡혔는지 확인."""
    try:
        ctx = rs.context()
        devs = ctx.query_devices()
        if len(devs) == 0:
            return None  # 장치 없음
        usb = devs[0].get_info(rs.camera_info.usb_type_descriptor)
        print(f"[정보] RealSense USB 연결 타입: {usb}")
        return usb.startswith("3")
    except Exception as e:
        print(f"[경고] USB 타입 확인 실패: {e}")
        return False


class RealSenseCamera:
    """
    Intel RealSense D435i 카메라 래퍼.
    USB3 면 컬러+깊이(640x480@30)로 실제 거리 측정,
    USB2 면 대역폭 한계로 컬러 단독(424x240@15) 저해상도 모드로 동작.
    """
    def __init__(self, use_depth):
        self.use_depth = use_depth
        self.pipeline = rs.pipeline()
        config = rs.config()

        if use_depth:
            config.enable_stream(rs.stream.color, 640, 480, rs.format.bgr8, 30)
            config.enable_stream(rs.stream.depth, 640, 480, rs.format.z16, 30)
        else:
            # USB2.0 안정 동작 구성 (컬러 단독)
            config.enable_stream(rs.stream.color, 424, 240, rs.format.bgr8, 15)

        self.profile = self.pipeline.start(config)

        # 컬러 카메라 초점거리(fx, 픽셀단위) — 단안 거리 추정에 사용
        color_stream = self.profile.get_stream(rs.stream.color).as_video_stream_profile()
        self.fx = color_stream.get_intrinsics().fx

        if use_depth:
            self.align = rs.align(rs.stream.color)
        else:
            self.align = None
        self.running = True

    def read(self):
        """(ret, color_image, depth_frame) 반환. 컬러 모드면 depth_frame 은 None."""
        try:
            frames = self.pipeline.wait_for_frames(timeout_ms=2000)
        except RuntimeError:
            return False, None, None

        if self.use_depth:
            aligned = self.align.process(frames)
            color_frame = aligned.get_color_frame()
            depth_frame = aligned.get_depth_frame()
            if not color_frame or not depth_frame:
                return False, None, None
            return True, np.asanyarray(color_frame.get_data()), depth_frame
        else:
            color_frame = frames.get_color_frame()
            if not color_frame:
                return False, None, None
            return True, np.asanyarray(color_frame.get_data()), None

    def isOpened(self):
        return self.running

    def release(self):
        self.running = False
        try:
            self.pipeline.stop()
        except RuntimeError:
            pass


def get_distance_at(depth_frame, px, py, w_img, h_img, window=7):
    """(px, py) 주변 window 영역의 유효 깊이값 중앙값(m). 유효값 없으면 0.0."""
    half = window // 2
    x0, x1 = max(0, px - half), min(w_img - 1, px + half)
    y0, y1 = max(0, py - half), min(h_img - 1, py + half)
    dists = []
    for yy in range(y0, y1 + 1):
        for xx in range(x0, x1 + 1):
            d = depth_frame.get_distance(xx, yy)
            if d > 0:
                dists.append(d)
    if not dists:
        return 0.0
    return float(np.median(dists))


def main():
    print("[연동] Intel RealSense D435i 카메라 연결 중...")
    usb3 = detect_usb3()
    if usb3 is None:
        print("[Error] RealSense 장치를 찾을 수 없습니다. USB 연결을 확인하세요.")
        return

    use_depth = bool(usb3)
    if use_depth:
        print("[모드] USB3 감지 -> 깊이센서 실거리 측정 모드 (640x480@30)")
    else:
        print("[모드] USB2 감지 -> 컬러 단독 저해상도 모드 (424x240@15)")
        print("       (깊이센서 미사용. 어깨-골반 비율로 거리 추정. USB3 케이블 권장)")

    try:
        cam = RealSenseCamera(use_depth=use_depth)
    except RuntimeError as e:
        print(f"[Error] RealSense 카메라를 열 수 없습니다: {e}")
        return

    time.sleep(0.5)
    ret, frame, depth_frame = cam.read()
    if not ret:
        print("[Error] 카메라에서 프레임을 받아올 수 없습니다.")
        cam.release()
        return

    print("==================================================")
    print("  [사람 인식 및 가상 제어 - D435i]")
    print("  - 코(Nose) 배제, 어깨 기준으로 뒷모습도 상시 트래킹")
    print("  - 종료하려면 카메라 창에서 'q' 키를 누르세요.")
    print("==================================================")

    # 제어 기준 상수
    TARGET_DISTANCE_CM = 130.0      # 유지 목표 거리(cm)
    REAL_SHOULDER_WIDTH_CM = 40.0   # (컬러 모드) 사람 어깨 너비 가정값 (단안 거리 추정용)

    frame_counter = 0
    last_person_cx = None
    last_person_cy = None
    last_distance_cm = None     # 측정/추정된 사람까지 거리(cm)
    last_pose_landmarks = None
    person_detected = False

    tm = cv2.TickMeter()
    inference_time_ms = 0.0
    prev_time = time.time()

    with mp_pose.Pose(
        static_image_mode=False,
        model_complexity=0,
        min_detection_confidence=0.5,
        min_tracking_confidence=0.5
    ) as pose:
        while cam.isOpened():
            ret, frame, depth_frame = cam.read()
            if not ret:
                print("[Warning] 프레임을 읽어올 수 없습니다. 재시도 중...")
                time.sleep(0.1)
                continue

            frame_counter += 1
            h_img, w_img, _ = frame.shape

            current_time = time.time()
            fps = 1.0 / max(1e-6, (current_time - prev_time))
            prev_time = current_time

            image_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            tm.reset(); tm.start()
            results = pose.process(image_rgb)
            tm.stop()
            inference_time_ms = tm.getTimeMilli()

            if results.pose_landmarks:
                lm = results.pose_landmarks.landmark
                ls = lm[mp_pose.PoseLandmark.LEFT_SHOULDER]
                rs_ = lm[mp_pose.PoseLandmark.RIGHT_SHOULDER]
                lhip = lm[mp_pose.PoseLandmark.LEFT_HIP]
                rhip = lm[mp_pose.PoseLandmark.RIGHT_HIP]

                if ls.visibility > 0.3 and rs_.visibility > 0.3:
                    person_detected = True
                    last_person_cx = (ls.x + rs_.x) / 2.0
                    last_person_cy = (ls.y + rs_.y) / 2.0

                    if use_depth:
                        # 깊이센서 실측 거리(cm)
                        px = int(last_person_cx * w_img)
                        py = int(last_person_cy * h_img)
                        d = get_distance_at(depth_frame, px, py, w_img, h_img, 7)
                        if d > 0:
                            last_distance_cm = d * 100.0
                    else:
                        # 단안 추정: 어깨 픽셀 너비 + 초점거리(fx)로 거리(cm) 계산
                        shoulder_px = abs(ls.x - rs_.x) * w_img
                        if shoulder_px > 1:
                            last_distance_cm = (REAL_SHOULDER_WIDTH_CM * cam.fx) / shoulder_px

                    last_pose_landmarks = results.pose_landmarks
                else:
                    person_detected = False
            else:
                person_detected = False

            if person_detected and last_person_cx is not None:
                angular_error = 0.5 - last_person_cx
                virtual_angular = max(-0.6, min(0.6, angular_error * 2.2))

                if last_distance_cm is not None:
                    # 목표보다 멀면(+) 전진. cm 오차를 m로 환산해 게인 적용
                    linear_error = (last_distance_cm - TARGET_DISTANCE_CM) / 100.0
                    virtual_linear = max(-0.15, min(0.15, linear_error * 0.3))
                    src = "depth" if use_depth else "est"
                    dist_text = f"Distance: {last_distance_cm:.0f} cm ({src})"
                else:
                    linear_error = 0.0
                    virtual_linear = 0.0
                    dist_text = "Distance: N/A"

                cv2.putText(frame, f"Person Center X: {last_person_cx:.2f}", (20, 80),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 0), 2)
                cv2.putText(frame, f"Ang Error: {angular_error:.2f} (Speed: {virtual_angular:.2f})", (20, 110),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)
                cv2.putText(frame, dist_text, (20, 140),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 0), 2)
                cv2.putText(frame, f"Lin Error: {linear_error:.2f} (Speed: {virtual_linear:.2f})", (20, 170),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)

                cv2.circle(frame, (int(last_person_cx * w_img), int(last_person_cy * h_img)),
                           8, (0, 255, 0), -1)
                if last_pose_landmarks:
                    mp_drawing.draw_landmarks(frame, last_pose_landmarks, mp_pose.POSE_CONNECTIONS)

            if person_detected:
                cv2.putText(frame, "STATUS: PERSON TRACKING", (20, 40),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
            else:
                cv2.putText(frame, "STATUS: SEARCHING...", (20, 40),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)

            mode_tag = "DEPTH" if use_depth else "COLOR(USB2)"
            cv2.putText(frame, f"FPS: {fps:.1f} [{mode_tag}]", (w_img - 230, 40),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
            cv2.putText(frame, f"Inference: {inference_time_ms:.1f} ms", (w_img - 230, h_img - 20),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.55, (100, 255, 100), 2)

            cv2.imshow('Turtlebot 3 Human Follower Simulation (D435i)', frame)
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break

    cam.release()
    cv2.destroyAllWindows()
    print("인식 테스트 시뮬레이션이 종료되었습니다.")


if __name__ == '__main__':
    main()
