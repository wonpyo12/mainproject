// ===================================================================
// [파트 1] 회원 관리 컨트롤러
//   - register : [MySQL] bcrypt 해싱 → users 테이블 INSERT
//   - login    : [MySQL] 이메일 조회 → 비밀번호 검증 → JWT 발급
//   - generateQR: [Redis] QR 세션 생성 (TTL 180초)
// ===================================================================
const bcrypt = require('bcrypt');
const jwt    = require('jsonwebtoken');
const { v4: uuidv4 } = require('uuid');

const pool  = require('../config/db');    // [MySQL]
const redis = require('../config/redis'); // [Redis]

const SALT_ROUNDS = 10;

// ───────────────────────────────────────────────
// POST /api/auth/register
// ───────────────────────────────────────────────
const register = async (req, res) => {
  const { email, password, name, phone, user_type } = req.body;

  if (!email || !password || !name) {
    return res.status(400).json({ success: false, message: '이메일, 비밀번호, 이름은 필수입니다.' });
  }

  const allowedTypes = ['GENERAL', 'ELDERLY'];
  const userType = allowedTypes.includes(user_type) ? user_type : 'GENERAL';

  try {
    // [MySQL] 이메일 중복 확인
    const [existing] = await pool.query(
      'SELECT id FROM users WHERE email = ?',
      [email]
    );
    if (existing.length > 0) {
      return res.status(409).json({ success: false, message: '이미 사용 중인 이메일입니다.' });
    }

    // bcrypt 비밀번호 해싱
    const hashedPassword = await bcrypt.hash(password, SALT_ROUNDS);

    // [MySQL] users 테이블 INSERT
    const [result] = await pool.query(
      `INSERT INTO users (email, password, name, phone, user_type, created_at)
       VALUES (?, ?, ?, ?, ?, NOW())`,
      [email, hashedPassword, name, phone || null, userType]
    );

    return res.status(201).json({
      success: true,
      message: '회원가입이 완료되었습니다.',
      userId: result.insertId,
    });
  } catch (err) {
    console.error('[Auth] register error:', err);
    return res.status(500).json({ success: false, message: '서버 오류가 발생했습니다.' });
  }
};

// ───────────────────────────────────────────────
// POST /api/auth/login
// ───────────────────────────────────────────────
const login = async (req, res) => {
  const { email, password } = req.body;

  if (!email || !password) {
    return res.status(400).json({ success: false, message: '이메일과 비밀번호를 입력해 주세요.' });
  }

  try {
    // [MySQL] 이메일로 유저 조회
    const [rows] = await pool.query(
      'SELECT id, email, password, name, phone, user_type FROM users WHERE email = ?',
      [email]
    );

    if (rows.length === 0) {
      return res.status(401).json({ success: false, message: '이메일 또는 비밀번호가 올바르지 않습니다.' });
    }

    const user = rows[0];

    // bcrypt 비밀번호 검증
    const isMatch = await bcrypt.compare(password, user.password);
    if (!isMatch) {
      return res.status(401).json({ success: false, message: '이메일 또는 비밀번호가 올바르지 않습니다.' });
    }

    // JWT 발급 - 페이로드: userId, email, userType
    const token = jwt.sign(
      { userId: user.id, email: user.email, userType: user.user_type },
      process.env.JWT_SECRET,
      { expiresIn: process.env.JWT_EXPIRES_IN || '7d' }
    );

    return res.status(200).json({
      success: true,
      message: '로그인에 성공했습니다.',
      token,
      user: {
        id: user.id,
        email: user.email,
        name: user.name,
        phone: user.phone,
        userType: user.user_type,
      },
    });
  } catch (err) {
    console.error('[Auth] login error:', err);
    return res.status(500).json({ success: false, message: '서버 오류가 발생했습니다.' });
  }
};

// ───────────────────────────────────────────────
// GET /api/auth/qr  (JWT 필요)
// ───────────────────────────────────────────────
const generateQR = async (req, res) => {
  const userId = req.user.userId;

  try {
    const qrToken   = uuidv4();
    const redisKey  = `qr:auth:${qrToken}`;

    // [Redis] qr:auth:{token} = userId, TTL 3분(180초)
    await redis.set(redisKey, String(userId), 'EX', 180);

    return res.status(200).json({
      success: true,
      qrToken,
      expiresIn: 180,
      message: 'QR 토큰이 생성되었습니다. 3분 내에 스캔해 주세요.',
    });
  } catch (err) {
    console.error('[Auth] generateQR error:', err);
    return res.status(500).json({ success: false, message: '서버 오류가 발생했습니다.' });
  }
};

module.exports = { register, login, generateQR };
