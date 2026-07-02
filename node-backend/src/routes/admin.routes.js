const express = require('express');
const router = express.Router();
const adminController = require('../controllers/admin.controller');
// const { authenticateToken } = require('../middleware/auth'); // 관리자 인증 필요 시 활성화

// [MySQL + Redis] 웹 관리자 대시보드 집계 (로봇 플릿 · 거래액 · 세션)
router.get('/dashboard', adminController.getDashboard);

// [TCP → 라파 cmd_server] 관리자 로봇 제어 (긴급 정지 / 해제 / 충전소 복귀)
router.post('/robot/command', adminController.robotCommand);

module.exports = router;
