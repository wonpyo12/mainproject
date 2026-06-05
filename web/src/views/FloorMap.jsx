import React from 'react';

export function FloorMap({ robots, selected, onSelect }) {
  const shelves = [
    { x: 18, y: 22, w: 22, h: 8, label: 'A · 신선식품' },
    { x: 54, y: 22, w: 22, h: 8, label: 'C · 음료' },
    { x: 30, y: 44, w: 30, h: 8, label: 'B · 가공식품' },
    { x: 66, y: 52, w: 20, h: 8, label: 'D · 생활용품' },
  ];
  
  const tone = (s) => ({
    following: 'var(--green)',
    alert: 'var(--red)',
    charging: 'var(--blue)',
    maintenance: 'var(--amber)',
    idle: 'var(--text-3)'
  }[s] || 'var(--text-3)');

  return (
    <div style={{ position: 'relative', width: '100%', aspectRatio: '16/9', background: 'var(--surface-2)', border: '1px solid var(--border)', borderRadius: 10, overflow: 'hidden' }}>
      {/* grid */}
      <div style={{ position: 'absolute', inset: 0, backgroundImage: 'linear-gradient(var(--border) 1px,transparent 1px),linear-gradient(90deg,var(--border) 1px,transparent 1px)', backgroundSize: '7.6% 13.5%', opacity: 0.4 }} />
      {/* entrance */}
      <div style={{ position: 'absolute', left: '44%', bottom: 0, width: '12%', height: 5, background: 'var(--text)', borderRadius: '3px 3px 0 0' }} />
      <div style={{ position: 'absolute', left: '44%', bottom: 8, fontSize: 9.5, color: 'var(--text-3)', fontWeight: 600, width: '12%', textAlign: 'center' }}>출입구</div>
      {/* charge station */}
      <div style={{ position: 'absolute', right: '2%', top: '78%', width: '14%', height: '16%', border: '1.5px dashed var(--blue)', borderRadius: 6, background: 'var(--blue-bg)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 9.5, color: 'var(--blue)', fontWeight: 700 }}>충전소</div>
      {/* shelves */}
      {shelves.map((s, i) => (
        <div key={i} style={{ position: 'absolute', left: s.x + '%', top: s.y + '%', width: s.w + '%', height: s.h + '%', background: 'var(--gray-bg)', border: '1px solid var(--border-strong)', borderRadius: 4, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 9.5, fontWeight: 600, color: 'var(--text-2)' }}>{s.label}</div>
      ))}
      {/* robots */}
      {robots.map((r) => {
        const on = selected === r.id;
        return (
          <button key={r.id} onClick={() => onSelect(r.id)} title={r.id} style={{
            position: 'absolute', left: r.x + '%', top: r.y + '%', transform: 'translate(-50%,-50%)',
            width: on ? 30 : 24, height: on ? 30 : 24, borderRadius: 99, cursor: 'pointer',
            background: 'var(--surface)', border: `2px solid ${tone(r.status)}`,
            boxShadow: on ? `0 0 0 4px ${tone(r.status)}22, 0 2px 6px rgba(0,0,0,.12)` : '0 1px 3px rgba(0,0,0,.14)',
            display: 'flex', alignItems: 'center', justifyContent: 'center', transition: 'all .15s', zIndex: on ? 3 : 2,
          }}>
            <span style={{ width: 9, height: 9, borderRadius: 2, background: tone(r.status) }} />
            {(r.status === 'following' || r.status === 'alert') && (
              <span style={{ position: 'absolute', inset: -2, borderRadius: 99, border: `1.5px solid ${tone(r.status)}`, opacity: 0.5, animation: 'ping 1.8s ease-out infinite' }} />
            )}
          </button>
        );
      })}
    </div>
  );
}
