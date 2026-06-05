import React from 'react';
import { Card } from '../components/Card';
import { Icon } from '../components/Icon';
import { Badge } from '../components/Badge';

const won = (n) => '₩' + n.toLocaleString('ko-KR');

export function InventoryView({ inventory = [] }) {
  if (inventory.length === 0) {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 12, padding: '90px 0', color: 'var(--text-3)' }}>
        <Icon name="package" size={30} />
        <div style={{ fontSize: 14, fontWeight: 600, color: 'var(--text-2)' }}>등록된 상품이 없습니다</div>
        <div style={{ fontSize: 12.5 }}>RFID 태그 상품 데이터를 연결하면 이 화면에 표시됩니다.</div>
      </div>
    );
  }

  return (
    <Card pad={0}>
      <div style={{ padding: '16px 18px', borderBottom: '1px solid var(--border)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <h3 style={{ fontSize: 15, fontWeight: 700 }}>RFID 상품 마스터 <span className="mono" style={{ fontSize: 11, color: 'var(--text-3)', fontWeight: 500 }}>{inventory.length} SKUs</span></h3>
        <span style={{ display: 'inline-flex', gap: 8, alignItems: 'center', fontSize: 12.5, color: 'var(--text-2)', fontWeight: 600, padding: '7px 12px', border: '1px solid var(--border)', borderRadius: 8, cursor: 'pointer' }}><Icon name="plus" size={14} />상품 등록</span>
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: '110px 1fr 100px 90px 90px 96px', gap: 12, padding: '10px 18px', fontSize: 11, fontWeight: 700, color: 'var(--text-3)', borderBottom: '1px solid var(--border)', textTransform: 'uppercase', letterSpacing: '0.03em' }}>
        <span>SKU</span><span>상품명</span><span>분류</span><span style={{ textAlign: 'right' }}>가격</span><span style={{ textAlign: 'right' }}>재고</span><span>RFID</span>
      </div>
      {inventory.map((it) => (
        <div key={it.sku} style={{ display: 'grid', gridTemplateColumns: '110px 1fr 100px 90px 90px 96px', gap: 12, alignItems: 'center', padding: '13px 18px', borderBottom: '1px solid var(--border)' }}>
          <span className="mono" style={{ fontSize: 12, color: 'var(--text-2)', fontWeight: 600 }}>{it.sku}</span>
          <span style={{ minWidth: 0 }}>
            <span style={{ fontSize: 13, fontWeight: 600, display: 'block', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{it.name}</span>
            <span style={{ fontSize: 11, color: 'var(--text-3)' }}>{it.en}</span>
          </span>
          <span style={{ fontSize: 12.5, color: 'var(--text-2)' }}>{it.cat}</span>
          <span className="mono" style={{ fontSize: 13, fontWeight: 600, textAlign: 'right' }}>{won(it.price)}</span>
          <span style={{ textAlign: 'right' }}>
            <span className="mono" style={{ fontSize: 13, fontWeight: 600, color: it.stock === 0 ? 'var(--red)' : it.stock <= 10 ? 'var(--amber)' : 'var(--text)' }}>{it.stock}</span>
          </span>
          <span>{it.tagged ? <Badge tone="green" dot={false}>등록</Badge> : <Badge tone="amber" dot={false}>미등록</Badge>}</span>
        </div>
      ))}
    </Card>
  );
}
