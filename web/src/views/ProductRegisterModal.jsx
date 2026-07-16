import React, { useState, useEffect, useRef } from 'react';
import { Icon } from '../components/Icon';
import { io } from 'socket.io-client';

import { BACKEND_URL } from '../api';


const CATEGORIES = ['과일', '채소', '음료', '유제품', '육류', '베이커리', '냉동식품', '기타'];
const EMPTY_FORM = { rfid_tag: '', name: '', price: '', category: '', stock: '' };

export function ProductRegisterModal({ open, onClose, onSubmit }) {
  const [form, setForm]             = useState(EMPTY_FORM);
  const [errors, setErrors]         = useState({});
  const [submitting, setSubmitting] = useState(false);
  const [submitOk, setSubmitOk]     = useState(false);
  const firstRef = useRef(null);

  useEffect(() => {
    if (open) {
      setForm(EMPTY_FORM);
      setErrors({});
      setSubmitOk(false);
      setTimeout(() => firstRef.current?.focus(), 80);
    }
  }, [open]);

  // ── 소켓: 모달 열릴 때 연결, 닫힐 때 해제 ──
  const [scanning, setScanning] = useState(false);
  useEffect(() => {
    if (!open) return;

    const socket = io(BACKEND_URL, {
      auth: { token: 'admin-cartpilot' },
      transports: ['websocket'],
    });

    socket.on('connect', () => {
      console.log('[Socket] Admin connected - RFID 대기 중');
      setScanning(true);
    });

    socket.on('rfid:scanned', ({ uid }) => {
      setForm((f) => ({ ...f, rfid_tag: uid }));
      setErrors((e) => { const n = { ...e }; delete n.rfid_tag; return n; });
      setScanning(false);
      console.log('[Socket] RFID 수신:', uid);
    });

    socket.on('disconnect', () => setScanning(false));
    socket.on('connect_error', () => setScanning(false));

    return () => {
      socket.disconnect();
      setScanning(false);
    };
  }, [open]);

  // ESC 닫기
  useEffect(() => {
    const onKey = (e) => { if (e.key === 'Escape' && !submitting) onClose(); };
    if (open) window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open, submitting, onClose]);

  const change = (field) => (e) => {
    setForm((f) => ({ ...f, [field]: e.target.value }));
    if (errors[field]) setErrors((er) => { const n = { ...er }; delete n[field]; return n; });
  };

  const validate = () => {
    const e = {};
    if (!form.rfid_tag.trim()) e.rfid_tag = 'RFID 태그를 입력하세요';
    if (!form.name.trim())     e.name     = '상품명을 입력하세요';
    if (!form.price || isNaN(+form.price) || +form.price < 0) e.price = '올바른 가격을 입력하세요';
    if (!form.stock || isNaN(+form.stock) || +form.stock < 0) e.stock = '올바른 재고를 입력하세요';
    return e;
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    const errs = validate();
    if (Object.keys(errs).length) { setErrors(errs); return; }
    setSubmitting(true);
    try {
      await onSubmit({
        rfid_tag: form.rfid_tag.trim().toUpperCase(),
        name:     form.name.trim(),
        price:    +form.price,
        category: form.category || null,
        stock:    +form.stock,
      });
      setSubmitOk(true);
      setTimeout(() => onClose(), 1000);
    } catch (err) {
      setErrors({ submit: err.message || '등록에 실패했습니다.' });
    } finally {
      setSubmitting(false);
    }
  };

  if (!open) return null;

  return (
    /* 배경 오버레이 */
    <div
      onClick={(e) => { if (e.target === e.currentTarget && !submitting) onClose(); }}
      style={{
        position: 'fixed', inset: 0, zIndex: 1000,
        background: 'rgba(10,12,20,0.45)',
        backdropFilter: 'blur(6px)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        animation: 'fadeIn 0.18s ease',
        padding: 24,
      }}
    >
      {/* 팝업 카드 */}
      <div
        style={{
          width: '100%', maxWidth: 540,
          background: 'var(--surface)',
          border: '1px solid var(--border)',
          borderRadius: 16,
          boxShadow: '0 24px 60px rgba(0,0,0,0.22), 0 4px 16px rgba(0,0,0,0.1)',
          overflow: 'hidden',
          animation: 'popIn 0.22s cubic-bezier(0.34,1.56,0.64,1)',
        }}
      >
        {/* 헤더 */}
        <div style={{
          padding: '20px 22px 18px',
          borderBottom: '1px solid var(--border)',
          display: 'flex', alignItems: 'center', gap: 12,
        }}>
          <div style={{
            width: 38, height: 38, borderRadius: 10,
            background: 'var(--text)', color: '#fff',
            display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0,
          }}>
            <Icon name="package-plus" size={18} />
          </div>
          <div>
            <div style={{ fontSize: 16, fontWeight: 800, letterSpacing: '-0.02em' }}>상품 등록</div>
            <div style={{ fontSize: 12, color: 'var(--text-3)', fontWeight: 500, marginTop: 1 }}>
              RFID 태그와 상품 정보를 입력하세요
            </div>
          </div>
          <button
            onClick={onClose}
            style={{
              marginLeft: 'auto', width: 32, height: 32,
              border: '1px solid var(--border)', background: 'transparent',
              borderRadius: 8, cursor: 'pointer',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              color: 'var(--text-3)', transition: 'all .12s',
            }}
            onMouseOver={e => { e.currentTarget.style.background = 'var(--surface-2)'; e.currentTarget.style.color = 'var(--text)'; }}
            onMouseOut={e => { e.currentTarget.style.background = 'transparent'; e.currentTarget.style.color = 'var(--text-3)'; }}
          >
            <Icon name="x" size={15} />
          </button>
        </div>

        {/* 폼 바디 */}
        <form onSubmit={handleSubmit} style={{ padding: '22px' }}>

          {/* RFID 태그 */}
          <Field label="RFID 태그" required error={errors.rfid_tag}>
            <div style={{ position: 'relative' }}>
              <span style={{
                position: 'absolute', left: 11, top: '50%', transform: 'translateY(-50%)',
                color: scanning ? 'var(--blue)' : 'var(--text-3)',
                display: 'flex', pointerEvents: 'none',
              }}>
                <Icon name="scan-line" size={14} />
              </span>
              <input
                ref={firstRef}
                value={form.rfid_tag}
                onChange={change('rfid_tag')}
                placeholder={scanning ? '아두이노 태그를 스캔하세요...' : '예) A1B2C3D4'}
                className="mono"
                style={inp(!!errors.rfid_tag, {
                  paddingLeft: 32,
                  paddingRight: scanning ? 100 : 12,
                  borderColor: scanning ? 'var(--blue)' : (errors.rfid_tag ? 'var(--red)' : 'var(--border)'),
                  background: scanning ? 'var(--blue-bg)' : (errors.rfid_tag ? 'var(--red-bg)' : 'var(--surface)'),
                })}
              />
              {scanning && (
                <span style={{
                  position: 'absolute', right: 10, top: '50%', transform: 'translateY(-50%)',
                  display: 'flex', alignItems: 'center', gap: 5,
                  fontSize: 11, fontWeight: 700, color: 'var(--blue)',
                }}>
                  <div style={{
                    width: 10, height: 10,
                    border: '2px solid var(--blue-bg)',
                    borderTopColor: 'var(--blue)',
                    borderRadius: 99, animation: 'spin 0.7s linear infinite',
                  }} />
                  대기중
                </span>
              )}
            </div>
          </Field>

          {/* 상품명 */}
          <Field label="상품명" required error={errors.name}>
            <input
              value={form.name}
              onChange={change('name')}
              placeholder="예) 제주 감귤"
              style={inp(!!errors.name)}
            />
          </Field>

          {/* 가격 + 재고 */}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14 }}>
            <Field label="가격 (₩)" required error={errors.price}>
              <div style={{ position: 'relative' }}>
                <span style={{
                  position: 'absolute', left: 10, top: '50%', transform: 'translateY(-50%)',
                  fontSize: 13, fontWeight: 700, color: 'var(--text-3)', pointerEvents: 'none',
                }}>₩</span>
                <input
                  type="number" min="0"
                  value={form.price}
                  onChange={change('price')}
                  placeholder="0"
                  className="mono"
                  style={inp(!!errors.price, { paddingLeft: 24 })}
                />
              </div>
            </Field>
            <Field label="재고 수량" required error={errors.stock}>
              <input
                type="number" min="0"
                value={form.stock}
                onChange={change('stock')}
                placeholder="0"
                className="mono"
                style={inp(!!errors.stock)}
              />
            </Field>
          </div>

          {/* 카테고리 칩 */}
          <Field label="카테고리" error={errors.category}>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 7, marginTop: 2 }}>
              {CATEGORIES.map((cat) => (
                <button
                  key={cat} type="button"
                  onClick={() => setForm((f) => ({ ...f, category: f.category === cat ? '' : cat }))}
                  style={{
                    padding: '5px 13px', borderRadius: 20, fontSize: 12.5, fontWeight: 600,
                    cursor: 'pointer', transition: 'all .12s',
                    border: `1.5px solid ${form.category === cat ? 'var(--text)' : 'var(--border)'}`,
                    background: form.category === cat ? 'var(--text)' : 'transparent',
                    color: form.category === cat ? '#fff' : 'var(--text-2)',
                  }}
                >
                  {cat}
                </button>
              ))}
            </div>
          </Field>

          {/* 에러 / 성공 */}
          {errors.submit && (
            <div style={banner('red')}>
              <Icon name="circle-x" size={15} />{errors.submit}
            </div>
          )}
          {submitOk && (
            <div style={banner('green')}>
              <Icon name="circle-check" size={15} />상품이 성공적으로 등록되었습니다!
            </div>
          )}
        </form>

        {/* 하단 버튼 */}
        <div style={{
          padding: '14px 22px 20px',
          display: 'flex', gap: 10,
        }}>
          <button
            type="button" onClick={onClose}
            style={{
              flex: 1, padding: '11px', borderRadius: 9,
              border: '1px solid var(--border)', background: 'transparent',
              fontSize: 13.5, fontWeight: 600, color: 'var(--text-2)', cursor: 'pointer',
              transition: 'all .12s',
            }}
            onMouseOver={e => e.currentTarget.style.background = 'var(--surface-2)'}
            onMouseOut={e => e.currentTarget.style.background = 'transparent'}
          >
            취소
          </button>
          <button
            onClick={handleSubmit}
            disabled={submitting || submitOk}
            style={{
              flex: 2, padding: '11px', borderRadius: 9, border: 'none',
              background: submitOk ? 'var(--green)' : 'var(--text)',
              color: '#fff', fontSize: 13.5, fontWeight: 700,
              cursor: submitting ? 'not-allowed' : 'pointer',
              opacity: submitting ? 0.72 : 1,
              display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8,
              transition: 'all .15s',
            }}
          >
            {submitting ? (
              <>
                <div style={{
                  width: 14, height: 14,
                  border: '2.5px solid rgba(255,255,255,0.35)',
                  borderTopColor: '#fff', borderRadius: 99,
                  animation: 'spin 0.7s linear infinite',
                }} />
                등록 중...
              </>
            ) : submitOk ? (
              <><Icon name="check" size={16} /> 등록 완료!</>
            ) : (
              <><Icon name="plus" size={16} /> 상품 등록</>
            )}
          </button>
        </div>
      </div>
    </div>
  );
}

