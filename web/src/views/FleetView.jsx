import React, { useState } from 'react';
import { Card } from '../components/Card';
import { SectionHead } from '../components/SectionHead';
import { Badge } from '../components/Badge';
import { Battery } from '../components/Battery';
import { Avatar } from '../components/Avatar';
import { Icon } from '../components/Icon';
import { FloorMap } from './FloorMap';
import { STATUS } from '../data';
import { sendRobotCommand } from '../api';

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
  const [halted, setHalted] = useState(false);  // 긴급 정지 래치 상태 (버튼 토글용)
  const [busy, setBusy] = useState(null);       // 전송 중인 명령
  const [msg, setMsg] = useState(null);         // { ok, text } 전송 결과 피드백

  const runCommand = async (command, confirmText) => {
    if (busy) return;
    if (confirmText && !window.confirm(confirmText)) return;
    setBusy(command);
    try {
      const r = await sendRobotCommand(command);
      setMsg({ ok: true, text: r.message });
      if (command === 'HALT') setHalted(true);
      if (command === 'RESUME') setHalted(false);
    } catch (e) {
      setMsg({ ok: false, text: e.message });
    } finally {
      setBusy(null);
      setTimeout(() => setMsg(null), 4000);
    }
  };

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
          {/* 충전소 복귀 → cmd_server RETURN (SLAM 홈 복귀) */}
          <button
            className="ctl-btn"
            disabled={busy != null}
            onClick={() => runCommand('RETURN', '로봇을 충전소(홈)로 복귀시킬까요?')}
          >
            <Icon name="battery-charging" size={15} />
            {busy === 'RETURN' ? '전송 중…' : '충전소 복귀'}
          </button>

          {/* 긴급 정지 ↔ 정지 해제 토글 → cmd_server HALT / RESUME */}
          <button
            className="ctl-btn"
            disabled={busy != null}
            style={halted ? { borderColor: 'var(--red)', color: 'var(--red)' } : { color: 'var(--red)' }}
            onClick={() => halted
              ? runCommand('RESUME')
              : runCommand('HALT', '로봇을 긴급 정지할까요?')}
          >
            <Icon name={halted ? 'play' : 'octagon-x'} size={15} />
            {busy === 'HALT' || busy === 'RESUME' ? '전송 중…' : halted ? '정지 해제' : '긴급 정지'}
          </button>
        </div>

        {/* 명령 전송 결과 */}
        {msg && (
          <div style={{
            marginTop: 10, padding: '8px 12px', borderRadius: 8, fontSize: 12, fontWeight: 600,
            background: msg.ok ? 'var(--green-bg)' : 'var(--red-bg)',
            color: msg.ok ? 'var(--green)' : 'var(--red)',
          }}>
            {msg.text}
          </div>
        )}
      </Card>
    </div>
  );
}
