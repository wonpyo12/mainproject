const express = require('express');
const router = express.Router();
const robotController = require('../controllers/robot.controller');
const { authenticateToken } = require('../middleware/auth');

// 정지 버튼 → 그 자리 래치 정지(HALT)
router.post('/stop',   authenticateToken, robotController.stopRobot);

// 추종 시작 버튼 → 정지 해제(RESUME)
router.post('/resume', authenticateToken, robotController.resumeRobot);

module.exports = router;
