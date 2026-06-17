#!/bin/bash

# TurtleBot3 Wi-Fi 설정 스크립트
# 용도: 핫스팟에서 5층 고정망으로 전환
# 사용: ssh ubuntu@<로봇_IP> < setup_wifi.sh
#       또는 로봇에서 직접 실행

set -e

echo "🔧 TurtleBot3 Wi-Fi 설정 시작"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# 설정값 (수정 필요)
HOTSPOT_PROFILE="zeeneePhone"
WIFI_SSID="${1:-}"
WIFI_PASSWORD="${2:-}"

# 입력값 확인
if [ -z "$WIFI_SSID" ] || [ -z "$WIFI_PASSWORD" ]; then
    echo "❌ 오류: Wi-Fi SSID와 비밀번호를 입력하세요"
    echo ""
    echo "사용법:"
    echo "  $0 '<5층_SSID>' '<비밀번호>'"
    echo ""
    echo "예시:"
    echo "  $0 'RoboCart-5F' 'password123'"
    exit 1
fi

# 1. 기존 핫스팟 프로파일 삭제
echo "1️⃣ 기존 핫스팟 프로파일 삭제..."
if nmcli con show "$HOTSPOT_PROFILE" &>/dev/null; then
    sudo nmcli con delete "$HOTSPOT_PROFILE"
    echo "   ✓ '$HOTSPOT_PROFILE' 삭제 완료"
else
    echo "   ✓ '$HOTSPOT_PROFILE' 미존재 (스킵)"
fi

# 2. 5층 Wi-Fi 프로파일 추가
echo ""
echo "2️⃣ 5층 Wi-Fi 프로파일 등록 중..."
PROFILE_NAME="5F-WiFi"

# 기존 프로파일이 있으면 삭제
if nmcli con show "$PROFILE_NAME" &>/dev/null; then
    sudo nmcli con delete "$PROFILE_NAME"
    echo "   ✓ 기존 '$PROFILE_NAME' 삭제"
fi

# 새 Wi-Fi 연결 생성
sudo nmcli con add \
    type wifi \
    ifname wlan0 \
    con-name "$PROFILE_NAME" \
    ssid "$WIFI_SSID" \
    -- \
    wifi-sec.key-mgmt wpa-psk \
    wifi-sec.psk "$WIFI_PASSWORD"

echo "   ✓ '$WIFI_SSID' 프로파일 등록 완료"

# 3. 우선순위 설정 (자동 연결 활성화, 높은 우선순위)
echo ""
echo "3️⃣ 자동 연결 우선순위 설정 중..."
sudo nmcli con modify "$PROFILE_NAME" \
    connection.autoconnect yes \
    connection.autoconnect-priority 100

echo "   ✓ 우선순위 100 설정 완료"

# 4. 현재 연결 상태 확인
echo ""
echo "4️⃣ 설정 확인..."
echo ""
echo "📡 등록된 Wi-Fi 연결:"
nmcli con show --active | grep -E "wifi|ethernet" || echo "   (활성 연결 없음)"

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ Wi-Fi 설정 완료!"
echo ""
echo "📝 다음 단계:"
echo "  1. 로봇 재부팅: sudo reboot"
echo "  2. 재부팅 후 IP 확인: ip addr show wlan0"
echo "  3. 5층 와이파이 IP 대역 연결 확인"
