/*
 * RoboCart 카메라 팬(pan) 서보 제어 펌웨어
 *
 * 하드웨어 : ESP32 + MG996R (GPIO 26)
 * 통신     : USB 시리얼 115200bps
 *
 * 명령 프로토콜 (PC → ESP32, 줄바꿈 \n 종료):
 *   A<각도>   지정 각도로 부드럽게 이동 (추적 모드)   예) A95
 *   S         탐색 스윕 시작 (0~180도 자체 왕복)
 *   H         스윕 정지 (현재 각도 유지)
 *   C         중앙(90도) 복귀
 *
 * 응답 (ESP32 → PC):
 *   P<현재각도>  매 이동 스텝마다 현재 각도 보고      예) P102
 *   OK / ERR     명령 수신 확인
 *
 * 모든 이동은 millis() 기반 non-blocking으로 처리되어
 * 시리얼 수신이 끊기지 않습니다.
 *
 * 보드/라이브러리:
 *   - 보드 매니저: "esp32" by Espressif Systems
 *   - 라이브러리: "ESP32Servo" by Kevin Harrington (라이브러리 매니저에서 설치)
 */

#include <ESP32Servo.h>

Servo myServo;
const int servoPin = 26;

// ── 동작 파라미터 ──────────────────────────────────────────────
const int  ANGLE_MIN        = 0;
const int  ANGLE_MAX        = 180;
const int  ANGLE_CENTER     = 90;
const unsigned long TRACK_STEP_MS = 15;  // 추적 이동 시 1도당 시간 (작을수록 빠름)
const unsigned long SWEEP_STEP_MS = 40;  // 탐색 스윕 시 1도당 시간 (천천히 훑어야 인식 가능)

// ── 상태 ──────────────────────────────────────────────────────
enum Mode { MODE_HOLD, MODE_TRACK, MODE_SWEEP };
Mode mode = MODE_HOLD;

int currentAngle = ANGLE_CENTER;  // 현재 서보 각도
int targetAngle  = ANGLE_CENTER;  // 추적 모드 목표 각도
int sweepDir     = 1;             // 스윕 방향 (+1 / -1)
unsigned long lastStepTime = 0;
unsigned long lastReportTime = 0;

String rxBuffer = "";

void setup() {
  Serial.begin(115200);
  myServo.attach(servoPin, 500, 2500);
  myServo.write(currentAngle);
  Serial.println("READY");
}

void moveOneStepToward(int goal) {
  if (currentAngle < goal)      currentAngle++;
  else if (currentAngle > goal) currentAngle--;
  myServo.write(currentAngle);
}

void handleCommand(const String& cmd) {
  if (cmd.length() == 0) return;

  char c = cmd.charAt(0);
  switch (c) {
    case 'A': {  // 각도 이동 (추적)
      int angle = cmd.substring(1).toInt();
      angle = constrain(angle, ANGLE_MIN, ANGLE_MAX);
      targetAngle = angle;
      mode = MODE_TRACK;
      Serial.println("OK");
      break;
    }
    case 'S':  // 탐색 스윕 시작
      mode = MODE_SWEEP;
      // 가까운 끝 방향부터 스윕 시작
      sweepDir = (currentAngle >= ANGLE_CENTER) ? -1 : 1;
      Serial.println("OK");
      break;
    case 'H':  // 정지 (현재 각도 유지)
      mode = MODE_HOLD;
      targetAngle = currentAngle;
      Serial.println("OK");
      break;
    case 'C':  // 중앙 복귀
      targetAngle = ANGLE_CENTER;
      mode = MODE_TRACK;
      Serial.println("OK");
      break;
    default:
      Serial.println("ERR");
      break;
  }
}

void loop() {
  // ── 시리얼 수신 (non-blocking) ──────────────────────────────
  while (Serial.available() > 0) {
    char ch = (char)Serial.read();
    if (ch == '\n' || ch == '\r') {
      handleCommand(rxBuffer);
      rxBuffer = "";
    } else if (rxBuffer.length() < 16) {
      rxBuffer += ch;
    }
  }

  // ── 서보 이동 (millis 기반) ─────────────────────────────────
  unsigned long now = millis();

  if (mode == MODE_TRACK) {
    if (currentAngle != targetAngle && now - lastStepTime >= TRACK_STEP_MS) {
      lastStepTime = now;
      moveOneStepToward(targetAngle);
    }
  } else if (mode == MODE_SWEEP) {
    if (now - lastStepTime >= SWEEP_STEP_MS) {
      lastStepTime = now;
      currentAngle += sweepDir;
      if (currentAngle >= ANGLE_MAX) { currentAngle = ANGLE_MAX; sweepDir = -1; }
      if (currentAngle <= ANGLE_MIN) { currentAngle = ANGLE_MIN; sweepDir = 1; }
      myServo.write(currentAngle);
    }
  }

  // ── 현재 각도 주기 보고 (100ms 간격) ────────────────────────
  if (now - lastReportTime >= 100) {
    lastReportTime = now;
    Serial.print("P");
    Serial.println(currentAngle);
  }
}
