const express = require('express');
const router = express.Router();
const orderController = require('../controllers/order.controller');
const { authenticateToken } = require('../middleware/auth');

// [Redis → MySQL] 결제 완료: Redis 장바구니 → MySQL 영구 저장 → 로봇 복귀
router.post('/complete', authenticateToken, orderController.completeOrder);

// [MySQL] 유저 주문 이력 조회
router.get('/history', authenticateToken, orderController.getOrderHistory);

module.exports = router;
