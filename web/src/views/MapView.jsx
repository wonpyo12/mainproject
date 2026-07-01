import React, { useState } from 'react';
import { Card } from '../components/Card';
import { Icon } from '../components/Icon';
import { Badge } from '../components/Badge';
import { SectionHead } from '../components/SectionHead';

export function MapView() {
  const [showGrid, setShowGrid] = useState(true);

  const mapMetadata = [
    { label: '맵 파일명', value: 'classroom_v3.pgm', icon: 'file-image' },
    { label: '해상도 (Resolution)', value: '0.05 m/pixel (5cm)', icon: 'zoom-in' },
    { label: '맵 원점 (Origin)', value: 'X: -4.71, Y: -3.33', icon: 'compass' },
    { label: '실제 크기 (Dimension)', value: '29.6m × 8.1m', icon: 'maximize-2' },
    { label: '점유 임계값', value: '65% (Occupied)', icon: 'shield-alert' },
    { label: '여유 공간 임계값', value: '25% (Free)', icon: 'shield-check' },
  ];

  return (
    <div style={{ display: 'grid', gridTemplateColumns: '1.6fr 1fr', gap: 18, alignItems: 'start' }}>
      
      {/* Left Column: Live Map Viewer */}
      <Card pad={0}>
        <div style={{ padding: '16px 18px', borderBottom: '1px solid var(--border)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <h3 style={{ fontSize: 15, fontWeight: 700 }}>SLAM 실시간 맵 모니터</h3>
            <Badge tone="green">ACTIVE</Badge>
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
            width: '100%', 
            aspectRatio: '135/104', 
            background: 'var(--surface-2)', 
            border: '1px solid var(--border)', 
            borderRadius: 8, 
            overflow: 'hidden' 
          }}>
            {/* SLAM Map Image */}
            <img 
              src="/classroom_v3.png" 
              alt="SLAM Map" 
              style={{ 
                position: 'absolute', 
                inset: 0, 
                width: '100%', 
                height: '100%', 
                objectFit: 'cover', 
                opacity: 0.95,
                mixBlendMode: 'multiply'
              }} 
            />

            {/* Grid Overlay */}
            {showGrid && (
              <div style={{ 
                position: 'absolute', 
                inset: 0, 
                backgroundImage: 'linear-gradient(var(--border) 0.5px,transparent 0.5px),linear-gradient(90deg,var(--border) 0.5px,transparent 0.5px)', 
                backgroundSize: '10% 10%', 
                opacity: 0.15 
              }} />
            )}
          </div>
          
          <div style={{ marginTop: 14, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span style={{ fontSize: 12, color: 'var(--text-3)' }}>
              * SLAM 모니터에서 매핑 현황을 모니터링할 수 있습니다.
            </span>
            <div style={{ display: 'flex', gap: 8 }}>
              <button className="icon-btn" title="확대"><Icon name="zoom-in" size={15} /></button>
              <button className="icon-btn" title="축소"><Icon name="zoom-out" size={15} /></button>
              <button className="icon-btn" title="초기화"><Icon name="rotate-ccw" size={15} /></button>
            </div>
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

        {/* Map Control Actions */}
        <Card>
          <SectionHead title="맵 제어 명령" en="SLAM Operations" />
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginTop: 12 }}>
            <button className="ctl-btn" style={{ justifyContent: 'flex-start', padding: '10px 14px' }}>
              <Icon name="refresh-cw" size={14} style={{ color: 'var(--green)' }} />
              <div style={{ textAlign: 'left' }}>
                <div style={{ fontSize: 12.5, fontWeight: 700 }}>SLAM 맵 재스캔 및 작성</div>
                <div style={{ fontSize: 10, color: 'var(--text-3)', fontWeight: 500 }}>현재 영역을 다시 레이저 스캔하여 동기화합니다.</div>
              </div>
            </button>
            
            <button className="ctl-btn" style={{ justifyContent: 'flex-start', padding: '10px 14px' }}>
              <Icon name="save" size={14} style={{ color: 'var(--blue)' }} />
              <div style={{ textAlign: 'left' }}>
                <div style={{ fontSize: 12.5, fontWeight: 700 }}>현재 매장 지도 파일 저장</div>
                <div style={{ fontSize: 10, color: 'var(--text-3)', fontWeight: 500 }}>수정된 구역 및 마크업 설정을 서버에 저장합니다.</div>
              </div>
            </button>

            <button className="ctl-btn" style={{ justifyContent: 'flex-start', padding: '10px 14px' }}>
              <Icon name="navigation" size={14} style={{ color: 'var(--amber)' }} />
              <div style={{ textAlign: 'left' }}>
                <div style={{ fontSize: 12.5, fontWeight: 700 }}>수동 목표 위치(Goal) 전송</div>
                <div style={{ fontSize: 10, color: 'var(--text-3)', fontWeight: 500 }}>지도를 클릭하여 지정한 좌표로 로봇을 보냅니다.</div>
              </div>
            </button>
          </div>
        </Card>
        
      </div>
      
    </div>
  );
}
