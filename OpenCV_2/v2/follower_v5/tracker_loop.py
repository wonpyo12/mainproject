# -*- coding: utf-8 -*-
"""[추종 주행 및 시각화 메인 루프 모듈] tracker_loop.py
- 주요 역할: 인물 신규 등록(register), MOSSE 경량 보간 트래커 관리 및 메인 추종 구동 루프 실행.
- 주요 구성:
  1. register (사용자 앞/뒷모습 20장 수집 및 프로필 JSON 저장)
  2. MosseBoxTracker (YOLO 연산 사이사이 빈 프레임의 박스 위치를 초고속 보간 추적)
  3. run_tracking (비전 검출 대조, % 인식률 화면 HUD 표시 및 로봇 주행 속도 연동 메인 루프)
  4. console_input_thread (터미널 콘솔 명령 '복귀'/'추종'/'정지' 입력 처리 스레드)
"""

from __future__ import annotations

import json
import threading
import time
from datetime import datetime

import cv2
import numpy as np

import light_features as LF
from light_models import OnnxReID

from .config import (
    DETECT_INTERVAL, HERE, KCF_MAX_AGE, PROFILE_PATH, RECORD_SEC,
    REG_DETECT_EVERY, REG_MAX_SEC, REG_MIN_SAMPLES, REID_MODEL_NAME,
    SEARCH_START_DELAY, WINDOW
)
from .utils import DBG, set_robot_led, speak_on_pi
from .worker import DetectionWorker, extract_features

_REC = None


def _avg_embed(embs):
    embs = [e for e in embs if e]
    if not embs:
        return []
    m = np.mean(np.asarray(embs, np.float32), axis=0)
    n = float(np.linalg.norm(m))
    return (m / n).tolist() if n > 0 else m.tolist()


def _pick_diverse(embs, k=8):
    embs = [e for e in embs if e]
    if len(embs) <= k:
        return embs
    idx = np.linspace(0, len(embs) - 1, k).round().astype(int)
    return [embs[i] for i in idx]


def _avg_color(colors):
    if not colors:
        return {}
    out = {}
    for k in ("top_hist", "bot_hist", "top_bgr", "bot_bgr"):
        out[k] = np.mean(np.asarray([c[k] for c in colors], np.float32), axis=0).tolist()
    return out


def largest_bbox(bboxes):
    return max(bboxes, key=lambda b: (b[2] - b[0]) * (b[3] - b[1])) if bboxes else None


def save_profile(profile):
    PROFILE_PATH.write_text(json.dumps(profile, ensure_ascii=False, indent=2))
    print(f"[profile] 저장: {PROFILE_PATH}")


def load_profile():
    if PROFILE_PATH.exists():
        return json.loads(PROFILE_PATH.read_text())
    return None


def _show(frame):
    cv2.imshow(WINDOW, frame)
    cv2.waitKey(1)


