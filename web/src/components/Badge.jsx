import React from 'react';

export const TONE = {
  green: { bg: 'var(--green-bg)', fg: 'var(--green)', dot: 'var(--green)' },
  blue:  { bg: 'var(--blue-bg)',  fg: 'var(--blue)',  dot: 'var(--blue)'  },
  red:   { bg: 'var(--red-bg)',   fg: 'var(--red)',   dot: 'var(--red)'   },
  amber: { bg: 'var(--amber-bg)', fg: 'var(--amber)', dot: 'var(--amber)' },
  gray:  { bg: 'var(--gray-bg)',  fg: 'var(--text-2)',dot: 'var(--text-3)'},
};

export function Badge({ tone = 'gray', children, dot = true }) {
  const t = TONE[tone] || TONE.gray;
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center', gap: 6,
      padding: '3px 9px 3px 8px', borderRadius: 99, background: t.bg, color: t.fg,
      fontSize: 12, fontWeight: 600, lineHeight: 1.4, whiteSpace: 'nowrap',
    }}>
      {dot && <span style={{ width: 6, height: 6, borderRadius: 99, background: t.dot, flex: 'none' }} />}
      {children}
    </span>
  );
}
