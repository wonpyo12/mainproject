#!/usr/bin/env python3
"""추종 디버그 로그(debug_logs/run_*.jsonl) 자동 진단.

  python3 analyze_debug.py            # 가장 최근 로그 분석
  python3 analyze_debug.py <파일>     # 특정 로그 분석

성능(추론/수신 fps), 인식 점수 분포, 추적 유지율, 주행 명령 이력을 요약하고
발견된 문제를 규칙 기반으로 짚어준다.
"""
import json
import statistics
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(errors="replace")   # 콘솔 인코딩(cp949 등)에 없는 문자 안전 처리

HERE = Path(__file__).parent


def load(path: Path):
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            rows.append(json.loads(line))
        except Exception:
            pass
    return rows


def pct(vals, p):
    if not vals:
        return 0.0
    s = sorted(vals)
    return s[min(len(s) - 1, int(len(s) * p / 100))]


def main():
    if len(sys.argv) > 1:
        path = Path(sys.argv[1])
    else:
        logs = sorted((HERE / "debug_logs").glob("run_*.jsonl"))
        if not logs:
            print("debug_logs/ 에 로그가 없습니다. 먼저 추종을 한 번 실행하세요.")
            return
        path = logs[-1]

    rows = load(path)
    if not rows:
        print(f"{path.name}: 비어 있음")
        return

    dur = rows[-1]["t"] - rows[0]["t"]
    dets = [r for r in rows if r["ev"] == "det"]
    cmds = [r for r in rows if r["ev"] == "cmd"]
    perfs = [r for r in rows if r["ev"] == "perf"]
    gaps = [r for r in rows if r["ev"] == "gap_end"]
    regs = [r for r in rows if r["ev"] == "register"]
    start = next((r for r in rows if r["ev"] == "start"), {})

    print(f"== {path.name}  ({dur:.0f}초, 이벤트 {len(rows)}건) ==")
    if start:
        print(f"설정: imgsz={start.get('imgsz')} reid={start.get('reid_model')} "
              f"mirror={start.get('mirror')} invert_turn={start.get('invert_turn')} "
              f"CPU={start.get('cpu')}코어")

    problems = []

    # ── 성능 ──
    if perfs:
        loop = [p["loop_fps"] for p in perfs]
        rx = [p["rx_fps"] for p in perfs]
        det_ms = [p["det_ms"] for p in perfs if p["det_ms"] > 0]
        print(f"\n[성능] 루프 {statistics.mean(loop):.1f}fps / 카메라 수신 {statistics.mean(rx):.1f}fps"
              + (f" / 검출 {statistics.mean(det_ms):.0f}ms" if det_ms else ""))
        if statistics.mean(rx) < 5:
            problems.append(f"카메라 수신 {statistics.mean(rx):.1f}fps — 너무 낮음. "
                            "Wi-Fi 혼잡 또는 라파 스트리머 문제 (다른 스트림 시청자 수도 확인)")
        if det_ms and statistics.mean(det_ms) > 300:
            problems.append(f"검출 {statistics.mean(det_ms):.0f}ms — 추론 느림. "
                            "--imgsz 192 사용 및 VM 코어 할당 확인")
        if statistics.mean(loop) < 8:
            problems.append(f"메인 루프 {statistics.mean(loop):.1f}fps — 화면/제어 반응 저하. CPU 부족 신호")

    # ── 등록 품질 ──
    for r in regs:
        flag = "" if r["n"] >= 15 else "  ← 부족!"
        print(f"[등록] {r['phase']}: {r['n']}개 / {r['sec']}초 (수신 {r['rx_fps']}fps){flag}")
        if r["n"] < 10:
            problems.append(f"등록 샘플({r['phase']}) {r['n']}개뿐 — 프로필 부실. "
                            "조명 확인, 1~2m 거리에서 재등록 권장")

    # ── 인식 점수 ──
    scored = [d for d in dets if d.get("total") is not None]
    if scored:
        ok = [d["total"] for d in scored if d["ok"]]
        rej = [d["total"] for d in scored if not d["ok"]]
        n_match = len(ok)
        print(f"\n[인식] 판정 {len(scored)}회: MATCH {n_match} / reject {len(rej)}"
              f" (매칭률 {n_match / len(scored) * 100:.0f}%)")
        if ok:
            print(f"  MATCH 점수: 평균 {statistics.mean(ok):.3f} (최저 {min(ok):.3f})")
        if rej:
            print(f"  reject 점수: 평균 {statistics.mean(rej):.3f} / 상위10% {pct(rej, 90):.3f}")
            thr_now = statistics.mode([d["thr"] for d in scored])
            near = [v for v in rej if thr_now - 0.06 <= v < thr_now]
            if len(near) > len(scored) * 0.3:
                problems.append(f"reject의 {len(near) / len(rej) * 100:.0f}%가 임계값({thr_now}) 바로 아래 "
                                f"({pct(near, 50):.2f} 부근) — 본인이 튕기는 패턴. "
                                f"임계값을 {pct(near, 30):.2f} 수준으로 낮추면 통과 예상")
        if len(scored) / max(dur, 1) < 1.0:
            problems.append(f"인식 판정이 {len(scored) / max(dur, 1):.1f}회/초 — 검출 주기 너무 낮음 (성능 항목 참조)")
        reid_low = [d for d in scored if d.get("reid") is not None and d["reid"] < 0.53 and not d["ok"]]
        if len(reid_low) > len(scored) * 0.4:
            problems.append(f"reject 중 ReID 하한(0.53) 미달이 다수({len(reid_low)}회) — "
                            "프로필과 실제 모습 차이 큼. 재등록(정확한 앞/뒤) 권장")

    # ── 추적/주행 ──
    if cmds:
        trk = [c for c in cmds if c.get("trk")]
        print(f"\n[주행] 명령 {len(cmds)}회, 추적 중 비율 {len(trk) / len(cmds) * 100:.0f}%")
        modes = {}
        for c in cmds:
            modes[c.get("mode", "?")] = modes.get(c.get("mode", "?"), 0) + 1
        print(f"  거리 소스: {modes}")
        if modes.get("Camera", 0) > 0 and modes.get("LiDAR", 0) == 0:
            problems.append("라이다 거리값이 한 번도 안 쓰임 — /scan 토픽이 VM에 도착하는지 확인 "
                            "(ros2 topic hz /scan)")
        errs = [abs(c["err"]) for c in trk if c.get("err") is not None]
        if errs and pct(errs, 90) > 0.6:
            problems.append(f"추적 중 사람이 화면 가장자리(|오차| {pct(errs, 90):.2f})에 자주 위치 — "
                            "회전이 못 따라감. KP_ANG 상향 또는 MAX_ANG 확인")
        moving = [c for c in trk if abs(c["v"]) > 0.02 or abs(c["w"]) > 0.05]
        if trk and len(moving) < len(trk) * 0.2:
            problems.append("추적 중인데 정지 명령이 대부분 — 거리(DIST_NEAR/FAR 데드존)나 "
                            "전방 차단(front_blocked) 과다 여부 확인")

    if gaps:
        total_gap = sum(g.get("n", 0) for g in gaps) * 0.02
        print(f"\n[스트림] 끊김 {len(gaps)}회, 누적 약 {total_gap:.1f}초")
        if len(gaps) / max(dur / 60, 0.1) > 3:
            problems.append(f"스트림 끊김 분당 {len(gaps) / max(dur / 60, 0.1):.1f}회 — 네트워크 불안정. "
                            "라파 스트리머 q35/10fps 적용 여부, 공유기 혼잡 확인")

    # ── 진단 결과 ──
    print("\n== 진단 ==")
    if problems:
        for i, p in enumerate(problems, 1):
            print(f"{i}. {p}")
    else:
        print("특이 문제 없음 — 정상 범위로 보입니다.")


if __name__ == "__main__":
    main()
