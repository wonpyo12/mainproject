import React from 'react';
import { Stat } from '../components/Stat';
import { Card } from '../components/Card';
import { Badge } from '../components/Badge';
import { SectionHead } from '../components/SectionHead';
import { Battery } from '../components/Battery';
import { Icon } from '../components/Icon';
import { FloorMap } from './FloorMap';
import { SessionsChart } from './SessionsChart';
import { STATUS } from '../data';

const won = (n) => '₩' + (n || 0).toLocaleString('ko-KR');

export function DashboardView({ selected, setSelected, robots = [], alerts = [], sessions = [], metrics = {} }) {
  const hasRobots = robots.length > 0;
  const hasAlerts = alerts.length > 0;
  const hasSessions = sessions.length > 0;
  const hasMetrics = metrics && Object.keys(metrics).length > 0;

  const active = robots.filter((r) => r.status === 'following').length;
  const sel = robots.find((r) => r.id === selected) || robots[0] || null;

  // Build stat cards dynamically — only include ones that have real data
  const statCards = [];
  if (hasRobots) {
    statCards.push({ label: '운행 중 로봇', value: active, sub: `/ ${robots.length}`, icon: 'bot' });
  }
  if (hasMetrics && metrics.todaySales != null) {
    statCards.push({ label: '오늘 거래액', value: won(metrics.todaySales), icon: 'wallet' });
  }
  if (hasMetrics && metrics.avgShoppingTime != null) {
    statCards.push({ label: '평균 쇼핑 시간', value: metrics.avgShoppingTime, icon: 'clock' });
  }
  if (hasMetrics && metrics.unprocessedAlerts != null) {
    statCards.push({ label: '미처리 알림', value: metrics.unprocessedAlerts, icon: 'bell' });
  }

  const hasStats = statCards.length > 0;
  const hasFloorOrDetail = hasRobots;
  const hasBottomRow = hasSessions || hasAlerts;

  // Nothing to show at all
  if (!hasStats && !hasFloorOrDetail && !hasBottomRow) {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 12, padding: '90px 0', color: 'var(--text-3)' }}>
        <Icon name="database" size={30} />
        <div style={{ fontSize: 14, fontWeight: 600, color: 'var(--text-2)' }}>표시할 데이터가 없습니다</div>
        <div style={{ fontSize: 12.5 }}>백엔드 서버를 연결하면 실시간 데이터가 이 화면에 표시됩니다.</div>
      </div>
    );
  }

  const statusConfig = sel ? (STATUS[sel.status] || { ko: '—', tone: 'gray' }) : null;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 18 }}>

      {/* Stat cards row */}
      {hasStats && (
        <div style={{ display: 'grid', gridTemplateColumns: `repeat(${statCards.length}, 1fr)`, gap: 14 }}>
          {statCards.map((s, i) => (
            <Stat key={i} label={s.label} value={s.value} sub={s.sub} icon={s.icon} />
          ))}
        </div>
      )}

      {/* Floor map + Robot detail */}
      {hasFloorOrDetail && (
        <div style={{ display: 'grid', gridTemplateColumns: sel ? '1.55fr 1fr' : '1fr', gap: 18 }}>
          <Card>
            <SectionHead title="실시간 매장 현황" en="Live Floor" action={<Badge tone="green">LIVE</Badge>} />
            <FloorMap robots={robots} selected={selected} onSelect={setSelected} />
            <div style={{ display: 'flex', gap: 16, marginTop: 14, flexWrap: 'wrap' }}>
              {[['추종중', 'var(--green)'], ['경고', 'var(--red)'], ['충전중', 'var(--blue)'], ['점검', 'var(--amber)'], ['대기', 'var(--text-3)']].map(([l, c]) => (
                <span key={l} style={{ display: 'inline-flex', alignItems: 'center', gap: 6, fontSize: 12, color: 'var(--text-2)', fontWeight: 500 }}>
                  <span style={{ width: 8, height: 8, borderRadius: 2, background: c }} />{l}
                </span>
              ))}
            </div>
          </Card>

          {sel && statusConfig && (
            <Card>
              <SectionHead title="로봇 상세" en={sel.id} />
              <div style={{ display: 'flex', alignItems: 'center', gap: 12, paddingBottom: 16, borderBottom: '1px solid var(--border)' }}>
                <div style={{ width: 46, height: 46, borderRadius: 10, background: 'var(--gray-bg)', border: '1px solid var(--border)', display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--text)' }}><Icon name="bot" size={22} /></div>
                <div style={{ flex: 1 }}>
                  <div className="mono" style={{ fontSize: 14, fontWeight: 700 }}>{sel.id}</div>
                  <div style={{ fontSize: 12, color: 'var(--text-3)' }}>TurtleBot Burger · ROS 2</div>
                </div>
                <Badge tone={statusConfig.tone}>{statusConfig.ko}</Badge>
              </div>
              <dl style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '14px 12px', margin: '16px 0' }}>
                {[
                  sel.user ? ['이용자', `${sel.user} · ${sel.userId}`] : null,
                  sel.zone ? ['현재 구역', sel.zone] : null,
                  sel.items != null ? ['담은 상품', sel.items + '개'] : null,
                  sel.battery != null ? ['배터리', null] : null,
                ].filter(Boolean).map(([k, v], i) => (
                  <div key={i}>
                    <dt style={{ fontSize: 11, color: 'var(--text-3)', fontWeight: 600, marginBottom: 5 }}>{k}</dt>
                    <dd style={{ fontSize: 13, fontWeight: 600, color: 'var(--text)' }}>{v === null ? <Battery level={sel.battery} /> : v}</dd>
                  </div>
                ))}
              </dl>
              {sel.amount != null && (
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '14px 16px', background: 'var(--surface-2)', border: '1px solid var(--border)', borderRadius: 10 }}>
                  <span style={{ fontSize: 12.5, color: 'var(--text-2)', fontWeight: 600, whiteSpace: 'nowrap' }}>예상 결제 금액</span>
                  <span style={{ fontSize: 18, fontWeight: 700 }}>{won(sel.amount)}</span>
                </div>
              )}
            </Card>
          )}
        </div>
      )}

      {/* Sessions chart + Alerts */}
      {hasBottomRow && (
        <div style={{ display: 'grid', gridTemplateColumns: hasSessions && hasAlerts ? '1.55fr 1fr' : '1fr', gap: 18 }}>
          {hasSessions && (
            <Card>
              <SectionHead title="시간대별 쇼핑 세션" en="Sessions / hour" />
              <SessionsChart data={sessions} />
            </Card>
          )}
          {hasAlerts && (
            <Card pad={0}>
              <div style={{ padding: '18px 18px 6px' }}><SectionHead title="최근 알림" en="Alerts" /></div>
              <div>
                {alerts.slice(0, 4).map((a, i) => (
                  <div key={i} style={{ display: 'flex', gap: 11, padding: '11px 18px', borderTop: '1px solid var(--border)' }}>
                    <span style={{ width: 7, height: 7, borderRadius: 99, marginTop: 6, flex: 'none', background: a.level === 'urgent' ? 'var(--red)' : a.level === 'warn' ? 'var(--amber)' : 'var(--text-3)' }} />
                    <div style={{ minWidth: 0 }}>
                      <div style={{ fontSize: 12.5, fontWeight: 600, color: 'var(--text)' }}><span className="mono">{a.cart}</span> · {a.ko}</div>
                      <div style={{ fontSize: 11, color: 'var(--text-3)', marginTop: 2 }}>{a.mins}분 전</div>
                    </div>
                  </div>
                ))}
              </div>
            </Card>
          )}
        </div>
      )}
    </div>
  );
}
