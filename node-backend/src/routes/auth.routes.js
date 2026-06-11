const express = require('express');
const router = express.Router();
const authController = require('../controllers/auth.controller');
const { authenticateToken } = require('../middleware/auth');

// [MySQL] 회원가입 - bcrypt 해싱 후 users 테이블 INSERT
router.post('/register', authController.register);

// [MySQL] 로그인 - 비밀번호 검증 후 JWT 발급
router.post('/login', authController.login);

// [Redis] QR 세션 생성 - 로그인 필수
router.get('/qr', authenticateToken, authController.generateQR);

module.exports = router;
