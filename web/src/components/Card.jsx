import React from 'react';

export function Card({ children, style = {}, pad = 20, className = '' }) {
  return (
    <div className={`card ${className}`} style={{
      background: 'var(--surface)', border: '1px solid var(--border)',
      borderRadius: 12, padding: pad, boxShadow: '0 1px 2px rgba(20,22,28,0.04)', ...style,
    }}>{children}</div>
  );
}
