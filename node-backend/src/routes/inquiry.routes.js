const express = require('express');
const router = express.Router();
const inquiryController = require('../controllers/inquiry.controller');
const { authenticateToken } = require('../middleware/auth');

// [MySQL] 앱에서 문의 접수 (로그인 사용자)
router.post('/', authenticateToken, inquiryController.createInquiry);

// [MySQL] 내 문의 내역 + 답변 조회 (앱 - 로그인 사용자) — '/:id' 보다 먼저
router.get('/mine', authenticateToken, inquiryController.getMyInquiries);

// [MySQL] 문의 목록 조회 (웹 관리자) — 별도 관리자 인증은 추후 적용
router.get('/', inquiryController.getInquiries);

// [MySQL] 답변 등록 (웹 관리자) → 상태 ANSWERED
router.patch('/:id/answer', inquiryController.answerInquiry);

// [MySQL] 문의 처리 상태 변경 (웹 관리자)
router.patch('/:id/status', inquiryController.updateStatus);

module.exports = router;
