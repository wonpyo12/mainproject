const express = require('express');
const router = express.Router();
const hardwareController = require('../controllers/hardware.controller');

// [Redis] 로봇이 QR 스캔 후 서버로 토큰 전송 → 유저-로봇 매칭
router.post('/qr-scan', hardwareController.qrScan);

// [MySQL + Redis + WebSocket] RFID 태그 인식 → 실시간 장바구니 업데이트 + 앱 푸시
router.post('/rfid', hardwareController.rfidScan);

module.exports = router;
