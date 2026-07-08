import React, { useState, useEffect } from 'react';
import { Card } from '../components/Card';
import { Icon } from '../components/Icon';
import { Badge } from '../components/Badge';
import { ProductRegisterModal } from './ProductRegisterModal';

const BACKEND_URL = 'http://192.168.0.30:3000';
const won = (n) => '₩' + n.toLocaleString('ko-KR');

export function InventoryView() {
  const [products, setProducts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [modalOpen, setModalOpen] = useState(false);

  const fetchProducts = async () => {
    try {
      setLoading(true);
      const res = await fetch(`${BACKEND_URL}/api/products`);
      if (!res.ok) throw new Error('상품 목록을 불러오지 못했습니다.');
      const data = await res.json();
      if (data.success) {
        setProducts(data.products);
      } else {
        throw new Error(data.message || '오류 발생');
      }
      setError(null);
    } catch (err) {
      console.error(err);
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchProducts();
  }, []);

  const handleCreateProduct = async (productData) => {
    const res = await fetch(`${BACKEND_URL}/api/products`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(productData),
    });

    const data = await res.json();
    if (!res.ok || !data.success) {
      throw new Error(data.message || '상품 등록에 실패했습니다.');
    }

    // 등록 성공 시 목록 갱신
    fetchProducts();
  };

  return (
    <>
      <Card pad={0}>
        {/* 헤더 */}
        <div style={{
          padding: '16px 18px', borderBottom: '1px solid var(--border)',
          display: 'flex', justifyContent: 'space-between', alignItems: 'center',
        }}>
          <h3 style={{ fontSize: 15, fontWeight: 700 }}>
            RFID 상품 마스터{' '}
            <span className="mono" style={{ fontSize: 11, color: 'var(--text-3)', fontWeight: 500 }}>
              {products.length} SKUs
            </span>
          </h3>
          <button
            id="btn-product-register"
            onClick={() => setModalOpen(true)}
            style={{
              display: 'inline-flex', gap: 7, alignItems: 'center',
              fontSize: 12.5, fontWeight: 600, padding: '8px 14px',
              background: 'var(--text)', color: '#fff',
              border: 'none', borderRadius: 8, cursor: 'pointer', transition: 'opacity .12s',
            }}
            onMouseOver={e => e.currentTarget.style.opacity = '0.82'}
            onMouseOut={e => e.currentTarget.style.opacity = '1'}
          >
            <Icon name="plus" size={14} />
            상품 등록
          </button>
        </div>

        {/* 로딩 상태 */}
        {loading ? (
          <div style={{ display: 'flex', justifyContent: 'center', padding: '40px 0' }}>
            <div style={{
              width: 24, height: 24, border: '2.5px solid var(--border-strong)', borderTopColor: 'var(--text)',
              borderRadius: 99, animation: 'spin 0.8s linear infinite'
            }} />
          </div>
        ) : error ? (
          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', padding: '40px 0', color: 'var(--red)', gap: 8 }}>
            <Icon name="octagon-x" size={24} />
            <div style={{ fontSize: 13, fontWeight: 600 }}>{error}</div>
            <button onClick={fetchProducts} style={{ fontSize: 12, padding: '4px 10px', background: 'var(--surface-2)', border: '1px solid var(--border)', borderRadius: 4, cursor: 'pointer' }}>재시도</button>
          </div>
        ) : products.length === 0 ? (
          /* 빈 상태 */
          <div style={{
            display: 'flex', flexDirection: 'column', alignItems: 'center',
            justifyContent: 'center', gap: 12, padding: '80px 0', color: 'var(--text-3)',
          }}>
            <Icon name="package" size={32} />
            <div style={{ fontSize: 14, fontWeight: 600, color: 'var(--text-2)' }}>등록된 상품이 없습니다</div>
            <div style={{ fontSize: 12.5 }}>상품 등록 버튼을 눌러 첫 번째 상품을 추가하세요.</div>
            <button
              onClick={() => setModalOpen(true)}
              style={{
                marginTop: 4, display: 'inline-flex', gap: 7, alignItems: 'center',
                fontSize: 13, fontWeight: 600, padding: '9px 18px',
                border: '1.5px dashed var(--border-strong)', borderRadius: 9,
                background: 'transparent', color: 'var(--text-2)', cursor: 'pointer',
                transition: 'all .12s',
              }}
              onMouseOver={e => { e.currentTarget.style.background = 'var(--surface-2)'; e.currentTarget.style.borderColor = 'var(--text)'; }}
              onMouseOut={e => { e.currentTarget.style.background = 'transparent'; e.currentTarget.style.borderColor = 'var(--border-strong)'; }}
            >
              <Icon name="plus" size={14} />
              첫 번째 상품 등록하기
            </button>
          </div>
        ) : (
          <>
            {/* 컬럼 헤더 */}
            <div style={{
              display: 'grid', gridTemplateColumns: '110px 1fr 100px 90px 90px 150px',
              gap: 12, padding: '10px 18px', fontSize: 11, fontWeight: 700,
              color: 'var(--text-3)', borderBottom: '1px solid var(--border)',
              textTransform: 'uppercase', letterSpacing: '0.03em',
            }}>
              <span>SKU</span><span>상품명</span><span>분류</span>
              <span style={{ textAlign: 'right' }}>가격</span>
              <span style={{ textAlign: 'right' }}>재고</span>
              <span>RFID 태그</span>
            </div>

            {/* 상품 행 */}
            {products.map((it) => (
              <div key={it.id} style={{
                display: 'grid', gridTemplateColumns: '110px 1fr 100px 90px 90px 150px',
                gap: 12, alignItems: 'center', padding: '13px 18px',
                borderBottom: '1px solid var(--border)',
              }}>
                <span className="mono" style={{ fontSize: 12, color: 'var(--text-2)', fontWeight: 600 }}>
                  PROD-{String(it.id).padStart(4, '0')}
                </span>
                <span style={{ minWidth: 0 }}>
                  <span style={{ fontSize: 13, fontWeight: 600, display: 'block', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {it.name}
                  </span>
                </span>
                <span style={{ fontSize: 12.5, color: 'var(--text-2)' }}>{it.category || '기타'}</span>
                <span className="mono" style={{ fontSize: 13, fontWeight: 600, textAlign: 'right' }}>{won(it.price)}</span>
                <span style={{ textAlign: 'right' }}>
                  <span className="mono" style={{
                    fontSize: 13, fontWeight: 600,
                    color: it.stock === 0 ? 'var(--red)' : it.stock <= 10 ? 'var(--amber)' : 'var(--text)',
                  }}>{it.stock}</span>
                </span>
                <span className="mono" style={{ fontSize: 12 }}>
                  <Badge tone="green" dot={false}>{it.rfid_tag}</Badge>
                </span>
              </div>
            ))}
          </>
        )}
      </Card>

      <ProductRegisterModal
        open={modalOpen}
        onClose={() => setModalOpen(false)}
        onSubmit={handleCreateProduct}
      />
    </>
  );
}
