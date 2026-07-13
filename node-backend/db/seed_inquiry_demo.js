// 데모용 깨끗한 한글 문의+답변 시드 (curl 인코딩 깨짐 보정)
const pool = require('../src/config/db');

(async () => {
  try {
    // inqtest 사용자 찾기
    const [u] = await pool.query(`SELECT id, name, email FROM users WHERE email = 'inqtest@cartme.com' LIMIT 1`);
    const user = u[0];
    if (!user) { console.log('inqtest 사용자 없음'); process.exit(0); }

    // 기존 깨진 데모 문의 정리 후 재삽입
    await pool.query(`DELETE FROM inquiries WHERE user_id = ?`, [user.id]);

    await pool.query(
      `INSERT INTO inquiries (user_id, name, email, category, content, answer, status, answered_at, created_at)
       VALUES (?, ?, ?, '앱 문의', ?, ?, 'ANSWERED', NOW(), NOW())`,
      [user.id, user.name, user.email,
       '결제 영수증을 다시 받고 싶어요. 이메일로도 보내주실 수 있나요?',
       '영수증은 앱 주문내역에서 재발급하실 수 있어요. 요청하신 이메일로도 방금 발송해 드렸습니다. 감사합니다!']
    );
    await pool.query(
      `INSERT INTO inquiries (user_id, name, email, category, content, status, created_at)
       VALUES (?, ?, ?, '앱 문의', ?, 'PENDING', NOW())`,
      [user.id, user.name, user.email,
       '카트가 자꾸 저를 놓치는데 카메라 각도를 어떻게 맞춰야 하나요?']
    );
    console.log('[Seed] 데모 문의 2건 삽입 완료 (답변 1건 포함)');
  } catch (err) {
    console.error('[Seed] 실패:', err.message);
  } finally {
    await pool.end();
    process.exit(0);
  }
})();
