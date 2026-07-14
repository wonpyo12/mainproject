"""kiosk_speak_server — 키오스크 PC 음성 안내 수신 서버 (백엔드 담당 전달용)

로봇 CV 스크립트가 이벤트 시점("촬영을 시작합니다" 등)에 HTTP로 문장을 보내면
이 서버가 키오스크 PC 스피커로 재생한다. RPi의 pi_camera_streamer /speak와 동일 규격.

사용법 (키오스크 PC에서):
    pip install gTTS playsound==1.2.2
    python3 kiosk_speak_server.py            # 포트 5000
    python3 kiosk_speak_server.py 5001       # QR 스트리머가 5000을 쓰고 있으면 다른 포트

테스트: 브라우저에서 http://localhost:5000/speak?text=테스트

CV 쪽 연결 (VM, v4_1_5부터):
    python3 ros_person_follower_nav2_v4_1_5.py --speak-ip <키오스크IP> ...
    ※ 포트를 5000이 아닌 값으로 열었다면 CV 담당(HJ)에게 알려줄 것 (speak 포트 상수 수정 필요)
"""
import os
import sys
import time
import tempfile
import threading
import subprocess
import platform
from http.server import BaseHTTPRequestHandler, HTTPServer
from socketserver import ThreadingMixIn
from urllib.parse import urlparse, parse_qs

last_spoken = {}   # 같은 문장 5초 쿨다운 (중복 재생 방지)


def play_mp3(path):
    """OS별 재생 폴백 체인."""
    sysname = platform.system()
    try:
        from playsound import playsound
        playsound(path)
        return
    except Exception:
        pass
    if sysname == "Windows":
        os.startfile(path)                       # 기본 플레이어
        time.sleep(3)
    elif sysname == "Darwin":
        subprocess.run(["afplay", path])
    else:
        subprocess.run(["mpg123", "-q", path])


def speak(text, cooldown=5.0):
    now = time.time()
    if now - last_spoken.get(text, 0) < cooldown:
        return
    last_spoken[text] = now

    def run():
        try:
            from gtts import gTTS
            fd, tmp = tempfile.mkstemp(suffix=".mp3")
            os.close(fd)
            try:
                gTTS(text=text, lang="ko").save(tmp)
                play_mp3(tmp)
            finally:
                if os.path.exists(tmp):
                    os.remove(tmp)
        except Exception as e:
            print(f"[speak] 재생 실패: {e} — 텍스트: {text}")

    threading.Thread(target=run, daemon=True).start()


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        u = urlparse(self.path)
        if u.path == "/speak":
            text = parse_qs(u.query).get("text", [""])[0]
            if text:
                print(f"[speak] 수신: {text}")
                speak(text)
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write("OK".encode())
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, *a):
        pass


class Server(ThreadingMixIn, HTTPServer):
    daemon_threads = True


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 5000
    print(f"[kiosk_speak_server] http://0.0.0.0:{port}/speak?text=... 대기 중")
    Server(("0.0.0.0", port), Handler).serve_forever()
