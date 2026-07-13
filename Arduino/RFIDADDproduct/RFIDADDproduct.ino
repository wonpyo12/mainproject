#include <SPI.h>
#include <MFRC522.h>
#include <ESP8266WiFi.h>
#include <ESP8266HTTPClient.h>
#include <WiFiClient.h>
#include <ESP8266WebServer.h>

#define SS_PIN D8
#define RST_PIN D3

// ── LED 핀 설정 ──────────────────────────────────
#define LED_RED D1      // 정지 상태 (빨간불)
#define LED_YELLOW D2   // 대기 상태 (노란불)
#define LED_GREEN D0    // 운행 상태 (초록불) - D0 일반 핀으로 변경 (D5 RFID SCK 핀 충돌 방지)

MFRC522 rfid(SS_PIN, RST_PIN);
ESP8266WebServer server(80);

// ── Wi-Fi 설정 ──────────────────────────────────
const char* ssid     = "test1111";
const char* password = "12345678";

// ── 서버 URL 설정 (RFID 태그 전송용) ───────────────
const char* serverURL = "http://192.168.0.17:3000/api/hardware/rfid";
const char* robotSerialNumber = "CartMe-ROS2-08";

// 동일 카드 연속 스캔 방지 (디바운스) 변수
String lastUid = "";
unsigned long lastScanTime = 0;
const unsigned long debounceDelay = 5000; // 5초 이내 동일 카드 무시

// LED 상태 제어 핸들러 (모든 LED가 HIGH일 때 켜지는 표준 Active-HIGH 상태)
void handleLED() {
  if (server.hasArg("status")) {
    String status = server.arg("status");
    Serial.println("LED 상태 변경 요청: " + status);
    
    if (status == "RUNNING") {
      digitalWrite(LED_GREEN, HIGH);  // 초록불 켬
      digitalWrite(LED_YELLOW, LOW);   // 노란불 끔
      digitalWrite(LED_RED, LOW);      // 빨간불 끔
    } else if (status == "STANDBY") {
      digitalWrite(LED_GREEN, LOW);   // 초록불 끔
      digitalWrite(LED_YELLOW, HIGH);  // 노란불 켬
      digitalWrite(LED_RED, LOW);      // 빨간불 끔
    } else if (status == "STOPPED") {
      digitalWrite(LED_GREEN, LOW);   // 초록불 끔
      digitalWrite(LED_YELLOW, LOW);   // 노란불 끔
      digitalWrite(LED_RED, HIGH);     // 빨간불 켬
    }
    server.send(200, "text/plain", "OK");
  } else {
    server.send(400, "text/plain", "Missing status parameter");
  }
}

void setup() {
  Serial.begin(115200);
  SPI.begin();
  rfid.PCD_Init();

  // LED 핀 출력 설정
  pinMode(LED_RED, OUTPUT);
  pinMode(LED_YELLOW, OUTPUT);
  pinMode(LED_GREEN, OUTPUT);

  // 초기 상태: 와이파이 연결 전 빨간불 켬
  digitalWrite(LED_RED, HIGH);
  digitalWrite(LED_YELLOW, LOW);
  digitalWrite(LED_GREEN, LOW);

  Serial.println();
  Serial.print("와이파이 연결중");
  WiFi.begin(ssid, password);

  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
    // 와이파이 연결 시도 중에는 노란불 깜빡임 효과
    digitalWrite(LED_YELLOW, !digitalRead(LED_YELLOW));
  }

  Serial.println("");
  Serial.print("연결 완료 - IP: ");
  Serial.println(WiFi.localIP());

  // 와이파이 연결 성공 시: VM 구동 전이므로 빨간불(정지/대기) 상태 유지
  digitalWrite(LED_RED, HIGH);
  digitalWrite(LED_YELLOW, LOW);
  digitalWrite(LED_GREEN, LOW);

  // HTTP LED 제어 경로 등록
  server.on("/led", handleLED);
  server.begin();
  Serial.println("HTTP LED 제어 서버 시작됨");
}

void loop() {
  // 웹 서버 요청 처리 (비블로킹)
  server.handleClient();

  // RC522 칩 통신 상태 자가진단 (Wi-Fi 노이즈로 인한 SPI 버스 멈춤 자동 복구)
  byte version = rfid.PCD_ReadRegister(rfid.VersionReg);
  if (version == 0x00 || version == 0xFF) {
    Serial.println("[RC522] 통신 오류 감지 - SPI 버스 및 리더기 강제 재부팅...");
    SPI.end();
    SPI.begin();
    rfid.PCD_Init();
  }

  // 스캔 간격 제한 (2초 이내 재스캔 방지, delay 제거로 서버 응답속도 보장)
  if (millis() - lastScanTime < 2000) {
    return;
  }

  // 새 카드 감지 확인
  if (!rfid.PICC_IsNewCardPresent()) return;
  if (!rfid.PICC_ReadCardSerial())   return;

  // UID → 16진수 문자열 변환
  String uidStr = "";
  for (byte i = 0; i < rfid.uid.size; i++) {
    if (rfid.uid.uidByte[i] < 0x10) uidStr += "0";
    uidStr += String(rfid.uid.uidByte[i], HEX);
  }
  uidStr.toUpperCase();

  // 5초 이내에 동일한 카드를 연속 스캔한 경우 무시
  if (uidStr == lastUid && (millis() - lastScanTime < debounceDelay)) {
    rfid.PICC_HaltA();
    rfid.PCD_StopCrypto1();
    return;
  }

  lastUid = uidStr;
  lastScanTime = millis();

  Serial.println("RFID 스캔: " + uidStr);

  // Wi-Fi 연결 확인 후 서버에 전송
  if (WiFi.status() == WL_CONNECTED) {
    WiFiClient client;
    HTTPClient http;
    http.begin(client, serverURL);
    http.setTimeout(3000); // 3초 타임아웃 설정 (서버 대기용)
    http.addHeader("Content-Type", "application/json");
    http.addHeader("Connection", "close"); // 소켓 누수 방지용 헤더 추가

    String body = "{\"rfidTag\":\"" + uidStr + "\",\"robotSerialNumber\":\"" + robotSerialNumber + "\"}";

    Serial.print("요청 URL: ");
    Serial.println(serverURL);

    int httpCode = http.POST(body);

    if (httpCode > 0) {
      Serial.print("서버 응답 코드: ");
      Serial.println(httpCode);
      if (httpCode == 200) {
        Serial.println(">> 서버 전송 완료!");
      } else {
        Serial.print("서버 응답 내용: ");
        Serial.println(http.getString());
      }
    } else {
      Serial.print("trans error code: ");
      Serial.println(httpCode);
      Serial.print("trans error message: ");
      Serial.println(http.errorToString(httpCode));
    }

    http.end();
    client.stop(); // 소켓 리소스 확실히 해제
  } else {
    Serial.println("Wi-Fi 끊김! 재연결 중...");
    WiFi.begin(ssid, password);
  }

  // 카드 정지 (중복 읽기 방지) 및 RC522 재기동 (전압 강하로 인한 프리징 방지)
  rfid.PICC_HaltA();
  rfid.PCD_StopCrypto1();
  rfid.PCD_Init();
}
