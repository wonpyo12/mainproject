// ===================================================================
// [파트 2 & 3] 하드웨어 연동 컨트롤러
//   - qrScan  : [Redis] QR 토큰 검증 → 로봇-유저 매칭
//   - rfidScan: [MySQL] 상품 조회 → [Redis] 장바구니 업데이트
//              → [WebSocket] 앱에 실시간 장바구니 푸시
// ===================================================================
const pool  = require('../config/db');    // [MySQL]
const redis = require('../config/redis'); // [Redis]

// ───────────────────────────────────────────────
// POST /api/hardware/qr-scan
// Body: { qrToken: string, robotSerialNumber: string }
// ───────────────────────────────────────────────
const qrScan = async (req, res) => {
  const { qrToken, robotSerialNumber } = req.body;

  if (!qrToken || !robotSerialNumber) {
    return res.status(400).json({ success: false, message: 'qrToken과 robotSerialNumber가 필요합니다.' });
  }

  try {
    const qrKey = `qr:auth:${qrToken}`;

    // [Redis] QR 토큰으로 유저 ID 조회
    const userId = await redis.get(qrKey);
    if (!userId) {
      return res.status(404).json({ success: false, message: 'QR 토큰이 만료되었거나 존재하지 않습니다.' });
    }

    // [Redis] 1회용 토큰 즉시 삭제 (재사용 방지)
    await redis.del(qrKey);

    // [Redis] 로봇 상태 캐시: robot:status:{serialNumber} = { userId, status, startedAt }
    const robotStatusKey = `robot:status:${robotSerialNumber}`;
    await redis.hset(robotStatusKey, {
      userId,
      status:    'SHOPPING',
      startedAt: new Date().toISOString(),
    });

    // [WebSocket] 해당 유저 룸으로 매칭 완료 이벤트 전송
    const io = req.app.get('io');
    io.to(`user:${userId}`).emit('robot:matched', {
      robotSerialNumber,
      status: 'SHOPPING',
    });

    return res.status(200).json({
      success: true,
      message: '로봇과 유저가 매칭되었습니다.',
      userId: Number(userId),
      robotSerialNumber,
    });
  } catch (err) {
    console.error('[Hardware] qrScan error:', err);
    return res.status(500).json({ success: false, message: '서버 오류가 발생했습니다.' });
  }
};

// ───────────────────────────────────────────────
// POST /api/hardware/rfid
// Body: { rfidTag: string, robotSerialNumber: string }
// ───────────────────────────────────────────────
const rfidScan = async (req, res) => {
  const { rfidTag, robotSerialNumber } = req.body;

  if (!rfidTag || !robotSerialNumber) {
    return res.status(400).json({ success: false, message: 'rfidTag와 robotSerialNumber가 필요합니다.' });
  }

  try {
    // [Redis] 로봇에 매칭된 유저 ID 조회
    const robotStatusKey = `robot:status:${robotSerialNumber}`;
    const userId = await redis.hget(robotStatusKey, 'userId');
    if (!userId) {
      return res.status(404).json({
        success: false,
        message: '매칭된 유저가 없습니다. QR 인증이 먼저 필요합니다.',
      });
    }

    // [MySQL] rfid_tag로 상품 정보 조회 (products 테이블)
    const [rows] = await pool.query(
      'SELECT id, name, price, category FROM products WHERE rfid_tag = ?',
      [rfidTag]
    );
    if (rows.length === 0) {
      return res.status(404).json({ success: false, message: '등록되지 않은 RFID 태그입니다.' });
    }

    const product = rows[0];
    const cartKey = `cart:${userId}:${robotSerialNumber}`;

    // [Redis] 장바구니에 상품 추가/수량 증가
    // 구조: HSET cart:{userId}:{serialNumber} {productId}_name  "상품명"
    //                                          {productId}_price "1000"
    //                                          {productId}_qty   "2"
    const existingQty = await redis.hget(cartKey, `${product.id}_qty`);
    const newQty = existingQty ? parseInt(existingQty, 10) + 1 : 1;

    await redis.hset(cartKey, {
      [`${product.id}_name`]:  product.name,
      [`${product.id}_price`]: String(product.price),
      [`${product.id}_qty`]:   String(newQty),
    });

    // [Redis] 업데이트된 장바구니 전체 조회
    const cartRaw   = await redis.hgetall(cartKey);
    const cartItems = parseCartFromRedis(cartRaw);
    const totalAmount = cartItems.reduce((sum, item) => sum + item.price * item.qty, 0);

    // [WebSocket] 유저 룸으로 장바구니 전체 + 총액 실시간 푸시 (1초 이내)
    const io = req.app.get('io');
    io.to(`user:${userId}`).emit('cart:updated', {
      items: cartItems,
      totalAmount,
      updatedAt: new Date().toISOString(),
    });

    return res.status(200).json({
      success: true,
      message: `${product.name}이(가) 장바구니에 추가되었습니다.`,
      addedProduct: { ...product, qty: newQty },
    });
  } catch (err) {
    console.error('[Hardware] rfidScan error:', err);
    return res.status(500).json({ success: false, message: '서버 오류가 발생했습니다.' });
  }
};

// Redis HSET 평탄화 데이터 → 상품 배열 변환
// { "1_name":"사과", "1_price":"1000", "1_qty":"2" } → [{ productId:1, name:"사과", ... }]
function parseCartFromRedis(cartRaw) {
  const items = {};
  for (const [field, value] of Object.entries(cartRaw)) {
    const underscoreIdx = field.indexOf('_');
    const productId     = field.substring(0, underscoreIdx);
    const attr          = field.substring(underscoreIdx + 1);

    if (!items[productId]) items[productId] = { productId: Number(productId) };
    if (attr === 'name')  items[productId].name  = value;
    if (attr === 'price') items[productId].price = Number(value);
    if (attr === 'qty')   items[productId].qty   = Number(value);
  }
  return Object.values(items);
}

module.exports = { qrScan, rfidScan };
