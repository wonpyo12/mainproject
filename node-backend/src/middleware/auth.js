// JWT 인증 미들웨어 - Authorization: Bearer <token> 헤더 검증
const jwt = require('jsonwebtoken');

function authenticateToken(req, res, next) {
  const authHeader = req.headers['authorization'];
  const token = authHeader && authHeader.split(' ')[1];

  if (!token) {
    return res.status(401).json({ success: false, message: '인증 토큰이 필요합니다.' });
  }

  jwt.verify(token, process.env.JWT_SECRET, (err, decoded) => {
    if (err) {
      return res.status(403).json({ success: false, message: '유효하지 않거나 만료된 토큰입니다.' });
    }
    req.user = decoded; // { userId, email, userType }
    next();
  });
}

module.exports = { authenticateToken };