def register(cam, yolo, reid, user_id, grace_sec: float = 5.0, pi_ip: str | None = None):
    if PROFILE_PATH.exists():
        PROFILE_PATH.unlink()
        print(f"[profile] 기존 프로필 삭제: {PROFILE_PATH.name}")

    speak_on_pi(pi_ip, "촬영을 시작합니다.")

    phases = [("front", "FRONT: face the camera"),
              ("back",  "BACK: turn around")]
    profile = {
        "user_id": user_id,
        "registered_at": datetime.now().isoformat(timespec="seconds"),
        "reid_model": REID_MODEL_NAME,
        "phases": {}
    }

    t_end = time.time() + grace_sec
    while time.time() < t_end:
        frame = cam.read()
        if frame is None:
            time.sleep(0.02)
            continue
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
                    time.sleep(0.02)
                    continue
                cv2.putText(frame, instruct, (20, 50),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 255, 255), 2)
                cv2.putText(frame, f"start in {sec}", (20, 95),
                            cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 200, 0), 3)
                _show(frame)

        embs, cols = [], []
        shared = {"bbox": None, "n": 0}
        stop_flag = {"v": False}
        lock = threading.Lock()

        def _worker():
            last_bb = None
            since_det = REG_DETECT_EVERY
            det_fails = 0
            last_rx = -1
            while not stop_flag["v"]:
                if hasattr(cam, "rx_count"):
                    rx = cam.rx_count()
                    if rx == last_rx:
                        time.sleep(0.005)
                        continue
                    last_rx = rx
                f = cam.read()
                if f is None:
                    time.sleep(0.01)
                    continue
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
                            embs.append(feat["reid_emb"])
                            cols.append(feat["color"])
                            shared["bbox"] = bb
                            shared["n"] = len(embs)
                        print(f"[register/{pname}] det={det_ms:.0f}ms emb={emb_ms:.0f}ms "
                              f"샘플 {len(embs)}개")

        th = threading.Thread(target=_worker, daemon=True)
        th.start()

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
                time.sleep(0.02)
                continue
            if bb is not None:
                cv2.rectangle(frame, (bb[0], bb[1]), (bb[2], bb[3]), (0, 255, 0), 2)
            cv2.putText(frame, f"{pname} capturing... {n}", (20, 50),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 255, 255), 2)
            _show(frame)
            time.sleep(0.01)

        stop_flag["v"] = True
        th.join(timeout=1.5)
        profile["phases"][pname] = {
            "reid_emb": _avg_embed(embs),
            "reid_embs": _pick_diverse(embs, 12),
            "color": _avg_color(cols)
        }
        dur = time.time() - t_start
        rx_fps = ((cam.rx_count() - rx_start) / dur) if hasattr(cam, "rx_count") else -1
        print(f"[register] {pname}: {len(embs)} 샘플 수집 ({dur:.1f}초, 카메라 수신 {rx_fps:.1f}fps)")
        DBG.log("register", phase=pname, n=len(embs), sec=round(dur, 1), rx_fps=round(rx_fps, 1))
        if len(embs) < REG_MIN_SAMPLES:
            print(f"[register] 경고: {pname} 샘플 {len(embs)}개뿐 — 인식률이 낮을 수 있습니다.")

    speak_on_pi(pi_ip, "촬영이 끝났습니다.")
    save_profile(profile)
    return profile


class MosseBoxTracker(LF.BoxTracker):
    SCALE = 0.5

    @staticmethod
    def _create():
        if hasattr(cv2, "legacy") and hasattr(cv2.legacy, "TrackerMOSSE_create"):
            return cv2.legacy.TrackerMOSSE_create()
        return LF.BoxTracker._create()

    def init(self, frame, bbox):
        small = cv2.resize(frame, None, fx=self.SCALE, fy=self.SCALE)
        return super().init(small, tuple(int(v * self.SCALE) for v in bbox))

    def update(self, frame):
        small = cv2.resize(frame, None, fx=self.SCALE, fy=self.SCALE)
        kb = super().update(small)
        if kb is None:
            return None
        return tuple(int(v / self.SCALE) for v in kb)


