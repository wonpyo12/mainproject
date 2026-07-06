#include <ESP32Servo.h>

Servo motor;
const int PIN = 26;
int angle = 90, dir = -1;
bool scanning = false;

void setup() {
  Serial.begin(9600);
  motor.attach(PIN);
  motor.write(90);
}

void loop() {
  if (Serial.available()) {
    String cmd = Serial.readStringUntil('\n');
    cmd.trim();
    if      (cmd == "SCAN_START") scanning = true;
    else if (cmd == "SCAN_STOP")  scanning = false;
    else if (cmd == "CENTER")     { angle = 90; motor.write(90); }
  }

  if (scanning) {
    angle += dir * 2;
    if (angle <= 45)  dir =  1;
    if (angle >= 135) dir = -1;
    motor.write(angle);
    delay(100);  // 속도 조절: 값 키우면 느려짐
  }
}