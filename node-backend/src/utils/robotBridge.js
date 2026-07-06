// ===================================================================
// 로봇(라파) 명령 브릿지
//   백엔드 ──TCP(9998)──→ 라파 cmd_server ──ROS2──→ 터틀봇3
//
//   - sendRobotCommand('HALT')    그 자리 래치 정지
//   - sendRobotCommand('RESUME')  정지 해제(추종 재개)
//   - sendRobotCommand('RETURN')  SLAM 홈 복귀 트리거
//
// DDS(노트북↔라파)가 불안정해 명령 전달은 TCP 로 우회하는 기존 구조를 그대로 사용.
// 라파 IP/포트는 .env 로 주입 (IP 가 자주 바뀜).
// ===================================================================
const net = require('net');

const PI_HOST = process.env.PI_HOST || 'localhost';
const PI_CMD_PORT = Number(process.env.PI_CMD_PORT) || 9998;
const CONNECT_TIMEOUT_MS = 3000;

/**
 * 라파 cmd_server 로 한 줄 명령을 전송한다. (1회 연결 → 전송 → 종료)
 * 실패해도 서버가 죽지 않도록 reject 는 호출부에서 처리.
 * @param {string} command  'HALT' | 'RESUME' | 'RETURN' (대문자, 개행은 자동 추가)
 * @returns {Promise<void>}
 */
function sendRobotCommand(command) {
  return new Promise((resolve, reject) => {
    const socket = new net.Socket();
    let settled = false;

    const done = (err) => {
      if (settled) return;
      settled = true;
      socket.destroy();
      if (err) reject(err);
      else resolve();
    };

    socket.setTimeout(CONNECT_TIMEOUT_MS);

    socket.connect(PI_CMD_PORT, PI_HOST, () => {
      socket.write(`${command}\n`, () => {
        console.log(`[RobotBridge] '${command}' → ${PI_HOST}:${PI_CMD_PORT} 전송`);
        done();
      });
    });

    socket.on('timeout', () => done(new Error(`로봇 연결 시간 초과 (${PI_HOST}:${PI_CMD_PORT})`)));
    socket.on('error', (err) => done(err));
  });
}

module.exports = { sendRobotCommand, PI_HOST, PI_CMD_PORT };
