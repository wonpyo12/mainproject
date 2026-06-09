const express = require('express');
const cors    = require('cors');
require('dotenv').config();

const authRoutes     = require('./routes/auth.routes');
const hardwareRoutes = require('./routes/hardware.routes');
const orderRoutes    = require('./routes/order.routes');
const productRoutes  = require('./routes/product.routes');


const app = express();

app.use(cors({ origin: '*' }));
app.use(express.json());
app.use(express.urlencoded({ extended: true }));

// ─── 라우터 등록 ───────────────────────────────
app.use('/api/auth',     authRoutes);     // 회원가입 / 로그인 / QR 생성
app.use('/api/hardware', hardwareRoutes); // QR 스캔 매칭 / RFID 상품 인식
app.use('/api/orders',   orderRoutes);    // 결제 완료 / 주문 이력
app.use('/api/products', productRoutes);  // 상품 CRUD + RFID 스캔 수신

// 헬스 체크
app.get('/health', (req, res) =>
  res.json({ status: 'ok', service: 'cartpilot-node-backend', timestamp: new Date().toISOString() })
);

// 404 핸들러
app.use((req, res) => {
  res.status(404).json({ success: false, message: '요청한 리소스를 찾을 수 없습니다.' });
});

// 전역 에러 핸들러
app.use((err, req, res, next) => { // eslint-disable-line no-unused-vars
  console.error('[App] Unhandled error:', err);
  res.status(500).json({ success: false, message: '서버 내부 오류가 발생했습니다.' });
});

module.exports = app;
