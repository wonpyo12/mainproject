import React, { useState } from 'react';
import { Card } from '../components/Card';
import { Icon } from '../components/Icon';
import { Badge } from '../components/Badge';
import { SectionHead } from '../components/SectionHead';
import { MAP, worldToPct } from '../mapConfig';
import { useRobotPose } from '../hooks/useRobotPose';

export function MapView() {
  const [showGrid, setShowGrid] = useState(true);
  const { pose, live } = useRobotPose();

  const marker = pose ? worldToPct(pose.x, pose.y) : null;
  // ROS theta: x축 기준 반시계(rad) / CSS rotate: 시계방향(deg) → 부호 반전
  const headingDeg = pose ? -(pose.theta * 180) / Math.PI : 0;

  const mapMetadata = [
    { label: '맵 파일명', value: 'map_classroom_final.pgm', icon: 'file-image' },
    { label: '해상도 (Resolution)', value: '0.05 m/pixel (5cm)', icon: 'zoom-in' },
    { label: '맵 원점 (Origin)', value: `X: ${MAP.originX}, Y: ${MAP.originY}`, icon: 'compass' },
    { label: '실제 크기 (Dimension)', value: `${(MAP.widthPx * MAP.resolution).toFixed(2)}m × ${(MAP.heightPx * MAP.resolution).toFixed(2)}m`, icon: 'maximize-2' },
    { label: '점유 임계값', value: '65% (Occupied)', icon: 'shield-alert' },
    { label: '여유 공간 임계값', value: '25% (Free)', icon: 'shield-check' },
  ];

  return (
    <div style={{ display: 'grid', gridTemplateColumns: '1.6fr 1fr', gap: 18, alignItems: 'start' }}>
      <style>{`
        @keyframes pose-pulse {
          0%   { transform: scale(1);   opacity: 0.55; }
          100% { transform: scale(2.6); opacity: 0; }
        }
      `}</style>

      {/* Left Column: Live Map Viewer */}
      <Card pad={0}>
        <div style={{ padding: '16px 18px', borderBottom: '1px solid var(--border)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <h3 style={{ fontSize: 15, fontWeight: 700 }}>SLAM 실시간 맵 모니터</h3>
            {live
              ? <Badge tone="green">LIVE</Badge>
              : <Badge tone="gray">위치 수신 대기</Badge>}
            {pose && pose.frame === 'odom' && <Badge tone="amber">ODOM 폴백</Badge>}
          </div>

          <div style={{ display: 'flex', gap: 6 }}>
            <button
              className="ctl-btn"
              style={{ width: 'auto', padding: '6px 10px', fontSize: 11.5, background: showGrid ? 'var(--gray-bg)' : 'transparent' }}
              onClick={() => setShowGrid(!showGrid)}
            >
              <Icon name="grid" size={13} />
              격자 {showGrid ? '숨기기' : '표시'}
            </button>
          </div>
        </div>

        <div style={{ padding: 18 }}>
          <div style={{
            position: 'relative',
            aspectRatio: `${MAP.widthPx}/${MAP.heightPx}`,
            maxHeight: 620,
            margin: '0 auto',
            background: 'var(--surface-2)',
            border: '1px solid var(--border)',
            borderRadius: 8,
            overflow: 'hidden'
          }}>
            {/* SLAM Map Image */}
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

            {/* Grid Overlay (1m 간격) */}
            {showGrid && (
              <div style={{
                position: 'absolute',
                inset: 0,
                backgroundImage: 'linear-gradient(var(--border) 0.5px,transparent 0.5px),linear-gradient(90deg,var(--border) 0.5px,transparent 0.5px)',
                backgroundSize: `${(1 / (MAP.widthPx * MAP.resolution)) * 100}% ${(1 / (MAP.heightPx * MAP.resolution)) * 100}%`,
                opacity: 0.2
              }} />
            )}

            {/* Robot Marker */}
            {marker && (
              <div style={{
                position: 'absolute',
                left: `${marker.left}%`,
                top: `${marker.top}%`,
                width: 0,
                height: 0,
                transition: 'left 0.25s linear, top 0.25s linear'
              }}>
                {/* 펄스 링 */}
                <div style={{
                  position: 'absolute', left: -11, top: -11, width: 22, height: 22,
                  borderRadius: '50%',
                  background: live ? 'var(--green)' : 'var(--text-3)',
                  animation: live ? 'pose-pulse 1.6s ease-out infinite' : 'none',
                  opacity: live ? undefined : 0.25,
                }} />
                {/* 본체 + 진행방향 화살표 */}
                <div style={{
                  position: 'absolute', left: -9, top: -9, width: 18, height: 18,
                  transform: `rotate(${headingDeg}deg)`,
                  transition: 'transform 0.25s linear',
                }}>
                  <svg viewBox="0 0 18 18" width="18" height="18">
                    <circle cx="9" cy="9" r="7" fill={live ? 'var(--green)' : 'var(--text-3)'} stroke="#fff" strokeWidth="2" />
                    <path d="M9 4.5 L12.5 9 L9 13.5 L9 4.5" fill="#fff" transform="rotate(-90 9 9)" />
                  </svg>
                </div>
              </div>
            )}
          </div>

          <div style={{ marginTop: 14, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span style={{ fontSize: 12, color: 'var(--text-3)' }}>
              {pose
                ? `로봇 위치 X: ${pose.x.toFixed(2)}m · Y: ${pose.y.toFixed(2)}m · θ: ${(pose.theta * 180 / Math.PI).toFixed(0)}° (${pose.frame})`
                : '* 로봇 위치 수신 대기중 — pose_bridge 실행 여부를 확인하세요.'}
            </span>
            {pose && (
              <span style={{ fontSize: 11.5, color: 'var(--text-3)' }}>
                마지막 수신 {new Date(pose.updatedAt).toLocaleTimeString('ko-KR')}
              </span>
            )}
          </div>
        </div>
      </Card>

      {/* Right Column: Metadata & Controls */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 18 }}>

        {/* Map Metadata Card */}
        <Card>
          <SectionHead title="지도 메타데이터" en="Map Info" />
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12, marginTop: 12 }}>
            {mapMetadata.map((m, i) => (
              <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 10, paddingBottom: 10, borderBottom: i < mapMetadata.length - 1 ? '1px solid var(--border)' : 'none' }}>
                <div style={{ width: 28, height: 28, borderRadius: 6, background: 'var(--surface-2)', display: 'flex', alignItems: 'center', justifycontent: 'center', color: 'var(--text-2)', padding: 7 }}>
                  <Icon name={m.icon} size={14} />
                </div>
                <div style={{ flex: 1 }}>
                  <div style={{ fontSize: 11, color: 'var(--text-3)', fontWeight: 600 }}>{m.label}</div>
                  <div style={{ fontSize: 12.5, fontWeight: 600, color: 'var(--text)' }}>{m.value}</div>
                </div>
              </div>
            ))}
          </div>
        </Card>

      </div>

    </div>
  );
}
