"""콘솔 입력 스레드 — 터미널에서 '복귀'/'추종'/'정지' 입력."""
from .notify import set_robot_led


# ══════════════════════════════════════════════════════════════════════════════
# 콘솔 입력 스레드 ('복귀' / '추종')
# ══════════════════════════════════════════════════════════════════════════════

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
                follower.cancel_nav()          # Nav2 목표 취소 → /cmd_vel 충돌 방지
                if not follower.is_registered:
                    follower.trigger_register = True
                    follower.get_logger().info("FOLLOW 요청 수신 -> 신규 사용자 등록을 시작합니다.")
                else:
                    follower.state = "FOLLOW"
                    follower.send_stop()           # 잔여 속도 정지 후 추종 재개
                    set_robot_led(follower.esp_ip, "STANDBY")
                    follower.get_logger().info("FOLLOW 모드로 전환 (기등록 사용자).")
        elif cmd == "정지":
            follower.cancel_nav()
            follower.state = "STOPPED"
            follower.send_stop()
            set_robot_led(follower.esp_ip, "STOPPED")
            follower.get_logger().info("정지(STOPPED) 모드로 전환. LED 빨간불.")


