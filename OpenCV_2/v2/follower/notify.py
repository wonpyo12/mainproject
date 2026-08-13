"""외부 알림 — 라파/키오스크 음성(TTS), ESP8266 LED 상태."""


# ══════════════════════════════════════════════════════════════════════════════
# 등록 (앞/뒤 촬영) — VM 디스플레이(cv2.imshow)로 안내
# ══════════════════════════════════════════════════════════════════════════════

def speak_on_pi(pi_ip, text):
    if not pi_ip:
        return
    def run():
        try:
            import urllib.parse
            import urllib.request
            encoded_text = urllib.parse.quote(text)
            # [07-15 백포트] "IP" 또는 "IP:포트" 허용 — 키오스크 음성 이관용 (주행 로직 무변경)
            host = pi_ip if ":" in str(pi_ip) else f"{pi_ip}:5000"
            url = f"http://{host}/speak?text={encoded_text}"
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=1.5) as response:
                pass
        except Exception as e:
            print(f"[speak_on_pi] 소리 출력 실패: {e}")
            
    import threading
    threading.Thread(target=run, daemon=True).start()


last_led_status = None

def set_robot_led(esp_ip, status, blocking=False):
    global last_led_status
    if not esp_ip or status == last_led_status:
        return
    last_led_status = status
    print(f"[set_robot_led] 아두이노({esp_ip})로 LED 상태 변경 전송: {status}")
    
    def run():
        try:
            import urllib.request
            import urllib.parse
            url = f"http://{esp_ip}/led?status={status}"
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=1.5) as response:
                pass
        except Exception as e:
            print(f"[set_robot_led] LED 제어 실패 ({status}): {e}")
            
    if blocking:
        run()
    else:
        import threading
        threading.Thread(target=run, daemon=True).start()


