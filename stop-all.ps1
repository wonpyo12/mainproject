# CartPilot 백엔드 전체 종료 스크립트
# 사용법: PowerShell에서  .\stop-all.ps1
# (MySQL·Redis는 켜둬도 무해해서 기본으로는 안 끕니다. 끄려면 -All)
param([switch]$All)

Write-Host "=== CartPilot 서비스 종료 ===" -ForegroundColor Cyan

# 포트 기준으로 Node(3000)/Spring(8080)/웹(5173) 프로세스 종료
foreach ($port in 3000, 8080, 5173) {
    $conns = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
    if ($conns) {
        $conns.OwningProcess | Select-Object -Unique | ForEach-Object {
            $name = (Get-Process -Id $_ -ErrorAction SilentlyContinue).ProcessName
            Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue
            Write-Host "  포트 $port ($name, PID $_) 종료" -ForegroundColor Yellow
        }
    } else {
        Write-Host "  포트 $port : 실행 중인 프로세스 없음" -ForegroundColor DarkGray
    }
}

# QR 스캐너(python) 종료 — qr_scanner_sim.py 실행 중이면
Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -like "*qr_scanner_sim*" } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force; Write-Host "  QR 스캐너 (PID $($_.ProcessId)) 종료" -ForegroundColor Yellow }

if ($All) {
    docker stop cartpilot-redis 2>$null | Out-Null; Write-Host "  Redis 컨테이너 정지" -ForegroundColor Yellow
    Stop-Service MySQL801 -ErrorAction SilentlyContinue; Write-Host "  MySQL 서비스 정지" -ForegroundColor Yellow
}

Write-Host "완료." -ForegroundColor Green
