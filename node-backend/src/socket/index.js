// ===================================================================
// Socket.io 이벤트 관리
//   - 일반 유저  : JWT 인증 → user:{userId} 룸 참여
//   - 관리자 웹  : token = "admin" → room:admin 룸 참여
//                  (상품 등록 시 RFID 태그 실시간 수신)
// ===================================================================
const jwt = require('jsonwebtoken');

function initSocket(io) {
  // 소켓 연결 인증 미들웨어
  io.use((socket, next) => {
    const token = socket.handshake.auth?.token;

    // ── 관리자 웹 연결 (간단한 admin 토큰) ──
    if (token === 'admin-cartpilot') {
      socket.role = 'admin';
      return next();
    }

    // ── 일반 유저 JWT 검증 ──
    if (!token) {
      return next(new Error('Authentication token required'));
    }
    jwt.verify(token, process.env.JWT_SECRET, (err, decoded) => {
      if (err) return next(new Error('Invalid or expired token'));
      socket.user = decoded; // { userId, email, userType }
      socket.role = 'user';
      next();
    });
  });

  io.on('connection', (socket) => {
    if (socket.role === 'admin') {
      // 관리자 웹: admin 룸 참여
      socket.join('room:admin');
      console.log(`[Socket] Admin connected (socketId: ${socket.id})`);

      socket.on('disconnect', (reason) => {
        console.log(`[Socket] Admin disconnected (${reason})`);
      });

    } else {
      // 일반 유저: 개인 룸 참여
      const userId = socket.user.userId;
      console.log(`[Socket] User ${userId} connected (socketId: ${socket.id})`);
      socket.join(`user:${userId}`);

      socket.on('disconnect', (reason) => {
        console.log(`[Socket] User ${userId} disconnected (${reason})`);
      });
    }
  });
}

module.exports = { initSocket };
