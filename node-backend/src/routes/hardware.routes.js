const express = require('express');
const router = express.Router();
const hardwareController = require('../controllers/hardware.controller');

// [Redis] 로봇이 QR 스캔 후 서버로 토큰 전송 → 유저-로봇 매칭
router.post('/qr-scan', hardwareController.qrScan);

// [MySQL + Redis + WebSocket] RFID 태그 인식 → 실시간 장바구니 업데이트 + 앱 푸시
router.post('/rfid', hardwareController.rfidScan);

// 실시간 카메라 비디오 피드 프록시 (CORS/포트 오리진 이슈 우회)
router.get('/video-feed', hardwareController.videoFeed);

// [WebSocket] 로봇 실시간 위치/텔레메트리 — pose_bridge.py 가 POST, 관리자 웹이 초기값 GET
router.post('/pose', hardwareController.updatePose);
router.get('/pose', hardwareController.getPose);
router.post('/telemetry', hardwareController.updateTelemetry);

module.exports = router;
