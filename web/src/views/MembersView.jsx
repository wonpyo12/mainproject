import React, { useState, useEffect, useCallback } from 'react';
import { Card } from '../components/Card';
import { Icon } from '../components/Icon';

const BACKEND_URL = 'http://192.168.0.9:3000';



const fmtDate = (iso) => {
  if (!iso) return '—';
  const d = new Date(iso);
  return d.toLocaleDateString('ko-KR', { year: 'numeric', month: '2-digit', day: '2-digit' }).replace(/\. /g, '.').replace('.', '년 ').replace('.', '월 ').replace('.', '일');
};

const fmtPhone = (p) => {
  if (!p) return '—';
  const n = p.replace(/\D/g, '');
  if (n.length === 11) return `${n.slice(0, 3)}-${n.slice(3, 7)}-${n.slice(7)}`;
  return p;
};

// ─── 회원 수정 모달 ───────────────────────────────────────
function EditMemberModal({ member, onClose, onSave }) {
  const [form, setForm] = useState({
    name: member.name || '',
    phone: member.phone || '',
  });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!form.name.trim()) { setError('이름을 입력해 주세요.'); return; }
    setSaving(true);
    setError(null);
    try {
      await onSave(member.id, form);
      onClose();
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div style={{
      position: 'fixed', inset: 0, zIndex: 1000,
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      background: 'rgba(10,12,20,0.45)', backdropFilter: 'blur(4px)',
    }} onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div style={{
        background: 'var(--surface)', border: '1px solid var(--border)',
        borderRadius: 16, padding: 28, width: 440, boxShadow: '0 20px 60px rgba(10,12,20,0.18)',
        animation: 'slideUp 0.18s ease-out',
      }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 22 }}>
          <div>
            <div style={{ fontSize: 16, fontWeight: 800, letterSpacing: '-0.02em' }}>회원 정보 수정</div>
            <div style={{ fontSize: 12, color: 'var(--text-3)', marginTop: 2 }}>{member.email}</div>
          </div>
          <button onClick={onClose} style={{ border: 'none', background: 'transparent', cursor: 'pointer', color: 'var(--text-3)', padding: 4 }}>
            <Icon name="x" size={18} />
          </button>
        </div>

        <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          <div>
            <label style={{ display: 'block', fontSize: 11.5, fontWeight: 700, color: 'var(--text-3)', marginBottom: 6, textTransform: 'uppercase', letterSpacing: '0.04em' }}>이름</label>
            <input
              id="edit-member-name"
              value={form.name}
              onChange={(e) => setForm(f => ({ ...f, name: e.target.value }))}
              placeholder="이름 입력"
              style={{
                width: '100%', padding: '10px 12px', border: '1px solid var(--border)',
                borderRadius: 9, fontSize: 13.5, outline: 'none', background: 'var(--surface-2)',
                color: 'var(--text)', fontFamily: 'inherit', transition: 'border-color .12s',
              }}
              onFocus={e => e.target.style.borderColor = 'var(--border-strong)'}
              onBlur={e => e.target.style.borderColor = 'var(--border)'}
            />
          </div>
          <div>
            <label style={{ display: 'block', fontSize: 11.5, fontWeight: 700, color: 'var(--text-3)', marginBottom: 6, textTransform: 'uppercase', letterSpacing: '0.04em' }}>전화번호</label>
            <input
              id="edit-member-phone"
              value={form.phone}
              onChange={(e) => setForm(f => ({ ...f, phone: e.target.value }))}
              placeholder="010-0000-0000"
              style={{
                width: '100%', padding: '10px 12px', border: '1px solid var(--border)',
                borderRadius: 9, fontSize: 13.5, outline: 'none', background: 'var(--surface-2)',
                color: 'var(--text)', fontFamily: 'inherit', transition: 'border-color .12s',
              }}
              onFocus={e => e.target.style.borderColor = 'var(--border-strong)'}
              onBlur={e => e.target.style.borderColor = 'var(--border)'}
            />
          </div>


          {error && (
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '10px 12px', background: 'var(--red-bg)', borderRadius: 8, color: 'var(--red)', fontSize: 12.5, fontWeight: 600 }}>
              <Icon name="circle-alert" size={14} /> {error}
            </div>
          )}

          <div style={{ display: 'flex', gap: 10, marginTop: 4 }}>
            <button type="button" onClick={onClose} style={{ flex: 1, padding: '10px 0', border: '1px solid var(--border)', background: 'var(--surface-2)', borderRadius: 9, fontSize: 13.5, fontWeight: 600, cursor: 'pointer', color: 'var(--text-2)', fontFamily: 'inherit' }}>
              취소
            </button>
            <button
              id="btn-member-save"
              type="submit"
              disabled={saving}
              style={{ flex: 1, padding: '10px 0', border: 'none', background: 'var(--text)', color: '#fff', borderRadius: 9, fontSize: 13.5, fontWeight: 700, cursor: 'pointer', fontFamily: 'inherit', opacity: saving ? 0.6 : 1, transition: 'opacity .12s' }}
            >
              {saving ? '저장 중…' : '저장'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

// ─── 삭제 확인 모달 ───────────────────────────────────────
function DeleteConfirmModal({ member, onClose, onConfirm }) {
  const [loading, setLoading] = useState(false);

  const handleConfirm = async () => {
    setLoading(true);
    try { await onConfirm(member.id); onClose(); } finally { setLoading(false); }
  };

  return (
    <div style={{
      position: 'fixed', inset: 0, zIndex: 1000,
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      background: 'rgba(10,12,20,0.45)', backdropFilter: 'blur(4px)',
    }} onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div style={{
        background: 'var(--surface)', border: '1px solid var(--border)',
        borderRadius: 16, padding: 28, width: 380, boxShadow: '0 20px 60px rgba(10,12,20,0.18)',
        animation: 'slideUp 0.18s ease-out',
      }}>
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 12, paddingBottom: 22, textAlign: 'center' }}>
          <div style={{ width: 52, height: 52, borderRadius: 99, background: 'var(--red-bg)', display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--red)' }}>
            <Icon name="trash-2" size={22} />
          </div>
          <div style={{ fontSize: 16, fontWeight: 800 }}>회원 삭제</div>
          <div style={{ fontSize: 13, color: 'var(--text-2)', lineHeight: 1.6 }}>
            <strong>{member.name}</strong> ({member.email}) 회원을<br />삭제하시겠습니까? 이 작업은 되돌릴 수 없습니다.
          </div>
        </div>
        <div style={{ display: 'flex', gap: 10 }}>
          <button onClick={onClose} style={{ flex: 1, padding: '10px 0', border: '1px solid var(--border)', background: 'var(--surface-2)', borderRadius: 9, fontSize: 13.5, fontWeight: 600, cursor: 'pointer', color: 'var(--text-2)', fontFamily: 'inherit' }}>
            취소
          </button>
          <button
            id="btn-member-delete-confirm"
            onClick={handleConfirm}
            disabled={loading}
            style={{ flex: 1, padding: '10px 0', border: 'none', background: 'var(--red)', color: '#fff', borderRadius: 9, fontSize: 13.5, fontWeight: 700, cursor: 'pointer', fontFamily: 'inherit', opacity: loading ? 0.6 : 1, transition: 'opacity .12s' }}
          >
            {loading ? '삭제 중…' : '삭제'}
          </button>
        </div>
      </div>
    </div>
  );
}

