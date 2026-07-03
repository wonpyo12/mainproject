// ===================================================================
// 웹 관리자 대시보드 집계 컨트롤러
//   GET /api/admin/dashboard
//   - robots  : [MySQL] robots 테이블 + [Redis] robot:status/cart + 실시간 pose/telemetry
//   - metrics : [MySQL] 오늘 거래액 · 평균 쇼핑시간(session_started_at 기반)
//   - sessions: [MySQL] 오늘 시간대별 결제 건수 (09~20시)
// 미처리 알림 수는 프론트의 실시간 알림 목록에서 계산한다.
// ===================================================================
const pool  = require('../config/db');    // [MySQL]
const redis = require('../config/redis'); // [Redis]
const robotState = require('../utils/robotState');
const { sendRobotCommand } = require('../utils/robotBridge');

// Redis robot:status 의 status → 웹 STATUS 키 매핑
function mapStatus(redisStatus, online) {
  if (!online) return 'offline';
  if (redisStatus === 'SHOPPING')  return 'following';
  if (redisStatus === 'RETURNING') return 'returning';
  return 'idle';
}

const getDashboard = async (req, res) => {
  try {
    const online = robotState.isOnline();
    const { pose, telemetry } = robotState.state;
    // pose/telemetry 를 보내는 실물 카트의 시리얼 (라파 pose_bridge 설정과 일치)
    const liveSerial = (pose && pose.robotSerialNumber)
      || (telemetry && telemetry.robotSerialNumber) || 'CartMe-ROS2-08';

    // ── 로봇 플릿: 등록 로봇(robots 테이블) + 실시간 상태 결합 ──
    const [robotRows] = await pool.query(
      'SELECT serial_number, model FROM robots ORDER BY id'
    );

    const robots = [];
    for (const row of robotRows) {
      const serial = row.serial_number;
      const isLive = serial === liveSerial && online;

      const statusHash = await redis.hgetall(`robot:status:${serial}`);
      const redisStatus = statusHash ? statusHash.status : null;

      // 매칭된 이용자 이름 + 장바구니 (SHOPPING 세션일 때만)
      let userName = null, userEmail = null, items = 0, amount = 0;
      let cartItems = [];
      const uid = statusHash && statusHash.userId ? statusHash.userId : null;
      if (uid) {
        const [urows] = await pool.query('SELECT name, email FROM users WHERE id = ?', [uid]);
        if (urows.length > 0) {
          userName  = urows[0].name;
          userEmail = urows[0].email;
        }
        // Redis 평탄화 해시 → [{ name, price, qty }] (카메라 모니터링 초기 표시용)
        const cartRaw = await redis.hgetall(`cart:${uid}:${serial}`);
        const byId = {};
        for (const [field, value] of Object.entries(cartRaw || {})) {
          const idx = field.indexOf('_');
          const pid = field.substring(0, idx);
          const attr = field.substring(idx + 1);
          if (!byId[pid]) byId[pid] = { productId: Number(pid) };
          if (attr === 'name')  byId[pid].name  = value;
          if (attr === 'price') byId[pid].price = Number(value);
          if (attr === 'qty')   byId[pid].qty   = Number(value);
        }
        cartItems = Object.values(byId);
        items  = cartItems.reduce((s, it) => s + (it.qty || 0), 0);
        amount = cartItems.reduce((s, it) => s + (it.price || 0) * (it.qty || 0), 0);
      }

      robots.push({
        id: serial,
        model: row.model,
        status: mapStatus(redisStatus, isLive),
        user: userName,
        userId: userEmail ? userEmail.split('@')[0] : null,
        zone: isLive && pose
          ? `맵 X ${pose.x.toFixed(1)} · Y ${pose.y.toFixed(1)}`
          : '—',
        battery: isLive && telemetry ? telemetry.battery : null,
        cpuTemp: isLive && telemetry ? telemetry.cpuTemp : null,
        x: isLive && pose ? pose.x : null,
        y: isLive && pose ? pose.y : null,
        items,
        amount,
        cartItems,
        sessionStatus: redisStatus || null,   // SHOPPING | RETURNING | null
      });
    }

    // ── 오늘 거래액 ──
    const [salesRows] = await pool.query(
      `SELECT COALESCE(SUM(total_price), 0) AS todaySales
       FROM orders
       WHERE payment_status = 'COMPLETED' AND DATE(ordered_at) = CURDATE()`
    );
    const todaySales = Number(salesRows[0].todaySales);

    // ── 평균 쇼핑시간 (오늘, 시작시각이 기록된 주문만) ──
    const [avgRows] = await pool.query(
      `SELECT AVG(TIMESTAMPDIFF(SECOND, session_started_at, ordered_at)) AS avgSec
       FROM orders
       WHERE payment_status = 'COMPLETED'
         AND session_started_at IS NOT NULL
         AND DATE(ordered_at) = CURDATE()`
    );
    const avgSec = avgRows[0].avgSec != null ? Number(avgRows[0].avgSec) : null;
    const avgShoppingTime = avgSec == null ? '—'
      : avgSec < 60 ? `${Math.round(avgSec)}초`
      : `${Math.round(avgSec / 60)}분`;

    // ── 시간대별 결제 세션 (오늘 09~20시) ──
    const [hourRows] = await pool.query(
      `SELECT HOUR(ordered_at) AS h, COUNT(*) AS v
       FROM orders
       WHERE payment_status = 'COMPLETED' AND DATE(ordered_at) = CURDATE()
       GROUP BY HOUR(ordered_at)`
    );
    const byHour = Object.fromEntries(hourRows.map(r => [Number(r.h), Number(r.v)]));
    const sessions = [];
    for (let h = 9; h <= 20; h++) {
      sessions.push({ h: `${String(h).padStart(2, '0')}시`, v: byHour[h] || 0 });
    }

    return res.status(200).json({
      success: true,
      robots,
      metrics: { todaySales, avgShoppingTime },
      sessions,
      pose,
      telemetry,
    });
  } catch (err) {
    console.error('[Admin] getDashboard error:', err);
    return res.status(500).json({ success: false, message: '서버 오류가 발생했습니다.' });
  }
};

// ───────────────────────────────────────────────
// POST /api/admin/robot/command  Body: { command: 'HALT'|'RESUME'|'RETURN' }
// 관리자 웹 제어 패널 → 라파 cmd_server TCP (긴급 정지 / 정지 해제 / 충전소 복귀)
// ───────────────────────────────────────────────
const ADMIN_COMMANDS = {
  HALT:   '로봇을 긴급 정지했습니다.',
  RESUME: '정지를 해제했습니다.',
  RETURN: '충전소 복귀를 시작합니다.',
};

const robotCommand = async (req, res) => {
  const { command } = req.body;
  if (!ADMIN_COMMANDS[command]) {
    return res.status(400).json({ success: false, message: '지원하지 않는 명령입니다. (HALT|RESUME|RETURN)' });
  }
  try {
    await sendRobotCommand(command);
    console.log(`[Admin] 로봇 제어: ${command}`);
    return res.status(200).json({ success: true, message: ADMIN_COMMANDS[command] });
  } catch (err) {
    console.error(`[Admin] robotCommand(${command}) error:`, err.message);
    return res.status(502).json({ success: false, message: `로봇에 신호를 전달하지 못했습니다: ${err.message}` });
  }
};

module.exports = { getDashboard, robotCommand };
