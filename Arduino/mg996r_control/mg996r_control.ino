/*
 * SmartCart ESP32 — MG996R 모터 제어 (USB 시리얼)
 *
 * 라즈베리파이가 USB 시리얼로 보내는 명령을 받아 서보 모터를 제어합니다.
 *   SCAN_START → 45°↔135° 왕복 스캔 시작
 *   SCAN_STOP  → 스캔 정지 (현재 각도 유지)
 *   CENTER     → 90° 정면 복귀
 *
 * 라이브러리: ESP32Servo (라이브러리 매니저에서 설치)
 * 보드: ESP32 Dev Module
 *
 * ※ 통신: 라파의 raspi_cmd_bridge.py 가 9600bps로 "명령\n" 송신 → 동일하게 9600 사용
 */

#include <ESP32Servo.h>

// ── 설정 ──────────────────────────────────────────────────────────────────────
const int MOTOR_PIN = 26;   // 서보 모터 핀

// ── 스캔 동작 상수 ────────────────────────────────────────────────────────────
#define SCAN_MIN_ANGLE  45
#define SCAN_MAX_ANGLE  135
#define SCAN_STEP       2
#define SCAN_DELAY_MS   80

// ── 서보 상태 ─────────────────────────────────────────────────────────────────
Servo motor;
int  angle    = 90;
int  scan_dir = -1;
bool scanning = false;

// ── 명령 처리 ─────────────────────────────────────────────────────────────────
void handle_cmd(String cmd) {
    cmd.trim();
    if (cmd == "SCAN_START") {
        scanning = true;
        Serial.println("[CMD] SCAN_START — 스캔 시작");
    } else if (cmd == "SCAN_STOP") {
        scanning = false;
        Serial.println("[CMD] SCAN_STOP  — 스캔 정지");
    } else if (cmd == "CENTER") {
        scanning = false;
        angle = 90;
        motor.write(90);
        Serial.println("[CMD] CENTER     — 정면 복귀(90°)");
    } else if (cmd.length() > 0) {
        Serial.print("[CMD] 알 수 없는 명령: ");
        Serial.println(cmd);
    }
}

// ── Setup ─────────────────────────────────────────────────────────────────────
void setup() {
    Serial.begin(9600);          // 라파 브리지와 동일 baud
    motor.attach(MOTOR_PIN);
    motor.write(90);
    Serial.println("[BOOT] 서보 초기화 완료 (90°). /robocart/cmd 시리얼 명령 대기 중...");
}

// ── Loop ─────────────────────────────────────────────────────────────────────
void loop() {
    // 시리얼 명령 수신
    if (Serial.available()) {
        handle_cmd(Serial.readStringUntil('\n'));
    }

    // 스캔 모션 (45° ↔ 135° 왕복)
    if (scanning) {
        angle += scan_dir * SCAN_STEP;
        if (angle <= SCAN_MIN_ANGLE) { angle = SCAN_MIN_ANGLE; scan_dir = 1; }
        if (angle >= SCAN_MAX_ANGLE) { angle = SCAN_MAX_ANGLE; scan_dir = -1; }
        motor.write(angle);
        delay(SCAN_DELAY_MS);
    }
}
