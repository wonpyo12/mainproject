// ===================================================================
// 회원 관리 컨트롤러 (관리자용)
//   - getMembers  : [MySQL] users 목록 조회 (페이징, 검색, 필터)
//   - getMember   : [MySQL] 특정 회원 상세 조회
//   - updateMember: [MySQL] 회원 정보 수정
//   - deleteMember: [MySQL] 회원 삭제 (soft delete)
// ===================================================================
const pool = require('../config/db'); // [MySQL]

// ───────────────────────────────────────────────
// GET /api/members
// Query: page, limit, search, user_type
// ───────────────────────────────────────────────
const getMembers = async (req, res) => {
  const page = Math.max(1, parseInt(req.query.page) || 1);
  const limit = Math.min(100, Math.max(1, parseInt(req.query.limit) || 20));
  const offset = (page - 1) * limit;
  const search = req.query.search ? `%${req.query.search}%` : null;
  const userType = req.query.user_type || null;

  try {
    // WHERE 조건 동적 빌드
    const conditions = [];
    const params = [];

    if (search) {
      conditions.push('(name LIKE ? OR email LIKE ? OR phone LIKE ?)');
      params.push(search, search, search);
    }
    if (userType && ['GENERAL', 'ELDERLY'].includes(userType)) {
      conditions.push('user_type = ?');
      params.push(userType);
    }

    const where = conditions.length > 0 ? `WHERE ${conditions.join(' AND ')}` : '';

    // 전체 카운트
    const [[{ total }]] = await pool.query(
      `SELECT COUNT(*) AS total FROM users ${where}`,
      params
    );

    // 목록 조회 (비밀번호 제외)
    const [rows] = await pool.query(
      `SELECT id, email, name, phone, user_type, created_at
       FROM users ${where}
       ORDER BY created_at DESC
       LIMIT ? OFFSET ?`,
      [...params, limit, offset]
    );

    return res.json({
      success: true,
      data: {
        members: rows,
        pagination: {
          total,
          page,
          limit,
          totalPages: Math.ceil(total / limit),
        },
      },
    });
  } catch (err) {
    console.error('[Member] getMembers error:', err);
    return res.status(500).json({ success: false, message: '서버 오류가 발생했습니다.' });
  }
};

// ───────────────────────────────────────────────
// GET /api/members/:id
// ───────────────────────────────────────────────
const getMember = async (req, res) => {
  const { id } = req.params;

  try {
    const [rows] = await pool.query(
      'SELECT id, email, name, phone, user_type, created_at FROM users WHERE id = ?',
      [id]
    );

    if (rows.length === 0) {
      return res.status(404).json({ success: false, message: '회원을 찾을 수 없습니다.' });
    }

    return res.json({ success: true, data: { member: rows[0] } });
  } catch (err) {
    console.error('[Member] getMember error:', err);
    return res.status(500).json({ success: false, message: '서버 오류가 발생했습니다.' });
  }
};

// ───────────────────────────────────────────────
// PATCH /api/members/:id
// ───────────────────────────────────────────────
const updateMember = async (req, res) => {
  const { id } = req.params;
  const { name, phone, user_type } = req.body;

  const allowedTypes = ['GENERAL', 'ELDERLY'];
  if (user_type && !allowedTypes.includes(user_type)) {
    return res.status(400).json({ success: false, message: '유효하지 않은 회원 유형입니다.' });
  }

  try {
    const [existing] = await pool.query('SELECT id FROM users WHERE id = ?', [id]);
    if (existing.length === 0) {
      return res.status(404).json({ success: false, message: '회원을 찾을 수 없습니다.' });
    }

    await pool.query(
      `UPDATE users SET
        name = COALESCE(?, name),
        phone = COALESCE(?, phone),
        user_type = COALESCE(?, user_type)
       WHERE id = ?`,
      [name || null, phone || null, user_type || null, id]
    );

    const [updated] = await pool.query(
      'SELECT id, email, name, phone, user_type, created_at FROM users WHERE id = ?',
      [id]
    );

    return res.json({
      success: true,
      message: '회원 정보가 수정되었습니다.',
      data: { member: updated[0] },
    });
  } catch (err) {
    console.error('[Member] updateMember error:', err);
    return res.status(500).json({ success: false, message: '서버 오류가 발생했습니다.' });
  }
};

// ───────────────────────────────────────────────
// DELETE /api/members/:id
// ───────────────────────────────────────────────
const deleteMember = async (req, res) => {
  const { id } = req.params;

  try {
    const [existing] = await pool.query('SELECT id FROM users WHERE id = ?', [id]);
    if (existing.length === 0) {
      return res.status(404).json({ success: false, message: '회원을 찾을 수 없습니다.' });
    }

    await pool.query('DELETE FROM users WHERE id = ?', [id]);

    return res.json({ success: true, message: '회원이 삭제되었습니다.' });
  } catch (err) {
    console.error('[Member] deleteMember error:', err);
    return res.status(500).json({ success: false, message: '서버 오류가 발생했습니다.' });
  }
};

module.exports = { getMembers, getMember, updateMember, deleteMember };
