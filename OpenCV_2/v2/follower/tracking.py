"""추종 루프 — 매칭 판정·화면 표시·주행 명령."""
import time

import cv2

import light_features as LF

from . import config
from .debug_log import DBG
from .detection import DetectionWorker, MosseBoxTracker
from .notify import set_robot_led
from .registration import register
from .util import clamp
from .config import (AUTO_RETURN_SEC, DETECT_INTERVAL, HERE, KCF_MAX_AGE,
    POST_REGISTER_WAIT_SEC, PRED_MAX_VX, SEARCH_START_DELAY, SOFT_MATCH_THR, WINDOW)

_REC = None   # 화면 녹화 상태(VideoWriter 등)


# ══════════════════════════════════════════════════════════════════════════════
# 추종 루프 (cv2.imshow 표시 + 인식률 % + 주행 연동)
# ══════════════════════════════════════════════════════════════════════════════

def interp_step(kcf, tracker, frame, new_frame, kcf_age):
    """검출 공백 구간의 bbox 보간 한 스텝. → (draw_bbox, interp, kcf_age)

    카메라 수신(≈9fps)보다 루프가 훨씬 빨라 같은 프레임이 반복 처리되므로,
    새 프레임일 때만 트래커를 돌리고 같은 프레임이면 직전 보간 박스를 재사용한다.
    """
    if new_frame:
        kb = kcf.update(frame)
        kcf_age += 1
    else:
        kb = tracker.last_bbox
    if kb is None:
        return None, False, kcf_age
    tracker.last_bbox = kb
    return kb, True, kcf_age

