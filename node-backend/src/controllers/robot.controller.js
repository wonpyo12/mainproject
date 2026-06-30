// ===================================================================
// 로봇 제어 컨트롤러 (앱 → 백엔드 → 라파 cmd_server → 터틀봇3)
//   - stopRobot   : 정지 버튼      → HALT   (그 자리 래치 정지)
//   - resumeRobot : 추종 시작 버튼 → RESUME (정지 해제)
//   복귀(RETURN)는 결제완료 흐름(order.controller)에서 함께 전송한다.
// ===================================================================
const { sendRobotCommand } = require('../utils/robotBridge');

// ───────────────────────────────────────────────
// POST /api/robot/stop   (JWT 필요)
// Body: { robotSerialNumber: string }
// ───────────────────────────────────────────────
const stopRobot = async (req, res) => {
  const { robotSerialNumber } = req.body;
  if (!robotSerialNumber) {
    return res.status(400).json({ success: false, message: 'robotSerialNumber가 필요합니다.' });
  }
  try {
    await sendRobotCommand('HALT');
    return res.status(200).json({ success: true, message: '로봇을 정지했습니다.' });
  } catch (err) {
    console.error('[Robot] stopRobot error:', err.message);
    return res.status(502).json({ success: false, message: '로봇에 정지 신호를 전달하지 못했습니다.' });
  }
};

// ───────────────────────────────────────────────
// POST /api/robot/resume (JWT 필요)
// Body: { robotSerialNumber: string }
// ───────────────────────────────────────────────
const resumeRobot = async (req, res) => {
  const { robotSerialNumber } = req.body;
  if (!robotSerialNumber) {
    return res.status(400).json({ success: false, message: 'robotSerialNumber가 필요합니다.' });
  }
  try {
    await sendRobotCommand('RESUME');
    return res.status(200).json({ success: true, message: '추종을 재개했습니다.' });
  } catch (err) {
    console.error('[Robot] resumeRobot error:', err.message);
    return res.status(502).json({ success: false, message: '로봇에 재개 신호를 전달하지 못했습니다.' });
  }
};

module.exports = { stopRobot, resumeRobot };
