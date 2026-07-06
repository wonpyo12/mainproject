// ===================================================================
// 서버 진입점 - HTTP + Socket.io 통합 초기화
// ===================================================================
require('dotenv').config();
const updateProjectIPs = require('./utils/ipUpdater');
updateProjectIPs(); // 백엔드 IP 자동 동기화 실행
const http = require('http');
const { Server: SocketServer } = require('socket.io');

const app          = require('./app');
const { initSocket } = require('./socket');

const PORT = process.env.PORT || 3000;

// HTTP 서버 생성 (Express 앱 래핑)
const httpServer = http.createServer(app);

// Socket.io 서버 초기화
const io = new SocketServer(httpServer, {
  cors: { origin: '*', methods: ['GET', 'POST'] },
});

// app 객체에 io 등록 → 컨트롤러에서 req.app.get('io')로 접근
app.set('io', io);

// Socket.io 인증 및 이벤트 핸들러 등록
initSocket(io);

httpServer.listen(PORT, () => {
  console.log(`[Server] CartPilot Node.js Backend running on http://localhost:${PORT}`);
});
