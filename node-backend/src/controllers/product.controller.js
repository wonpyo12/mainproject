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

// ───────────────────────────────────────────────
// POST /api/products/rfid-scan
// Body: { uid: string }   ← 아두이노에서 전송
//
// 1. Redis에 임시 저장 (30초 TTL)
// 2. WebSocket으로 관리자 웹에 실시간 push
// ───────────────────────────────────────────────
const rfidScan = async (req, res) => {
  const { uid } = req.body;

  if (!uid) {
    return res.status(400).json({ success: false, message: 'uid가 필요합니다.' });
  }

  const tag = uid.trim().toUpperCase();

  try {
    // [Redis] 30초 TTL로 pending 태그 임시 저장
    await redis.set('rfid:pending:admin', tag, 'EX', 30);

    // [WebSocket] 관리자 룸에 RFID 태그 push
    const io = req.app.get('io');
    io.to('room:admin').emit('rfid:scanned', { uid: tag, scannedAt: new Date().toISOString() });

    console.log(`[Product] RFID scan received: ${tag}`);

    return res.status(200).json({
      success: true,
      message: '태그가 전송되었습니다.',
      uid: tag,
    });
  } catch (err) {
    console.error('[Product] rfidScan error:', err);
    return res.status(500).json({ success: false, message: '서버 오류가 발생했습니다.' });
  }
};

module.exports = { getProducts, createProduct, deleteProduct, rfidScan };
