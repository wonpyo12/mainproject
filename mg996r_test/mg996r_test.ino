#include <ESP32Servo.h>

Servo myServo;
const int servoPin = 26; 

// ★ 속도 조절 변수 (밀리초 단위)
// 이 값을 늘리면 모터가 천천히 움직이고, 줄이면 빨라집니다.
// 추천 범위: 10 (매우 빠름) ~ 100 (매우 느림)
const int servoSpeedDelay = 50; 

void setup() {
  Serial.begin(115200);
  myServo.attach(servoPin, 500, 2500); 
  Serial.println("[설정] 속도 조절 테스트 코드가 시작되었습니다.");
}

void loop() {
  // 1. 0도 -> 180도로 '지정한 속도'로 회전
  Serial.println("\n>> [동작] 0도에서 180도로 천천히 이동 중...");
  for (int pos = 0; pos <= 180; pos += 1) { // 1도씩 쪼개서 이동
    myServo.write(pos);
    
    // 현재 각도를 시리얼 모니터에 출력
    Serial.print("[현재 각도] ");
    Serial.print(pos);
    Serial.println("도");
    
    delay(servoSpeedDelay); // 이 딜레이 시간만큼 속도가 제어됩니다.
  }
  
  Serial.println("[대기] 180도 도달 - 2초간 정지");
  delay(2000);

  // 2. 180도 -> 0도로 '지정한 속도'로 회전
  Serial.println("\n>> [동작] 180도에서 0도로 천천히 이동 중...");
  for (int pos = 180; pos >= 0; pos -= 1) {
    myServo.write(pos);
    
    Serial.print("[현재 각도] ");
    Serial.print(pos);
    Serial.println("도");
    
    delay(servoSpeedDelay);
  }
  
  Serial.println("[대기] 0도 도달 - 2초간 정지");
  delay(2000);
}