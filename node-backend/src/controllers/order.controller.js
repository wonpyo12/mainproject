// ===================================================================
// [파트 4] 쇼핑 완료 컨트롤러
//   - completeOrder  : [Redis] 장바구니 읽기
//                    → [MySQL] orders + order_items 영구 저장 (트랜잭션)
//                    → [Redis] 장바구니 삭제, 로봇 상태 RETURNING
//                    → [WebSocket] 결제 완료 이벤트 푸시
//                    → ROS2 복귀 명령 전송
//   - getOrderHistory: [MySQL] 주문 이력 조회
// ===================================================================
const pool  = require('../config/db');    // [MySQL]
const redis = require('../config/redis'); // [Redis]
const { sendRobotCommand } = require('../utils/robotBridge'); // [로봇] TCP 명령 브릿지

// ───────────────────────────────────────────────
// POST /api/orders/complete  (JWT 필요)
// Body: { robotSerialNumber: string }
// ───────────────────────────────────────────────
const completeOrder = async (req, res) => {
  // returnRobot=false: 주문만 저장하고 복귀 신호는 보내지 않는다 (결제 완료 화면의 [복귀] 버튼에서 별도 전송)
  const { robotSerialNumber, returnRobot = true } = req.body;
  const userId = req.user.userId;

  if (!robotSerialNumber) {
    return res.status(400).json({ success: false, message: 'robotSerialNumber가 필요합니다.' });
  }

  const cartKey        = `cart:${userId}:${robotSerialNumber}`;
  const robotStatusKey = `robot:status:${robotSerialNumber}`;

  // MySQL 트랜잭션용 전용 커넥션 획득
  const conn = await pool.getConnection();

  try {
    // [Redis] 현재 장바구니 전체 읽기
    // 장바구니가 비어 있으면 결제 없이 '카트 반납'으로 처리 (복귀 명령은 항상 전송)
    const cartRaw = await redis.hgetall(cartKey);
    if (!cartRaw || Object.keys(cartRaw).length === 0) {
      conn.release();

      await redis.hmset(robotStatusKey, {
        status:      'RETURNING',
        userId:      '',
        completedAt: new Date().toISOString(),
      });
      sendRobotReturnCommand(robotSerialNumber);

      const io = req.app.get('io');
      io.to('room:admin').emit('session:update', {
        robotSerialNumber,
        status: 'RETURNING',
        user: null,
        items: [],
        totalAmount: 0,
        orderTotal: 0,
        updatedAt: new Date().toISOString(),
      });

      return res.status(200).json({
        success: true,
        message: '구매한 상품이 없어 카트만 반납합니다.',
        orderId: null,
        totalPrice: 0,
      });
    }

    const cartItems   = parseCartFromRedis(cartRaw);
    const totalPrice  = cartItems.reduce((sum, item) => sum + item.price * item.qty, 0);

    // [Redis] QR 매칭 때 기록된 쇼핑 시작 시각 (평균 쇼핑시간 통계용, 없으면 NULL)
    const startedAtRaw = await redis.hget(robotStatusKey, 'startedAt');
    const sessionStartedAt = startedAtRaw ? new Date(startedAtRaw) : null;

    // [MySQL] robots 테이블에서 serial_number로 robot DB id 조회
    const [robotRows] = await conn.query(
      'SELECT id FROM robots WHERE serial_number = ?',
      [robotSerialNumber]
    );
    if (robotRows.length === 0) {
      conn.release();
      return res.status(404).json({ success: false, message: '등록되지 않은 로봇입니다.' });
    }
    const robotId = robotRows[0].id;

    await conn.beginTransaction();

    // [MySQL] orders 테이블 INSERT
    // 컬럼: user_id, robot_id, total_price, payment_status, session_started_at, ordered_at
    const [orderResult] = await conn.query(
      `INSERT INTO orders (user_id, robot_id, total_price, payment_status, session_started_at, ordered_at)
       VALUES (?, ?, ?, 'COMPLETED', ?, NOW())`,
      [userId, robotId, totalPrice, sessionStartedAt]
    );
    const orderId = orderResult.insertId;

    // [MySQL] order_items 일괄 INSERT (bulk insert)
    // 컬럼: order_id, product_id, quantity, price
    const itemValues = cartItems.map(item => [orderId, item.productId, item.qty, item.price]);
    await conn.query(
      'INSERT INTO order_items (order_id, product_id, quantity, price) VALUES ?',
      [itemValues]
    );

    await conn.commit();
    conn.release();

    // [Redis] 장바구니 데이터 삭제
    await redis.del(cartKey);

    if (returnRobot) {
      // [Redis] 로봇 상태 → RETURNING
      await redis.hmset(robotStatusKey, {
        status:      'RETURNING',
        userId:      '',
        completedAt: new Date().toISOString(),
      });

      // ROS2 / 로봇 복귀 명령 전송 (가상 메서드)
      sendRobotReturnCommand(robotSerialNumber);
    }

    // [WebSocket] 유저 앱으로 결제 완료 이벤트 푸시
    const io = req.app.get('io');
    io.to(`user:${userId}`).emit('order:completed', {
      orderId,
      totalPrice,
      items: cartItems,
      completedAt: new Date().toISOString(),
    });

    if (returnRobot) {
      // [WebSocket] 관리자 웹(카메라 모니터링)으로 세션 종료 push — 결제 완료 → 복귀
      io.to('room:admin').emit('session:update', {
        robotSerialNumber,
        status: 'RETURNING',
        user: null,
        items: [],
        totalAmount: 0,
        orderTotal: totalPrice,
        updatedAt: new Date().toISOString(),
      });
    } else {
      // 결제만 완료 — 세션(사용자·SHOPPING 상태)은 유지하고 비워진 장바구니만 반영
      const [userRows] = await pool.query('SELECT name FROM users WHERE id = ?', [userId]);
      io.to('room:admin').emit('session:update', {
        robotSerialNumber,
        status: 'SHOPPING',
        user: { id: Number(userId), name: userRows.length > 0 ? userRows[0].name : null },
        items: [],
        totalAmount: 0,
        orderTotal: totalPrice,
        updatedAt: new Date().toISOString(),
      });
    }

    return res.status(200).json({
      success: true,
      message: '결제가 완료되었습니다.',
      orderId,
      totalPrice,
    });
  } catch (err) {
    await conn.rollback();
    conn.release();
    console.error('[Order] completeOrder error:', err);
    return res.status(500).json({ success: false, message: '서버 오류가 발생했습니다.' });
  }
};

