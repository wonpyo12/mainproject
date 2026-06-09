import React from 'react';

export function Avatar({ name, size = 30 }) {
  const ch = name ? name.slice(-2) : '··';
  return (
    <span style={{
      width: size, height: size, borderRadius: 99, flex: 'none',
      background: 'var(--gray-bg)', color: 'var(--text-2)',
      display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
      fontSize: size * 0.38, fontWeight: 700, border: '1px solid var(--border)',
    }}>{ch}</span>
  );
}