def run_tracking(cam, yolo, reid, face, profile, use_face=True, follower=None,
                 just_registered=False):
    tracker = LF.TrackingState()
    last_harvest = {}
    kcf = MosseBoxTracker()
    kcf_age = 0
    rx_last = -1
    frame_count = 0
    none_n = 0
    perf_t = time.time()
    perf_frames = 0
    perf_rx0 = cam.rx_count() if hasattr(cam, "rx_count") else 0
    pred_vx = 0.0
    prev_cx, prev_match_t = None, 0.0
    last_seen_t = time.time()
    fps_t, fps_n, fps_val = time.time(), 0, 0.0

    avg = {"det": 0.0, "reid": 0.0}
    last_seq = 0
    cur_label = "-"
    cur_pct = 0
    last_bboxes, last_scores = [], {}
    reg_det_bbox = None

    worker = DetectionWorker(yolo, reid, face, profile, use_face)
    worker.start()

    try:
        MosseBoxTracker._create()
        kcf_env = True
    except Exception:
        kcf_env = False
        print("[경고] OpenCV KCF/MOSSE 추적기 없음")
    DBG.log("env", kcf=kcf_env)

    print("=== 추종 시작 ===")
    prev_state = follower.state if follower is not None else "FOLLOW"
    while True:
        if follower is not None and getattr(follower, 'trigger_register', False):
            follower.trigger_register = False
            worker.stop()
            worker.join()
            new_profile = register(cam, yolo, reid, "user", grace_sec=3.0, pi_ip=follower.pi_ip)
            profile = new_profile
            worker = DetectionWorker(yolo, reid, face, profile, use_face)
            worker.start()
            follower.is_registered = True
            _t5 = time.time() + 5.0
            while time.time() < _t5:
                cam.read()
                time.sleep(0.05)
            follower.state = "FOLLOW"
            set_robot_led(follower.esp_ip, "STANDBY")
            tracker.reset(); kcf.deinit(); reg_det_bbox = None
            last_bboxes, last_scores = [], {}
            follower.reset_search()
            last_seen_t = time.time()
            continue

        frame = cam.read()
        if frame is None:
            none_n += 1
            if none_n == 5:
                DBG.log("gap_start")
            if follower is not None and none_n >= 5 and none_n % 5 == 0:
                br = follower.lidar_bridge() if follower.state == "FOLLOW" else None
                if br is not None:
                    follower.send_velocity(*br)
                else:
                    follower.send_velocity(0.0, 0.0)
            time.sleep(0.02)
            continue
        if none_n >= 5:
            DBG.log("gap_end", n=none_n)
        none_n = 0
        frame_count += 1
        perf_frames += 1
        h_f, w_f = frame.shape[:2]

        rx_now = cam.rx_count() if hasattr(cam, "rx_count") else frame_count
        new_frame = (rx_now != rx_last)
        rx_last = rx_now

        now = time.time()
        if now - perf_t >= 5.0:
            rx = cam.rx_count() if hasattr(cam, "rx_count") else 0
            DBG.log("perf", loop_fps=round(perf_frames / (now - perf_t), 1),
                    rx_fps=round((rx - perf_rx0) / (now - perf_t), 1),
                    det_ms=round(avg["det"], 1), reid_ms=round(avg["reid"], 1))
            perf_t, perf_frames, perf_rx0 = now, 0, rx

        cur_state = follower.state if follower is not None else "FOLLOW"

        if (follower is not None 
                and cur_state == "FOLLOW" 
                and follower.is_registered 
                and last_seen_t is not None 
                and (time.time() - last_seen_t > 60.0)):
            follower.get_logger().info("1분 동안 사람 미인식 -> 자동 원점 복귀를 수행합니다.")
            DBG.log("ros_cmd", cmd="auto_return_60s", prev_state="FOLLOW")
            follower.state = "RETURN"
            follower.is_registered = False
            follower.send_stop()
            set_robot_led(follower.esp_ip, "RUNNING")
            if not follower.has_start_pose:
                follower.get_logger().warn("AMCL 시작 위치 미저장 → (0,0) 복귀 시도.")
            follower.send_nav_goal(follower.start_x, follower.start_y, follower.start_yaw)

            tracker.reset(); kcf.deinit(); reg_det_bbox = None
            last_bboxes, last_scores = [], {}
            follower.reset_search()
            prev_state = "RETURN"
            cur_state = "RETURN"
            continue

        if cur_state != "FOLLOW" and prev_state == "FOLLOW":
            tracker.reset(); kcf.deinit(); reg_det_bbox = None
            last_bboxes, last_scores = [], {}
            if follower is not None:
                follower.reset_search()
        elif cur_state == "FOLLOW" and prev_state != "FOLLOW":
            last_seen_t = time.time()
        prev_state = cur_state
        follow_active = (cur_state == "FOLLOW")

        interp_alive = follow_active and tracker.is_tracking and kcf.ok
        if follow_active and ((not interp_alive) or kcf_age >= KCF_MAX_AGE
                              or frame_count % DETECT_INTERVAL == 0):
            worker.submit(frame.copy(), tracker.last_bbox)

        det = worker.result()
        fresh = det["seq"] != last_seq
        last_seq = det["seq"]

        draw_bbox = None
        interp = False

        if fresh:
            last_bboxes, last_scores = det["bboxes"], det["scores"]
            avg["det"] = 0.8 * avg["det"] + 0.2 * det["det_ms"]
            avg["reid"] = 0.8 * avg["reid"] + 0.2 * det["reid_ms"]
            bb, total, detail, ori = (det["best_bbox"], det["best_total"],
                                       det["best_detail"], det["best_ori"])
            if tracker.is_tracking:
                thr = LF.KEEP_THRESHOLD
                reid_floor, color_floor = LF.KEEP_REID_FLOOR, 0.0
            else:
                thr = LF.SEARCH_MATCH_THR
                reid_floor, color_floor = LF.REID_FLOOR, LF.COLOR_FLOOR
            reid_ok = detail is not None and detail.get("reid", 0) >= reid_floor
            color_ok = detail is not None and detail.get("color", 0) >= color_floor
            matched = (bb is not None and total >= thr and reid_ok and color_ok)

            rescued = False
            if (not matched and bb is not None
                    and not tracker.is_tracking and tracker.had_track
                    and detail is not None
                    and detail.get("reid", 0) >= LF.SEARCH_REID_RESCUE
                    and detail.get("color", 0) >= LF.COLOR_FLOOR):
                matched = rescued = True
            if matched:
                tracker.update(True, bb, total)
                cur_pct = int(round(total * 100))
                cur_label = f"{profile['user_id']} [{ori}] {cur_pct}%"
                kcf.init(frame, bb); kcf_age = 0
                draw_bbox = bb; reg_det_bbox = bb
                t_m = time.time()
                cx_m = (bb[0] + bb[2]) / 2.0
                if prev_cx is not None and 0.05 < t_m - prev_match_t < 1.5:
                    vx_now = (cx_m - prev_cx) / (t_m - prev_match_t)
                    pred_vx = 0.6 * pred_vx + 0.4 * LF.clamp(vx_now, -400.0, 400.0)
                prev_cx, prev_match_t = cx_m, t_m

                if (tracker.status == "tracking" and not rescued
                        and detail.get("reid", 0) >= LF.HARVEST_REID_MIN
                        and det.get("best_emb")
                        and t_m - last_harvest.get(ori, 0.0) >= LF.HARVEST_INTERVAL_S):
                    ph = profile.get("phases", {}).get(ori)
                    if ph is not None:
                        live = ph.setdefault("reid_embs_live", [])
                        live.append(det["best_emb"])
                        if len(live) > LF.HARVEST_EXTRA_MAX:
                            live.pop(0)
                        last_harvest[ori] = t_m
                        DBG.log("harvest", ori=ori, reid=round(detail["reid"], 3),
                                n_live=len(live))
            else:
                tracker.update(False)
                reg_det_bbox = None
                if tracker.is_tracking and kcf.ok:
                    if new_frame:
                        kb = kcf.update(frame); kcf_age += 1
                    else:
                        kb = tracker.last_bbox
                    if kb is not None:
                        tracker.last_bbox = kb
                        draw_bbox = kb; interp = True
                else:
                    kcf.deinit()

            if detail is not None:
                print(f"[score] match={total*100:5.1f}%  "
                      f"reid={detail['reid']*100:4.0f}% color={detail['color']*100:4.0f}% "
                      f"pos={detail['position']*100:4.0f}%  thr={thr*100:.0f}% "
                      f"=> {'RESCUE' if rescued else ('MATCH' if matched else 'reject')} "
                      f"(cand={len(last_bboxes)})")
            DBG.log("det", det_ms=round(det["det_ms"], 1), reid_ms=round(det["reid_ms"], 1),
                    cand=len(last_bboxes), thr=thr, ok=matched, rescue=rescued,
                    trk=tracker.is_tracking, st=tracker.status,
                    total=round(total, 3) if detail is not None else None,
                    reid=round(detail["reid"], 3) if detail is not None else None,
                    color=round(detail["color"], 3) if detail is not None else None)
        elif interp_alive:
            if new_frame:
                kb = kcf.update(frame); kcf_age += 1
            else:
                kb = tracker.last_bbox
            if kb is not None:
                tracker.last_bbox = kb
                draw_bbox = kb; interp = True

        if draw_bbox is not None:
            last_seen_t = time.time()

        for bb in last_bboxes:
            if bb == reg_det_bbox:
                continue
            x1, y1, x2, y2 = bb
            cv2.rectangle(frame, (x1, y1), (x2, y2), (95, 95, 95), 1)
            cv2.putText(frame, f"{int(last_scores.get(bb, 0) * 100)}%", (x1, max(15, y1 - 4)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.45, (95, 95, 95), 1)

        if draw_bbox is not None:
            x1, y1, x2, y2 = draw_bbox
            cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 3)
            mark = "~" if interp else ""
            cv2.putText(frame, cur_label + mark, (x1, max(18, y1 - 8)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
        elif tracker.status.startswith("lost") and tracker.last_bbox:
            x1, y1, x2, y2 = tracker.last_bbox
            cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 140, 255), 2)
            cv2.putText(frame, tracker.status, (x1, max(18, y1 - 8)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 140, 255), 2)

        fps_n += 1
        _now = time.time()
        if _now - fps_t >= 0.5:
            fps_val = fps_n / (_now - fps_t)
            fps_t, fps_n = _now, 0
        mode = "DET" if fresh else ("KCF" if interp else "-")
        state_tag = follower.state if follower is not None else "NO-DRIVE"
        match_tag = f"MATCH:{cur_pct}%" if tracker.is_tracking else "MATCH:--"
        hud = (f"FPS:{fps_val:.1f} {mode} det:{avg['det']:.0f} reid:{avg['reid']:.0f}ms "
               f"{match_tag} Cand:{len(last_bboxes)} {tracker.status.upper()} [{state_tag}]")
        cv2.rectangle(frame, (0, 0), (w_f, 24), (0, 0, 0), -1)
        cv2.putText(frame, hud, (6, 17), cv2.FONT_HERSHEY_SIMPLEX, 0.5,
                    (0, 255, 0) if tracker.is_tracking else (160, 160, 255), 1)

        if follower is not None:
            if follower.state == "FOLLOW":
                if tracker.is_tracking and draw_bbox is not None:
                    v, w = follower.compute(draw_bbox, w_f, h_f, True)
                    follower.reset_search()
                elif tracker.is_tracking:
                    v, w = 0.0, 0.0
                elif draw_bbox is not None:
                    v, w = 0.0, 0.0
                    follower.reset_search()
                else:
                    if fresh and det["best_total"] > 0.63 and det["best_bbox"] is not None:
                        v, w = 0.0, 0.0
                        follower.reset_search()
                    elif time.time() - last_seen_t < SEARCH_START_DELAY:
                        v, w = 0.0, 0.0
                        follower.reset_search()
                    else:
                        v, w = follower.search_rotate()

                if draw_bbox is not None:
                    set_robot_led(follower.esp_ip, "RUNNING")
                else:
                    set_robot_led(follower.esp_ip, "STANDBY")

                follower.send_velocity(v, w)
                if frame_count % 3 == 0:
                    err_c = (((draw_bbox[0] + draw_bbox[2]) / 2 - w_f / 2) / (w_f / 2)
                             if draw_bbox is not None else None)
                    DBG.log("cmd", v=round(follower.last_v, 3), w=round(follower.last_w, 3),
                            dist=round(follower.last_dist_cm, 1),
                            mode=getattr(follower, "_dist_mode", "?"),
                            err=round(err_c, 3) if err_c is not None else None,
                            trk=tracker.is_tracking)
                dist_mode = getattr(follower, "_dist_mode", "?")
                cv2.putText(frame,
                            f"WHEEL v={v:+.2f} w={w:+.2f} dist={follower.last_dist_cm:.0f}cm [{dist_mode}]",
                            (6, h_f - 12), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 1)
            else:
                cv2.putText(frame, f"[{follower.state}] Nav2 controlling. type '추종' to follow.",
                            (6, h_f - 12), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 200, 255), 1)
                if follower.state == "RETURN":
                    set_robot_led(follower.esp_ip, "RUNNING")
                elif follower.state == "STOPPED":
                    set_robot_led(follower.esp_ip, "STOPPED")

        global _REC
        if RECORD_SEC > 0:
            now_r = time.time()
            if _REC is None:
                path = str(HERE / "debug" / f"record_{time.strftime('%Y%m%d_%H%M%S')}.mp4")
                _REC = {"vw": cv2.VideoWriter(path, cv2.VideoWriter_fourcc(*"mp4v"),
                                              15.0, (w_f, h_f)),
                        "path": path, "t0": now_r, "last": 0.0}
                print(f"[record] 녹화 시작: {path} ({RECORD_SEC:.0f}초)")
            if now_r - _REC["last"] >= 1.0 / 15.0:
                _REC["vw"].write(frame)
                _REC["last"] = now_r
            if now_r - _REC["t0"] >= RECORD_SEC:
                _REC["vw"].release()
                print(f"[record] 녹화 완료({RECORD_SEC:.0f}초) → {_REC['path']} — 자동 종료")
                break

        cv2.imshow(WINDOW, frame)
        if (cv2.waitKey(1) & 0xFF) == ord("q"):
            break

        if frame_count % 30 == 0:
            print(f"[perf] {hud}")


