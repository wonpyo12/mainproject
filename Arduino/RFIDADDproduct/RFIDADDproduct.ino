
#include <SPI.h>
#include <MFRC522.h>
#include <ESP8266WiFi.h>
#include <ESP8266HTTPClient.h>
#include <WiFiClient.h>

#define SS_PIN D8
#define RST_PIN D3

MFRC522 rfid(SS_PIN, RST_PIN);

// ── Wi-Fi 설정 ──────────────────────────────────
const char* ssid     = "5층";
const char* password = "48864886";

// ── 서버 URL 설정 ───────────────────────────────
// PC의 로컬 IP로 변경하세요 (예: 192.168.0.10)
// cmd에서 ipconfig 실행 후 IPv4 주소 확인
const char* serverURL = "http://192.168.0.9:3000/api/hardware/rfid";
const char* robotSerialNumber = "CartMe-ROS2-08";

// 동일 카드 연속 스캔 방지 (디바운스) 변수
String lastUid = "";
unsigned long lastScanTime = 0;
const unsigned long debounceDelay = 5000; // 5초 이내 동일 카드 무시

void setup() {
  Serial.begin(115200);
  SPI.begin();
  rfid.PCD_Init();

  Serial.println();
  Serial.print("와이파이 연결중");
  WiFi.begin(ssid, password);

  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }

  Serial.println("");
  Serial.print("연결 완료 - IP: ");
  Serial.println(WiFi.localIP());
}

void loop() {
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
    http.addHeader("Content-Type", "application/json");

    // JSON 바디: { "rfidTag": "XXXXXXXX", "robotSerialNumber": "CartMe-ROS2-08" }
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
      Serial.print("전송 실패 코드: ");
      Serial.println(httpCode);
      Serial.print("전송 실패 메시지: ");
      Serial.println(http.errorToString(httpCode));
    }

    http.end();
  } else {
    Serial.println("Wi-Fi 끊김! 재연결 중...");
    WiFi.begin(ssid, password);
  }

  // 카드 정지 (중복 읽기 방지)
  rfid.PICC_HaltA();
  rfid.PCD_StopCrypto1();

  delay(2000); // 2초 대기 후 다음 스캔
}
