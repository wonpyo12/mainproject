"""추종 시스템 설정 — 경로·모델·주행/인식 튜닝 상수.

값 하나하나가 실측 주행 로그 근거로 정해졌다(주석 참고).
임의 변경은 주행 거동을 직접 바꾸므로 근거 없이 손대지 말 것.
"""
from pathlib import Path

# follower/ 의 부모 = OpenCV_2/v2 (모델·프로필 파일 위치 기준)
HERE = Path(__file__).resolve().parent.parent
MODELS_DIR   = HERE / "models_light"
PROFILE_PATH = HERE / "robocart_profile_v3.json"
REID_ONNX  = MODELS_DIR / "osnet_x1_0.onnx"

# ── 런타임 설정 (main() 에서 실행 인자로 갱신) ────────────────────────────────
# 다른 모듈은 반드시 `from . import config` 후 `config.X` 로 읽을 것.
# `from .config import X` 로 가져오면 main 의 갱신이 전달되지 않는다.
RECORD_SEC = 0.0           # --record-sec: 화면 녹화 시간(초), 0=끔
REID_MODEL_NAME = "x1_0"   # --reid-model 값으로 갱신. 프로필 호환성 검사용
YUNET_ONNX = MODELS_DIR / "face_detection_yunet.onnx"
YOLO_ONNX_BY_SZ = {320: MODELS_DIR / "yolov8n.onnx",
                   256: MODELS_DIR / "yolov8n_256.onnx",
                   192: MODELS_DIR / "yolov8n_192.onnx"}

DETECT_INTERVAL = 8      # 검출 사이 KCF 보간 프레임 수
KCF_MAX_AGE     = 40     # KCF 단독 보간 허용 최대 (초과 시 강제 재검출)
# 이 시간(초)보다 오래된 프레임은 없는 것으로 처리 — 끊긴 스트림으로 주행 판단 방지
FRAME_STALE_SEC = 2.0

WINDOW = "robocart v5 - Registered User Follow + Nav2"


def pick_yolo_onnx(imgsz: int):
    p = YOLO_ONNX_BY_SZ.get(imgsz)
    if p and p.exists():
        return p, imgsz
    return MODELS_DIR / "yolov8n.onnx", 320



# ══════════════════════════════════════════════════════════════════════════════
# 주행 제어 노드 — FOLLOW(bbox→cmd_vel) + RETURN(Nav2 복귀)
# ══════════════════════════════════════════════════════════════════════════════

# TurtleBot3 Burger 하드 속도 한계 (절대 초과 금지)
BURGER_MAX_LIN = 0.22
BURGER_MAX_ANG = 2.84

# 거리 추정(bbox 폭 핀홀): 거리[cm] = CALIB_K / bbox_width[px]  (실차 보정 필요)
CALIB_K        = 22000.0
# 거리 유지 기준: TARGET 35 / NEAR 30 / FAR 40 cm (NEAR 30cm > FRONT_STOP 25cm)
TARGET_DIST_CM = 35.0
DIST_NEAR_CM   = 30.0
DIST_FAR_CM    = 40.0
CENTER_DEADBAND = 0.05   # 0.08→0.05: 중앙 유지 판정 강화
# 중앙 우선 주행: |중심 오차|×이 값 만큼 전진 감속 (1.5면 오차 0.67에서 전진 0)
CENTER_HOLD_GAIN = 1.5

KP_LIN_DIST = 0.006      # 0.004→0.006: 사람 보행 속도 대응 (err 20cm 이상이면 MAX_LIN 도달)
KP_ANG      = 0.8        # 0.5→0.8: 회전 추종 반응 강화 (시야 이탈 방지)
MAX_LIN     = 0.16       # [07-15] 0.18의 90% — 전원 상황 맞춤 감속 (원복: 0.18)
MAX_LIN_REV = 0.08
MAX_ANG     = 0.9        # [07-15] 1.0의 90% — 제자리 회전 전류 피크 완화 (원복: 1.0)
ALLOW_REVERSE = True

FRONT_STOP_M = 0.25      # 전방 라이다 이 거리 이내 장애물이면 전진 0 (안전)

# 유실 탐색: 등록자 놓치면 제자리서 좌우 교대 저속 회전(v=0)으로 재탐색
SEARCH_ANG         = 0.20   # 탐색 회전 각속도(rad/s)
SEARCH_HALF_PERIOD = 15.7   # 한 방향 회전 지속(초) — 좌우 180도(π rad) 회전: π/SEARCH_ANG ≈ 15.7초
SEARCH_START_DELAY = 5.0   # 유실 후 이 시간(초) 동안은 정지 대기, 넘겨야 탐색 회전 시작
# 유실 중 후보 점수가 이 값을 넘으면 탐색 회전을 멈추고 제자리에서 confirm 기회를 준다
# (회전이 재인식을 방해하는 것 방지). 확정 임계는 light_features 의 SEARCH_MATCH_THR.
SOFT_MATCH_THR     = 0.63

# 세션 운영
AUTO_RETURN_SEC        = 60.0  # 이 시간(초) 동안 등록자 미인식이면 자동 원점 복귀
POST_REGISTER_WAIT_SEC = 5.0   # 촬영 완료 후 출발까지 대기(초) — 사용자가 자세·위치 잡을 시간

# 등록 촬영: 방향(front/back)당 최소 샘플 수 — 미달이면 REG_MAX_SEC까지 수집 연장
REG_MIN_SAMPLES = 20
REG_MAX_SEC     = 15.0

# 라이다 브리징: 카메라 유실 직후 마지막 방위의 라이다 덩어리(사람 다리)를 잠시 추종
BRIDGE_MAX_SEC  = 2.0    # 마지막 카메라 추적 후 이 시간까지만 브리징 허용
BRIDGE_CONE_DEG = 20     # 마지막 방위 ± 탐색 콘(도)
BRIDGE_MIN_M    = 0.2    # 이보다 가까우면 무시 (로봇 자신/벽 오인 방지)
BRIDGE_MAX_M    = 1.5    # 이보다 멀면 사람 아님으로 간주
BRIDGE_MAX_LIN  = 0.10   # 브리징 중 전진 상한 (보수적, 후진 없음)
# 등록 중 YOLO 재검출 주기(샘플 단위) — 사이 프레임은 직전 bbox 재사용(ReID만)
REG_DETECT_EVERY = 5

# 부드러운 주행: 속도 명령 가속도 제한 (계단식 명령 → 미끄러지듯 변화)
ACC_LIN_UP   = 0.25   # 전진 가속 한계 (m/s²)
ACC_LIN_DOWN = 0.80   # 감속 한계 (안전상 감속은 빠르게)
ACC_ANG      = 2.5    # 회전 가속 한계 (rad/s²)

# 검출 공백 시 bbox 속도 외삽(예측 조향): 옛 위치가 아닌 현재 추정 위치로 조향
PRED_MAX_SEC = 0.8    # 마지막 검출 후 외삽 허용 최대 시간
PRED_MAX_VX  = 400.0  # 수평 이동 외삽 속도 상한 (px/s)


