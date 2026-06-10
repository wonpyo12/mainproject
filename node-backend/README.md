# CartPilot Node.js 백엔드 API 서버


##  기술 스택
- **Runtime**: Node.js
- **Framework**: Express
- **Database**: MySQL (`mysql2/promise` 라이브러리 사용)
- **Cache**: Redis (`ioredis` 라이브러리 사용)
- **Real-time Communication**: Socket.io
- **Auth**: JWT (`jsonwebtoken` 라이브러리 사용)

---

## 📂 핵심 연동 기능 및 코드 구조

### 1. 회원 관리 (Member Management)
관리자 화면에서 전체 회원 목록을 조회하고, 특정 회원의 상세 정보를 확인 및 수정/삭제하는 API입니다.
- **주요 API**:
  - `GET /api/members`: 전체 회원 목록 조회 (페이징 및 검색 필터 지원)
  - `GET /api/members/:id`: 특정 회원 상세 조회
  - `PATCH /api/members/:id`: 회원 정보 수정 (이름, 전화번호, 회원 유형 등)
  - `DELETE /api/members/:id`: 회원 영구 삭제
- **관련 파일 경로**:
  - 라우터 정의: [`src/routes/member.routes.js`](./src/routes/member.routes.js)
  - 컨트롤러 로직: [`src/controllers/member.controller.js`](./src/controllers/member.controller.js)
  - 데이터베이스 테이블: MySQL의 `users` 테이블 (스키마 참조: [`db/schema.sql`](./db/schema.sql))

---

### 2. 상품 등록 & RFID 연동 (Product Registration & RFID Integration)
아두이노 하드웨어가 실시간으로 RFID 태그를 스캔했을 때, 웹 관리자 화면의 상품 등록 폼에 UID가 자동으로 대입되도록 구현된 실시간 연동 기능입니다.

####  연동 동작 시나리오:
1. **소켓 대기**: 관리자가 웹 브라우저에서 **상품 등록 모달**을 열면, 프론트엔드가 `token: "admin-cartpilot"` 인증 토큰을 담아 WebSocket 연결을 맺고, `room:admin` 소켓 룸에 참가합니다.
2. **RFID 스캔**: 아두이노(MFRC522)에서 RFID 태그 카드를 감지하여 추출한 `uid`를 백엔드의 `POST /api/products/rfid-scan` API로 전송합니다.
3. **Redis 캐싱 & 브로드캐스트**: 백엔드는 이 `uid`를 Redis에 임시 대기열(Key: `rfid:pending:admin`, TTL 30초)로 설정한 뒤, `room:admin` 룸에 접속 중인 관리자 브라우저로 `rfid:scanned` 이벤트를 발생시켜 데이터를 실시간으로 푸시합니다.
4. **자동 입력**: 웹 화면의 상품 등록 폼이 소켓 이벤트를 받아 RFID 입력란에 태그 UID를 자동으로 대입합니다.
5. **상품 등록 완료**: 관리자가 상품명, 가격 등을 기입하고 최종 제출(`POST /api/products`)하면 백엔드는 MySQL에 상품 정보를 영구 저장하고, Redis에 임시 저장되었던 `rfid:pending:admin` 대기열 키를 완전히 제거하여 프로세스를 완료합니다.

- **관련 파일 경로**:
  - API 라우터 정의: [`src/routes/product.routes.js`](./src/routes/product.routes.js)
  - API 컨트롤러 로직: [`src/controllers/product.controller.js`](./src/controllers/product.controller.js)
  - Socket.io 인증 및 룸 설정: [`src/socket/index.js`](./src/socket/index.js)
  - 데이터베이스 테이블: MySQL의 `products` 테이블 (스키마 참조: [`db/schema.sql`](./db/schema.sql))

---

##  로컬 실행 방법

### 1. 환경 변수 세팅
`node-backend/` 디렉토리에 `.env` 파일을 만들고 아래 내용을 환경에 맞춰 입력합니다.
```env
# Server
PORT=3000
JWT_SECRET=cartpilot-jwt-secret-key-2024
JWT_EXPIRES_IN=7d

# MySQL Connection Info
DB_HOST=localhost
DB_PORT=3306
DB_NAME=cartpilot_db
DB_USER=root
DB_PASSWORD=your_password

# Redis Connection Info
REDIS_HOST=localhost
REDIS_PORT=6379
```

### 2. 패키지 설치 & 실행
```bash
# 백앤드 서버 이동 
cd node-backend

# 패키지 의존성 설치
npm install

# 개발 서버 실행 (nodemon)
npm run dev

# 일반 실행
npm start
```

##  Spring Boot 백엔드와의 연동 및 역할 분담

이 프로젝트(Node.js 백엔드)는 메인 비즈니스 서버인 **Spring Boot 백엔드**와 유기적으로 연동되어 작동합니다.

1. **데이터베이스 공유 (MySQL `3306`)**:
   - 두 백엔드 서버는 동일한 MySQL 데이터베이스(`cartpilot_db`)를 공유합니다.
   - Node.js API를 통해 추가/수정/삭제된 회원 데이터나 주문 데이터는 DB에 즉시 반영되며, Spring Boot 백엔드에서도 동일하게 실시간으로 접근 및 관리가 가능합니다.

2. **역할 분담 및 특화 기능 (Node.js)**:
   - **실시간성 특화**: Node.js는 비동기 이벤트 기반으로 실시간 소켓 통신(Socket.io) 및 인메모리 캐싱(Redis) 처리에 특화되어 있습니다.
   - **실시간 데이터 중개**: 아두이노 장비에서 실시간으로 스캔한 RFID 태그 정보를 빠르게 받아 Redis 캐싱에 적재하고, 이를 웹 화면으로 실시간 Socket.io 브로드캐스트하는 역할을 전담합니다.

## 3. 추천 실행 순서

전체 시스템의 유기적인 연동과 실시간 데이터 흐름을 위해 아래 순서대로 구동하는 것을 권장합니다.

1. **Node.js 서버 실행** (RFID 및 실시간 소켓 통신을 처리하므로 가장 먼저 실행해야 합니다.)
2. **Spring Boot 웹서버 실행** (IntelliJ 등에서 실행)
3. **웹 프론트엔드(React) 실행** (Vite 개발 서버 구동)
4. **아두이노 하드웨어 전원 ON** (Wi-Fi 연결 및 RFID 카드 태깅 시작)