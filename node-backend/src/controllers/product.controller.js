// ===================================================================
// 상품 관리 컨트롤러 (CRUD + RFID 스캔 수신)
//   - getProducts   : GET    /api/products            전체 상품 목록
//   - createProduct : POST   /api/products            신규 상품 등록 → MySQL
//   - deleteProduct : DELETE /api/products/:id        상품 삭제
//   - rfidScan      : POST   /api/products/rfid-scan  아두이노 UID 수신 → WebSocket push
// ===================================================================
const pool  = require('../config/db');
const redis = require('../config/redis');

// ───────────────────────────────────────────────
// GET /api/products
// ───────────────────────────────────────────────
const getProducts = async (req, res) => {
  try {
    const [rows] = await pool.query(
      'SELECT id, rfid_tag, name, price, category, stock FROM products ORDER BY id DESC'
    );
    return res.status(200).json({ success: true, products: rows });
  } catch (err) {
    console.error('[Product] getProducts error:', err);
    return res.status(500).json({ success: false, message: '서버 오류가 발생했습니다.' });
  }
};

// ───────────────────────────────────────────────
// POST /api/products
// Body: { rfid_tag, name, price, category, stock }
// ───────────────────────────────────────────────
const createProduct = async (req, res) => {
  const { rfid_tag, name, price, category, stock } = req.body;

  if (!rfid_tag || !name || price === undefined) {
    return res.status(400).json({
      success: false,
      message: 'rfid_tag, name, price 는 필수 항목입니다.',
    });
  }

  try {
    // RFID 중복 체크
    const [existing] = await pool.query(
      'SELECT id FROM products WHERE rfid_tag = ?',
      [rfid_tag]
    );
    if (existing.length > 0) {
      return res.status(409).json({
        success: false,
        message: '이미 등록된 RFID 태그입니다.',
      });
    }

    const [result] = await pool.query(
      'INSERT INTO products (rfid_tag, name, price, category, stock) VALUES (?, ?, ?, ?, ?)',
      [rfid_tag, name, Number(price), category || null, Number(stock) || 0]
    );

    const [newProduct] = await pool.query(
      'SELECT id, rfid_tag, name, price, category, stock FROM products WHERE id = ?',
      [result.insertId]
    );

    // Redis에 임시 저장된 pending RFID 삭제 (등록 완료)
    await redis.del('rfid:pending:admin');

    return res.status(201).json({
      success: true,
      message: `${name} 상품이 등록되었습니다.`,
      product: newProduct[0],
    });
  } catch (err) {
    console.error('[Product] createProduct error:', err);
    return res.status(500).json({ success: false, message: '서버 오류가 발생했습니다.' });
  }
};

// ───────────────────────────────────────────────
// DELETE /api/products/:id
// ───────────────────────────────────────────────
const deleteProduct = async (req, res) => {
  const { id } = req.params;

  try {
    const [existing] = await pool.query('SELECT id, name FROM products WHERE id = ?', [id]);
    if (existing.length === 0) {
      return res.status(404).json({ success: false, message: '상품을 찾을 수 없습니다.' });
    }

    await pool.query('DELETE FROM products WHERE id = ?', [id]);

    return res.status(200).json({
      success: true,
      message: `${existing[0].name} 상품이 삭제되었습니다.`,
    });
  } catch (err) {
    console.error('[Product] deleteProduct error:', err);
    return res.status(500).json({ success: false, message: '서버 오류가 발생했습니다.' });
  }
};

// Redis HSET 평탄화 데이터 → 상품 배열 변환
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

