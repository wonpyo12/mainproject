// ===================================================================
// Socket.io 이벤트 관리
//   - 연결 시 JWT 검증 (handshake.auth.token)
//   - 인증 성공 → user:{userId} 룸 자동 참여
//   - 하드웨어 컨트롤러에서 io.to(`user:${userId}`).emit(...) 으로 푸시
//
// 앱에서 연결 예시 (React Native / socket.io-client):
//   const socket = io('http://서버IP:3000', { auth: { token: 'JWT_TOKEN' } });
//   socket.on('cart:updated',   (data) => { ... });
//   socket.on('robot:matched',  (data) => { ... });
//   socket.on('order:completed',(data) => { ... });
// ===================================================================
const jwt = require('jsonwebtoken');

function initSocket(io) {
  // 소켓 연결 인증 미들웨어 - JWT 검증
  io.use((socket, next) => {
    const token = socket.handshake.auth?.token;
    if (!token) {
      return next(new Error('Authentication token required'));
    }
    jwt.verify(token, process.env.JWT_SECRET, (err, decoded) => {
      if (err) return next(new Error('Invalid or expired token'));
      socket.user = decoded; // { userId, email, userType }
      next();
    });
  });

  io.on('connection', (socket) => {
    const userId = socket.user.userId;
    console.log(`[Socket] User ${userId} connected  (socketId: ${socket.id})`);

    // 유저 전용 룸 참여 - 하드웨어 이벤트 수신 타겟
    socket.join(`user:${userId}`);

    socket.on('disconnect', (reason) => {
      console.log(`[Socket] User ${userId} disconnected (${reason})`);
    });
  });
}

module.exports = { initSocket };
