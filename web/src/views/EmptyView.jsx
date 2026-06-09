import React from 'react';
import { Icon } from '../components/Icon';

export function EmptyView({ title }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 12, padding: '90px 0', color: 'var(--text-3)' }}>
      <Icon name="construction" size={30} />
      <div style={{ fontSize: 14, fontWeight: 600, color: 'var(--text-2)' }}>{title} 화면 준비 중</div>
      <div style={{ fontSize: 12.5 }}>이번 시안 범위에는 포함되지 않았습니다.</div>
    </div>
  );
}
