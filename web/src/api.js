const BACKEND_URL = 'http://192.168.0.17:3000';

// 화면 표시용 고정 정보 (매장명/관리자) — 데이터 아님
const STATIC_INFO = {
  storeInfo: { name: '카트파일럿 데모 샵' },
  userInfo: { name: '관리자' },
};

// 관리자 로봇 제어 — 백엔드 → 라파 cmd_server TCP
// command: 'HALT'(긴급 정지) | 'RESUME'(정지 해제) | 'RETURN'(충전소 복귀)
export async function sendRobotCommand(command) {
  const res = await fetch(`${BACKEND_URL}/api/admin/robot/command`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ command }),
  });
  const d = await res.json().catch(() => ({}));
  if (!res.ok || !d.success) throw new Error(d.message || `명령 전송 실패 (${res.status})`);
  return d;
}

// 로봇 쇼핑 세션 강제 초기화
export async function resetRobotSession(robotSerialNumber) {
  const res = await fetch(`${BACKEND_URL}/api/admin/robot/reset-session`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ robotSerialNumber }),
  });
  const d = await res.json().catch(() => ({}));
  if (!res.ok || !d.success) throw new Error(d.message || `세션 초기화 실패 (${res.status})`);
  return d;
}

// 백엔드 대시보드 집계 API — 로봇 플릿·오늘 거래액·평균 쇼핑시간·시간대별 세션 (실데이터)
// 백엔드가 꺼져 있으면 mockData.json 으로 폴백해 화면은 유지한다.
export async function fetchDashboard() {
  try {
    const res = await fetch(`${BACKEND_URL}/api/admin/dashboard`);
    if (!res.ok) throw new Error(`dashboard API ${res.status}`);
    const d = await res.json();
    return {
      ...STATIC_INFO,
      robots: d.robots || [],
      metrics: d.metrics || {},
      sessions: d.sessions || [],
      alerts: [], // 알림은 소켓 실시간 이벤트로만 쌓는다
      live: true,
    };
  } catch (err) {
    console.warn('[API] 백엔드 대시보드 연결 실패 — mockData 폴백:', err.message);
    const res = await fetch('/mockData.json');
    if (!res.ok) throw new Error('Failed to load operational data');
    const mock = await res.json();
    return { ...mock, ...STATIC_INFO, live: false };
  }
}
