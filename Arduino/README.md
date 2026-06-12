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
