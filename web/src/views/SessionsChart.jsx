import React from 'react';

export function SessionsChart({ data }) {
  const max = Math.max(...data.map((d) => d.v));
  return (
    <div style={{ display: 'flex', alignItems: 'flex-end', gap: 8, height: 132, paddingTop: 6 }}>
      {data.map((d, i) => (
        <div key={i} style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 7, height: '100%', justifyContent: 'flex-end' }}>
          <div style={{ width: '100%', maxWidth: 26, height: (d.v / max) * 100 + '%', minHeight: 4, background: d.v === max ? 'var(--text)' : 'var(--border-strong)', borderRadius: '4px 4px 2px 2px', transition: 'height .4s' }} title={d.v + ' sessions'} />
          <span className="mono" style={{ fontSize: 10, color: 'var(--text-3)' }}>{d.h}</span>
        </div>
      ))}
    </div>
  );
}