// ─── 회원 상세 패널 ───────────────────────────────────────
function MemberDetailPanel({ member, onEdit, onDelete, onClose }) {
  if (!member) return null;

  const initials = (member.name || '?').slice(0, 2).toUpperCase();
  const colors = ['#3b82f6', '#8b5cf6', '#ec4899', '#f59e0b', '#10b981'];
  const color = colors[member.id % colors.length];

  return (
    <div style={{
      borderLeft: '1px solid var(--border)',
      background: 'var(--surface)',
      display: 'flex', flexDirection: 'column',
      height: '100%', overflow: 'hidden',
    }}>
      {/* 패널 헤더 */}
      <div style={{ padding: '18px 20px', borderBottom: '1px solid var(--border)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <span style={{ fontSize: 13, fontWeight: 700, color: 'var(--text-2)' }}>회원 상세</span>
        <button onClick={onClose} style={{ border: 'none', background: 'transparent', cursor: 'pointer', color: 'var(--text-3)', padding: 4 }}>
          <Icon name="x" size={16} />
        </button>
      </div>

      {/* 프로필 */}
      <div style={{ padding: '24px 20px 20px', borderBottom: '1px solid var(--border)', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 10 }}>
        <div style={{
          width: 64, height: 64, borderRadius: 99, background: color,
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          color: '#fff', fontSize: 22, fontWeight: 800, letterSpacing: '-0.03em',
          boxShadow: `0 0 0 4px ${color}22`,
        }}>{initials}</div>
        <div style={{ textAlign: 'center' }}>
          <div style={{ fontSize: 16, fontWeight: 800, letterSpacing: '-0.02em' }}>{member.name}</div>
          <div style={{ fontSize: 12.5, color: 'var(--text-3)', marginTop: 3 }}>{member.email}</div>
        </div>
      </div>

      {/* 정보 목록 */}
      <div style={{ padding: '18px 20px', flex: 1, display: 'flex', flexDirection: 'column', gap: 16 }}>
        {[
          { icon: 'hash', label: '회원 ID', value: `#${member.id}` },
          { icon: 'phone', label: '전화번호', value: fmtPhone(member.phone) },
          { icon: 'calendar', label: '가입일', value: fmtDate(member.created_at) },
        ].map(({ icon, label, value }) => (
          <div key={label} style={{ display: 'flex', alignItems: 'flex-start', gap: 12 }}>
            <div style={{ width: 32, height: 32, borderRadius: 8, background: 'var(--surface-2)', border: '1px solid var(--border)', display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--text-3)', flex: 'none' }}>
              <Icon name={icon} size={14} />
            </div>
            <div>
              <div style={{ fontSize: 11, color: 'var(--text-3)', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.04em' }}>{label}</div>
              <div style={{ fontSize: 13.5, fontWeight: 600, color: 'var(--text)', marginTop: 2 }}>{value}</div>
            </div>
          </div>
        ))}
      </div>

      {/* 액션 버튼 */}
      <div style={{ padding: '16px 20px', borderTop: '1px solid var(--border)', display: 'flex', gap: 8 }}>
        <button
          id="btn-member-edit"
          onClick={() => onEdit(member)}
          style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 7, padding: '10px 0', border: '1px solid var(--border)', background: 'var(--surface-2)', borderRadius: 9, fontSize: 13, fontWeight: 600, cursor: 'pointer', color: 'var(--text)', fontFamily: 'inherit', transition: 'all .12s' }}
          onMouseOver={e => { e.currentTarget.style.background = 'var(--bg)'; e.currentTarget.style.borderColor = 'var(--border-strong)'; }}
          onMouseOut={e => { e.currentTarget.style.background = 'var(--surface-2)'; e.currentTarget.style.borderColor = 'var(--border)'; }}
        >
          <Icon name="pencil" size={13} /> 수정
        </button>
        <button
          id="btn-member-delete"
          onClick={() => onDelete(member)}
          style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 7, padding: '10px 0', border: '1px solid var(--red-bg)', background: 'var(--red-bg)', borderRadius: 9, fontSize: 13, fontWeight: 600, cursor: 'pointer', color: 'var(--red)', fontFamily: 'inherit', transition: 'all .12s' }}
          onMouseOver={e => e.currentTarget.style.opacity = '0.75'}
          onMouseOut={e => e.currentTarget.style.opacity = '1'}
        >
          <Icon name="trash-2" size={13} /> 삭제
        </button>
      </div>
    </div>
  );
}

// ─── 메인: MembersView ───────────────────────────────────
export function MembersView() {
  const [members, setMembers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [search, setSearch] = useState('');
  const [page, setPage] = useState(1);
  const [pagination, setPagination] = useState({ total: 0, totalPages: 1 });
  const [selectedMember, setSelectedMember] = useState(null);
  const [editTarget, setEditTarget] = useState(null);
  const [deleteTarget, setDeleteTarget] = useState(null);

  const fetchMembers = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams({ page, limit: 10 });
      if (search) params.set('search', search);

      const res = await fetch(`${BACKEND_URL}/api/members?${params}`);
      if (!res.ok) throw new Error('회원 정보를 불러오지 못했습니다.');
      const data = await res.json();
      if (!data.success) throw new Error(data.message);
      setMembers(data.data.members);
      setPagination(data.data.pagination);
    } catch (err) {
      console.error('[Members] fetchMembers error:', err);
      setError(err.message || '백엔드 서버와 통신 중 오류가 발생했습니다.');
      setMembers([]);
      setPagination({ total: 0, totalPages: 1 });
    } finally {
      setLoading(false);
    }
  }, [page, search]);

  useEffect(() => { fetchMembers(); }, [fetchMembers]);

  // 검색 시 page 리셋
  const handleSearch = (val) => { setSearch(val); setPage(1); };

  const handleSave = async (id, form) => {
    const res = await fetch(`${BACKEND_URL}/api/members/${id}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(form),
    });
    if (!res.ok) {
      const d = await res.json();
      throw new Error(d.message || '회원 정보 수정에 실패했습니다.');
    }
    fetchMembers();
    if (selectedMember?.id === id) {
      setSelectedMember(prev => ({ ...prev, ...form }));
    }
  };

  const handleDelete = async (id) => {
    try {
      const res = await fetch(`${BACKEND_URL}/api/members/${id}`, { method: 'DELETE' });
      if (!res.ok) { const d = await res.json(); throw new Error(d.message); }
      fetchMembers();
      if (selectedMember?.id === id) setSelectedMember(null);
    } catch (err) {
      alert(err.message || '회원 삭제에 실패했습니다.');
    }
  };

  return (
    <>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 18 }}>

        {/* 상단 헤더 영역: 통계 카드 */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 14 }}>
          {/* 통계 카드 */}
          <div style={{
            background: 'var(--surface)', border: '1px solid var(--border)',
            borderRadius: 12, padding: '18px 20px',
            display: 'flex', alignItems: 'center', gap: 14,
            boxShadow: '0 1px 2px rgba(20,22,28,0.04)',
            width: 'fit-content',
          }}>
            <div style={{
              width: 44, height: 44, borderRadius: 10, flex: 'none',
              background: 'var(--gray-bg)', border: '1px solid var(--border)',
              display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--text)',
            }}>
              <Icon name="users" size={20} />
            </div>
            <div>
              <div style={{ fontSize: 11.5, color: 'var(--text-3)', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.04em' }}>전체 회원</div>
              <div style={{ fontSize: 24, fontWeight: 800, letterSpacing: '-0.03em', marginTop: 2 }}>{pagination.total}</div>
            </div>
          </div>
        </div>

        {/* 메인 테이블 영역 */}
        <div style={{ display: 'grid', gridTemplateColumns: selectedMember ? '1fr 320px' : '1fr', gap: 18, alignItems: 'start' }}>
          <Card pad={0}>
            {/* 테이블 헤더 영역 */}
            <div style={{ padding: '16px 18px', borderBottom: '1px solid var(--border)', display: 'flex', gap: 12, alignItems: 'center', flexWrap: 'wrap' }}>
              {/* 검색 */}
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, background: 'var(--surface-2)', border: '1px solid var(--border)', borderRadius: 9, padding: '8px 12px', flex: 1, minWidth: 200 }}>
                <Icon name="search" size={14} style={{ color: 'var(--text-3)' }} />
                <input
                  id="member-search-input"
                  placeholder="이름, 이메일, 전화번호 검색"
                  value={search}
                  onChange={(e) => handleSearch(e.target.value)}
                  style={{ border: 'none', background: 'transparent', outline: 'none', fontSize: 13, color: 'var(--text)', fontFamily: 'inherit', flex: 1 }}
                />
                {search && (
                  <button onClick={() => handleSearch('')} style={{ border: 'none', background: 'transparent', cursor: 'pointer', color: 'var(--text-3)', padding: 0, display: 'flex' }}>
                    <Icon name="x" size={13} />
                  </button>
                )}
              </div>



              {/* 총 카운트 */}
              <span style={{ fontSize: 12.5, color: 'var(--text-3)', fontWeight: 600, whiteSpace: 'nowrap' }}>
                총 <strong style={{ color: 'var(--text)' }}>{pagination.total}</strong>명
              </span>
            </div>

            {/* 컬럼 헤더 */}
            <div style={{
              display: 'grid', gridTemplateColumns: '48px 1fr 200px 150px 110px',
              gap: 12, padding: '10px 18px',
              fontSize: 11, fontWeight: 700, color: 'var(--text-3)',
              borderBottom: '1px solid var(--border)',
              textTransform: 'uppercase', letterSpacing: '0.04em',
            }}>
              <span>#</span>
              <span>회원 정보</span>
              <span>이메일</span>
              <span>전화번호</span>
              <span>가입일</span>
            </div>

            {/* 로딩 */}
            {loading ? (
              <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', gap: 10, padding: '50px 0', color: 'var(--text-3)' }}>
                <div style={{ width: 20, height: 20, border: '2.5px solid var(--border-strong)', borderTopColor: 'var(--text)', borderRadius: 99, animation: 'spin 0.8s linear infinite' }} />
                <span style={{ fontSize: 13, fontWeight: 600 }}>불러오는 중…</span>
              </div>
            ) : error ? (
              <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', padding: '50px 0', color: 'var(--red)', gap: 8 }}>
                <Icon name="octagon-x" size={24} />
                <div style={{ fontSize: 13, fontWeight: 600 }}>{error}</div>
                <button onClick={fetchMembers} style={{ fontSize: 12, padding: '6px 14px', background: 'var(--surface-2)', border: '1px solid var(--border)', borderRadius: 7, cursor: 'pointer', fontFamily: 'inherit' }}>재시도</button>
              </div>
            ) : members.length === 0 ? (
              <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 10, padding: '60px 0', color: 'var(--text-3)' }}>
                <Icon name="users" size={30} />
                <div style={{ fontSize: 14, fontWeight: 600, color: 'var(--text-2)' }}>회원이 없습니다</div>
                <div style={{ fontSize: 12.5 }}>{search ? '검색 조건에 맞는 회원이 없습니다.' : '아직 가입한 회원이 없습니다.'}</div>
              </div>
            ) : (
              members.map((m) => {
                const isSelected = selectedMember?.id === m.id;
                const initials = (m.name || '?').slice(0, 2).toUpperCase();
                const colors = ['#3b82f6', '#8b5cf6', '#ec4899', '#f59e0b', '#10b981'];
                const color = colors[m.id % colors.length];
                return (
                  <div
                    key={m.id}
                    id={`member-row-${m.id}`}
                    onClick={() => setSelectedMember(isSelected ? null : m)}
                    style={{
                      display: 'grid', gridTemplateColumns: '48px 1fr 200px 150px 110px',
                      gap: 12, alignItems: 'center', padding: '13px 18px',
                      borderBottom: '1px solid var(--border)', cursor: 'pointer',
                      background: isSelected ? 'var(--surface-2)' : 'transparent',
                      transition: 'background .1s',
                    }}
                    onMouseOver={e => { if (!isSelected) e.currentTarget.style.background = 'var(--surface-2)'; }}
                    onMouseOut={e => { if (!isSelected) e.currentTarget.style.background = 'transparent'; }}
                  >
                    {/* ID */}
                    <span className="mono" style={{ fontSize: 12, color: 'var(--text-3)', fontWeight: 600 }}>
                      #{m.id}
                    </span>

                    {/* 이름 + 아바타 */}
                    <div style={{ display: 'flex', alignItems: 'center', gap: 10, minWidth: 0 }}>
                      <div style={{
                        width: 34, height: 34, borderRadius: 99, background: color, flex: 'none',
                        display: 'flex', alignItems: 'center', justifyContent: 'center',
                        color: '#fff', fontSize: 12, fontWeight: 800,
                      }}>{initials}</div>
                      <span style={{ fontSize: 13.5, fontWeight: 700, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{m.name}</span>
                    </div>

                    {/* 이메일 */}
                    <span style={{ fontSize: 12.5, color: 'var(--text-2)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{m.email}</span>

                    {/* 전화 */}
                    <span className="mono" style={{ fontSize: 12.5, color: 'var(--text-2)' }}>{fmtPhone(m.phone)}</span>

                    {/* 가입일 */}
                    <span style={{ fontSize: 12, color: 'var(--text-3)' }}>{fmtDate(m.created_at)}</span>
                  </div>
                );
              })
            )}

            {/* 페이지네이션 */}
            {pagination.totalPages > 1 && (
              <div style={{ padding: '14px 18px', display: 'flex', justifyContent: 'center', alignItems: 'center', gap: 6, borderTop: '1px solid var(--border)' }}>
                <button
                  id="page-prev"
                  onClick={() => setPage(p => Math.max(1, p - 1))}
                  disabled={page <= 1}
                  style={{ padding: '7px 14px', border: '1px solid var(--border)', background: 'var(--surface-2)', borderRadius: 8, cursor: page <= 1 ? 'not-allowed' : 'pointer', fontSize: 12.5, fontWeight: 600, color: page <= 1 ? 'var(--text-3)' : 'var(--text)', fontFamily: 'inherit', display: 'flex', alignItems: 'center', gap: 5 }}
                >
                  <Icon name="chevron-left" size={13} /> 이전
                </button>
                {Array.from({ length: pagination.totalPages }, (_, i) => i + 1).map(p => (
                  <button
                    key={p}
                    id={`page-${p}`}
                    onClick={() => setPage(p)}
                    style={{
                      width: 34, height: 34, border: page === p ? 'none' : '1px solid var(--border)',
                      background: page === p ? 'var(--text)' : 'var(--surface-2)',
                      color: page === p ? '#fff' : 'var(--text-2)',
                      borderRadius: 8, cursor: 'pointer', fontSize: 12.5, fontWeight: 700, fontFamily: 'inherit',
                    }}
                  >{p}</button>
                ))}
                <button
                  id="page-next"
                  onClick={() => setPage(p => Math.min(pagination.totalPages, p + 1))}
                  disabled={page >= pagination.totalPages}
                  style={{ padding: '7px 14px', border: '1px solid var(--border)', background: 'var(--surface-2)', borderRadius: 8, cursor: page >= pagination.totalPages ? 'not-allowed' : 'pointer', fontSize: 12.5, fontWeight: 600, color: page >= pagination.totalPages ? 'var(--text-3)' : 'var(--text)', fontFamily: 'inherit', display: 'flex', alignItems: 'center', gap: 5 }}
                >
                  다음 <Icon name="chevron-right" size={13} />
                </button>
              </div>
            )}
          </Card>

          {/* 상세 패널 */}
          {selectedMember && (
            <Card pad={0} style={{ position: 'sticky', top: 0 }}>
              <MemberDetailPanel
                member={selectedMember}
                onEdit={(m) => setEditTarget(m)}
                onDelete={(m) => setDeleteTarget(m)}
                onClose={() => setSelectedMember(null)}
              />
            </Card>
          )}
        </div>
      </div>

      {/* 수정 모달 */}
      {editTarget && (
        <EditMemberModal
          member={editTarget}
          onClose={() => setEditTarget(null)}
          onSave={handleSave}
        />
      )}

      {/* 삭제 확인 모달 */}
      {deleteTarget && (
        <DeleteConfirmModal
          member={deleteTarget}
          onClose={() => setDeleteTarget(null)}
          onConfirm={handleDelete}
        />
      )}
    </>
  );
}