// ───────────────────────────────────────────────
// POST /api/products/rfid-scan
// Body: { uid: string }   ← 아두이노에서 전송
//
// 1. 매칭된 쇼핑 유저(CartMe-ROS2-08)가 있고 이미 등록된 상품이면 장바구니에 추가
// 2. 쇼핑 중이 아니거나 미등록 상품이면 상품 등록 대기열(Redis)로 전송
// ───────────────────────────────────────────────
const rfidScan = async (req, res) => {
  const { uid } = req.body;

  if (!uid) {
    return res.status(400).json({ success: false, message: 'uid가 필요합니다.' });
  }

  const tag = uid.trim().toUpperCase();

  try {
    // [Redis] 2.5초 이내 동일 카드 중복 스캔 방지 (백엔드 디바운싱)
    const robotSerialNumber = 'CartMe-ROS2-08';
    const debounceKey = `robot:last_scan:${robotSerialNumber}`;
    const lastScan = await redis.hgetall(debounceKey);
    const now = Date.now();

    if (lastScan && lastScan.tag === tag) {
      const lastScanTime = parseInt(lastScan.scannedAt, 10);
      if (now - lastScanTime < 2500) {
        console.log(`[Product -> Debounce] Ignored duplicate scan for tag: ${tag} within 2.5s`);
        
        // 업데이트된 장바구니 전체 조회하여 현재 화면 유지되도록 전송
        const robotStatusKey = `robot:status:${robotSerialNumber}`;
        const userId = await redis.hget(robotStatusKey, 'userId');
        if (userId) {
          const cartKey = `cart:${userId}:${robotSerialNumber}`;
          const cartRaw   = await redis.hgetall(cartKey);
          const cartItems = parseCartFromRedis(cartRaw);
          const totalAmount = cartItems.reduce((sum, item) => sum + item.price * item.qty, 0);
          
          const io = req.app.get('io');
          io.to(`user:${userId}`).emit('cart:updated', {
            items: cartItems,
            totalAmount,
            updatedAt: new Date().toISOString(),
          });
        }

        return res.status(200).json({
          success: true,
          message: '중복 스캔이 방지되었습니다.',
          ignored: true
        });
      }
    }

    // 최신 스캔 기록 저장 (5초 TTL)
    await redis.hmset(debounceKey, { tag, scannedAt: String(now) });
    await redis.expire(debounceKey, 5);

    // [Redis] 로봇에 매칭된 쇼핑 유저 ID 조회
    const robotStatusKey = `robot:status:${robotSerialNumber}`;
    const userId = await redis.hget(robotStatusKey, 'userId');

    if (userId) {
      // [MySQL] rfid_tag로 상품 정보 조회 (products 테이블)
      const [rows] = await pool.query(
        'SELECT id, name, price, category, stock FROM products WHERE rfid_tag = ?',
        [tag]
      );
      
      // 이미 등록된 상품인 경우 장바구니에 실시간 추가
      if (rows.length > 0) {
        const product = rows[0];
        const cartKey = `cart:${userId}:${robotSerialNumber}`;

        const existingQty = await redis.hget(cartKey, `${product.id}_qty`);
        const newQty = existingQty ? parseInt(existingQty, 10) + 1 : 1;

        // [Stock Limit Check]
        const dbStock = (product.stock !== null && product.stock !== undefined) ? Number(product.stock) : 0;
        if (newQty > dbStock) {
          console.log(`[Product] Stock limit exceeded for product: ${product.name}. Stock: ${dbStock}, Requested: ${newQty}`);
          
          const io = req.app.get('io');
          io.to(`user:${userId}`).emit('cart:error', {
            message: `${product.name}의 재고가 부족합니다. (남은 재고: ${dbStock}개)`
          });
          return res.status(400).json({ success: false, message: '재고가 부족합니다.' });
        }

        await redis.hmset(cartKey, {
          [`${product.id}_name`]:  product.name,
          [`${product.id}_price`]: String(product.price),
          [`${product.id}_qty`]:   String(newQty),
        });

        // 업데이트된 장바구니 전체 조회
        const cartRaw   = await redis.hgetall(cartKey);
        const cartItems = parseCartFromRedis(cartRaw);
        const totalAmount = cartItems.reduce((sum, item) => sum + item.price * item.qty, 0);

        // [WebSocket] 유저 룸으로 장바구니 업데이트 실시간 푸시
        const io = req.app.get('io');
        io.to(`user:${userId}`).emit('cart:updated', {
          items: cartItems,
          totalAmount,
          updatedAt: new Date().toISOString(),
        });

        console.log(`[Product -> Shopping] Added ${product.name} to cart for user ${userId} from robot: ${robotSerialNumber}`);

        return res.status(200).json({
          success: true,
          message: `${product.name}이(가) 장바구니에 추가되었습니다.`,
          addedProduct: { ...product, qty: newQty },
        });
      }
    }

    // [Fallback] 쇼핑 유저가 없거나 미등록 상품인 경우 관리자 상품 등록 대기열로 임시 저장
    await redis.set('rfid:pending:admin', tag, 'EX', 30);

    // [WebSocket] 관리자 룸에 RFID 태그 push
    const io = req.app.get('io');
    io.to('room:admin').emit('rfid:scanned', { uid: tag, scannedAt: new Date().toISOString() });

    console.log(`[Product -> Admin] Routed RFID scan to admin pending registration: ${tag}`);

    return res.status(200).json({
      success: true,
      message: '상품 등록 대기열로 전송되었습니다.',
      uid: tag,
    });
  } catch (err) {
    console.error('[Product] rfidScan error:', err);
    return res.status(500).json({ success: false, message: '서버 오류가 발생했습니다.' });
  }
};

module.exports = { getProducts, createProduct, deleteProduct, rfidScan };
