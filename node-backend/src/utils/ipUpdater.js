const fs = require('fs');
const path = require('path');

/**
 * .env 파일의 BACKEND_IP 값을 읽어 다른 클라이언트 파일들의 IP 설정을 자동 동기화합니다.
 */
function updateProjectIPs() {
  const backendIp = process.env.BACKEND_IP;
  if (!backendIp) {
    console.log('[IP Updater] BACKEND_IP가 env에 정의되지 않아 IP 동기화를 건너뜁니다.');
    return;
  }

  console.log(`[IP Updater] 프로젝트 백엔드 IP 설정을 [ ${backendIp} ] 로 동기화 중...`);

  // 1. Arduino (RFIDADDproduct.ino)
  const arduinoPath = path.join(__dirname, '../../../Arduino/RFIDADDproduct/RFIDADDproduct.ino');
  if (fs.existsSync(arduinoPath)) {
    try {
      let content = fs.readFileSync(arduinoPath, 'utf8');
      // const char* serverURL = "http://<IP>:3000/api/hardware/rfid"; 패턴 매칭
      const regex = /const char\* serverURL = "http:\/\/([^:]+):3000\/api\/hardware\/rfid";/;
      if (regex.test(content)) {
        content = content.replace(regex, `const char* serverURL = "http://${backendIp}:3000/api/hardware/rfid";`);
        fs.writeFileSync(arduinoPath, content, 'utf8');
        console.log(`[IP Updater] 아두이노 파일 업데이트 성공: ${path.basename(arduinoPath)}`);
      } else {
        console.warn('[IP Updater] 아두이노 파일 내 serverURL 패턴을 찾지 못했습니다.');
      }
    } catch (err) {
      console.error('[IP Updater] 아두이노 파일 수정 중 오류:', err.message);
    }
  } else {
    console.warn(`[IP Updater] 아두이노 파일 없음: ${arduinoPath}`);
  }

  // 2. Android App (RetrofitClient.kt)
  const androidPath = path.join(__dirname, '../../../app/android-handoff/app/src/main/java/com/example/network/RetrofitClient.kt');
  if (fs.existsSync(androidPath)) {
    try {
      let content = fs.readFileSync(androidPath, 'utf8');
      // const val BASE_URL = "http://<IP>:3000/" 패턴 매칭
      const regex = /const val BASE_URL = "http:\/\/([^:]+):3000\/";?/;
      if (regex.test(content)) {
        content = content.replace(regex, `const val BASE_URL = "http://${backendIp}:3000/"`);
        fs.writeFileSync(androidPath, content, 'utf8');
        console.log(`[IP Updater] 안드로이드 파일 업데이트 성공: ${path.basename(androidPath)}`);
      } else {
        console.warn('[IP Updater] 안드로이드 파일 내 BASE_URL 패턴을 찾지 못했습니다.');
      }
    } catch (err) {
      console.error('[IP Updater] 안드로이드 파일 수정 중 오류:', err.message);
    }
  } else {
    console.warn(`[IP Updater] 안드로이드 파일 없음: ${androidPath}`);
  }

  // 3. Web Frontend 파일들
  const webFiles = [
    '../../../web/src/api.js',
    '../../../web/src/App.jsx',
    '../../../web/src/hooks/useRobotPose.js',
    '../../../web/src/hooks/useRobotSession.js',
    '../../../web/src/views/InquiriesView.jsx',
    '../../../web/src/views/InventoryView.jsx',
    '../../../web/src/views/MembersView.jsx',
    '../../../web/src/views/ProductRegisterModal.jsx',
  ];

  let webUpdatedCount = 0;
  for (const relPath of webFiles) {
    const filePath = path.join(__dirname, relPath);
    if (fs.existsSync(filePath)) {
      try {
        let content = fs.readFileSync(filePath, 'utf8');
        // const BACKEND_URL = 'http://<IP>:3000'; 패턴 매칭
        const regex = /const BACKEND_URL = 'http:\/\/([^:]+):3000';?/;
        const newContent = content.replace(regex, `const BACKEND_URL = 'http://${backendIp}:3000';`);
        if (newContent !== content) {
          fs.writeFileSync(filePath, newContent, 'utf8');
          webUpdatedCount++;
        }
      } catch (err) {
        console.error(`[IP Updater] 웹 파일(${path.basename(filePath)}) 수정 중 오류:`, err.message);
      }
    }
  }
  // 4. ROS2 Pose Bridge (pose_bridge.py)
  const poseBridgePath = path.join(__dirname, '../../../ros_ws/bridge/pose_bridge.py');
  if (fs.existsSync(poseBridgePath)) {
    try {
      let content = fs.readFileSync(poseBridgePath, 'utf8');
      const regex = /self.declare_parameter\("backend_url", "http:\/\/([^:]+):3000"\)/;
      if (regex.test(content)) {
        content = content.replace(regex, `self.declare_parameter("backend_url", "http://${backendIp}:3000")`);
        fs.writeFileSync(poseBridgePath, content, 'utf8');
        console.log(`[IP Updater] pose_bridge.py 업데이트 성공`);
      }
    } catch (err) {
      console.error('[IP Updater] pose_bridge.py 수정 중 오류:', err.message);
    }
  }

  // 5. QR Scanner Sim (qr_scanner_sim.py)
  const qrSimPath = path.join(__dirname, '../../../qr/qr_scanner_sim.py');
  if (fs.existsSync(qrSimPath)) {
    try {
      let content = fs.readFileSync(qrSimPath, 'utf8');
      const regex = /SERVER_URL = "http:\/\/([^:]+):3000\/api\/hardware\/qr-scan"/;
      if (regex.test(content)) {
        content = content.replace(regex, `SERVER_URL = "http://${backendIp}:3000/api/hardware/qr-scan"`);
        fs.writeFileSync(qrSimPath, content, 'utf8');
        console.log(`[IP Updater] qr_scanner_sim.py 업데이트 성공`);
      }
    } catch (err) {
      console.error('[IP Updater] qr_scanner_sim.py 수정 중 오류:', err.message);
    }
  }

  console.log(`[IP Updater] 웹 프론트엔드 파일 업데이트 성공 (${webUpdatedCount}개 파일 완료)`);
}

module.exports = updateProjectIPs;