def run_tracking(cam, yolo, reid, face, profile, use_face=True, follower=None):
    tracker = LF.TrackingState()
    last_harvest = {}   # 온라인 프로필 보강 — phase별 마지막 수확 시각
    # [sh 인식] 촬영 직후 빠른 진입(warm_start) 미사용 — sh 원본대로 진입도 동일 기준(from_search) 적용
    kcf = MosseBoxTracker()   # 보간 트래커 (MOSSE — KCF 대비 8배 경량)
    kcf_age = 0
    rx_last = -1              # 새 카메라 프레임에서만 트래커 업데이트 (동일 프레임 반복 연산 방지)
    frame_count = 0
    none_n = 0        # 연속 프레임 미수신 카운터 (스트림 끊김 안전 정지용)
    perf_t = time.time()          # 주기적 성능 스냅샷 타이머
    perf_frames = 0
    perf_rx0 = cam.rx_count() if hasattr(cam, "rx_count") else 0
    pred_vx = 0.0                 # 등록자 수평 이동 속도 추정 (px/s, 예측 조향용)
    prev_cx, prev_match_t = None, 0.0
    last_seen_t = time.time()     # 등록자 마지막 확인 시각 — 유실 후 SEARCH_START_DELAY 지나야 탐색 회전
    fps_t, fps_n, fps_val = time.time(), 0, 0.0

    avg = {"det": 0.0, "reid": 0.0}
    last_seq = 0
    cur_label = "-"
    cur_pct = 0
    last_bboxes, last_scores = [], {}
    reg_det_bbox = None

    worker = DetectionWorker(yolo, reid, face, profile, use_face)
    worker.start()

    # KCF 보간 추적기 가용성 확인 (opencv-contrib 없으면 조용히 죽어 있던 문제 가시화)
    try:
        MosseBoxTracker._create()
        kcf_env = True
    except Exception:
        kcf_env = False
        print("[경고] OpenCV KCF 추적기 없음 → 검출 사이 bbox 보간 비활성 (마지막 위치 조향으로 대체 동작). "
              "개선하려면 VM에서: pip install opencv-contrib-python")
    DBG.log("env", kcf=kcf_env)

    print("=== 추종 시작 ===  (화면 'q' 종료 / 터미널 '복귀'·'추종' 입력으로 모드 전환)")
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
            # [07-15] 촬영 직후 바로 출발하지 않고 대기 — 사용자가 자세/위치 잡을 시간
            # (음성 안내 없음 — "촬영이 끝났습니다"가 마지막 TTS)
            _t5 = time.time() + POST_REGISTER_WAIT_SEC
            while time.time() < _t5:
                cam.read()          # 대기 중 프레임 소모 (스트림 밀림 방지)
                time.sleep(0.05)
            follower.state = "FOLLOW"
            set_robot_led(follower.esp_ip, "STANDBY")
            tracker.reset(); kcf.deinit(); reg_det_bbox = None
            # [sh 인식] warm_start 미사용 — sh 원본대로 재획득도 동일 기준(from_search) 적용
            last_bboxes, last_scores = [], {}
            follower.reset_search()
            last_seen_t = time.time()   # 촬영 직후 = 대상이 바로 앞 → 유실 탐색 대기 타이머 리셋
            continue

        frame = cam.read()
        if frame is None:
            # 스트림 끊김: 라이다 브리징 시도, 안 되면 정지 명령 (마지막 속도 유지 방지)
            none_n += 1
            if none_n == 5:
                DBG.log("gap_start")
            if follower is not None and none_n >= 5 and none_n % 5 == 0:
                br = follower.lidar_bridge() if follower.state == "FOLLOW" else None
                if br is not None:
                    follower.send_velocity(*br)
                else:
                    follower.send_velocity(0.0, 0.0)
            time.sleep(0.02); continue
        if none_n >= 5:
            DBG.log("gap_end", n=none_n)
        none_n = 0
        frame_count += 1
        perf_frames += 1
        h_f, w_f = frame.shape[:2]
        # 카메라 수신(≈9fps)보다 루프(수십fps)가 훨씬 빨라 같은 프레임이 반복 처리됨 —
        # 트래커 업데이트는 새 프레임에서만 수행 (동일 프레임에 MOSSE/KCF 재실행 낭비 제거)
        rx_now = cam.rx_count() if hasattr(cam, "rx_count") else frame_count
        new_frame = (rx_now != rx_last)
        rx_last = rx_now

        # 5초마다 성능 스냅샷 (루프 fps / 카메라 수신 fps / 추론 시간 이동평균)
        now = time.time()
        if now - perf_t >= 5.0:
            rx = cam.rx_count() if hasattr(cam, "rx_count") else 0
            DBG.log("perf", loop_fps=round(perf_frames / (now - perf_t), 1),
                    rx_fps=round((rx - perf_rx0) / (now - perf_t), 1),
                    det_ms=round(avg["det"], 1), reid_ms=round(avg["reid"], 1))
            perf_t, perf_frames, perf_rx0 = now, 0, rx

        # [기능 2] 복귀(RETURN) 중엔 추종 연산 정지 (SLAM/Nav2 전용). FOLLOW→RETURN 전환 시 추적 리셋.
        cur_state = follower.state if follower is not None else "FOLLOW"
        
        # AUTO_RETURN_SEC 이상 사람 미인식 시 자동 원점 복귀 트리거
        if (follower is not None
                and cur_state == "FOLLOW"
                and follower.is_registered
                and last_seen_t is not None
                and (time.time() - last_seen_t > AUTO_RETURN_SEC)):

            follower.get_logger().info(
                f"{AUTO_RETURN_SEC:.0f}초 동안 사람 미인식 -> 자동 원점 복귀를 수행합니다.")
            DBG.log("ros_cmd", cmd="auto_return_60s", prev_state="FOLLOW")
            follower.state = "RETURN"
            follower.is_registered = False  # 다음 사용자를 위해 등록 리셋
            follower.send_stop()
            set_robot_led(follower.esp_ip, "RUNNING")
            if not follower.has_start_pose:
                follower.get_logger().warn("AMCL 시작 위치 미저장 → (0,0) 복귀 시도.")
            follower.send_nav_goal(follower.start_x, follower.start_y, follower.start_yaw)
            
            # 상태 변수 업데이트 및 추적 리셋
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
            last_seen_t = time.time()   # FOLLOW 재진입 → 유실 탐색 대기 타이머 리셋
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
            # [히스테리시스] 진입 엄격 / 유지 느슨: 상태별로 임계값·하드게이트를 다르게 적용
            #   추적 유지 = KEEP(0.56) + ReID 하한 완화(0.45) + 색상 게이트 생략
            #   유실 후 재획득 = SEARCH(0.65), 최초 진입 = MATCH(0.74) + 진입 게이트(0.55/0.15)
            if tracker.is_tracking:
                thr = LF.KEEP_THRESHOLD
                reid_floor, color_floor = LF.KEEP_REID_FLOOR, 0.0
            else:
                # 탐색·확정(confirm) 공통 임계 — 확정 프레임에만 MATCH(0.74)를 적용하면
                # 본인 점수가 71~74%일 때 68↔74 핑퐁으로 진입이 영구 불가(실측 확인).
                # 연속 매칭(SEARCH_CONFIRM_FRAMES) 요구가 타인 차단을 담당한다.
                thr = LF.SEARCH_MATCH_THR
                reid_floor, color_floor = LF.REID_FLOOR, LF.COLOR_FLOOR
            reid_ok = detail is not None and detail.get("reid", 0) >= reid_floor
            color_ok = detail is not None and detail.get("color", 0) >= color_floor
            matched = (bb is not None and total >= thr and reid_ok and color_ok)
            # [이슈 #48] 유실 재획득 구제: 탐색 중 color 붕괴로 total 미달이어도
            # ReID가 충분히 높으면(0.62↑) 재획득 허용. 최초 진입에는 미적용(had_track).
            # SEARCH_CONFIRM_FRAMES(3연속)가 그대로 적용되어 타인 오인식을 이중 차단.
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
                # 예측 조향용 수평 속도 추정 (연속 매칭 간 cx 변화율, 지수평활)
                t_m = time.time()
                cx_m = (bb[0] + bb[2]) / 2.0
                if prev_cx is not None and 0.05 < t_m - prev_match_t < 1.5:
                    vx_now = (cx_m - prev_cx) / (t_m - prev_match_t)
                    pred_vx = 0.6 * pred_vx + 0.4 * clamp(vx_now, -PRED_MAX_VX, PRED_MAX_VX)
                prev_cx, prev_match_t = cx_m, t_m
                # [온라인 프로필 보강] 고신뢰 프레임 임베딩 자동 수확.
                # 가드: ①ReID≥0.75(유지 임계보다 훨씬 엄격) ②추적 성립 상태만(confirm/rescue 제외)
                #       ③2초 간격 ④등록 원본 불변, 수확 풀만 오래된 것부터 교체
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
                # [유지 느슨] 한 프레임 리젝됐다고 KCF를 버리지 않는다. 추적이 살아 있으면
                # (lost N/LOST_MAX 유예 중) KCF 보간으로 초록 박스를 유지하고,
                # 실제로 추적이 끊겼을 때(is_tracking=False)만 폐기 → "잠깐 유실→주황/탐색" 방지.
                if tracker.is_tracking and kcf.ok:
                    draw_bbox, interp, kcf_age = interp_step(
                        kcf, tracker, frame, new_frame, kcf_age)
                else:
                    kcf.deinit()
            # [기능 3] 인식률 % 터미널 로그 (임계값 튜닝 근거)
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
            draw_bbox, interp, kcf_age = interp_step(
                kcf, tracker, frame, new_frame, kcf_age)

        if draw_bbox is not None:
            last_seen_t = time.time()   # 등록자 확인 → 유실 탐색 대기 타이머 갱신

        # 비등록자(회색) — % 표시
        for bb in last_bboxes:
            if bb == reg_det_bbox:
                continue
            x1, y1, x2, y2 = bb
            cv2.rectangle(frame, (x1, y1), (x2, y2), (95, 95, 95), 1)
            cv2.putText(frame, f"{int(last_scores.get(bb, 0) * 100)}%", (x1, max(15, y1 - 4)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.45, (95, 95, 95), 1)

        # 등록자(초록) — 라벨에 인식률 %
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
        # [기능 3] HUD 에 현재 추종 대상 인식률 % 상시 표시
        match_tag = f"MATCH:{cur_pct}%" if tracker.is_tracking else "MATCH:--"
        hud = (f"FPS:{fps_val:.1f} {mode} det:{avg['det']:.0f} reid:{avg['reid']:.0f}ms "
               f"{match_tag} Cand:{len(last_bboxes)} {tracker.status.upper()} [{state_tag}]")
        cv2.rectangle(frame, (0, 0), (w_f, 24), (0, 0, 0), -1)
        cv2.putText(frame, hud, (6, 17), cv2.FONT_HERSHEY_SIMPLEX, 0.5,
                    (0, 255, 0) if tracker.is_tracking else (160, 160, 255), 1)

        # ── 주행 ──
        if follower is not None:
            if follower.state == "FOLLOW":
                if tracker.is_tracking and draw_bbox is not None:
                    # 검출 또는 KCF 보간 박스가 실제로 있음 = 화면에 보임 → 추종 주행
                    # (점수가 낮아 주황이어도 KCF가 살아 있으면 주행 유지 → 멈칫 방지)
                    v, w = follower.compute(draw_bbox, w_f, h_f, True)
                    follower.reset_search()      # 추종 중 → 탐색 종료
                elif tracker.is_tracking:
                    # [유실 시 정지] KCF도 놓침 = 진짜 시야에서 사라짐 → 즉시 정지.
                    # 기존엔 마지막 위치+외삽(pred_vx)으로 계속 전진했는데, 방향이 틀리면
                    # 불안정 전진이 되므로 제거. 재매칭되면 위 분기로 복귀해 그 방향 전진.
                    v, w = 0.0, 0.0
                elif draw_bbox is not None:      # 재확인(confirm) 중 → 회전 말고 정지 대기
                    v, w = 0.0, 0.0
                    follower.reset_search()
                else:                            # 완전 유실 → 좌우 탐색 회전 (sh 방식)
                    # 소프트 매치(후보 스코어 SOFT_MATCH_THR↑): 회전 멈추고 confirm 기회 부여
                    if (fresh and det["best_total"] > SOFT_MATCH_THR
                            and det["best_bbox"] is not None):
                        v, w = 0.0, 0.0
                        follower.reset_search()
                    elif time.time() - last_seen_t < SEARCH_START_DELAY:
                        v, w = 0.0, 0.0          # 유실 5초 미만 → 정지 대기 (재등장 기대, 회전이 재인식 방해 방지)
                        follower.reset_search()
                    else:
                        v, w = follower.search_rotate()
                
                # 사람이 인식되면 초록불(RUNNING), 인식되지 않으면(유실/재확인 포함) 즉시 노란불(STANDBY)
                if draw_bbox is not None:
                    set_robot_led(follower.esp_ip, "RUNNING")
                else:
                    set_robot_led(follower.esp_ip, "STANDBY")
                    
                # 매 루프 발행(~15-20Hz) — 가속도 필터가 있어 급변 없이 촘촘하게 갱신
                follower.send_velocity(v, w)
                if frame_count % 3 == 0:        # 로그는 ≈5-7Hz로 샘플링
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
            else:  # RETURN / IDLE — Nav2 가 /cmd_vel 통제
                cv2.putText(frame, f"[{follower.state}] Nav2 controlling. type '추종' to follow.",
                            (6, h_f - 12), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 200, 255), 1)
                
                # Nav2 복귀 동작 중에는 초록불(RUNNING)
                if follower.state == "RETURN":
                    set_robot_led(follower.esp_ip, "RUNNING")
                elif follower.state == "STOPPED":
                    set_robot_led(follower.esp_ip, "STOPPED")

        # ── 화면 녹화 (--record-sec) : HUD 포함 프레임을 mp4로 저장, 시간 경과 시 자동 종료 ──
        global _REC
        if config.RECORD_SEC > 0:
            now_r = time.time()
            if _REC is None:
                path = str(HERE / "debug" / f"record_{time.strftime('%Y%m%d_%H%M%S')}.mp4")
                _REC = {"vw": cv2.VideoWriter(path, cv2.VideoWriter_fourcc(*"mp4v"),
                                              15.0, (w_f, h_f)),
                        "path": path, "t0": now_r, "last": 0.0}
                print(f"[record] 녹화 시작: {path} ({config.RECORD_SEC:.0f}초)")
            if now_r - _REC["last"] >= 1.0 / 15.0:
                _REC["vw"].write(frame)
                _REC["last"] = now_r
            if now_r - _REC["t0"] >= config.RECORD_SEC:
                _REC["vw"].release()
                print(f"[record] 녹화 완료({config.RECORD_SEC:.0f}초) → {_REC['path']} — 자동 종료")
                break

        cv2.imshow(WINDOW, frame)
        if (cv2.waitKey(1) & 0xFF) == ord("q"):
            break

        if frame_count % 30 == 0:
            print(f"[perf] {hud}")




def close_recorder():
    """녹화 중이면 파일을 닫는다 (q 종료 등 조기 종료 시 파일 보존)."""
    global _REC
    if _REC is not None:
        _REC["vw"].release()
        _REC = None
