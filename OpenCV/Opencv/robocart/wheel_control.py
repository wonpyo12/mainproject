#!/usr/bin/env python3
"""
SmartCart 바퀴 추종 제어 (TurtleBot3 Burger 전용)

robocart_main.py 의 사용자 인식 결과(bbox)를 받아 /cmd_vel (geometry_msgs/Twist)
를 발행한다. TurtleBot3 표준 주행 스택(turtlebot3_bringup)이 /cmd_vel 을 구독해
바퀴를 구동하므로, 이 파일은 '인식 → 속도 명령' 변환만 담당한다.

제어:
  - 거리 유지(전후진): bbox 높이로 거리를 추정 → 목표 높이 비율과의 오차 P제어 → linear.x
  - 좌우 추종(회전):  bbox 중심의 좌우 편차 P제어 → angular.z
  - 안전: 미추적(is_tracking=False)이면 즉시 정지, 속도 상한 제한, (1차엔)후진 금지

주의:
  - 카메라 pan 서보(ESP32, raspi_cmd_bridge.py)와는 완전히 별개 경로다.
  - 유실 시 카메라 모터 재탐색 기능은 이번 단계 제외.

사용:
  # 1) 인식과 연동 (robocart_main.py 에서 --follow 로 호출)
  bash robocart.sh start --follow

  # 2) 단독 배선 점검 (인식 없이 /cmd_vel 직접 발행 — 로봇/시뮬레이터 동작 확인용)
  source /opt/ros/humble/setup.bash
  python3 wheel_control.py --test spin --secs 2
  python3 wheel_control.py --test forward --secs 1
  python3 wheel_control.py --test stop
"""
from __future__ import annotations

import argparse
import sys
import time

try:
    import rclpy
    from rclpy.node import Node
    from geometry_msgs.msg import Twist
    _ROS2_OK = True
except ImportError:
    _ROS2_OK = False


# ── TurtleBot3 Burger 하드 속도 한계 (이 값 이상은 절대 내보내지 않음) ──────────
BURGER_MAX_LIN = 0.22   # m/s
BURGER_MAX_ANG = 2.84   # rad/s

# ── 거리 추정 (bbox 폭 기반, 핀홀 모델) ───────────────────────────────────────
# 근거리(60~80cm)에선 서 있는 사람이 세로로 화면 밖으로 잘려 bbox 높이가 부정확.
# 폭은 잘리지 않으므로 폭을 쓴다. 같은 사람: 거리 × 폭(px) = 상수(CALIB_K).
#   거리[cm] = CALIB_K / bbox_width[px]
# CALIB_K 는 알려진 거리에서 1회 보정해 확정한다(아래 기본값은 C920 기하 추정치).
#   보정법: 70cm 에 서서 HUD 의 dist 표시값을 보고, CALIB_K *= (실제70 / 표시값)
CALIB_K       = 22000.0   # ≈ 70cm × 약 314px (실차 보정 필요)
TARGET_DIST_CM = 70.0     # 목표 추종 거리 (60~80 가운데)
DIST_NEAR_CM   = 60.0     # 이보다 가까우면 정지(후진 비허용 시)
DIST_FAR_CM    = 80.0     # 이보다 멀면 전진
                          # → 60~80 구간 안이면 정지 = 사용자 정지 시 로봇 정지

CENTER_DEADBAND = 0.12    # 중심 편차(정규화)가 이 이내면 회전 정지(전진 유지)

KP_LIN_DIST = 0.004  # 거리 오차[cm] → 선속도 게인 (err 30cm 에서 약 MAX_LIN)
KP_ANG      = 0.5    # 좌우 편차 → 각속도 게인 (제자리 회전 방지 위해 낮춤)

# 운용 상한 (Burger 하드 한계보다 보수적으로 — 첫 확인 단계는 천천히)
MAX_LIN = 0.12       # m/s (전진 상한)
MAX_LIN_REV = 0.08   # m/s (후진 상한 — 후방 센서 없어 블라인드라 더 보수적으로)
MAX_ANG = 0.5        # rad/s (전진을 덮어쓰는 강한 회전 금지 → 제자리 스핀 방지)
ALLOW_REVERSE = True # 60cm 보다 가까우면 뒤로 물러나 거리 유지


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


