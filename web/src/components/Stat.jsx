import React from 'react';
import { Card } from './Card';
import { Icon } from './Icon';

export function Stat({ label, value, sub, delta, deltaTone = 'green', icon }) {
  return (
    <Card pad={18}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 14 }}>
        <span style={{ fontSize: 12.5, color: 'var(--text-2)', fontWeight: 600, letterSpacing: '-0.01em', whiteSpace: 'nowrap' }}>{label}</span>
        {icon && <span style={{ color: 'var(--text-3)' }}><Icon name={icon} size={16} /></span>}
      </div>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 8 }}>
        <span style={{ fontSize: 28, fontWeight: 700, letterSpacing: '-0.02em', color: 'var(--text)' }}>{value}</span>
        {sub && <span style={{ fontSize: 13, color: 'var(--text-3)', fontWeight: 500 }}>{sub}</span>}
      </div>
      {delta && (
        <div style={{ marginTop: 8, fontSize: 12, fontWeight: 600, color: deltaTone === 'green' ? 'var(--green)' : deltaTone === 'red' ? 'var(--red)' : 'var(--text-2)' }}>
          {delta}
        </div>
      )}
    </Card>
  );
}
