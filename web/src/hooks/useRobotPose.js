import { useState, useEffect, useRef } from 'react';
import { io } from 'socket.io-client';

import { BACKEND_URL } from '../api';
const STALE_MS = 4000; // 이 시간 동안 pose 없으면 신호 끊김 처리

// 로봇 실시간 위치 구독 훅 — 매장 지도 / 대시보드 공용
// 초기값은 GET /api/hardware/pose, 이후 socket 'robot:pose' 로 갱신
export function useRobotPose() {
  const [pose, setPose] = useState(null);   // { x, y, theta, frame, updatedAt }
  const [live, setLive] = useState(false);
  const lastRecvRef = useRef(0);

  useEffect(() => {
    fetch(`${BACKEND_URL}/api/hardware/pose`)
      .then(r => r.json())
      .then(d => { if (d.pose) setPose(d.pose); })
      .catch(() => {});

    const socket = io(BACKEND_URL, {
      auth: { token: 'admin-cartpilot' },
      transports: ['websocket'],
    });
    socket.on('robot:pose', (p) => {
      lastRecvRef.current = Date.now();
      setPose(p);
      setLive(true);
    });

    const staleTimer = setInterval(() => {
      if (Date.now() - lastRecvRef.current > STALE_MS) setLive(false);
    }, 1000);

    return () => {
      clearInterval(staleTimer);
      socket.disconnect();
    };
  }, []);

  return { pose, live };
}
