"""수학 유틸 — 값 제한, yaw ↔ 쿼터니언 변환."""
import math


def clamp(x, lo, hi):
    return max(lo, min(hi, x))


def yaw_to_quat(yaw: float):
    return (0.0, 0.0, math.sin(yaw / 2.0), math.cos(yaw / 2.0))


def quat_to_yaw(x, y, z, w):
    return math.atan2(2.0 * (w * z + x * y), 1.0 - 2.0 * (y * y + z * z))


