"""등록(앞/뒤 촬영) — VM 디스플레이로 안내하며 ReID 표본 수집."""
import threading
import time
from datetime import datetime

import cv2

from . import config
from .debug_log import DBG
from .notify import speak_on_pi
from .profile import (_avg_color, _avg_embed, _pick_diverse, extract_features,
                      largest_bbox, save_profile)
from .config import (PROFILE_PATH, REG_DETECT_EVERY, REG_MAX_SEC, REG_MIN_SAMPLES, WINDOW)


def _show(frame):
    cv2.imshow(WINDOW, frame)
    cv2.waitKey(1)


def register(cam, yolo, reid, user_id, grace_sec: float = 5.0, pi_ip: str = None):
    # [기능 2] 재촬영 시 기존 프로필 삭제 → 기록 누적 방지(항상 새 1개만 유지)
    if PROFILE_PATH.exists():
        PROFILE_PATH.unlink()
        print(f"[profile] 기존 프로필 삭제: {PROFILE_PATH.name}")

    speak_on_pi(pi_ip, "촬영을 시작합니다.")

    phases = [("front", "FRONT: face the camera"),
              ("back",  "BACK: turn around")]
    profile = {"user_id": user_id,
               "registered_at": datetime.now().isoformat(timespec="seconds"),
               "reid_model": config.REID_MODEL_NAME,   # 모델이 다르면 임베딩 호환 안 됨
               "phases": {}}

    # 위치 잡을 시간(grace) 카운트다운
    t_end = time.time() + grace_sec
    while time.time() < t_end:
        frame = cam.read()
        if frame is None:
            time.sleep(0.02); continue
        left = int(t_end - time.time()) + 1
        cv2.putText(frame, "STAND in view", (20, 50),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 255, 255), 2)
        cv2.putText(frame, f"capture starts in {left}s", (20, 95),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 200, 0), 2)
        _show(frame)

    for pname, instruct in phases:
        if pname == "back":
            speak_on_pi(pi_ip, "뒤돌아 주세요.")

        for sec in (3, 2, 1):
            t_end = time.time() + 1.0
            while time.time() < t_end:
                frame = cam.read()
                if frame is None:
                    time.sleep(0.02); continue
                cv2.putText(frame, instruct, (20, 50),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 255, 255), 2)
                cv2.putText(frame, f"start in {sec}", (20, 95),
                            cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 200, 0), 3)
                _show(frame)

        # ~3초간 샘플 수집. YOLO/ReID 는 워커 스레드에서 돌려 화면 멈춤 방지.
        embs, cols = [], []
        shared = {"bbox": None, "n": 0}
        stop_flag = {"v": False}
        lock = threading.Lock()

        def _worker():
            # 등록 중엔 대상이 제자리에 서 있으므로 무거운 YOLO 검출은
            # REG_DETECT_EVERY 샘플마다 한 번만 하고, 그 사이엔 직전 bbox를
            # 재사용해 가벼운 ReID 임베딩만 수행 → 샘플 수집 속도 수 배 향상
            last_bb = None
            since_det = REG_DETECT_EVERY   # 첫 프레임은 반드시 검출
            det_fails = 0
            last_rx = -1
            while not stop_flag["v"]:
                # 새 프레임이 도착했을 때만 처리 (같은 프레임 중복 샘플 방지)
                if hasattr(cam, "rx_count"):
                    rx = cam.rx_count()
                    if rx == last_rx:
                        time.sleep(0.005); continue
                    last_rx = rx
                f = cam.read()
                if f is None:
                    time.sleep(0.01); continue
                det_ms = 0.0
                if last_bb is None or since_det >= REG_DETECT_EVERY:
                    t0 = time.time()
                    bb = largest_bbox(yolo.detect(f))
                    det_ms = (time.time() - t0) * 1000
                    since_det = 0
                    if bb is None:
                        det_fails += 1
                        print(f"[register/{pname}] det={det_ms:.0f}ms 사람검출 실패 {det_fails}회 "
                              f"(frame {f.shape[1]}x{f.shape[0]})")
                        # 등록 중엔 대상이 제자리 → 일시적 검출 실패(블러/조명)는
                        # 직전 bbox로 계속 샘플 수집. 3연속 실패 시에만 bbox 폐기.
                        if last_bb is not None and det_fails < 3:
                            bb = last_bb
                        else:
                            last_bb = None
                            with lock:
                                shared["bbox"] = None
                            continue
                    else:
                        det_fails = 0
                        last_bb = bb
                else:
                    bb = last_bb
                since_det += 1
                x1, y1, x2, y2 = bb
                crop = f[max(0, y1):y2, max(0, x1):x2]
                if crop.size > 0:
                    t1 = time.time()
                    feat = extract_features(crop, reid)
                    emb_ms = (time.time() - t1) * 1000
                    if feat["reid_emb"]:
                        with lock:
                            embs.append(feat["reid_emb"]); cols.append(feat["color"])
                            shared["bbox"] = bb; shared["n"] = len(embs)
                        print(f"[register/{pname}] det={det_ms:.0f}ms emb={emb_ms:.0f}ms "
                              f"샘플 {len(embs)}개")

        th = threading.Thread(target=_worker, daemon=True)
        th.start()
        # 기본 3초 수집하되, 샘플이 REG_MIN_SAMPLES 미만이면 REG_MAX_SEC까지 연장
        # (추론이 느리거나 검출이 늦으면 3초 안에 1~2개만 모여 프로필이 부실해짐)
        t_start = time.time()
        rx_start = cam.rx_count() if hasattr(cam, "rx_count") else 0
        while True:
            elapsed = time.time() - t_start
            with lock:
                bb, n = shared["bbox"], shared["n"]
            if elapsed >= 3.0 and (n >= REG_MIN_SAMPLES or elapsed >= REG_MAX_SEC):
                break
            frame = cam.read()
            if frame is None:
                time.sleep(0.02); continue
            if bb is not None:
                cv2.rectangle(frame, (bb[0], bb[1]), (bb[2], bb[3]), (0, 255, 0), 2)
            cv2.putText(frame, f"{pname} capturing... {n}", (20, 50),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 255, 255), 2)
            _show(frame)
            time.sleep(0.01)   # 표시 루프 CPU 양보 (추론 스레드 우선)
        stop_flag["v"] = True
        th.join(timeout=1.5)
        profile["phases"][pname] = {"reid_emb": _avg_embed(embs),
                                    # 대표 표본 8→12: 매칭은 512-dim 코사인 12회(µs 단위)라 부하 무시 가능,
                                    # 자세/각도 커버리지 증가로 재획득 ReID 점수 상승 기대 (이슈 #48)
                                    "reid_embs": _pick_diverse(embs, 12),
                                    "color": _avg_color(cols)}
        dur = time.time() - t_start
        rx_fps = ((cam.rx_count() - rx_start) / dur) if hasattr(cam, "rx_count") else -1
        print(f"[register] {pname}: {len(embs)} 샘플 수집 ({dur:.1f}초, 카메라 수신 {rx_fps:.1f}fps)")
        DBG.log("register", phase=pname, n=len(embs), sec=round(dur, 1), rx_fps=round(rx_fps, 1))
        if len(embs) < REG_MIN_SAMPLES:
            print(f"[register] 경고: {pname} 샘플 {len(embs)}개뿐 — 인식률이 낮을 수 있습니다. "
                  f"조명/거리(1~2m)를 확인하고 재촬영을 권장합니다.")

    speak_on_pi(pi_ip, "촬영이 끝났습니다.")
    save_profile(profile)
    return profile


