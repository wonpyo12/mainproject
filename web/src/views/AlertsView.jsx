import React from 'react';
import { Card } from '../components/Card';
import { Badge } from '../components/Badge';
import { Icon } from '../components/Icon';

export function AlertsView({ alerts = [] }) {
  if (alerts.length === 0) {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 12, padding: '90px 0', color: 'var(--text-3)' }}>
        <Icon name="bell" size={30} />
        <div style={{ fontSize: 14, fontWeight: 600, color: 'var(--text-2)' }}>알림이 없습니다</div>
        <div style={{ fontSize: 12.5 }}>알림 데이터를 연결하면 이 화면에 표시됩니다.</div>
      </div>
    );
  }

  const meta = {
    urgent: { tone: 'red', ko: '긴급' },
    warn: { tone: 'amber', ko: '경고' },
    info: { tone: 'gray', ko: '정보' }
  };
  const icons = {
    zone: 'shield-alert',
    battery: 'battery-low',
    rfid: 'radio',
    track: 'scan-search'
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12, maxWidth: 760 }}>
      {alerts.map((a, i) => {
        const m = meta[a.level] || meta.info;
        return (
          <Card key={i} pad={0}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 14, padding: '16px 18px' }}>
              <div style={{
                width: 40, height: 40, borderRadius: 10, flex: 'none',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                background: `var(--${m.tone}-bg)`, color: `var(--${m.tone === 'gray' ? 'text-2' : m.tone})`
              }}>
                <Icon name={icons[a.type] || 'bell'} size={19} />
              </div>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 9, marginBottom: 3 }}>
                  <Badge tone={m.tone}>{m.ko}</Badge>
                  <span className="mono" style={{ fontSize: 12.5, fontWeight: 700 }}>{a.cart}</span>
                </div>
                <div style={{ fontSize: 13.5, fontWeight: 600, color: 'var(--text)' }}>{a.ko}</div>
              </div>
              <span style={{ fontSize: 12, color: 'var(--text-3)', flex: 'none' }}>{a.mins}분 전</span>
              <button className="ctl-btn" style={{ flex: 'none', width: 'auto', padding: '8px 14px' }}>확인</button>
            </div>
          </Card>
        );
      })}
    </div>
  );
}
