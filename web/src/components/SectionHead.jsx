import React from 'react';

export function SectionHead({ title, en, action }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 14 }}>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 9 }}>
        <h3 style={{ fontSize: 15, fontWeight: 700, letterSpacing: '-0.01em', whiteSpace: 'nowrap' }}>{title}</h3>
        {en && <span className="mono" style={{ fontSize: 11, color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>{en}</span>}
      </div>
      {action}
    </div>
  );
}
