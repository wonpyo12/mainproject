#!/usr/bin/env python3
import cv2
from ultralytics import YOLO
import numpy as np
import time
import os
import pyrealsense2 as rs

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
    print("  [사람 인식 및 가상 제어 - D435i (YOLOv8-Pose)]")
    print("  - YOLOv8-pose 기반 실시간 객체 및 관절 트래킹")
    # YOLOv8-pose 모델 로드
    script_dir = os.path.dirname(os.path.abspath(__file__))
    model_path = os.path.join(script_dir, 'yolov8n-pose.pt')
    print(f"  - 모델 로드 중: {model_path}")
    try:
        model = YOLO(model_path)
    except Exception as e:
        print(f"[Error] YOLOv8-Pose 모델을 불러올 수 없습니다: {e}")
        cam.release()
        return
    print("  - 종료하려면 카메라 창에서 'q' 키를 누르세요.")
    print("==================================================")

    # 제어 기준 상수
    TARGET_DISTANCE_CM = 130.0      # 유지 목표 거리(cm)
    REAL_SHOULDER_WIDTH_CM = 40.0   # (컬러 모드) 사람 어깨 너비 가정값 (단안 거리 추정용)

    last_person_cx = None
    last_person_cy = None
    last_distance_cm = None     # 측정/추정된 사람까지 거리(cm)
    best_candidate = None
    person_detected = False

    tm = cv2.TickMeter()
    inference_time_ms = 0.0
    prev_time = time.time()

    while cam.isOpened():
        ret, frame, depth_frame = cam.read()
        if not ret:
            print("[Warning] 프레임을 읽어올 수 없습니다. 재시도 중...")
            time.sleep(0.1)
            continue

        h_img, w_img, _ = frame.shape

        current_time = time.time()
        fps = 1.0 / max(1e-6, (current_time - prev_time))
        prev_time = current_time

        # YOLOv8-pose 추론 실행
        tm.reset()
        tm.start()
        results = model(frame, conf=0.15, verbose=False)
        tm.stop()
        inference_time_ms = tm.getTimeMilli()

        person_detected = False
        best_candidate = None
        min_dist_to_center = 999.0

        if results and len(results) > 0:
            r = results[0]
            if r.boxes is not None and len(r.boxes.xyxyn) > 0:
                for idx, bbox_tensor in enumerate(r.boxes.xyxyn):
                    bbox = bbox_tensor.cpu().numpy()
                    bx1, by1, bx2, by2 = bbox
                    cx = (bx1 + bx2) / 2.0

                    if r.keypoints is not None and len(r.keypoints.xyn) > idx:
                        kps = r.keypoints.xyn[idx].cpu().numpy()
                        if len(kps) > 12:
                            l_sh = kps[5]  # Left shoulder [x, y]
                            r_sh = kps[6]  # Right shoulder [x, y]
                            l_hip = kps[11] # Left hip [x, y]
                            r_hip = kps[12] # Right hip [x, y]

                            # 어깨가 둘 다 유효하게 검출된 경우
                            if not (l_sh[0] == 0.0 and l_sh[1] == 0.0) and not (r_sh[0] == 0.0 and r_sh[1] == 0.0):
                                dist = abs(cx - 0.5)
                                if dist < min_dist_to_center:
                                    min_dist_to_center = dist
                                    best_candidate = {
                                        'cx': float((l_sh[0] + r_sh[0]) / 2.0),
                                        'cy': float((l_sh[1] + r_sh[1]) / 2.0),
                                        'l_sh': l_sh,
                                        'r_sh': r_sh,
                                        'l_hip': l_hip,
                                        'r_hip': r_hip,
                                        'bbox': bbox
                                    }

        if best_candidate is not None:
            person_detected = True
            last_person_cx = best_candidate['cx']
            last_person_cy = best_candidate['cy']

            if use_depth:
                # 깊이센서 실측 거리(cm)
                px = int(last_person_cx * w_img)
                py = int(last_person_cy * h_img)
                d = get_distance_at(depth_frame, px, py, w_img, h_img, 7)
                if d > 0:
                    last_distance_cm = d * 100.0
                else:
                    last_distance_cm = None
            else:
                # 단안 추정: 어깨 픽셀 너비 + 초점거리(fx)로 거리(cm) 계산
                shoulder_px = abs(best_candidate['l_sh'][0] - best_candidate['r_sh'][0]) * w_img
                if shoulder_px > 1:
                    last_distance_cm = (REAL_SHOULDER_WIDTH_CM * cam.fx) / shoulder_px
                else:
                    last_distance_cm = None
        else:
            person_detected = False

        # 화면 출력 및 가상 제어 연산
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

            # 이미지에 사람의 어깨 중심 표시 (초록색 원)
            cv2.circle(frame, (int(last_person_cx * w_img), int(last_person_cy * h_img)),
                       8, (0, 255, 0), -1)

            # 욜로 바운딩 박스 그리기
            bx1, by1, bx2, by2 = best_candidate['bbox']
            cv2.rectangle(frame, 
                          (int(bx1 * w_img), int(by1 * h_img)), 
                          (int(bx2 * w_img), int(by2 * h_img)), 
                          (0, 255, 0), 2)

            # 관절 그리기 및 연결선
            pt_l_shoulder = (int(best_candidate['l_sh'][0] * w_img), int(best_candidate['l_sh'][1] * h_img))
            pt_r_shoulder = (int(best_candidate['r_sh'][0] * w_img), int(best_candidate['r_sh'][1] * h_img))
            pt_l_hip = (int(best_candidate['l_hip'][0] * w_img), int(best_candidate['l_hip'][1] * h_img))
            pt_r_hip = (int(best_candidate['r_hip'][0] * w_img), int(best_candidate['r_hip'][1] * h_img))

            # 어깨선, 골반선
            cv2.line(frame, pt_l_shoulder, pt_r_shoulder, (255, 0, 0), 2)
            cv2.line(frame, pt_l_hip, pt_r_hip, (255, 0, 0), 2)
            # 몸통 양 옆선 (어깨-골반)
            cv2.line(frame, pt_l_shoulder, pt_l_hip, (255, 0, 0), 2)
            cv2.line(frame, pt_r_shoulder, pt_r_hip, (255, 0, 0), 2)

            # 관절 점 표시
            for pt in [pt_l_shoulder, pt_r_shoulder, pt_l_hip, pt_r_hip]:
                cv2.circle(frame, pt, 5, (0, 0, 255), -1)

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

        cv2.imshow('Turtlebot 3 Human Follower Simulation (D435i - YOLOv8)', frame)
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    cam.release()
    cv2.destroyAllWindows()
    print("인식 테스트 시뮬레이션이 종료되었습니다.")


if __name__ == '__main__':
    main()
