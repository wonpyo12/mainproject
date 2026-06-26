import React from 'react';

export function FloorMap({ robots, selected, onSelect }) {
  const tone = (s) => ({
    following: 'var(--green)',
    alert: 'var(--red)',
    charging: 'var(--blue)',
    maintenance: 'var(--amber)',
    idle: 'var(--text-3)'
  }[s] || 'var(--text-3)');

  // Map original coordinate (0-100% of 592x162) to cropped coordinate (0-100% of 135x104)
  const mapCoords = (origX, origY) => {
    const px = (origX / 100) * 592;
    const py = (origY / 100) * 162;
    const croppedX = ((px - 15) / 135) * 100;
    const croppedY = ((py - 46) / 104) * 100;
    return { x: croppedX, y: croppedY };
  };

  return (
    <div style={{ position: 'relative', width: '100%', aspectRatio: '135/104', background: 'var(--surface-2)', border: '1px solid var(--border)', borderRadius: 10, overflow: 'hidden' }}>
      {/* SLAM Map Background */}
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

      {/* grid overlay for tech look */}
      <div style={{ position: 'absolute', inset: 0, backgroundImage: 'linear-gradient(var(--border) 0.5px,transparent 0.5px),linear-gradient(90deg,var(--border) 0.5px,transparent 0.5px)', backgroundSize: '15% 15%', opacity: 0.1 }} />

      {/* robots */}
      {robots.map((r) => {
        const on = selected === r.id;
        const pos = mapCoords(r.x, r.y);
        return (
          <button key={r.id} onClick={() => onSelect(r.id)} title={r.id} style={{
            position: 'absolute', left: pos.x + '%', top: pos.y + '%', transform: 'translate(-50%,-50%)',
            width: on ? 28 : 22, height: on ? 28 : 22, borderRadius: 99, cursor: 'pointer',
            background: 'var(--surface)', border: `2.5px solid ${tone(r.status)}`,
            boxShadow: on ? `0 0 0 4px ${tone(r.status)}22, 0 2px 6px rgba(0,0,0,.12)` : '0 1px 3px rgba(0,0,0,.14)',
            display: 'flex', alignItems: 'center', justifyContent: 'center', transition: 'all .15s', zIndex: on ? 3 : 2,
          }}>
            <span style={{ width: 8, height: 8, borderRadius: 2, background: tone(r.status) }} />
            {(r.status === 'following' || r.status === 'alert') && (
              <span style={{ position: 'absolute', inset: -2, borderRadius: 99, border: `1.5px solid ${tone(r.status)}`, opacity: 0.5, animation: 'ping 1.8s ease-out infinite' }} />
            )}
          </button>
        );
      })}
    </div>
  );
}



