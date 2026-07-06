// ===================================================================
// [파트 2 & 3] 하드웨어 연동 컨트롤러
//   - qrScan  : [Redis] QR 토큰 검증 → 로봇-유저 매칭
//   - rfidScan: [MySQL] 상품 조회 → [Redis] 장바구니 업데이트
//              → [WebSocket] 앱에 실시간 장바구니 푸시
// ===================================================================
const pool  = require('../config/db');    // [MySQL]
const redis = require('../config/redis'); // [Redis]
const http  = require('http');            // [HTTP for proxying camera stream]


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

    // [Redis] 기존 장바구니 데이터 초기화 (새 쇼핑 세션 시작)
    const cartKey = `cart:${userId}:${robotSerialNumber}`;
    await redis.del(cartKey);

    // [Redis] 로봇 상태 캐시: robot:status:{serialNumber} = { userId, status, startedAt }
    const robotStatusKey = `robot:status:${robotSerialNumber}`;
    await redis.hmset(robotStatusKey, {
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

    // [WebSocket] 장바구니 초기화(비어있음) 전송
    io.to(`user:${userId}`).emit('cart:updated', {
      items: [],
      totalAmount: 0,
      updatedAt: new Date().toISOString(),
    });

    // [WebSocket] 관리자 웹(카메라 모니터링)으로 세션 시작 push — QR 스캔 → 고객정보 연동
    const [userRows] = await pool.query('SELECT name FROM users WHERE id = ?', [userId]);
    io.to('room:admin').emit('session:update', {
      robotSerialNumber,
      status: 'SHOPPING',
      user: { id: Number(userId), name: userRows.length > 0 ? userRows[0].name : null },
      items: [],
      totalAmount: 0,
      updatedAt: new Date().toISOString(),
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
// Body: { rfidTag: string (or uid), robotSerialNumber: string }
// ───────────────────────────────────────────────
const rfidScan = async (req, res) => {
  const rawTag = req.body.rfidTag || req.body.uid;
  const { robotSerialNumber } = req.body;

  if (!rawTag || !robotSerialNumber) {
    return res.status(400).json({ success: false, message: 'rfidTag(또는 uid)와 robotSerialNumber가 필요합니다.' });
  }

  const tag = rawTag.trim().toUpperCase();

  try {
    // [Redis] 2.5초 이내 동일 카드 중복 스캔 방지 (백엔드 디바운싱)
    const debounceKey = `robot:last_scan:${robotSerialNumber}`;
    const lastScan = await redis.hgetall(debounceKey);
    const now = Date.now();

    if (lastScan && lastScan.tag === tag) {
      const lastScanTime = parseInt(lastScan.scannedAt, 10);
      if (now - lastScanTime < 2500) {
        console.log(`[Hardware -> Debounce] Ignored duplicate scan for tag: ${tag} within 2.5s`);
        
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

    // [Redis] 로봇에 매칭된 유저 ID 조회
    const robotStatusKey = `robot:status:${robotSerialNumber}`;
    const userId = await redis.hget(robotStatusKey, 'userId');
    
    if (!userId) {
      // [Fallback] 쇼핑 매칭된 유저가 없다면 관리자 상품 등록 대기열(Redis)로 임시 등록 후 Socket.io 전송
      await redis.set('rfid:pending:admin', tag, 'EX', 30);

      // [WebSocket] 관리자 룸에 RFID 태그 push
      const io = req.app.get('io');
      io.to('room:admin').emit('rfid:scanned', { uid: tag, scannedAt: new Date().toISOString() });

      console.log(`[Hardware -> Admin] No active session. Routed RFID scan to admin pending registration: ${tag} from robot: ${robotSerialNumber}`);

      return res.status(200).json({
        success: true,
        message: '매칭된 활성 쇼핑 유저가 없어 관리자 상품 등록 대기열로 전송되었습니다.',
        uid: tag,
      });
    }

    // [MySQL] rfid_tag로 상품 정보 조회 (products 테이블)
    const [rows] = await pool.query(
      'SELECT id, name, price, category, stock FROM products WHERE rfid_tag = ?',
      [tag]
    );
    if (rows.length === 0) {
      // [Fallback] 쇼핑 세션이 있더라도 DB에 존재하지 않는 신규 태그라면 등록 대기열(Redis)로 임시 등록 후 Socket.io 전송
      await redis.set('rfid:pending:admin', tag, 'EX', 30);

      // [WebSocket] 관리자 룸에 RFID 태그 push
      const io = req.app.get('io');
      io.to('room:admin').emit('rfid:scanned', { uid: tag, scannedAt: new Date().toISOString() });

      console.log(`[Hardware -> Admin Fallback] Unregistered tag scanned during shopping session. Routed to admin: ${tag}`);

      return res.status(200).json({
        success: true,
        message: '등록되지 않은 RFID 태그입니다. 관리자 등록 대기열로 전송되었습니다.',
        uid: tag,
      });
    }

    const product = rows[0];
    const cartKey = `cart:${userId}:${robotSerialNumber}`;

    // [Redis] 장바구니에 상품 추가/수량 증가
    const existingQty = await redis.hget(cartKey, `${product.id}_qty`);
    const newQty = existingQty ? parseInt(existingQty, 10) + 1 : 1;

    // [Stock Limit Check]
    const dbStock = (product.stock !== null && product.stock !== undefined) ? Number(product.stock) : 0;
    if (newQty > dbStock) {
      console.log(`[Hardware] Stock limit exceeded for product: ${product.name}. Stock: ${dbStock}, Requested: ${newQty}`);
      
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

    // [WebSocket] 관리자 웹(카메라 모니터링)으로도 장바구니 실시간 push
    const [userRows] = await pool.query('SELECT name FROM users WHERE id = ?', [userId]);
    io.to('room:admin').emit('session:update', {
      robotSerialNumber,
      status: 'SHOPPING',
      user: { id: Number(userId), name: userRows.length > 0 ? userRows[0].name : null },
      items: cartItems,
      totalAmount,
      lastScanned: product.name,
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

// ───────────────────────────────────────────────
// GET /api/hardware/video-feed
// 실시간 카메라 MJPEG 스트림 프록시 (크래시 방지 처리)
// ───────────────────────────────────────────────
// ───────────────────────────────────────────────
// 로봇 실시간 위치/텔레메트리 (라파 pose_bridge.py 가 주기 전송)
//   POST /api/hardware/pose      : SLAM 맵 좌표 (x, y, theta)
//   POST /api/hardware/telemetry : 배터리 % · CPU 온도 (하트비트 겸용)
//   GET  /api/hardware/pose      : 웹 관리자 첫 렌더링용 최신 위치 조회
// DB 없이 메모리(robotState)에만 유지 → 소켓(room:admin)으로 실시간 push
// ───────────────────────────────────────────────
const robotState = require('../utils/robotState');

const updatePose = (req, res) => {
  const { x, y, theta, frame, robotSerialNumber } = req.body;

  if (typeof x !== 'number' || typeof y !== 'number') {
    return res.status(400).json({ success: false, message: 'x, y 숫자 좌표가 필요합니다.' });
  }

  robotState.state.pose = {
    x,
    y,
    theta: typeof theta === 'number' ? theta : 0,
    frame: frame || 'map',                       // 'map'(AMCL) | 'odom'(폴백)
    robotSerialNumber: robotSerialNumber || 'CartMe-ROS2-08',
    updatedAt: new Date().toISOString(),
  };

  // [WebSocket] 관리자 웹(매장 지도 화면)으로 실시간 push
  const io = req.app.get('io');
  io.to('room:admin').emit('robot:pose', robotState.state.pose);

  return res.status(200).json({ success: true });
};

const getPose = (req, res) => {
  return res.status(200).json({ success: true, pose: robotState.state.pose });
};

const updateTelemetry = (req, res) => {
  const { battery, cpuTemp, robotSerialNumber } = req.body;

  robotState.state.telemetry = {
    battery: typeof battery === 'number' ? Math.round(battery) : null, // % (배터리 토픽 없으면 null)
    cpuTemp: typeof cpuTemp === 'number' ? cpuTemp : null,             // ℃ (라파 SoC)
    robotSerialNumber: robotSerialNumber || 'CartMe-ROS2-08',
    updatedAt: new Date().toISOString(),
  };

  const io = req.app.get('io');
  io.to('room:admin').emit('robot:telemetry', robotState.state.telemetry);

  return res.status(200).json({ success: true });
};

// GET /api/hardware/video-feed[?source=robot]
//   기본          : 노트북 QR 스캐너 캠 (qr_scanner_sim, 127.0.0.1:5000)
//   ?source=robot : 라파 추종 카메라 (web_stream_node, PI_HOST:8090/stream)
// QR 인증 전엔 노트북 캠, 매칭 후엔 로봇 캠을 웹이 골라 요청한다.
const PI_HOST = process.env.PI_HOST || 'localhost';

const videoFeed = (req, res) => {
  const robot = req.query.source === 'robot';
  const proxyReq = http.request(
    robot
      ? { host: PI_HOST, port: 8090, path: '/stream', method: 'GET' }
      : { host: '127.0.0.1', port: 5000, path: '/video_feed', method: 'GET' },
    (proxyRes) => {
      // 수신 스트림 에러 핸들링 (파이썬 서버 종료 시 크래시 방지)
      proxyRes.on('error', (err) => {
        console.error('[Video Feed Proxy Response Error]:', err.message);
      });

      // 클라이언트 응답 스트림 에러 핸들링
      res.on('error', (err) => {
        console.error('[Video Feed Client Response Error]:', err.message);
      });

      // 헤더 및 상태 코드 그대로 클라이언트로 포워딩
      res.writeHead(proxyRes.statusCode, proxyRes.headers);
      proxyRes.pipe(res);
    }
  );

  proxyReq.on('error', (err) => {
    console.error('[Video Feed Proxy Request Error]:', err.message);
    if (!res.headersSent) {
      res.status(502).send(robot
        ? `로봇 카메라(${PI_HOST}:8090)에 연결할 수 없습니다. 라파 camera_node/web_stream_node 를 확인하세요.`
        : '카메라 스트리밍 서버(Port 5000)를 연결할 수 없습니다. QR 스캐너(qr_scanner_sim.py)가 켜져 있는지 확인하세요.');
    }
  });

  // 클라이언트가 연결을 끊으면 프록시 요청도 즉시 파괴
  req.on('close', () => {
    proxyReq.destroy();
  });

  proxyReq.end();
};

module.exports = { qrScan, rfidScan, videoFeed, updatePose, getPose, updateTelemetry };
