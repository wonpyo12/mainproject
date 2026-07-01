// 일회성 마이그레이션: inquiries 에 답변 컬럼 추가
// 실행: node db/migrate_inquiry_answer.js
const pool = require('../src/config/db');

(async () => {
  try {
    const [cols] = await pool.query(
      `SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS
       WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'inquiries'`
    );
    const names = cols.map(c => c.COLUMN_NAME.toLowerCase());
    if (!names.includes('answer')) {
      await pool.query(`ALTER TABLE inquiries ADD COLUMN answer TEXT DEFAULT NULL AFTER content`);
      console.log('[Migrate] answer 컬럼 추가');
    } else { console.log('[Migrate] answer 컬럼 이미 존재'); }
    if (!names.includes('answered_at')) {
      await pool.query(`ALTER TABLE inquiries ADD COLUMN answered_at DATETIME DEFAULT NULL AFTER status`);
      console.log('[Migrate] answered_at 컬럼 추가');
    } else { console.log('[Migrate] answered_at 컬럼 이미 존재'); }
    console.log('[Migrate] 완료');
  } catch (err) {
    console.error('[Migrate] 실패:', err.message);
  } finally {
    await pool.end();
    process.exit(0);
  }
})();
