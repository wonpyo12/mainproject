"""디버그 로그(JSONL) — analyze_debug.py 로 분석."""
import json
import time
from datetime import datetime

from .config import HERE


# ══════════════════════════════════════════════════════════════════════════════
# 디버그 로그 (JSONL) — analyze_debug.py 로 분석
# ══════════════════════════════════════════════════════════════════════════════

class DebugLog:
    """인식/주행 이벤트를 debug_logs/run_*.jsonl 에 기록. 비활성화 시 no-op."""

    def __init__(self, enabled: bool = False):
        self.f = None
        self.path = None
        if enabled:
            self.enable()

    def enable(self):
        """로그 파일을 열어 기록을 시작한다 (이미 열려 있으면 무시).

        객체를 새로 만들지 않고 내부 상태만 바꾼다 — 각 모듈이 import 해 둔
        DBG 참조가 그대로 유효해야 하기 때문.
        """
        if self.f is not None:
            return
        d = HERE / "debug" / "debug_logs"
        d.mkdir(parents=True, exist_ok=True)
        self.path = d / f"run_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jsonl"
        self.f = open(self.path, "w", encoding="utf-8", buffering=1)  # 줄 단위 flush

    def log(self, ev: str, **kw):
        if self.f is None:
            return
        kw["ev"] = ev
        kw["t"] = round(time.time(), 3)
        try:
            self.f.write(json.dumps(kw, ensure_ascii=False) + "\n")
        except Exception:
            pass


# 전역 싱글톤 — main()에서 DBG.enable() 로 켠다.
# (객체를 교체하지 않고 내부 상태만 바꿔야 각 모듈이 import 한 참조가 유효하다)
DBG = DebugLog()


