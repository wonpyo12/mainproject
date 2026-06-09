import React from 'react';

export function Battery({ level }) {
  const tone = level <= 20 ? 'var(--red)' : level <= 45 ? 'var(--amber)' : 'var(--green)';
  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 7 }}>
      <span style={{ position: 'relative', width: 26, height: 13, border: '1.5px solid var(--border-strong)', borderRadius: 3 }}>
        <span style={{ position: 'absolute', right: -3.5, top: 3.5, width: 2, height: 4, background: 'var(--border-strong)', borderRadius: 1 }} />
        <span style={{ position: 'absolute', left: 1.5, top: 1.5, bottom: 1.5, width: `calc(${level}% - 3px)`, minWidth: 2, background: tone, borderRadius: 1.5 }} />
      </span>
      <span className="mono" style={{ fontSize: 12, color: 'var(--text-2)', fontWeight: 600 }}>{level}%</span>
    </span>
  );
}