def console_input_thread(follower):
    print("  - '복귀' 입력 → 시작 위치(AMCL 기록)로 Nav2 복귀")
    print("  - '추종' 입력 → 다시 FOLLOW 모드")
    print("  - '정지' 입력 → 비상 정지 및 빨간불")
    while True:
        try:
            cmd = input().strip()
        except (EOFError, KeyboardInterrupt):
            break
        if cmd == "복귀":
            if follower.state != "RETURN":
                follower.state = "RETURN"
                follower.send_stop()
                set_robot_led(follower.esp_ip, "RUNNING")
                if not follower.has_start_pose:
                    follower.get_logger().warn(
                        "AMCL 시작 위치 미저장 → (0,0) 으로 복귀 시도. RViz 2D Pose Estimate 권장.")
                follower.send_nav_goal(follower.start_x, follower.start_y, follower.start_yaw)
        elif cmd == "추종":
            if follower.state != "FOLLOW":
                follower.cancel_nav()
                if not follower.is_registered:
                    follower.trigger_register = True
                    follower.get_logger().info("FOLLOW 요청 수신 -> 신규 사용자 등록을 시작합니다.")
                else:
                    follower.state = "FOLLOW"
                    follower.send_stop()
                    set_robot_led(follower.esp_ip, "STANDBY")
                    follower.get_logger().info("FOLLOW 모드로 전환 (기등록 사용자).")
        elif cmd == "정지":
            follower.cancel_nav()
            follower.state = "STOPPED"
            follower.send_stop()
            set_robot_led(follower.esp_ip, "STOPPED")
            follower.get_logger().info("정지(STOPPED) 모드로 전환. LED 빨간불.")
