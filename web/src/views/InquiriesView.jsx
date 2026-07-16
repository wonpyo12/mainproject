import React, { useState, useEffect, useCallback } from 'react';
import { Card } from '../components/Card';
import { Icon } from '../components/Icon';

import { BACKEND_URL } from '../api';

const fmtDateTime = (iso) => {
  if (!iso) return '—';
  const d = new Date(iso);
  return d.toLocaleString('ko-KR', {
    month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false,
  });
};

const STATUS = {
  PENDING:  { label: '대기', color: '#f59e0b', bg: 'rgba(245,158,11,0.12)' },
  ANSWERED: { label: '완료', color: '#10b981', bg: 'rgba(16,185,129,0.12)' },
};

function StatusBadge({ status }) {
  const s = STATUS[status] || STATUS.PENDING;
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center', gap: 5,
      padding: '3px 10px', borderRadius: 99, fontSize: 11.5, fontWeight: 700,
      color: s.color, background: s.bg,
    }}>
      <span style={{ width: 6, height: 6, borderRadius: 99, background: s.color }} />
      {s.label}
    </span>
  );
}

function StatCard({ icon, label, value, accent }) {
  return (
    <div style={{
      background: 'var(--surface)', border: '1px solid var(--border)',
      borderRadius: 12, padding: '18px 20px', display: 'flex', alignItems: 'center', gap: 14,
      boxShadow: '0 1px 2px rgba(20,22,28,0.04)', minWidth: 180,
    }}>
      <div style={{
        width: 44, height: 44, borderRadius: 10, flex: 'none',
        background: accent ? 'rgba(245,158,11,0.12)' : 'var(--gray-bg)',
        border: '1px solid var(--border)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        color: accent ? '#f59e0b' : 'var(--text)',
      }}>
        <Icon name={icon} size={20} />
      </div>
      <div>
        <div style={{ fontSize: 11.5, color: 'var(--text-3)', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.04em' }}>{label}</div>
        <div style={{ fontSize: 24, fontWeight: 800, letterSpacing: '-0.03em', marginTop: 2 }}>{value}</div>
      </div>
    </div>
  );
}

export function InquiriesView() {
  const [inquiries, setInquiries] = useState([]);
  const [pending, setPending] = useState(0);
  const [pagination, setPagination] = useState({ total: 0, totalPages: 1 });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [filter, setFilter] = useState('ALL');   // ALL | PENDING | ANSWERED
  const [search, setSearch] = useState('');
  const [expanded, setExpanded] = useState(null);
  const [drafts, setDrafts] = useState({});      // { [id]: 답변 초안 }
  const [sending, setSending] = useState(null);

  const fetchInquiries = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams({ limit: 100 });
      if (filter !== 'ALL') params.set('status', filter);
      if (search) params.set('search', search);

      const res = await fetch(`${BACKEND_URL}/api/inquiries?${params}`);
      if (!res.ok) throw new Error('문의 목록을 불러오지 못했습니다.');
      const data = await res.json();
      if (!data.success) throw new Error(data.message);
      setInquiries(data.data.inquiries);
      setPending(data.data.pending);
      setPagination(data.data.pagination);
    } catch (err) {
      console.error('[Inquiries] fetch error:', err);
      setError(err.message || '백엔드 서버와 통신 중 오류가 발생했습니다.');
      setInquiries([]);
    } finally {
      setLoading(false);
    }
  }, [filter, search]);

  useEffect(() => { fetchInquiries(); }, [fetchInquiries]);

  // 30초마다 자동 새로고침 (새 문의 반영)
  useEffect(() => {
    const id = setInterval(fetchInquiries, 30000);
    return () => clearInterval(id);
  }, [fetchInquiries]);

  const changeStatus = async (id, status) => {
    try {
      const res = await fetch(`${BACKEND_URL}/api/inquiries/${id}/status`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ status }),
      });
      if (!res.ok) { const d = await res.json(); throw new Error(d.message); }
      fetchInquiries();
    } catch (err) {
      alert(err.message || '상태 변경에 실패했습니다.');
    }
  };

  const submitAnswer = async (id) => {
    const answer = (drafts[id] || '').trim();
    if (!answer) return;
    setSending(id);
    try {
      const res = await fetch(`${BACKEND_URL}/api/inquiries/${id}/answer`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ answer }),
      });
      if (!res.ok) { const d = await res.json(); throw new Error(d.message); }
      setDrafts(prev => { const n = { ...prev }; delete n[id]; return n; });
      fetchInquiries();
    } catch (err) {
      alert(err.message || '답변 등록에 실패했습니다.');
    } finally {
      setSending(null);
    }
  };

  const TABS = [
    { id: 'ALL', label: '전체' },
    { id: 'PENDING', label: '대기' },
    { id: 'ANSWERED', label: '완료' },
  ];
  const colors = ['#3b82f6', '#8b5cf6', '#ec4899', '#f59e0b', '#10b981'];

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 18 }}>
      {/* 통계 */}
      <div style={{ display: 'flex', gap: 14, flexWrap: 'wrap' }}>
        <StatCard icon="message-square" label="전체 문의" value={pagination.total} />
        <StatCard icon="clock" label="대기중" value={pending} accent />
      </div>

      <Card pad={0}>
        {/* 툴바: 검색 + 필터 탭 */}
        <div style={{ padding: '16px 18px', borderBottom: '1px solid var(--border)', display: 'flex', gap: 12, alignItems: 'center', flexWrap: 'wrap' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, background: 'var(--surface-2)', border: '1px solid var(--border)', borderRadius: 9, padding: '8px 12px', flex: 1, minWidth: 200 }}>
            <Icon name="search" size={14} style={{ color: 'var(--text-3)' }} />
            <input
              placeholder="내용, 이름, 이메일 검색"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              style={{ border: 'none', background: 'transparent', outline: 'none', fontSize: 13, color: 'var(--text)', fontFamily: 'inherit', flex: 1 }}
            />
            {search && (
              <button onClick={() => setSearch('')} style={{ border: 'none', background: 'transparent', cursor: 'pointer', color: 'var(--text-3)', padding: 0, display: 'flex' }}>
                <Icon name="x" size={13} />
              </button>
            )}
          </div>
          <div style={{ display: 'flex', gap: 4, background: 'var(--surface-2)', border: '1px solid var(--border)', borderRadius: 9, padding: 3 }}>
            {TABS.map(t => (
              <button
                key={t.id}
                onClick={() => setFilter(t.id)}
                style={{
                  padding: '6px 14px', border: 'none', borderRadius: 7, cursor: 'pointer',
                  fontSize: 12.5, fontWeight: 700, fontFamily: 'inherit',
                  background: filter === t.id ? 'var(--surface)' : 'transparent',
                  color: filter === t.id ? 'var(--text)' : 'var(--text-3)',
                  boxShadow: filter === t.id ? '0 1px 2px rgba(20,22,28,0.08)' : 'none',
                }}
              >{t.label}</button>
            ))}
          </div>
          <button onClick={fetchInquiries} title="새로고침" style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '8px 12px', border: '1px solid var(--border)', background: 'var(--surface-2)', borderRadius: 9, cursor: 'pointer', fontSize: 12.5, fontWeight: 600, color: 'var(--text-2)', fontFamily: 'inherit' }}>
            <Icon name="refresh-cw" size={13} /> 새로고침
          </button>
        </div>

        {/* 컬럼 헤더 */}
        <div style={{
          display: 'grid', gridTemplateColumns: '50px 160px 1fr 90px 150px',
          gap: 12, padding: '10px 18px', fontSize: 11, fontWeight: 700, color: 'var(--text-3)',
          borderBottom: '1px solid var(--border)', textTransform: 'uppercase', letterSpacing: '0.04em',
        }}>
          <span>#</span><span>문의자</span><span>내용</span><span>상태</span><span>접수 · 처리</span>
        </div>

        {/* 목록 */}
        {loading ? (
          <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', gap: 10, padding: '50px 0', color: 'var(--text-3)' }}>
            <div style={{ width: 20, height: 20, border: '2.5px solid var(--border-strong)', borderTopColor: 'var(--text)', borderRadius: 99, animation: 'spin 0.8s linear infinite' }} />
            <span style={{ fontSize: 13, fontWeight: 600 }}>불러오는 중…</span>
          </div>
        ) : error ? (
          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', padding: '50px 0', color: 'var(--red)', gap: 8 }}>
            <Icon name="octagon-x" size={24} />
            <div style={{ fontSize: 13, fontWeight: 600 }}>{error}</div>
            <button onClick={fetchInquiries} style={{ fontSize: 12, padding: '6px 14px', background: 'var(--surface-2)', border: '1px solid var(--border)', borderRadius: 7, cursor: 'pointer', fontFamily: 'inherit' }}>재시도</button>
          </div>
        ) : inquiries.length === 0 ? (
          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 10, padding: '60px 0', color: 'var(--text-3)' }}>
            <Icon name="inbox" size={30} />
            <div style={{ fontSize: 14, fontWeight: 600, color: 'var(--text-2)' }}>문의가 없습니다</div>
            <div style={{ fontSize: 12.5 }}>{search || filter !== 'ALL' ? '조건에 맞는 문의가 없습니다.' : '아직 접수된 문의가 없습니다.'}</div>
          </div>
        ) : (
          inquiries.map((q) => {
            const isOpen = expanded === q.id;
            const initials = (q.name || '익명').slice(0, 2).toUpperCase();
            const color = colors[(q.user_id || q.id) % colors.length];
            return (
              <div key={q.id} style={{ borderBottom: '1px solid var(--border)' }}>
                <div
                  onClick={() => setExpanded(isOpen ? null : q.id)}
                  style={{
                    display: 'grid', gridTemplateColumns: '50px 160px 1fr 90px 150px',
                    gap: 12, alignItems: 'center', padding: '13px 18px', cursor: 'pointer',
                    transition: 'background .1s',
                  }}
                  onMouseOver={e => e.currentTarget.style.background = 'var(--surface-2)'}
                  onMouseOut={e => e.currentTarget.style.background = 'transparent'}
                >
                  <span className="mono" style={{ fontSize: 12, color: 'var(--text-3)', fontWeight: 600 }}>#{q.id}</span>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 9, minWidth: 0 }}>
                    <div style={{ width: 30, height: 30, borderRadius: 99, background: color, flex: 'none', display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#fff', fontSize: 11, fontWeight: 800 }}>{initials}</div>
                    <div style={{ minWidth: 0 }}>
                      <div style={{ fontSize: 13, fontWeight: 700, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{q.name || '익명'}</div>
                      <div style={{ fontSize: 11, color: 'var(--text-3)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{q.category || '일반'}</div>
                    </div>
                  </div>
                  <span style={{
                    fontSize: 13, color: 'var(--text-2)', lineHeight: 1.5,
                    overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: isOpen ? 'normal' : 'nowrap',
                  }}>{q.content}</span>
                  <StatusBadge status={q.status} />
                  <span style={{ fontSize: 12, color: 'var(--text-3)' }}>{fmtDateTime(q.created_at)}</span>
                </div>

                {/* 펼침: 문의 내용 + 답변 작성 */}
                {isOpen && (
                  <div style={{ padding: '0 18px 16px 68px', display: 'flex', flexDirection: 'column', gap: 12 }} onClick={(e) => e.stopPropagation()}>
                    {/* 문의 내용 */}
                    <div style={{ background: 'var(--surface-2)', border: '1px solid var(--border)', borderRadius: 10, padding: '14px 16px', fontSize: 13.5, color: 'var(--text)', lineHeight: 1.65, whiteSpace: 'pre-wrap' }}>
                      {q.content}
                    </div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 14, fontSize: 12, color: 'var(--text-3)', flexWrap: 'wrap' }}>
                      {q.email && <span style={{ display: 'inline-flex', alignItems: 'center', gap: 5 }}><Icon name="mail" size={13} /> {q.email}</span>}
                      <span style={{ display: 'inline-flex', alignItems: 'center', gap: 5 }}><Icon name="calendar" size={13} /> {fmtDateTime(q.created_at)}</span>
                    </div>

                    {/* 기존 답변 (등록됨) */}
                    {q.answer && (
                      <div style={{ background: 'rgba(16,185,129,0.08)', border: '1px solid rgba(16,185,129,0.25)', borderRadius: 10, padding: '12px 14px' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 11.5, fontWeight: 700, color: '#10b981', marginBottom: 6 }}>
                          <Icon name="message-circle-reply" size={13} /> 등록된 답변 · {fmtDateTime(q.answered_at)} · 앱에서 사용자에게 표시됨
                        </div>
                        <div style={{ fontSize: 13.5, color: 'var(--text)', lineHeight: 1.65, whiteSpace: 'pre-wrap' }}>{q.answer}</div>
                      </div>
                    )}

                    {/* 답변 작성 */}
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                      <label style={{ fontSize: 11.5, fontWeight: 700, color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                        {q.answer ? '답변 수정' : '답변 작성'} <span style={{ color: 'var(--text-3)', fontWeight: 500, textTransform: 'none' }}>— 등록하면 사용자 앱에 바로 표시돼요</span>
                      </label>
                      <textarea
                        value={drafts[q.id] ?? q.answer ?? ''}
                        onChange={(e) => setDrafts(prev => ({ ...prev, [q.id]: e.target.value }))}
                        placeholder="사용자에게 전달할 답변을 입력하세요"
                        style={{ width: '100%', minHeight: 80, resize: 'vertical', fontFamily: 'inherit', fontSize: 13.5, lineHeight: 1.6, color: 'var(--text)', border: '1px solid var(--border)', borderRadius: 10, padding: '11px 13px', background: 'var(--surface-2)', outline: 'none' }}
                        onFocus={e => e.target.style.borderColor = 'var(--border-strong)'}
                        onBlur={e => e.target.style.borderColor = 'var(--border)'}
                      />
                      <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
                        {q.status === 'ANSWERED' && (
                          <button
                            onClick={() => changeStatus(q.id, 'PENDING')}
                            style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '9px 14px', border: '1px solid var(--border)', background: 'var(--surface-2)', color: 'var(--text-2)', borderRadius: 9, fontSize: 12.5, fontWeight: 600, cursor: 'pointer', fontFamily: 'inherit' }}
                          >
                            <Icon name="rotate-ccw" size={13} /> 대기로 되돌리기
                          </button>
                        )}
                        <button
                          onClick={() => submitAnswer(q.id)}
                          disabled={sending === q.id || !(drafts[q.id] ?? q.answer ?? '').trim()}
                          style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '9px 18px', border: 'none', background: 'var(--text)', color: '#fff', borderRadius: 9, fontSize: 12.5, fontWeight: 700, cursor: 'pointer', fontFamily: 'inherit', opacity: (sending === q.id || !(drafts[q.id] ?? q.answer ?? '').trim()) ? 0.55 : 1 }}
                        >
                          <Icon name="send" size={13} /> {sending === q.id ? '등록 중…' : (q.answer ? '답변 수정' : '답변 등록')}
                        </button>
                      </div>
                    </div>
                  </div>
                )}
              </div>
            );
          })
        )}
      </Card>
    </div>
  );
}
