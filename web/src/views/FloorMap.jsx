import React from 'react';
import { MAP, worldToPct } from '../mapConfig';
import { useRobotPose } from '../hooks/useRobotPose';

// 대시보드 실시간 매장 현황 — SLAM 맵 위에 실제 로봇(추종 카트) 위치 표시.
// pose 는 라파 pose_bridge → 백엔드 → socket 'robot:pose' 로 수신.
export function FloorMap({ robots, selected, onSelect }) {
  const { pose, live } = useRobotPose();

  const marker = pose ? worldToPct(pose.x, pose.y) : null;
  // ROS theta: x축 기준 반시계(rad) / CSS rotate: 시계방향(deg) → 부호 반전
  const headingDeg = pose ? -(pose.theta * 180) / Math.PI : 0;
  // 실물 카트는 플릿 목록의 첫 로봇으로 취급 (클릭 시 상세 패널 연동)
  const cartId = robots && robots.length > 0 ? robots[0].id : null;
  const on = cartId && selected === cartId;

  return (
    <div style={{ position: 'relative', aspectRatio: `${MAP.widthPx}/${MAP.heightPx}`, maxHeight: 420, margin: '0 auto', background: 'var(--surface-2)', border: '1px solid var(--border)', borderRadius: 10, overflow: 'hidden' }}>
      {/* SLAM Map Background */}
      <img
        src={MAP.image}
        alt="SLAM Map"
        style={{
          position: 'absolute',
          inset: 0,
          width: '100%',
          height: '100%',
          imageRendering: 'pixelated',
          opacity: 0.95,
          mixBlendMode: 'multiply'
        }}
      />

      {/* grid overlay (1m 간격) */}
      <div style={{ position: 'absolute', inset: 0, backgroundImage: 'linear-gradient(var(--border) 0.5px,transparent 0.5px),linear-gradient(90deg,var(--border) 0.5px,transparent 0.5px)', backgroundSize: `${(1 / (MAP.widthPx * MAP.resolution)) * 100}% ${(1 / (MAP.heightPx * MAP.resolution)) * 100}%`, opacity: 0.12 }} />

      {/* 실제 로봇 위치 */}
      {marker ? (
        <button
          onClick={() => cartId && onSelect(cartId)}
          title={pose.robotSerialNumber || cartId || 'ROBOCART'}
          style={{
            position: 'absolute', left: `${marker.left}%`, top: `${marker.top}%`,
            transform: 'translate(-50%,-50%)',
            width: on ? 30 : 24, height: on ? 30 : 24, borderRadius: 99, cursor: 'pointer',
            background: 'var(--surface)',
            border: `2.5px solid ${live ? 'var(--green)' : 'var(--text-3)'}`,
            boxShadow: on ? '0 0 0 4px var(--green-bg), 0 2px 6px rgba(0,0,0,.12)' : '0 1px 3px rgba(0,0,0,.14)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            transition: 'left 0.25s linear, top 0.25s linear, width .15s, height .15s', zIndex: 2, padding: 0,
          }}
        >
          {/* 진행방향 화살표 */}
          <svg viewBox="0 0 14 14" width="13" height="13" style={{ transform: `rotate(${headingDeg}deg)`, transition: 'transform 0.25s linear' }}>
            <path d="M12 7 L4 3 L6 7 L4 11 Z" fill={live ? 'var(--green)' : 'var(--text-3)'} />
          </svg>
          {live && (
            <span style={{ position: 'absolute', inset: -2, borderRadius: 99, border: '1.5px solid var(--green)', opacity: 0.5, animation: 'ping 1.8s ease-out infinite' }} />
          )}
        </button>
      ) : (
        <div style={{ position: 'absolute', inset: 0, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 12, color: 'var(--text-3)', fontWeight: 600 }}>
          로봇 위치 수신 대기중…
        </div>
      )}

      {/* 좌표 라벨 */}
      {pose && (
        <div style={{ position: 'absolute', left: 8, bottom: 6, fontSize: 10.5, color: 'var(--text-3)', fontWeight: 600, background: 'var(--surface)', padding: '2px 7px', borderRadius: 6, border: '1px solid var(--border)', opacity: 0.9 }}>
          X {pose.x.toFixed(2)}m · Y {pose.y.toFixed(2)}m {pose.frame === 'odom' ? '· odom' : ''}
        </div>
      )}
    </div>
  );
}
