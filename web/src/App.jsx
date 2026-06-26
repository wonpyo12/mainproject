import React, { useState, useEffect } from 'react';
import { Icon } from './components/Icon';
import { Avatar } from './components/Avatar';
import { DashboardView } from './views/DashboardView';
import { FleetView } from './views/FleetView';
import { InventoryView } from './views/InventoryView';
import { AlertsView } from './views/AlertsView';
import { EmptyView } from './views/EmptyView';
import { MembersView } from './views/MembersView';
import { CameraView } from './views/CameraView';
import { fetchMockData } from './api';
import { io } from 'socket.io-client';

const BACKEND_URL = 'http://localhost:3000';


const NAV = [
  { id: 'dashboard', ko: '대시보드', en: 'Dashboard', icon: 'layout-dashboard' },
  { id: 'camera', ko: '카메라 모니터링', en: 'Camera Monitor', icon: 'video' },
  { id: 'fleet', ko: '로봇 관리', en: 'Fleet', icon: 'bot' },
  { id: 'inventory', ko: '재고 / RFID', en: 'Inventory', icon: 'package' },
  { id: 'alerts', ko: '알림', en: 'Alerts', icon: 'bell' },
];

const NAV2 = [
  { id: 'map', ko: '매장 지도', en: 'Zones', icon: 'map' },
  { id: 'members', ko: '회원', en: 'Members', icon: 'users' },
  { id: 'settings', ko: '설정', en: 'Settings', icon: 'settings' },
];

const TITLES = {
  dashboard: ['대시보드', '실시간 매장 운영 현황'],
  camera: ['카메라 모니터링', '로봇 카메라 실시간 스트리밍 피드'],
  fleet: ['로봇 관리', '추종 카트 플릿 모니터링 · 제어'],
  inventory: ['재고 / RFID', 'RFID 태그 상품 마스터'],
  alerts: ['알림', '도난 방지 · 배터리 · 추적 이벤트'],
  map: ['매장 지도', 'SLAM 맵 · 운영 구역'],
  members: ['회원', 'QR 인증 사용자'],
  settings: ['설정', '시스템 환경설정'],
};

function NavItem({ item, active, onClick, badge }) {
  return (
    <button onClick={onClick} className={`nav-item${active ? ' active' : ''}`}>
      <Icon name={item.icon} size={17} />
      <span style={{ flex: 1, textAlign: 'left' }}>{item.ko}</span>
      {badge > 0 && <span className="nav-badge">{badge}</span>}
    </button>
  );
}

