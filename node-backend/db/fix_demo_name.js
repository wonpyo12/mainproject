const pool = require('../src/config/db');
(async () => {
  try {
    await pool.query(`UPDATE users SET name = '김카트' WHERE email = 'inqtest@cartme.com'`);
    await pool.query(`UPDATE inquiries SET name = '김카트'
       WHERE user_id = (SELECT id FROM users WHERE email = 'inqtest@cartme.com')`);
    console.log('[Fix] 이름 정상화 완료');
  } catch (e) { console.error(e.message); }
  finally { await pool.end(); process.exit(0); }
})();
