import React, { useState } from 'react';
import { Card } from '../components/Card';
import { SectionHead } from '../components/SectionHead';
import { Badge } from '../components/Badge';
import { Battery } from '../components/Battery';
import { Avatar } from '../components/Avatar';
import { Icon } from '../components/Icon';
import { STATUS } from '../data';

export function CameraView({ robots = [], onTitleClick }) {
  const [streamError, setStreamError] = useState(false);
  const [retryKey, setRetryKey] = useState(0);

  // 'CartMe-ROS2-08'을 우선 검색하고 없으면 첫 번째 로봇 선택
  const targetRobot = robots.find(r => r.id === 'CartMe-ROS2-08') || robots[0] || null;

  const handleRetry = () => {
    setStreamError(false);
    setRetryKey(prev => prev + 1);
  };

  const statusConfig = targetRobot ? (STATUS[targetRobot.status] || { ko: '—', tone: 'gray' }) : null;

  const backendHost = window.location.hostname || 'localhost';
  const streamUrl = `http://${backendHost}:3000/api/hardware/video-feed?t=${retryKey}`;


  return (
    <div style={{ display: 'grid', gridTemplateColumns: '1fr 360px', gap: 18, alignItems: 'start' }}>
      
      {/* 왼쪽: 카메라 실시간 영상 카드 */}
      <Card pad={0}>
        <div style={{ padding: '16px 18px 14px', borderBottom: '1px solid var(--border)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <h3 
            onClick={onTitleClick}
            style={{ fontSize: 15, fontWeight: 700, display: 'flex', alignItems: 'center', gap: 8, margin: 0, cursor: onTitleClick ? 'pointer' : 'default', userSelect: 'none' }}
          >
            <span style={{ 
              display: 'inline-block', 
              width: 8, 
              height: 8, 
              borderRadius: '99px', 
              background: streamError ? 'var(--red)' : 'var(--green)' 
            }} />
            카메라 실시간 영상 피드
          </h3>
          <button onClick={handleRetry} className="ctl-btn" style={{ width: 'auto', padding: '6px 12px', fontSize: 12, display: 'flex', alignItems: 'center', gap: 6 }}>
            <Icon name="refresh-cw" size={13} />
            새로고침
          </button>
        </div>

        <div style={{ position: 'relative', width: '100%', aspectRatio: '4/3', background: '#090a0f', display: 'flex', justifyContent: 'center', alignItems: 'center', overflow: 'hidden' }}>
          {!streamError ? (
            <img
              key={retryKey}
              src={streamUrl}
              alt="Robot Camera Stream"
              onError={() => setStreamError(true)}
              style={{ width: '100%', height: '100%', objectFit: 'contain' }}
            />
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 12, padding: '40px', color: 'var(--text-3)' }}>
              <div style={{ width: 54, height: 54, borderRadius: 50, background: 'rgba(229, 72, 77, 0.1)', display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--red)' }}>
                <Icon name="video-off" size={24} />
              </div>
              <div style={{ fontSize: 14, fontWeight: 700, color: 'var(--text)' }}>스트리밍 서버와 연결할 수 없습니다</div>
              <div style={{ fontSize: 12.5, textAlign: 'center', lineHeight: '18px' }}>
                로봇의 카메라 서버가 켜져 있는지 확인해 주세요.<br />
                (기본 포트: 5000)
              </div>
              <button onClick={handleRetry} className="ctl-btn" style={{ width: 'auto', padding: '8px 16px', marginTop: 8 }}>
                재연결 시도
              </button>
            </div>
          )}
        </div>
      </Card>

      {/* 오른쪽: 로봇 상세 정보 및 상태 관제 */}
      {targetRobot ? (
        <Card>
          <SectionHead title="로봇 세션 정보" en={targetRobot.id} />
          
          <div style={{ display: 'flex', alignItems: 'center', gap: 12, paddingBottom: 16, borderBottom: '1px solid var(--border)', marginBottom: 16 }}>
            <div style={{ width: 44, height: 44, borderRadius: 10, background: 'var(--gray-bg)', border: '1px solid var(--border)', display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--text)' }}>
              <Icon name="bot" size={20} />
            </div>
            <div style={{ flex: 1 }}>
              <div className="mono" style={{ fontSize: 14, fontWeight: 700 }}>{targetRobot.id}</div>
              <div style={{ fontSize: 12, color: 'var(--text-3)' }}>스마트 팔로잉 쇼핑카트</div>
            </div>
            {statusConfig && (
              <Badge tone={statusConfig.tone}>{statusConfig.ko}</Badge>
            )}
          </div>

          <dl style={{ display: 'grid', gridTemplateColumns: '1fr', gap: '16px 0', margin: 0 }}>
            <div>
              <dt style={{ fontSize: 11.5, color: 'var(--text-3)', fontWeight: 600, marginBottom: 5, textTransform: 'uppercase' }}>배터리 잔량</dt>
              <dd style={{ display: 'flex', alignItems: 'center', gap: 8, margin: 0 }}>
                <Battery level={targetRobot.battery} />
                <span style={{ fontSize: 13, fontWeight: 700, color: 'var(--text-2)' }}>{targetRobot.battery}%</span>
              </dd>
            </div>

            <div style={{ height: '1px', background: 'var(--border)', margin: '4px 0' }} />

            <div>
              <dt style={{ fontSize: 11.5, color: 'var(--text-3)', fontWeight: 600, marginBottom: 6, textTransform: 'uppercase' }}>매칭 사용자</dt>
              <dd style={{ margin: 0 }}>
                {targetRobot.user ? (
                  <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                    <Avatar name={targetRobot.user} size={28} />
                    <div style={{ display: 'flex', flexDirection: 'column' }}>
                      <span style={{ fontSize: 13, fontWeight: 700, color: 'var(--text)' }}>{targetRobot.user}</span>
                      <span className="mono" style={{ fontSize: 11, color: 'var(--text-3)' }}>ID: {targetRobot.userId}</span>
                    </div>
                  </div>
                ) : (
                  <span style={{ fontSize: 13, color: 'var(--text-3)', fontWeight: 500 }}>현재 매칭된 사용자가 없습니다.</span>
                )}
              </dd>
            </div>

            <div style={{ height: '1px', background: 'var(--border)', margin: '4px 0' }} />

            <div>
              <dt style={{ fontSize: 11.5, color: 'var(--text-3)', fontWeight: 600, marginBottom: 5, textTransform: 'uppercase' }}>현재 위치 구역</dt>
              <dd style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 13, fontWeight: 600, color: 'var(--text-2)', margin: 0 }}>
                <Icon name="map-pin" size={14} style={{ color: 'var(--text-3)' }} />
                {targetRobot.zone || '알 수 없음'}
              </dd>
            </div>
          </dl>
        </Card>
      ) : (
        <Card>
          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 10, padding: '40px 0', color: 'var(--text-3)' }}>
            <Icon name="bot" size={26} />
            <div style={{ fontSize: 13.5, fontWeight: 600 }}>활성화된 카트 정보 없음</div>
          </div>
        </Card>
      )}

    </div>
  );
}
