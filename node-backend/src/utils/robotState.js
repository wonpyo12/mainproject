// ===================================================================
// 로봇 실시간 상태 (메모리) — 라파 pose_bridge.py 가 POST 로 주기 갱신
//   pose      : { x, y, theta, frame, robotSerialNumber, updatedAt }
//   telemetry : { battery, cpuTemp, robotSerialNumber, updatedAt }
// hardware.controller(수신) 와 admin.controller(대시보드 집계) 가 공유.
// ===================================================================
const FRESH_MS = 12000; // 이 시간 내 수신이 있어야 '온라인' 판정

const state = {
  pose: null,
  telemetry: null,
};

// 마지막 pose/telemetry 수신이 충분히 최근이면 로봇 온라인
function isOnline() {
  const now = Date.now();
  const fresh = (v) => v && now - new Date(v.updatedAt).getTime() < FRESH_MS;
  return fresh(state.pose) || fresh(state.telemetry);
}

module.exports = { state, isOnline, FRESH_MS };
