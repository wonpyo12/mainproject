// ===================================================================
// 문의(Inquiry) 컨트롤러
//   - createInquiry : [MySQL] 앱 '문의하기' 접수 (사용자 인증 필요)
//   - getInquiries  : [MySQL] 문의 목록 조회 (웹 관리자용)
//   - updateStatus  : [MySQL] 문의 처리 상태 변경 (PENDING | ANSWERED)
// ===================================================================
const pool = require('../config/db'); // [MySQL]

// ───────────────────────────────────────────────
// POST /api/inquiries   (인증)
// Body: { content, category? }
// ───────────────────────────────────────────────
const createInquiry = async (req, res) => {
  const { content, category } = req.body;

  if (!content || !content.trim()) {
    return res.status(400).json({ success: false, message: '문의 내용을 입력해 주세요.' });
  }
  if (content.length > 2000) {
    return res.status(400).json({ success: false, message: '문의 내용이 너무 깁니다. (최대 2000자)' });
  }

  try {
    // 인증 미들웨어가 채운 req.user 에서 사용자 식별 (없으면 익명 허용)
    const userId = req.user?.userId || null;

    // 이름/이메일 스냅샷 확보 (users 조회)
    let name = null;
    let email = req.user?.email || null;
    if (userId) {
      const [rows] = await pool.query('SELECT name, email FROM users WHERE id = ?', [userId]);
      if (rows.length > 0) {
        name = rows[0].name;
        email = rows[0].email;
      }
    }

    const [result] = await pool.query(
      `INSERT INTO inquiries (user_id, name, email, category, content)
       VALUES (?, ?, ?, ?, ?)`,
      [userId, name, email, (category && category.trim()) || '일반', content.trim()]
    );

    return res.status(201).json({
      success: true,
      message: '문의가 접수되었습니다.',
      data: { id: result.insertId },
    });
  } catch (err) {
    console.error('[Inquiry] createInquiry error:', err);
    return res.status(500).json({ success: false, message: '서버 오류가 발생했습니다.' });
  }
};

// ───────────────────────────────────────────────
// GET /api/inquiries   (웹 관리자)
// Query: status?, search?, page?, limit?
// ───────────────────────────────────────────────
const getInquiries = async (req, res) => {
  const page = Math.max(1, parseInt(req.query.page) || 1);
  const limit = Math.min(100, Math.max(1, parseInt(req.query.limit) || 50));
  const offset = (page - 1) * limit;
  const status = req.query.status || null;
  const search = req.query.search ? `%${req.query.search}%` : null;

  try {
    const conditions = [];
    const params = [];

    if (status && ['PENDING', 'ANSWERED'].includes(status)) {
      conditions.push('status = ?');
      params.push(status);
    }
    if (search) {
      conditions.push('(content LIKE ? OR name LIKE ? OR email LIKE ?)');
      params.push(search, search, search);
    }
    const where = conditions.length > 0 ? `WHERE ${conditions.join(' AND ')}` : '';

    const [[{ total }]] = await pool.query(
      `SELECT COUNT(*) AS total FROM inquiries ${where}`,
      params
    );
    const [[{ pending }]] = await pool.query(
      `SELECT COUNT(*) AS pending FROM inquiries WHERE status = 'PENDING'`
    );

    const [rows] = await pool.query(
      `SELECT id, user_id, name, email, category, content, answer, status, answered_at, created_at
       FROM inquiries ${where}
       ORDER BY created_at DESC
       LIMIT ? OFFSET ?`,
      [...params, limit, offset]
    );

    return res.json({
      success: true,
      data: {
        inquiries: rows,
        pending,
        pagination: { total, page, limit, totalPages: Math.ceil(total / limit) },
      },
    });
  } catch (err) {
    console.error('[Inquiry] getInquiries error:', err);
    return res.status(500).json({ success: false, message: '서버 오류가 발생했습니다.' });
  }
};

// ───────────────────────────────────────────────
// PATCH /api/inquiries/:id/status
// Body: { status }
// ───────────────────────────────────────────────
const updateStatus = async (req, res) => {
  const { id } = req.params;
  const { status } = req.body;

  if (!['PENDING', 'ANSWERED'].includes(status)) {
    return res.status(400).json({ success: false, message: '유효하지 않은 상태입니다.' });
  }

  try {
    const [result] = await pool.query('UPDATE inquiries SET status = ? WHERE id = ?', [status, id]);
    if (result.affectedRows === 0) {
      return res.status(404).json({ success: false, message: '문의를 찾을 수 없습니다.' });
    }
    return res.json({ success: true, message: '상태가 변경되었습니다.' });
  } catch (err) {
    console.error('[Inquiry] updateStatus error:', err);
    return res.status(500).json({ success: false, message: '서버 오류가 발생했습니다.' });
  }
};

// ───────────────────────────────────────────────
// PATCH /api/inquiries/:id/answer   (웹 관리자)
// Body: { answer }  → 답변 저장 + 상태 ANSWERED
// ───────────────────────────────────────────────
const answerInquiry = async (req, res) => {
  const { id } = req.params;
  const { answer } = req.body;

  if (!answer || !answer.trim()) {
    return res.status(400).json({ success: false, message: '답변 내용을 입력해 주세요.' });
  }

  try {
    const [result] = await pool.query(
      `UPDATE inquiries
       SET answer = ?, status = 'ANSWERED', answered_at = NOW()
       WHERE id = ?`,
      [answer.trim(), id]
    );
    if (result.affectedRows === 0) {
      return res.status(404).json({ success: false, message: '문의를 찾을 수 없습니다.' });
    }
    return res.json({ success: true, message: '답변이 등록되었습니다.' });
  } catch (err) {
    console.error('[Inquiry] answerInquiry error:', err);
    return res.status(500).json({ success: false, message: '서버 오류가 발생했습니다.' });
  }
};

// ───────────────────────────────────────────────
// GET /api/inquiries/mine   (앱 - 로그인 사용자 본인 문의 + 답변)
// ───────────────────────────────────────────────
const getMyInquiries = async (req, res) => {
  const userId = req.user?.userId;
  if (!userId) {
    return res.status(401).json({ success: false, message: '인증이 필요합니다.' });
  }
  try {
    const [rows] = await pool.query(
      `SELECT id, category, content, answer, status, answered_at, created_at
       FROM inquiries
       WHERE user_id = ?
       ORDER BY created_at DESC
       LIMIT 50`,
      [userId]
    );
    return res.json({ success: true, data: { inquiries: rows } });
  } catch (err) {
    console.error('[Inquiry] getMyInquiries error:', err);
    return res.status(500).json({ success: false, message: '서버 오류가 발생했습니다.' });
  }
};

module.exports = { createInquiry, getInquiries, updateStatus, answerInquiry, getMyInquiries };
