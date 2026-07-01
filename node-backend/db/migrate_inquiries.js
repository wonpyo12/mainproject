// 일회성 마이그레이션: inquiries 테이블 생성
// 실행: node db/migrate_inquiries.js
const pool = require('../src/config/db');

const DDL = `
CREATE TABLE IF NOT EXISTS inquiries (
  id         BIGINT       NOT NULL AUTO_INCREMENT,
  user_id    BIGINT       DEFAULT NULL,
  name       VARCHAR(50)  DEFAULT NULL,
  email      VARCHAR(100) DEFAULT NULL,
  category   VARCHAR(30)  DEFAULT '일반',
  content    TEXT         NOT NULL,
  status     VARCHAR(20)  NOT NULL DEFAULT 'PENDING',
  created_at DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  INDEX idx_inq_created (created_at),
  CONSTRAINT fk_inq_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
`;

(async () => {
  try {
    await pool.query(DDL);
    console.log('[Migrate] inquiries 테이블 생성 완료 (또는 이미 존재)');
  } catch (err) {
    console.error('[Migrate] 실패:', err.message);
  } finally {
    await pool.end();
    process.exit(0);
  }
})();
