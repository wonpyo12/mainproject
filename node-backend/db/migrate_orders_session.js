// 일회성 마이그레이션: orders.session_started_at 추가 (평균 쇼핑시간 계산용)
// QR 매칭(쇼핑 시작) 시각을 결제 시점에 Redis robot:status 에서 읽어와 저장한다.
// 실행: node db/migrate_orders_session.js
const pool = require('../src/config/db');

(async () => {
  try {
    const [cols] = await pool.query(
      `SELECT COUNT(*) AS n FROM information_schema.columns
       WHERE table_schema = DATABASE() AND table_name = 'orders'
         AND column_name = 'session_started_at'`
    );
    if (cols[0].n > 0) {
      console.log('[Migrate] orders.session_started_at 이미 존재 — 건너뜀');
    } else {
      await pool.query(
        `ALTER TABLE orders ADD COLUMN session_started_at DATETIME DEFAULT NULL AFTER payment_status`
      );
      console.log('[Migrate] orders.session_started_at 컬럼 추가 완료');
    }
  } catch (err) {
    console.error('[Migrate] 실패:', err.message);
  } finally {
    await pool.end();
    process.exit(0);
  }
})();
