# 아두이노

SmartCart 하드웨어 제어 코드 모음입니다.

| 폴더 | 보드 | 내용 |
|---|---|---|
| [`mg996r_test/`](mg996r_test/) | ESP32 | MG996R 단독 동작 테스트 — 0°↔180° 왕복하며 속도 조절 확인용 |
| [`camera_servo/`](camera_servo/) | ESP32 | **카메라 팬 서보 제어 펌웨어** — PC의 사용자 추적 프로그램과 시리얼 연동 |
| [`RFIDADDproduct/`](RFIDADDproduct/) | ESP8266 | **RFID 상품 등록** — 태그 UID를 백엔드로 전송, 웹 상품 등록과 연동 |

---

# 카메라 팬 서보 제어 (ESP32 + MG996R)

## 하드웨어 구성

```
[PC] ──USB 시리얼(115200)── [ESP32] ──GPIO 26── [MG996R] ──장착── [카메라]
```

- **신호선**: MG996R 주황색 → ESP32 GPIO 26
- **전원**: MG996R은 부하 시 1A 이상 소모하므로 **별도 5~6V 전원 권장** (ESP32 5V 핀 단독 사용 시 전압 강하로 보드 리셋 발생 가능)
- **GND**: ESP32와 서보 전원의 GND 공통 연결 필수

## camera_servo 펌웨어

PC에서 실행되는 사용자 추적 프로그램(`OpenCV/smart_cart/smart_cart_main.py`)이
시리얼로 명령을 보내면 서보를 제어합니다.

### 동작 모드

| 모드 | 설명 |
|---|---|
| TRACK | PC가 보낸 목표 각도로 부드럽게 이동 (사용자를 화면 중앙에 유지) |
| SWEEP | 0°↔180° 자체 왕복 스캔 (사용자 유실 시 탐색) — PC 명령 없이 ESP32가 스스로 수행 |
| HOLD | 현재 각도 유지 (잠깐 유실 시 대기) |

모든 이동은 `millis()` 기반 non-blocking으로 처리되어 스윕 중에도 시리얼 명령을 즉시 수신합니다.

### 시리얼 프로토콜 (115200bps, `\n` 종료)

| PC → ESP32 | 동작 |
|---|---|
| `A<각도>` (예: `A95`) | 지정 각도로 이동 (TRACK) |
| `S` | 탐색 스윕 시작 (SWEEP) |
| `H` | 정지, 현재 각도 유지 (HOLD) |
| `C` | 중앙 복귀 |

| ESP32 → PC | 의미 |
|---|---|
| `READY` | 부팅 완료 |
| `P<각도>` | 현재 각도 (100ms 주기 보고) |
| `OK` / `ERR` | 명령 수신 확인 / 잘못된 명령 |

### 튜닝 상수 (`camera_servo.ino` 상단)

| 상수 | 기본값 | 설명 |
|---|---|---|
| `ANGLE_CENTER` | 75 | 카메라가 정면을 보는 각도 — **서보 혼 장착 오차 보정값** (실측으로 결정) |
| `TRACK_STEP_MS` | 15 | 추적 이동 속도 (1도당 ms, 작을수록 빠름) |
| `SWEEP_STEP_MS` | 40 | 탐색 스윕 속도 — 너무 빠르면 카메라가 인식하기 전에 지나침 |

### 업로드 방법

1. Arduino IDE에서 `ESP32Servo` 라이브러리 설치
2. 보드: ESP32 Dev Module 선택 후 `camera_servo.ino` 업로드
3. **업로드 후 시리얼 모니터는 닫기** — 열려 있으면 PC 추적 프로그램이 포트를 열지 못함 (`PermissionError`)

### 중앙각 보정

서보 혼이 비뚤게 장착되면 90°가 정면이 아닐 수 있습니다.
`OpenCV/smart_cart/servo_controller.py`의 교정 테스트로 실제 정면 각도를 찾은 뒤,
`.ino`의 `ANGLE_CENTER`와 `servo_controller.py`의 `ANGLE_CENTER`를 같은 값으로 맞춰주세요.
(현재 보정값: **75°**)

---

# RFID 상품 등록 시스템 (Arduino & Web 연동)

## 1. 하드웨어 구성 (Pin Mapping)