export default function App() {
  const [isAdmin, setIsAdmin] = useState(() => localStorage.getItem('cartpilot_is_admin') === 'true');
  const [view, setView] = useState(() => {
    const savedAdmin = localStorage.getItem('cartpilot_is_admin') === 'true';
    return savedAdmin ? 'dashboard' : 'camera';
  });
  const [selected, setSelected] = useState(null);
  const [t, st] = useState('00:00');

  const [apiData, setApiData] = useState(null);
  const [alerts, setAlerts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const [toast, setToast] = useState(null);
  const [clickCount, setClickCount] = useState(0);

  const showToast = (message, type = 'success') => {
    setToast({ message, type });
  };

  // 2초 동안 추가 탭이 없으면 클릭 카운트 초기화
  useEffect(() => {
    if (clickCount > 0) {
      const tId = setTimeout(() => setClickCount(0), 2000);
      return () => clearTimeout(tId);
    }
  }, [clickCount]);

  // 토스트 자동 페이드아웃
  useEffect(() => {
    if (toast) {
      const tId = setTimeout(() => setToast(null), 3000);
      return () => clearTimeout(tId);
    }
  }, [toast]);

  // 키보드로 "admin" 입력 감지하여 관리자 모드 전환
  useEffect(() => {
    let keys = '';
    const handleKeyDown = (e) => {
      if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;
      keys += e.key.toLowerCase();
      if (keys.length > 5) keys = keys.slice(-5);
      if (keys === 'admin') {
        setIsAdmin((curr) => {
          const next = !curr;
          localStorage.setItem('cartpilot_is_admin', String(next));
          setView(next ? 'dashboard' : 'camera');
          showToast(next ? '관리자 모드가 활성화되었습니다.' : '사용자 모드(Kiosk)로 전환되었습니다.', 'success');
          return next;
        });
        keys = '';
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, []);

  const handleTitleClick = () => {
    setClickCount((prev) => {
      const next = prev + 1;
      if (next >= 5) {
        setIsAdmin((curr) => {
          const nextAdmin = !curr;
          localStorage.setItem('cartpilot_is_admin', String(nextAdmin));
          setView(nextAdmin ? 'dashboard' : 'camera');
          showToast(nextAdmin ? '관리자 모드가 활성화되었습니다.' : '사용자 모드(Kiosk)로 전환되었습니다.', 'success');
          return nextAdmin;
        });
        return 0;
      }
      return next;
    });
  };

  // 경과 시간 계산 헬퍼 함수
  const calculateMinutesAgo = (isoString) => {
    if (!isoString) return 0;
    const diffMs = new Date() - new Date(isoString);
    return Math.max(0, Math.floor(diffMs / 60000));
  };

  useEffect(() => {
    const tick = () => {
      const d = new Date();
      st(d.toLocaleTimeString('ko-KR', { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false }));
    };
    tick();
    const id = setInterval(tick, 1000);
    return () => clearInterval(id);
  }, []);

  useEffect(() => {
    fetchMockData()
      .then(res => {
        setApiData(res);
        
        // localStorage에서 기존 로그인 알림 복구 및 경과 시간 갱신
        const saved = localStorage.getItem('cartpilot_login_alerts');
        const customAlerts = saved ? JSON.parse(saved) : [];
        const updatedCustomAlerts = customAlerts.map(a => ({
          ...a,
          mins: calculateMinutesAgo(a.timestamp)
        }));

        setAlerts([...updatedCustomAlerts, ...(res.alerts || [])]);
        
        // Auto-select first robot if available
        if (res.robots && res.robots.length > 0) {
          setSelected(res.robots[0].id);
        }
        setLoading(false);
      })
      .catch(err => {
        console.error(err);
        setError(err.message);
        setLoading(false);
      });
  }, []);

  useEffect(() => {
    const socket = io(BACKEND_URL, {
      auth: { token: 'admin-cartpilot' },
      transports: ['websocket'],
    });

    socket.on('connect', () => {
      console.log('[Socket] Global Web Admin connected');
    });

    socket.on('user:login', (data) => {
      console.log('[Socket] user:login received:', data);
      
      const newAlert = {
        level: 'info',
        cart: 'SYSTEM',
        ko: `${data.userName} 님이 로그인했습니다.`,
        mins: 0,
        timestamp: data.timestamp || new Date().toISOString()
      };

      setAlerts((prev) => {
        const nextAlerts = [newAlert, ...prev];
        // localStorage에 새 로그인 알림 저장
        const saved = localStorage.getItem('cartpilot_login_alerts');
        const customAlerts = saved ? JSON.parse(saved) : [];
        localStorage.setItem('cartpilot_login_alerts', JSON.stringify([newAlert, ...customAlerts]));
        return nextAlerts;
      });
    });

    return () => {
      socket.disconnect();
    };
  }, []);

  const handleDismissAlert = (index) => {
    const alertToDismiss = alerts[index];
    setAlerts((prev) => prev.filter((_, i) => i !== index));

    // 만약 localStorage에 저장된 로그인 알림이라면, localStorage에서도 제거합니다.
    if (alertToDismiss && alertToDismiss.level === 'info' && alertToDismiss.cart === 'SYSTEM') {
      const saved = localStorage.getItem('cartpilot_login_alerts');
      if (saved) {
        const customAlerts = JSON.parse(saved);
        const updated = customAlerts.filter(a => a.timestamp !== alertToDismiss.timestamp);
        localStorage.setItem('cartpilot_login_alerts', JSON.stringify(updated));
      }
    }
  };

  if (loading) {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', height: '100vh', gap: 16, background: 'var(--bg)', color: 'var(--text-2)' }}>
        <div style={{
          width: 32, height: 32, border: '3.5px solid var(--border-strong)', borderTopColor: 'var(--text)',
          borderRadius: 99, animation: 'spin 0.8s linear infinite'
        }} />
        <div style={{ fontSize: 13.5, fontWeight: 600 }}>데이터 로딩 중...</div>
      </div>
    );
  }

  if (error) {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', height: '100vh', gap: 14, background: 'var(--bg)', color: 'var(--red)' }}>
        <Icon name="octagon-x" size={32} />
        <div style={{ fontSize: 14, fontWeight: 700 }}>시스템 데이터를 불러오는 데 실패했습니다.</div>
        <div style={{ fontSize: 12.5, color: 'var(--text-3)' }}>{error}</div>
        <button onClick={() => window.location.reload()} className="ctl-btn" style={{ width: 'auto', padding: '8px 18px', marginTop: 8 }}>재시도</button>
      </div>
    );
  }

  const data = apiData || {};
  const robots = data.robots || [];
  const sessions = data.sessions || [];
  const inventory = data.inventory || [];
  const metrics = data.metrics || {};
  const storeInfo = data.storeInfo || {};
  const userInfo = data.userInfo || {};
  const alertCount = alerts.filter(a => a.level === 'urgent' || a.level === 'warn').length;

  const currentView = isAdmin ? view : 'camera';
  const [tk, tken] = TITLES[currentView] || ['화면', ''];

  let body;
  if (currentView === 'dashboard') {
    body = <DashboardView selected={selected} setSelected={setSelected} robots={robots} alerts={alerts} sessions={sessions} metrics={metrics} />;
  } else if (currentView === 'camera') {
    body = <CameraView robots={robots} onTitleClick={handleTitleClick} />;
  } else if (currentView === 'fleet') {
    body = <FleetView selected={selected} setSelected={setSelected} robots={robots} />;
  } else if (currentView === 'inventory') {
    body = <InventoryView inventory={inventory} />;
  } else if (currentView === 'alerts') {
    body = <AlertsView alerts={alerts} onDismiss={handleDismissAlert} />;
  } else if (currentView === 'members') {
    body = <MembersView />;
  } else {
    body = <EmptyView title={tk} />;
  }

  return (
    <div className={`shell${!isAdmin ? ' kiosk' : ''}`}>
      {isAdmin && (
        <aside className="sidebar">
          <div className="brand">
            <div className="brand-mark"><Icon name="shopping-cart" size={18} /></div>
            <div>
              <div className="brand-name">CartPilot</div>
              <div className="brand-sub">Robot Console</div>
            </div>
          </div>

          {storeInfo.name && (
            <div className="store-pill">
              <Icon name="store" size={14} />
              <span>{storeInfo.name}</span>
              <Icon name="chevron-down" size={14} style={{ marginLeft: 'auto', color: 'var(--text-3)' }} />
            </div>
          )}

          <nav className="nav-group">
            <div className="nav-label">운영</div>
            {NAV.map((n) => (
              <NavItem key={n.id} item={n} active={currentView === n.id} onClick={() => setView(n.id)} badge={n.id === 'alerts' ? alertCount : 0} />
            ))}
          </nav>
          <nav className="nav-group">
            <div className="nav-label">관리</div>
            {NAV2.map((n) => (
              <NavItem key={n.id} item={n} active={currentView === n.id} onClick={() => setView(n.id)} />
            ))}
          </nav>

        </aside>
      )}

      <div className="main">
        {isAdmin && (
          <header className="topbar">
            <div>
              <h1 className="page-title">{tk}</h1>
              <p className="page-sub">{tken}</p>
            </div>
            <div className="topbar-right">
              <div className="search">
                <Icon name="search" size={15} style={{ color: 'var(--text-3)' }} />
                <input placeholder="검색" />
                <span className="kbd">⌘K</span>
              </div>
              <div className="clock"><span className="live-dot" />{t}</div>
              {alertCount > 0 && (
                <button className="icon-btn">
                  <Icon name="bell" size={17} />
                  <span className="dot-red" />
                </button>
              )}
              {userInfo.name && (
                <div className="me">
                  <Avatar name={userInfo.name} size={32} />
                </div>
              )}
            </div>
          </header>
        )}
        <main className="content" style={!isAdmin ? { padding: '24px 28px' } : undefined}>{body}</main>
      </div>

      {toast && (
        <div style={{
          position: 'fixed',
          bottom: 24,
          left: '50%',
          transform: 'translateX(-50%)',
          background: 'var(--text)',
          color: '#fff',
          padding: '12px 24px',
          borderRadius: '8px',
          fontSize: '13px',
          fontWeight: 700,
          boxShadow: '0 8px 24px rgba(0,0,0,0.18)',
          zIndex: 9999,
          display: 'flex',
          alignItems: 'center',
          gap: 8,
          animation: 'slideUp 0.2s cubic-bezier(0.16, 1, 0.3, 1) both'
        }}>
          <Icon name="shield" size={15} style={{ color: 'var(--green)' }} />
          {toast.message}
        </div>
      )}
    </div>
  );
}
