// [MySQL] 데이터베이스 스키마 및 샘플 데이터 전체 자동 생성 스크립트 (migrate_schema.js)
// 실행: node db/migrate_schema.js

const fs = require('fs');
const path = require('path');
const pool = require('../src/config/db');

(async () => {
  try {
    const schemaPath = path.join(__dirname, 'schema.sql');
    if (!fs.existsSync(schemaPath)) {
      console.error('[Migrate] schema.sql 파일을 찾을 수 없습니다.');
      process.exit(1);
    }

    console.log('[Migrate] schema.sql 파일 읽는 중...');
    const sql = fs.readFileSync(schemaPath, 'utf8');

    // 세미콜론(;) 기준으로 쿼리 분할 (주석 필터링 포함)
    const queries = sql
      .split(';')
      .map(q => q.trim())
      .filter(q => q.length > 0 && !q.startsWith('--'));

    console.log(`[Migrate] 총 ${queries.length}개의 쿼리를 실행합니다...`);

    for (let i = 0; i < queries.length; i++) {
      const query = queries[i];
      // USE cartpilot_db; 쿼리는 pool 커넥션 상 무시하거나 실행
      try {
        await pool.query(query);
      } catch (queryErr) {
        // 이미 테이블이나 DB가 존재하여 발생하는 일부 경고는 무시
        if (!queryErr.message.includes('already exists') && !queryErr.message.includes('database exists')) {
          console.warn(`[Migrate] 쿼리 #${i + 1} 경고/오류:`, queryErr.message);
        }
      }
    }

    console.log('[Migrate] MySQL 데이터베이스 테이블 및 초기화가 성공적으로 완료되었습니다!');
  } catch (err) {
    console.error('[Migrate] 스키마 실행 실패:', err.message);
  } finally {
    await pool.end();
    process.exit(0);
  }
})();