class WheelFollower:
    """인식 bbox → /cmd_vel(Twist) 변환·발행기.

    구독/타이머가 없으므로 spin 이 필요 없다(publish 만 함). rclpy 가 아직
    init 되지 않았으면 스스로 init 한다(다른 모드와 충돌 없이 재사용 가능).
    """

    def __init__(self, topic: str = "/cmd_vel"):
        if not _ROS2_OK:
            raise RuntimeError(
                "rclpy/geometry_msgs 불러오기 실패 — "
                "source /opt/ros/humble/setup.bash 후 실행하세요.")
        if not rclpy.ok():
            rclpy.init()
        self._node = Node("robocart_wheel_follower")
        self._pub = self._node.create_publisher(Twist, topic, 10)
        self._node.get_logger().info(f"바퀴 추종 시작 → {topic} (Twist) 발행")
        self.last_v = 0.0
        self.last_w = 0.0
        self.last_dist_cm = 0.0   # HUD 표시·보정용 추정 거리

    def compute(self, bbox, frame_w: int, frame_h: int, is_tracking: bool):
        """bbox·추적상태 → (선속도 v[m/s], 각속도 w[rad/s]). 발행은 하지 않음."""
        if not is_tracking or bbox is None or frame_w <= 0 or frame_h <= 0:
            self.last_dist_cm = 0.0
            return 0.0, 0.0

        x1, y1, x2, y2 = bbox
        bbox_w = max(1, x2 - x1)
        cx = (x1 + x2) / 2.0

        # ── 거리 제어: bbox 폭으로 거리 추정(핀홀), 60~80cm 유지 ──
        dist_cm = CALIB_K / bbox_w
        self.last_dist_cm = dist_cm
        if DIST_NEAR_CM <= dist_cm <= DIST_FAR_CM:
            v = 0.0                                   # 유지 구간 → 정지(사용자 정지 시 정지)
        else:
            err_dist = dist_cm - TARGET_DIST_CM       # +면 멀다 → 전진, -면 가까움 → 후진
            v = _clamp(KP_LIN_DIST * err_dist, -MAX_LIN, MAX_LIN)
            if v < 0:
                if not ALLOW_REVERSE:
                    v = 0.0
                else:
                    v = max(v, -MAX_LIN_REV)          # 후진은 더 보수적으로 제한

        # ── 방향 제어: bbox 중심의 좌우 편차 ──
        err_center = (cx - frame_w / 2.0) / (frame_w / 2.0)   # [-1,1], +면 우측
        if abs(err_center) < CENTER_DEADBAND:
            w = 0.0
        else:
            # 대상이 우측(+)이면 시계방향 회전 = angular.z 음수
            w = _clamp(-KP_ANG * err_center, -MAX_ANG, MAX_ANG)

        return v, w

    def update(self, bbox, frame_w: int, frame_h: int, is_tracking: bool):
        """compute 후 곧바로 /cmd_vel 발행. (v, w) 반환(HUD 표시용)."""
        v, w = self.compute(bbox, frame_w, frame_h, is_tracking)
        self.publish(v, w)
        return v, w

    def publish(self, v: float, w: float) -> None:
        # 하드 한계 재클램프 (어떤 경로로 들어와도 Burger 한계 초과 금지)
        v = _clamp(v, -BURGER_MAX_LIN, BURGER_MAX_LIN)
        w = _clamp(w, -BURGER_MAX_ANG, BURGER_MAX_ANG)
        msg = Twist()
        msg.linear.x = float(v)
        msg.angular.z = float(w)
        self._pub.publish(msg)
        self.last_v, self.last_w = v, w

    def stop(self) -> None:
        self.publish(0.0, 0.0)

    def destroy(self) -> None:
        try:
            self.stop()
            self._node.destroy_node()
        except Exception:
            pass


# ══════════════════════════════════════════════════════════════════════════════
# 단독 배선 점검 모드 (인식 없이 /cmd_vel 직접 발행)
# ══════════════════════════════════════════════════════════════════════════════

def _run_test(mode: str, secs: float, topic: str) -> int:
    table = {
        "forward": (0.08, 0.0),
        "back":    (-0.08, 0.0),
        "left":    (0.0,  0.5),
        "right":   (0.0, -0.5),
        "spin":    (0.0,  0.5),
        "stop":    (0.0,  0.0),
    }
    if mode not in table:
        print(f"[오류] 알 수 없는 test 모드: {mode}")
        return 1
    v, w = table[mode]
    f = WheelFollower(topic)
    print(f"[test] {mode}: v={v} w={w}  {secs}초간 10Hz 발행 → 이후 정지")
    try:
        t_end = time.time() + secs
        while time.time() < t_end:
            f.publish(v, w)
            time.sleep(0.1)
    except KeyboardInterrupt:
        pass
    finally:
        f.stop()
        time.sleep(0.2)
        f.destroy()
        if rclpy.ok():
            rclpy.shutdown()
    print("[test] 완료(정지 명령 발행)")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description="TurtleBot3 Burger 바퀴 추종/점검")
    p.add_argument("--test", choices=["forward", "back", "left", "right", "spin", "stop"],
                   help="인식 없이 /cmd_vel 직접 발행해 배선/구동 확인")
    p.add_argument("--secs", type=float, default=2.0, help="test 발행 지속 시간(초)")
    p.add_argument("--topic", default="/cmd_vel", help="발행 토픽 (기본 /cmd_vel)")
    args = p.parse_args()

    if not _ROS2_OK:
        print("[오류] rclpy 없음 — source /opt/ros/humble/setup.bash 후 실행하세요.")
        return 1

    if args.test:
        return _run_test(args.test, args.secs, args.topic)

    print("단독 실행은 --test 모드만 지원합니다. 인식 연동은 robocart.sh start --follow 로 실행하세요.")
    print("예) python3 wheel_control.py --test spin --secs 2")
    return 0


if __name__ == "__main__":
    sys.exit(main())
