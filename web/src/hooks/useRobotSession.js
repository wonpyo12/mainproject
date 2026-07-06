import { useState, useEffect } from 'react';
import { io } from 'socket.io-client';

const BACKEND_URL = 'http://192.168.0.29:3000';

// 고객 쇼핑 세션 실시간 구독 훅 — 카메라 모니터링 화면용
// QR 매칭 / RFID 스캔 / 결제 완료 때 백엔드가 room:admin 으로 쏘는
// 'session:update' { robotSerialNumber, status, user, items, totalAmount, lastScanned }
export function useRobotSession(initialRobot) {
  const [session, setSession] = useState(null);

  // 초기값: 대시보드 API 가 내려준 로봇의 세션 스냅샷
  useEffect(() => {
    if (initialRobot && session === null) {
      setSession({
        robotSerialNumber: initialRobot.id,
        status: initialRobot.sessionStatus || null,
        user: initialRobot.user ? { name: initialRobot.user } : null,
        items: initialRobot.cartItems || [],
        totalAmount: initialRobot.amount || 0,
        updatedAt: null,
      });
    }
  }, [initialRobot]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    const socket = io(BACKEND_URL, {
      auth: { token: 'admin-cartpilot' },
      transports: ['websocket'],
    });
    socket.on('session:update', (s) => setSession(s));
    return () => socket.disconnect();
  }, []);

  return session;
}