ESP8266(NodeMCU) 보드와 MFRC522 RFID 모듈 간의 핀 연결 정보입니다. MFRC522은 반드시 **3.3V**에 연결해야 합니다. (5V에 연결 시 모듈이 손상될 수 있습니다.)

| MFRC522 핀 | ESP8266 (NodeMCU) 핀 | 설명 |
| :--- | :--- | :--- |
| **SDA (SS)** | **D8** (GPIO15) | SPI Chip Select |
| **SCK** | **D5** (GPIO14) | SPI Clock |
| **MOSI** | **D7** (GPIO13) | SPI Master Out Slave In |
| **MISO** | **D6** (GPIO12) | SPI Master In Slave Out |
| **IRQ** | *연결 안 함 (N/C)* | Interrupt Request |
| **GND** | **GND** | Ground |
| **RST** | **D3** (GPIO0) | Reset Pin |
| **3.3V** | **3.3V** | Power Supply (3.3V) |

---

## 2. 아두이노 개발 환경 설정

### 라이브러리 설치
아두이노 IDE를 실행한 뒤 **라이브러리 관리자(Ctrl + Shift + I)**에서 아래 라이브러리들을 검색하여 설치합니다.
1. **MFRC522** (by GithubCommunity)
2. **ESP8266 보드 패키지 설치** (아두이노 IDE -> 설정 -> 추가 보드 매니저 URL에 `http://arduino.esp8266.com/stable/package_esp8266com_index.json` 등록 후 보드 매니저에서 `esp8266` 설치)

### 소스 코드 설정 (`RFIDADDproduct.ino`)
[RFIDADDproduct.ino](./RFIDADDproduct/RFIDADDproduct.ino) 파일 내의 Wi-Fi 및 로컬 서버 IP 정보를 환경에 맞게 수정해야 합니다.

```cpp
// ── Wi-Fi 설정 ──────────────────────────────────
const char* ssid     = "SSID_이름_입력";
const char* password = "비밀번호_입력";

// ── 서버 URL 설정 ───────────────────────────────
// 백엔드 서버가 실행 중인 PC의 로컬 IP(IPv4) 주소와 포트를 입력합니다.
// (예: cmd 창에서 `ipconfig` 입력 후 확인한 192.168.x.x 주소)
const char* serverURL = "http://(백엔드 서버 IP):3000/api/products/rfid-scan";
```

---

## 3. 연동 동작 상세 설명

### ① 아두이노 (하드웨어 측)
- RFID 태그 감지 시 UID(Unique Identifier)를 읽어와 16진수 대문자 문자열로 변환합니다.
- Wi-Fi가 연결된 상태에서 `HTTPClient`를 이용해 백엔드의 `/api/products/rfid-scan` 라우터로 `POST` 요청을 전달합니다.
- 데이터 포맷: `JSON` `{"uid": "A1B2C3D4"}`

### ② 백엔드 (Node.js / Express 측)
- **API 경로**: `POST /api/products/rfid-scan` ([product.controller.js](../node-backend/src/controllers/product.controller.js))
- **역할**:
  1. 수신한 태그 UID를 Redis에 `rfid:pending:admin` 키로 저장하며, 유효 시간은 30초로 설정합니다 (`EX`, 30).
  2. 현재 웹 페이지에서 대기 중인 관리자에게 알리기 위해 **Socket.io** 채널 (`room:admin`)을 통해 `rfid:scanned` 이벤트를 발생시킵니다.
  ```javascript
  await redis.set('rfid:pending:admin', tag, 'EX', 30);
  io.to('room:admin').emit('rfid:scanned', { uid: tag, scannedAt: new Date().toISOString() });
  ```

### ③ 웹 프론트엔드 (React / Vite 측)
- **컴포넌트**: `ProductRegisterModal.jsx` ([ProductRegisterModal.jsx](../web/src/views/ProductRegisterModal.jsx))
- **역할**:
  - 관리자가 상품 등록 팝업을 열면, 자동으로 WebSocket 커넥션을 맺고 대기 상태에 들어갑니다.
  - 소켓으로부터 `rfid:scanned` 이벤트를 수신하는 즉시 RFID 태그 입력창에 UID가 자동 입력됩니다.
  - 수동으로 태그 번호를 입력할 필요가 없어 빠르고 정확하게 상품을 등록할 수 있습니다.
