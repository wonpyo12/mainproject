# ros_ws — SmartCart 분산 처리 실행 스크립트

VMware(노트북)와 RPi4(로봇 탑재)가 ROS2 DDS로 통신하는 분산 구조의 실행 파일 모음.

```
[VMware] robocart_main.py ──ROS2 /robocart/image_raw──▶ 인식 처리
                           ──ROS2 /robocart/cmd       ──▶ [RPi4] raspi_cmd_bridge_esp32.py ──시리얼──▶ ESP32
[RPi4]   C920 카메라 ──────────────────────────────────▶ raspi_camera_launch.sh (ROS2 토픽)
                                                          raspi_mjpeg_launch.sh  (HTTP, 대안)
```

---

## 실행 순서 (분산 모드)

### RPi4 — 터미널 1: 카메라 영상 송출

**방법 A — ROS2 토픽 (기본)**
```bash
bash raspi_camera_launch.sh
# 발행 토픽: /robocart/image_raw/compressed
```

**방법 B — HTTP MJPEG (WiFi 불안정·CPU 포화 시 대안)**
```bash
bash raspi_mjpeg_launch.sh
# 스트림: http://<RPI_IP>:8090/stream
```

### RPi4 — 터미널 2: 모터 명령 수신 (ESP32 연결)
```bash
bash raspi_cmd_bridge_esp32.sh                     # 기본 포트 /dev/ttyUSB0
bash raspi_cmd_bridge_esp32.sh --port /dev/ttyACM0  # ESP32가 ACM 포트일 때
# 구독 토픽: /robocart/cmd → USB 시리얼 → ESP32
```

### VMware — 터미널 1: 인식 노드 실행
```bash
bash vmware_run.sh             # 일반 실행
bash vmware_run.sh --register  # 사용자 등록 모드
bash vmware_run.sh --reset     # 등록 초기화
# 방법 B 사용 시: robocart_main.py --mjpeg http://<RPI_IP>:8090/stream 직접 실행
```

---

## 파일 목록

### RPi4 실행 파일

| 파일 | 역할 |
|------|------|
| `raspi_camera_launch.sh` | C920 카메라 영상을 ROS2 토픽으로 발행 (usb_cam 패키지) |
| `raspi_mjpeg_launch.sh` | C920 영상을 HTTP MJPEG으로 패스스루 송출 (ffmpeg, ROS2 불필요) |
| `raspi_mjpeg_server.py` | `raspi_mjpeg_launch.sh`의 실제 서버 본체 (CPU 부하 없음) |
| `raspi_cmd_bridge_esp32.sh` | `raspi_cmd_bridge_esp32.py` 실행 래퍼 (ROS2 환경 설정 포함) |
| `raspi_cmd_bridge_esp32.py` | ROS2 `/robocart/cmd` 구독 → ESP32 USB 시리얼 전달 브리지 노드 |

### VMware 실행 파일

| 파일 | 역할 |
|------|------|
| `vmware_run.sh` | ROS2 환경 설정 후 `robocart_main.py --ros2` 실행 |

### DDS 설정 (멀티캐스트 불가 환경 전용)

| 파일 | 역할 |
|------|------|
| `fastdds_raspi.xml` | RPi4 유니캐스트 디스커버리 프로파일 |
| `fastdds_vmware.xml` | VMware 유니캐스트 디스커버리 프로파일 |

> 같은 서브넷 WiFi 환경에서는 기본 멀티캐스트로 자동 연결됨.  
> 연결 안 될 때만 두 파일의 IP 수정 후 `USE_FASTDDS_UNICAST=1` 환경변수로 실행.

### 디버그

| 파일 | 역할 |
|------|------|
| `web_camera_view.py` | ROS2 토픽 구독 → MJPEG HTTP 스트리밍 (VMware에서 imshow 검은 창 회피용) |

---

## ROS2 토픽 요약

| 토픽 | 방향 | 내용 |
|------|------|------|
| `/robocart/image_raw/compressed` | RPi4 → VMware | C920 카메라 영상 (MJPEG) |
| `/robocart/cmd` | VMware → RPi4 | 모터 제어 명령 |

- `ROS_DOMAIN_ID=42` (RPi4·VMware 동일하게 설정)
