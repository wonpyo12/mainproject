#!/usr/bin/env python3
"""2단계 tracking-by-detection 검증 하니스 (카메라 없이 합성 영상으로 end-to-end 구동).

등록 샘플(front)을 캔버스에 합성해 좌우로 움직이는 가짜 카메라를 만들고,
실제 robocart_main.run_tracking 을 헤드리스로 돌려서 다음을 측정한다:
  - 메인 루프 프레임 수 vs 무거운 검출(YOLO+ReID) 실행 수  → 검출 주기화 효과
  - KCF 보간 프레임 수 / KCF 재고정 수                     → 보간 동작
  - 추종(tracking) 진입 여부
출력 마지막 어노테이션 캔버스 1장을 verify_out.jpg 로 저장한다.
"""
import sys, time, threading
# 카메라/ROS/시리얼 경로 회피: 순수 import 모드
sys.argv = [sys.argv[0]]

import cv2
import numpy as np
import robocart_main as M

# ── 통계 카운터 ──
stat = {"main": 0, "detect": 0, "kcf_update": 0, "kcf_reanchor": 0,
        "tracking_frames": 0, "det_frames": 0, "kcf_frames": 0}
_last_canvas = {"img": None}

# DetectionWorker._process 래핑 → 무거운 검출 횟수 카운트
_orig_process = M.DetectionWorker._process
def _wrap_process(self, frame, last_bbox):
    stat["detect"] += 1
    return _orig_process(self, frame, last_bbox)
M.DetectionWorker._process = _wrap_process

# BoxTracker 래핑 → 보간/재고정 카운트
_orig_init = M.BoxTracker.init
def _wrap_init(self, frame, bbox):
    r = _orig_init(self, frame, bbox)
    if r:
        stat["kcf_reanchor"] += 1
    return r
M.BoxTracker.init = _wrap_init
_orig_update = M.BoxTracker.update
def _wrap_update(self, frame):
    stat["kcf_update"] += 1
    return _orig_update(self, frame)
M.BoxTracker.update = _wrap_update

# display 캡처 (창 띄우지 않음) + HUD 모드 집계
def _fake_display(winname, frame):
    _last_canvas["img"] = frame.copy()
M.display = _fake_display

# wait_key: N 프레임 후 ESC(27) 반환해 루프 종료
RUN_SECONDS = 14.0
_start = time.time()
def _fake_wait_key(delay):
    stat["main"] += 1
    if time.time() - _start > RUN_SECONDS:
        return 27
    return -1
M.wait_key = _fake_wait_key

# 추종/모드 집계: TrackingState 를 통해 매 프레임 상태 확인은 어려우니
# run_tracking 내부 대신 wait_key 호출 시점에 전역 추적 상태를 본다.
# (간단히 카운트만; 정확 모드 분해는 detect/kcf_update 수로 갈음)


class FakeCam:
    """등록 front 샘플을 캔버스에 합성해 좌우로 움직이는 가짜 카메라."""
    def __init__(self):
        self.person = cv2.imread("data/samples/front/owner_001_001.jpg")
        assert self.person is not None
        self.W, self.H = 640, 480
        self.t0 = time.time()

    def get_frame(self):
        # ~30fps 스로틀 (메인 루프가 워커를 굶기지 않도록)
        time.sleep(1 / 30)
        canvas = np.full((self.H, self.W, 3), 90, np.uint8)  # 회색 배경
        ph, pw = self.person.shape[:2]
        # 좌우 왕복 이동 (느린 보행 속도 모사: 약 25초 주기, 진폭 축소)
        phase = (time.time() - self.t0) / 25.0
        x = int((self.W - pw) * (0.5 + 0.25 * np.sin(phase * 2 * np.pi)))
        y = (self.H - ph) // 2
        canvas[y:y+ph, x:x+pw] = self.person
        return canvas


def main():
    print("[검증] 모델 로드...")
    yolo = M.create_yolo()
    hog = None
    pose = M.create_pose_estimator()
    reid = M.create_reid_model()
    profile = M.load_profile()
    cam = FakeCam()

    print(f"[검증] run_tracking {RUN_SECONDS}s 구동 (DETECT_INTERVAL={M.DETECT_INTERVAL}, "
          f"KCF_MAX_AGE={M.KCF_MAX_AGE})")
    M.run_tracking(yolo, hog, pose, reid, profile, ros2_node=cam)

    if _last_canvas["img"] is not None:
        cv2.imwrite("verify_out.jpg", _last_canvas["img"])

    print("\n========== 검증 결과 ==========")
    el = time.time() - _start
    print(f"실행 시간          : {el:.1f}s")
    print(f"메인 루프 프레임   : {stat['main']}  ({stat['main']/el:.1f} fps)")
    print(f"무거운 검출 실행   : {stat['detect']}  ({stat['detect']/el:.1f}/s)")
    print(f"KCF update 호출    : {stat['kcf_update']}")
    print(f"KCF 재고정(init)   : {stat['kcf_reanchor']}")
    if stat["main"]:
        ratio = stat["detect"] / stat["main"]
        print(f"검출/메인 비율     : {ratio:.2f}  (1.0=매프레임검출, 낮을수록 보간 효과↑)")
    print(f"어노테이션 저장    : verify_out.jpg ({'OK' if _last_canvas['img'] is not None else '없음'})")
    print("================================")
    # 판정
    ok = (stat["detect"] > 0 and stat["kcf_reanchor"] > 0
          and stat["kcf_update"] > 0 and stat["detect"] < stat["main"])
    print("판정:", "PASS — 검출 주기화 + KCF 보간 동작 확인" if ok
          else "CHECK — 추종 미진입 가능(아래 수치 확인)")


if __name__ == "__main__":
    main()
