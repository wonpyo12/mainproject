/*
 * esp32_scan_motor.ino — robocart 검색용 서보(mg996r) 제어
 *
 * 라즈베리파이의 esp32_motor_node 가 /robocart/servo 토픽 명령을
 * USB 시리얼(9600bps)로 그대로 흘려보낸다. 이 펌웨어는 한 줄 단위로 수신한다.
 *
 * 명령 (개행 '\n' 종료):
 *   SCAN_START   45~135도 좌우 스윕 시작 (사람 없을 때)
 *   SCAN_STOP    스윕 정지 (현재 각도 유지)
 *   CENTER       90도 중앙 복귀 (사람 인식되면)
 *   A<각도>      지정 각도로 이동 (예: A120) — 선택 기능
 *
 * 100ms마다 현재 각도를 "P<각도>\n" 로 회신(노트북 디버그용, 미사용해도 무방).
 *
 * 배선: 서보 신호선 → GPIO26, 서보 전원은 외부 5V(공통 GND).
 * 라이브러리: ESP32Servo (Arduino IDE 라이브러리 매니저에서 설치)
 */
#include <ESP32Servo.h>

Servo motor;
const int PIN = 26;
const int CENTER_ANGLE = 90;
const int SCAN_MIN = 45;
const int SCAN_MAX = 135;

int angle = CENTER_ANGLE;
int dir = -1;
bool scanning = false;
unsigned long lastMove = 0;
unsigned long lastReport = 0;

void applyAngle(int a) {
  if (a < 0)   a = 0;
  if (a > 180) a = 180;
  angle = a;
  motor.write(angle);
}

void handleCommand(String cmd) {
  cmd.trim();
  if (cmd.length() == 0) return;

  if (cmd == "SCAN_START") {
    scanning = true;
  } else if (cmd == "SCAN_STOP") {
    scanning = false;
  } else if (cmd == "CENTER") {
    scanning = false;
    applyAngle(CENTER_ANGLE);
  } else if (cmd.charAt(0) == 'A') {            // A<각도> 직접 이동
    scanning = false;
    applyAngle(cmd.substring(1).toInt());
  }
}

void setup() {
  Serial.begin(9600);
  motor.attach(PIN);
  applyAngle(CENTER_ANGLE);
}

void loop() {
  // 1) 명령 수신
  if (Serial.available()) {
    String cmd = Serial.readStringUntil('\n');
    handleCommand(cmd);
  }

  unsigned long now = millis();

  // 2) 스캔 모드 — 100ms마다 2도씩 좌우 스윕
  if (scanning && (now - lastMove >= 100)) {
    lastMove = now;
    angle += dir * 2;
    if (angle <= SCAN_MIN) { angle = SCAN_MIN; dir =  1; }
    if (angle >= SCAN_MAX) { angle = SCAN_MAX; dir = -1; }
    motor.write(angle);
  }

  // 3) 현재 각도 회신 (100ms 주기)
  if (now - lastReport >= 100) {
    lastReport = now;
    Serial.print('P');
    Serial.println(angle);
  }
}