/* ── 헬퍼 ── */
function Field({ label, required, error, children }) {
  return (
    <div style={{ marginBottom: 16 }}>
      <label style={{
        display: 'block', fontSize: 12, fontWeight: 700,
        color: error ? 'var(--red)' : 'var(--text-2)',
        marginBottom: 6, letterSpacing: '0.01em',
      }}>
        {label}{required && <span style={{ color: 'var(--red)', marginLeft: 3 }}>*</span>}
      </label>
      {children}
      {error && (
        <div style={{ fontSize: 11.5, color: 'var(--red)', marginTop: 5, display: 'flex', alignItems: 'center', gap: 4 }}>
          <Icon name="triangle-alert" size={11} />{error}
        </div>
      )}
    </div>
  );
}

function inp(hasError, extra = {}) {
  return {
    width: '100%', padding: '10px 12px',
    border: `1.5px solid ${hasError ? 'var(--red)' : 'var(--border)'}`,
    borderRadius: 9,
    background: hasError ? 'var(--red-bg)' : 'var(--surface)',
    fontSize: 13.5, color: 'var(--text)', outline: 'none',
    fontFamily: 'inherit', transition: 'border-color .12s',
    ...extra,
  };
}

function banner(tone) {
  return {
    marginBottom: 12, padding: '10px 14px', borderRadius: 9,
    background: `var(--${tone}-bg)`, border: `1px solid var(--${tone})`,
    color: `var(--${tone})`, fontSize: 13, fontWeight: 600,
    display: 'flex', alignItems: 'center', gap: 8,
  };
}
