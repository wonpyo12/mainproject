import React, { useState, useEffect, useRef } from 'react';
import jsQR from 'jsqr';
import { Card } from '../components/Card';
import { SectionHead } from '../components/SectionHead';
import { Badge } from '../components/Badge';
import { Battery } from '../components/Battery';
import { Avatar } from '../components/Avatar';
import { Icon } from '../components/Icon';
import { STATUS } from '../data';
import { useRobotSession } from '../hooks/useRobotSession';
import { resetRobotSession, BACKEND_URL } from '../api';

const won = (n) => '₩' + (n || 0).toLocaleString('ko-KR');

export function CameraView({ robots = [], onTitleClick }) {
  const [streamError, setStreamError] = useState(false);
  const [retryKey, setRetryKey] = useState(0);

  const targetRobot = robots[0] || null;
  // QR 매칭 → RFID 스캔 → 결제까지 고객 세션 실시간 반영
  const session = useRobotSession(targetRobot);

  const handleResetSession = async () => {
    if (!targetRobot) return;
    if (window.confirm("현재 고객의 쇼핑 세션을 강제로 종료하고 초기화하시겠습니까?")) {
      try {
        await resetRobotSession(targetRobot.id);
        alert("성공적으로 초기화되었습니다.");
      } catch (err) {
        alert(err.message);
      }
    }
  };

  const videoRef = useRef(null);
  const canvasRef = useRef(null);
  const [scanStatus, setScanStatus] = useState('idle'); // 'idle' | 'scanning' | 'success' | 'error'
  const [scannedToken, setScannedToken] = useState(null);

  const handleRetry = () => {
    setStreamError(false);
    setScanStatus('scanning');
    setRetryKey(prev => prev + 1);
  };

  const statusConfig = targetRobot ? (STATUS[targetRobot.status] || { ko: '—', tone: 'gray' }) : null;
  const shopping = session && session.status === 'SHOPPING';
  const items = (session && session.items) || [];

  // QR 인증 전: 브라우저 내 웹캠으로 QR 스캔 / 매칭 후(쇼핑중): 로봇 추종 카메라
  const source = shopping ? 'robot' : 'laptop';
  const streamUrl = `${BACKEND_URL}/api/hardware/video-feed?${source === 'robot' ? 'source=robot&' : ''}t=${retryKey}`;

  // 세션 상태가 바뀌어 소스가 전환되면 에러 상태 초기화 + 스트림 재요청
  React.useEffect(() => {
    setStreamError(false);
    setRetryKey(prev => prev + 1);
  }, [source]);

  // QR 매칭 성공 핸들러
  const handleQRScanSuccess = async (qrToken) => {
    setScanStatus('success');
    setScannedToken(qrToken);
    
    const robotSerial = targetRobot ? targetRobot.id : "CartMe-ROS2-08";
    
    try {
      const res = await fetch(`${BACKEND_URL}/api/hardware/qr-scan`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ qrToken, robotSerialNumber: robotSerial })
      });
      const d = await res.json().catch(() => ({}));
      if (res.ok && d.success) {
        console.log("[QR 스캔] 매칭 성공!");
      } else {
        alert(d.message || "QR 인증 실패");
        setScanStatus('scanning');
        setRetryKey(prev => prev + 1);
      }
    } catch (err) {
      console.error("[QR 스캔 API 에러]", err.message);
      alert("백엔드 통신 에러가 발생했습니다.");
      setScanStatus('scanning');
      setRetryKey(prev => prev + 1);
    }
  };

  // laptop 모드(QR 인증 전)일 때 브라우저 웹캠 활성화 및 QR 코드 실시간 탐지
  useEffect(() => {
    let stream = null;
    let animationFrameId = null;

    function stopCamera() {
      if (stream) {
        stream.getTracks().forEach(track => track.stop());
        stream = null;
      }
      if (animationFrameId) {
        cancelAnimationFrame(animationFrameId);
        animationFrameId = null;
      }
    }

    async function startCamera() {
      try {
        setScanStatus('scanning');
        setStreamError(false);
        if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
          throw new Error("SECURE_CONTEXT_ERROR");
        }
        stream = await navigator.mediaDevices.getUserMedia({
          video: { facingMode: 'environment', width: { ideal: 640 }, height: { ideal: 480 } }
        });
        if (videoRef.current) {
          videoRef.current.srcObject = stream;
          videoRef.current.setAttribute("playsinline", true); // iOS 호환
          videoRef.current.play().catch(e => console.warn("Video play interrupted", e));
          animationFrameId = requestAnimationFrame(tick);
        }
      } catch (err) {
        console.error("Camera access error:", err);
        if (err.message === "SECURE_CONTEXT_ERROR") {
          setScanStatus('secure-error');
        } else {
          setScanStatus('error');
        }
        setStreamError(true);
      }
    }

    function tick() {
      if (videoRef.current && videoRef.current.readyState === videoRef.current.HAVE_ENOUGH_DATA) {
        const video = videoRef.current;
        const canvas = canvasRef.current;
        if (canvas) {
          const ctx = canvas.getContext('2d');
          canvas.width = video.videoWidth;
          canvas.height = video.videoHeight;
          ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
          
          const imageData = ctx.getImageData(0, 0, canvas.width, canvas.height);
          const code = jsQR(imageData.data, imageData.width, imageData.height, {
            inversionAttempts: "dontInvert",
          });

          if (code) {
            console.log("QR Code found:", code.data);
            handleQRScanSuccess(code.data);
            stopCamera();
            return;
          }
        }
      }
      animationFrameId = requestAnimationFrame(tick);
    }

    if (source !== 'laptop') {
      stopCamera();
      return;
    }

    startCamera();

    return () => {
      stopCamera();
    };
  }, [source, retryKey]);

  const scanLineStyle = `
    @keyframes scan-line {
      0% { top: 5% }
      50% { top: 95% }
      100% { top: 5% }
    }
  `;

  return (
    <div style={{ display: 'grid', gridTemplateColumns: '1fr 360px', gap: 18, alignItems: 'start' }}>
      <style>{scanLineStyle}</style>
      
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
            {source === 'robot'
              ? <Badge tone="green" dot={false}>로봇 추종 카메라</Badge>
              : <Badge tone="blue" dot={false}>QR 인증 카메라</Badge>}
          </h3>
          <button onClick={handleRetry} className="ctl-btn" style={{ width: 'auto', padding: '6px 12px', fontSize: 12, display: 'flex', alignItems: 'center', gap: 6 }}>
            <Icon name="refresh-cw" size={13} />
            새로고침
          </button>
        </div>

        <div style={{ position: 'relative', width: '100%', aspectRatio: '4/3', background: '#090a0f', display: 'flex', justifyContent: 'center', alignItems: 'center', overflow: 'hidden' }}>
          {source === 'robot' ? (
            !streamError ? (
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
                  로봇(라파)의 카메라 노드가 켜져 있는지 확인해 주세요.<br />(web_stream :8090)
                </div>
                <button onClick={handleRetry} className="ctl-btn" style={{ width: 'auto', padding: '8px 16px', marginTop: 8 }}>
                  재연결 시도
                </button>
              </div>
            )
          ) : (
            <div style={{ width: '100%', height: '100%', position: 'relative', display: 'flex', justifyContent: 'center', alignItems: 'center' }}>
              {scanStatus === 'error' || scanStatus === 'secure-error' ? (
                <div style={{ color: 'var(--red)', textAlign: 'center', padding: 20 }}>
                  <div style={{ width: 54, height: 54, borderRadius: 50, background: 'rgba(229, 72, 77, 0.1)', display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--red)', margin: '0 auto 12px' }}>
                    <Icon name="video-off" size={24} />
                  </div>
                  <div style={{ fontWeight: 700 }}>카메라를 시작할 수 없습니다</div>
                  <div style={{ fontSize: 12, color: 'var(--text-3)', marginTop: 4, lineHeight: '18px' }}>
                    {scanStatus === 'secure-error' ? (
                      <>
                        보안 접속(HTTPS) 환경이 아니어서 카메라 접근이 차단되었습니다.<br />
                        스마트폰/노트북 브라우저에서 아래 설정을 완료해 주세요:<br />
                        <strong>chrome://flags/#unsafely-treat-insecure-origin-as-secure</strong><br />
                        위 주소에서 <code>http://192.168.0.29:5173</code>을 추가하고 활성화해 주세요.
                      </>
                    ) : (
                      <>
                        브라우저의 카메라 사용 권한을 허용해 주시거나,<br />
                        웹캠 장치가 정상적으로 연결되어 있는지 확인해 주세요.
                      </>
                    )}
                  </div>
                </div>
              ) : scanStatus === 'success' ? (
                <div style={{ color: 'var(--green)', textAlign: 'center', padding: 20 }}>
                  <div style={{ width: 54, height: 54, borderRadius: 50, background: 'rgba(53, 194, 160, 0.1)', display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--green)', margin: '0 auto 12px' }}>
                    <Icon name="check" size={24} />
                  </div>
                  <div style={{ fontWeight: 700, fontSize: 15 }}>QR 스캔 완료!</div>
                  <div style={{ fontSize: 12, color: 'var(--text-3)', marginTop: 4 }}>
                    인증 데이터를 처리 중입니다...
                  </div>
                </div>
              ) : (
                <>
                  <video
                    ref={videoRef}
                    style={{ width: '100%', height: '100%', objectFit: 'cover' }}
                    muted
                  />
                  <div style={{
                    position: 'absolute',
                    top: 0, left: 0, right: 0, bottom: 0,
                    border: '40px solid rgba(0, 0, 0, 0.5)',
                    display: 'flex',
                    flexDirection: 'column',
                    justifyContent: 'center',
                    alignItems: 'center',
                    pointerEvents: 'none'
                  }}>
                    <div style={{
                      width: '200px',
                      height: '200px',
                      border: '3px solid var(--amber)',
                      boxShadow: '0 0 15px rgba(248, 192, 56, 0.4)',
                      borderRadius: '8px',
                      position: 'relative'
                    }}>
                      <div style={{
                        position: 'absolute',
                        width: '100%',
                        height: '2px',
                        background: 'var(--amber)',
                        boxShadow: '0 0 8px var(--amber)',
                        top: '50%',
                        animation: 'scan-line 2s infinite ease-in-out'
                      }} />
                    </div>
                    <div style={{ color: '#fff', fontSize: 12.5, fontWeight: 700, marginTop: 16, background: 'rgba(0,0,0,0.7)', padding: '6px 12px', borderRadius: '4px' }}>
                      여기에 유저 앱의 QR 코드를 비춰주세요
                    </div>
                  </div>
                </>
              )}
              <canvas ref={canvasRef} style={{ display: 'none' }} />
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
              <dt style={{ fontSize: 11.5, color: 'var(--text-3)', fontWeight: 600, marginBottom: 6, textTransform: 'uppercase' }}>
                매칭 고객 {shopping && <Badge tone="green">쇼핑중</Badge>}
              </dt>
              <dd style={{ margin: 0 }}>
                {session && session.user && session.user.name ? (
                  <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                    <Avatar name={session.user.name} size={28} />
                    <div style={{ display: 'flex', flexDirection: 'column' }}>
                      <span style={{ fontSize: 13, fontWeight: 700, color: 'var(--text)' }}>{session.user.name}</span>
                      <span className="mono" style={{ fontSize: 11, color: 'var(--text-3)' }}>
                        QR 인증 · {session.updatedAt ? new Date(session.updatedAt).toLocaleTimeString('ko-KR') : '세션 유지중'}
                      </span>
                    </div>
                  </div>
                ) : (
                  <span style={{ fontSize: 13, color: 'var(--text-3)', fontWeight: 500 }}>
                    {session && session.status === 'RETURNING'
                      ? '결제 완료 — 카트 복귀중입니다.'
                      : 'QR 인증 대기중 — 모바일 QR을 카메라에 보여주세요.'}
                  </span>
                )}
              </dd>
            </div>

            <div style={{ height: '1px', background: 'var(--border)', margin: '4px 0' }} />

            {/* 담은 물품 — RFID 스캔 실시간 연동 */}
            <div>
              <dt style={{ fontSize: 11.5, color: 'var(--text-3)', fontWeight: 600, marginBottom: 6, textTransform: 'uppercase' }}>
                담은 물품 <span className="mono">{items.reduce((s, it) => s + (it.qty || 0), 0)}개</span>
              </dt>
              <dd style={{ margin: 0 }}>
                {items.length > 0 ? (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                    {items.map((it, i) => (
                      <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 12.5 }}>
                        <Icon name="package" size={13} style={{ color: 'var(--text-3)' }} />
                        <span style={{ flex: 1, fontWeight: 600, color: 'var(--text)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                          {it.name}
                          {session && session.lastScanned === it.name && (
                            <Badge tone="blue" dot={false}>방금 스캔</Badge>
                          )}
                        </span>
                        <span className="mono" style={{ color: 'var(--text-3)' }}>×{it.qty}</span>
                        <span className="mono" style={{ fontWeight: 600, color: 'var(--text-2)' }}>{won((it.price || 0) * (it.qty || 0))}</span>
                      </div>
                    ))}
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: 6, padding: '10px 12px', background: 'var(--surface-2)', border: '1px solid var(--border)', borderRadius: 8 }}>
                      <span style={{ fontSize: 12, color: 'var(--text-2)', fontWeight: 600 }}>예상 결제 금액</span>
                      <span style={{ fontSize: 15, fontWeight: 700 }}>{won(session ? session.totalAmount : 0)}</span>
                    </div>
                  </div>
                ) : (
                  <span style={{ fontSize: 13, color: 'var(--text-3)', fontWeight: 500 }}>
                    {shopping ? 'RFID 상품 스캔을 기다리는 중입니다.' : '아직 담은 물품이 없습니다.'}
                  </span>
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

            {shopping && (
              <>
                <div style={{ height: '1px', background: 'var(--border)', margin: '8px 0 4px' }} />
                <button
                  onClick={handleResetSession}
                  className="ctl-btn"
                  style={{
                    width: '100%',
                    background: 'rgba(229, 72, 77, 0.1)',
                    color: 'var(--red)',
                    border: '1px solid rgba(229, 72, 77, 0.2)',
                    padding: '8px 12px',
                    borderRadius: 8,
                    fontWeight: 600,
                    cursor: 'pointer',
                    fontSize: 12.5,
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    gap: 6,
                    marginTop: 8
                  }}
                >
                  <Icon name="log-out" size={14} />
                  세션 강제 종료 (초기화)
                </button>
              </>
            )}
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
