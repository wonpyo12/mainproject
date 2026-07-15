# CartPilot 백엔드 전체 시작 스크립트
# 사용법: PowerShell에서  .\start-all.ps1
# Node/Spring/웹은 각각 새 창으로 뜨므로 로그를 창별로 볼 수 있습니다.

Write-Host "=== CartPilot 서비스 시작 ===" -ForegroundColor Cyan

# 1. MySQL 서비스
if ((Get-Service MySQL801).Status -ne 'Running') {
    Start-Service MySQL801; Write-Host "  MySQL 시작" -ForegroundColor Yellow
} else { Write-Host "  MySQL 이미 실행 중" -ForegroundColor DarkGray }

# 2. Redis (docker)
$redis = docker ps --filter "name=cartpilot-redis" --format "{{.Names}}"
if (-not $redis) {
    docker start cartpilot-redis | Out-Null; Write-Host "  Redis 시작" -ForegroundColor Yellow
} else { Write-Host "  Redis 이미 실행 중" -ForegroundColor DarkGray }

# 3. Node 백엔드 (3000) — 시작 시 ipUpdater가 .env의 BACKEND_IP로 IP 자동 동기화
if (-not (Get-NetTCPConnection -LocalPort 3000 -State Listen -ErrorAction SilentlyContinue)) {
    Start-Process powershell -ArgumentList "-NoExit","-Command","cd d:\YH\node-backend; npm start"
    Write-Host "  Node 백엔드 시작 (새 창)" -ForegroundColor Yellow
} else { Write-Host "  Node(3000) 이미 실행 중" -ForegroundColor DarkGray }

# 4. Spring 백엔드 (8080)
if (-not (Get-NetTCPConnection -LocalPort 8080 -State Listen -ErrorAction SilentlyContinue)) {
    Start-Process powershell -ArgumentList "-NoExit","-Command","cd d:\YH\backend; .\gradlew.bat bootRun"
    Write-Host "  Spring 백엔드 시작 (새 창)" -ForegroundColor Yellow
} else { Write-Host "  Spring(8080) 이미 실행 중" -ForegroundColor DarkGray }

# 5. 웹 (5173)
if (-not (Get-NetTCPConnection -LocalPort 5173 -State Listen -ErrorAction SilentlyContinue)) {
    Start-Process powershell -ArgumentList "-NoExit","-Command","cd d:\YH\web; npm run dev"
    Write-Host "  웹 dev 서버 시작 (새 창)" -ForegroundColor Yellow
} else { Write-Host "  웹(5173) 이미 실행 중" -ForegroundColor DarkGray }

Write-Host "완료. 웹: http://localhost:5173" -ForegroundColor Green
