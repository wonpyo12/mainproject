#!/usr/bin/env python3
"""
[Windows] WSL 없이 라파를 직접 제어하는 SSH 헬퍼 (paramiko).

WSL mirrored 네트워킹이 불안정해 SSH 가 끊길 때, Windows 네트워킹으로 직접 접속.

사용:
  python pi_ssh.py "<원격 명령>"
  python pi_ssh.py --restart-cam      # 카메라+web_stream 작은 설정으로 재시작
  python pi_ssh.py --status           # 노드 상태
"""
import os
import sys
import paramiko

PI = os.environ.get("PI_HOST", "YOUR_PI_IP")
USER = os.environ.get("PI_USER", "ubuntu")
PW = os.environ.get("PI_PASSWORD", "YOUR_PI_PASSWORD")

SETUP = "source /opt/ros/humble/setup.bash; source ~/ros2_ws/test0615/install/setup.bash; export ROS_DOMAIN_ID=30"


def run(cmd, timeout=40):
    cli = paramiko.SSHClient()
    cli.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    cli.connect(PI, username=USER, password=PW, timeout=15,
                banner_timeout=15, auth_timeout=15)
    _, out, err = cli.exec_command(cmd, timeout=timeout)
    o = out.read().decode(errors="ignore")
    e = err.read().decode(errors="ignore")
    cli.close()
    return o, e


RESTART_CAM = f"""
for p in $(pgrep -f 'robocart_pi camera_node'); do kill -9 $p 2>/dev/null; done
for p in $(pgrep -f web_stream_node); do kill -9 $p 2>/dev/null; done
sleep 3
setsid bash -c "{SETUP}; exec ros2 run robocart_pi camera_node --ros-args -p width:=416 -p height:=240 -p jpeg_quality:=35 -p fps:=12.0" > /tmp/cam.log 2>&1 < /dev/null &
setsid bash -c "{SETUP}; exec python3 /tmp/web_stream_node.py --ros-args -p topic:=/image/compressed" > /tmp/web.log 2>&1 < /dev/null &
sleep 8
echo "cam:$(pgrep -f 'robocart_pi camera_node'|grep -v bash|wc -l) web:$(pgrep -f web_stream_node|grep -v bash|wc -l)"
echo "web:$(curl -s --max-time 3 -o /dev/null -w '%{{http_code}}' http://localhost:8090/snapshot)"
"""

STATUS = ("echo cam:$(pgrep -f 'robocart_pi camera_node'|grep -v bash|wc -l) "
          "web:$(pgrep -f web_stream_node|grep -v bash|wc -l) "
          "cmd:$(pgrep -f cmd_server|grep -v bash|wc -l) "
          "esp:$(pgrep -f esp32_motor|grep -v bash|wc -l)")

# 모든 중복 정리 → 카메라(작게)/web/cmd/esp 각 1개만
CLEAN = f"""
for pat in 'robocart_pi camera_node' web_stream_node cmd_server esp32_motor; do
  for p in $(pgrep -f "$pat"); do kill -9 $p 2>/dev/null; done
done
sleep 3
S() {{ setsid bash -c "{SETUP}; exec $1" > /tmp/$2.log 2>&1 < /dev/null & disown; }}
S "ros2 run robocart_pi camera_node --ros-args -p width:=416 -p height:=240 -p jpeg_quality:=35 -p fps:=12.0" cam
S "python3 /tmp/web_stream_node.py --ros-args -p topic:=/image/compressed" web
S "python3 /tmp/cmd_server.py" cmdsrv
S "ros2 run robocart_pi esp32_motor_node --ros-args -p port:=/dev/ttyUSB0 -p baud:=9600" esp32
sleep 9
echo "cam:$(pgrep -f 'robocart_pi camera_node'|grep -v bash|wc -l) web:$(pgrep -f web_stream_node|grep -v bash|wc -l) cmd:$(pgrep -f cmd_server|grep -v bash|wc -l) esp:$(pgrep -f esp32_motor|grep -v bash|wc -l)"
echo "web_http:$(curl -s --max-time 3 -o /dev/null -w '%{{http_code}}' http://localhost:8090/snapshot)"
echo "esp_log:$(cat /tmp/esp32.log 2>/dev/null | tr -cd '[:print:]\\n' | grep -aiE 'ESP32|SIM' | head -1)"
"""


def clean_restart():
    """중복 정리 → 1개씩 재시작 (단순 명령 여러 번 — paramiko 안정)."""
    import time
    # 넓은 패턴으로 launcher+실제 노드 모두 종료 (ros2 run 노드는 실행파일명만 가짐)
    for pat in ["camera_node", "web_stream_node", "cmd_server", "esp32_motor_node"]:
        run(f"pkill -9 -f {pat}", timeout=15)
    time.sleep(3)
    starts = {
        "cam": "ros2 run robocart_pi camera_node --ros-args -p width:=416 -p height:=240 -p jpeg_quality:=35 -p fps:=12.0",
        "web": "python3 /tmp/web_stream_node.py --ros-args -p topic:=/image/compressed",
        "cmdsrv": "python3 /tmp/cmd_server.py",
        "esp32": "ros2 run robocart_pi esp32_motor_node --ros-args -p port:=/dev/ttyUSB0 -p baud:=9600",
    }
    for tag, c in starts.items():
        run(f"setsid bash -c '{SETUP}; exec {c}' > /tmp/{tag}.log 2>&1 < /dev/null & disown; sleep 0.3", timeout=15)
    time.sleep(9)
    o, _ = run(STATUS)
    print(o.strip())
    o, _ = run("curl -s --max-time 3 -o /dev/null -w 'web_http:%{http_code}\\n' http://localhost:8090/snapshot")
    print(o.strip())
    o, _ = run("cat /tmp/esp32.log 2>/dev/null | grep -aiE 'ESP32|SIM' | head -1")
    print("esp:", o.strip()[:80])


if __name__ == "__main__":
    arg = sys.argv[1] if len(sys.argv) > 1 else "--status"
    try:
        if arg == "--clean":
            clean_restart()
        else:
            cmd = {"--status": STATUS}.get(arg, arg)
            o, e = run(cmd)
            print(o.strip())
            if e.strip():
                print("[stderr]", e.strip()[:300])
    except Exception as ex:
        print("[SSH 실패]", ex)
        sys.exit(1)
