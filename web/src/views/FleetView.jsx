import React from 'react';
import { Card } from '../components/Card';
import { SectionHead } from '../components/SectionHead';
import { Badge } from '../components/Badge';
import { Battery } from '../components/Battery';
import { Avatar } from '../components/Avatar';
import { Icon } from '../components/Icon';
import { FloorMap } from './FloorMap';
import { STATUS } from '../data';

function RobotRow({ r, selected, onSelect }) {
  const s = STATUS[r.status] || { ko: '—', tone: 'gray' };
  return (
    <button onClick={() => onSelect(r.id)} style={{
      display: 'grid', gridTemplateColumns: '92px 96px 1fr 100px 78px', alignItems: 'center', gap: 12,
      width: '100%', textAlign: 'left', padding: '12px 14px', cursor: 'pointer',
      background: selected === r.id ? 'var(--surface-2)' : 'transparent',
      border: 'none', borderBottom: '1px solid var(--border)', transition: 'background .12s',
    }}>
      <span className="mono" style={{ fontSize: 12.5, fontWeight: 700, color: 'var(--text)' }}>{r.id}</span>
      <Badge tone={s.tone}>{s.ko}</Badge>
      <span style={{ display: 'flex', alignItems: 'center', gap: 8, minWidth: 0 }}>
        {r.user ? (
          <>
            <Avatar name={r.user} size={26} />
            <span style={{ fontSize: 13, fontWeight: 600, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{r.user}</span>
            <span className="mono" style={{ fontSize: 11, color: 'var(--text-3)' }}>{r.userId}</span>
          </>
        ) : (
          <span style={{ fontSize: 13, color: 'var(--text-3)' }}>—</span>
        )}
      </span>
      <span style={{ fontSize: 12.5, color: 'var(--text-2)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{r.zone}</span>
      <Battery level={r.battery} />
    </button>
  );
}

export function FleetView({ selected, setSelected, robots = [] }) {
  if (robots.length === 0) {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 12, padding: '90px 0', color: 'var(--text-3)' }}>
        <Icon name="bot" size={30} />
        <div style={{ fontSize: 14, fontWeight: 600, color: 'var(--text-2)' }}>등록된 로봇이 없습니다</div>
        <div style={{ fontSize: 12.5 }}>백엔드 서버에서 로봇 데이터를 연결하면 이 화면에 표시됩니다.</div>
      </div>
    );
  }

  return (
    <div style={{ display: 'grid', gridTemplateColumns: '1fr 360px', gap: 18, alignItems: 'start' }}>
      <Card pad={0}>
        <div style={{ padding: '16px 16px 14px', borderBottom: '1px solid var(--border)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <h3 style={{ fontSize: 15, fontWeight: 700 }}>로봇 플릿 <span className="mono" style={{ fontSize: 11, color: 'var(--text-3)', fontWeight: 500 }}>{robots.length} units</span></h3>
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: '92px 96px 1fr 100px 78px', gap: 12, padding: '9px 14px', fontSize: 11, fontWeight: 700, color: 'var(--text-3)', borderBottom: '1px solid var(--border)', textTransform: 'uppercase', letterSpacing: '0.03em' }}>
          <span>ID</span><span>상태</span><span>이용자</span><span>구역</span><span>배터리</span>
        </div>
        {robots.map((r) => (
          <RobotRow key={r.id} r={r} selected={selected} onSelect={setSelected} />
        ))}
      </Card>
      <Card>
        <SectionHead title="제어 패널" en="Control" />
        <FloorMap robots={robots} selected={selected} onSelect={setSelected} />
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, marginTop: 16 }}>
          {[
            ['충전소 복귀', 'battery-charging'],
            ['긴급 정지', 'octagon-x'],
            ['재탐색', 'scan-search'],
            ['사용자 호출', 'megaphone']
          ].map(([l, ic]) => (
            <button key={l} className="ctl-btn">
              <Icon name={ic} size={15} />{l}
            </button>
          ))}
        </div>
      </Card>
    </div>
  );
}