// ───────────────────────────────────────────────
// GET /api/orders/history  (JWT 필요)
// ───────────────────────────────────────────────
const getOrderHistory = async (req, res) => {
  const userId = req.user.userId;

  try {
    // [MySQL] 유저 주문 목록과 주문 상품 JOIN 조회
    const [rows] = await pool.query(
      `SELECT
         o.id          AS orderId,
         o.total_price AS totalPrice,
         o.payment_status AS paymentStatus,
         o.ordered_at  AS orderedAt,
         oi.product_id AS productId,
         oi.quantity,
         oi.price      AS unitPrice,
         p.name        AS productName
       FROM orders o
       JOIN order_items oi ON o.id = oi.order_id
       JOIN products    p  ON oi.product_id = p.id
       WHERE o.user_id = ?
       ORDER BY o.ordered_at DESC`,
      [userId]
    );

    // 주문 id 기준으로 그룹핑
    const grouped = {};
    for (const row of rows) {
      if (!grouped[row.orderId]) {
        grouped[row.orderId] = {
          orderId:       row.orderId,
          totalPrice:    row.totalPrice,
          paymentStatus: row.paymentStatus,
          orderedAt:     row.orderedAt,
          items:         [],
        };
      }
      grouped[row.orderId].items.push({
        productId:   row.productId,
        productName: row.productName,
        quantity:    row.quantity,
        unitPrice:   row.unitPrice,
      });
    }

    return res.status(200).json({
      success: true,
      orders: Object.values(grouped),
    });
  } catch (err) {
    console.error('[Order] getOrderHistory error:', err);
    return res.status(500).json({ success: false, message: '서버 오류가 발생했습니다.' });
  }
};

// 로봇 SLAM 복귀 명령 전송
//   백엔드 ──TCP(9998)──→ 라파 cmd_server "RETURN"
//   → /robocart/return=RETURN_HOME 발행 + 추종 정지(nav2 가 /cmd_vel 제어)
// 결제(트랜잭션·웹소켓)는 이미 끝난 뒤이므로, 전송 실패해도 결제는 성공 처리하고 로그만 남긴다.
function sendRobotReturnCommand(robotSerialNumber) {
  sendRobotCommand('RETURN')
    .then(() => console.log(`[Robot] ${robotSerialNumber} → SLAM 복귀(RETURN_HOME) 신호 전송`))
    .catch((err) => console.error(`[Robot] ${robotSerialNumber} 복귀 신호 전송 실패:`, err.message));
}

// Redis HSET 평탄화 → 상품 배열
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

module.exports = { completeOrder, getOrderHistory };
