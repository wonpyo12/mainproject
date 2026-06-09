const express = require('express');
const router  = express.Router();
const productController = require('../controllers/product.controller');

// [아두이노] RFID 태그 스캔 수신 → WebSocket push
// ※ /rfid-scan 을 /:id 보다 먼저 등록해야 충돌 방지
router.post('/rfid-scan', productController.rfidScan);

// 전체 상품 목록 조회
router.get('/', productController.getProducts);

// 신규 상품 등록 → MySQL
router.post('/', productController.createProduct);

// 상품 삭제
router.delete('/:id', productController.deleteProduct);

module.exports = router;
