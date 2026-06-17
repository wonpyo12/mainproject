# robocart_follower — 사람 추종 ROS2 패키지

## 실행 명령어 (Quick Start)

### 1. VM에 의존성 설치 (한 번만)
```bash
pip install ultralytics opencv-python numpy pyserial
python3 -c "from ultralytics import YOLO; YOLO('yolov8n.pt')"   # 모델 다운로드(7MB)
```

### 2. 빌드 (RPi4와 VM 양쪽)
```bash
cd ~/ros_ws
colcon build --packages-select robocart_follower
source install/setup.bash
```

### 3. 실행

**RPi4 터미널 ①** — 카메라 + 모터 노드
```bash
ros2 launch robocart_follower robot.launch.py
```

**VM 터미널 ②** — YOLO 추론 노드 (등록/추종)
```bash
ros2 launch robocart_follower remote.launch.py
```

**VM 터미널 ③** — RViz 시각화
```bash
rviz2 -d ~/ros_ws/install/robocart_follower/share/robocart_follower/config/follower.rviz
```

---

## 노드 구성

| 노드 | 위치 | 역할 |
|------|------|------|
| `camera_node`    | RPi4 | USB 웹캠 → `/robocart/image_raw/compressed` 발행 (멀티스레드 30fps) |
| `inference_node` | VM   | 이미지 구독 → YOLOv8n + 매칭 → 소켓으로 모터 명령 송신 |
| `motor_node`     | RPi4 | TCP 9999 수신 → ESP32 시리얼 변환 (`A<각도>` / `S` / `H` / `C`) |

---

## 통신 구조

```
[RPi4 camera_node]
      ↓  ROS 토픽 (압축 JPEG)
[VM inference_node] ──→ YOLO + 매칭
      ↓  TCP 소켓 (JSON)
[RPi4 motor_node]
      ↓  USB 시리얼
[ESP32 + MG996R 서보]
```

영상은 ROS 토픽으로, 모터 명령은 소켓으로 보낸다.

---

## 사람 등록 방법

### 자동 등록 (셀프서비스, 기본)
`inference_node` 시작 시 등록 정보가 없으면 자동으로 **카운트다운**(기본 5초)이 시작된다.

1. 카메라 정면에 들어가 자세를 잡는다.
2. 오버레이 영상에 `REG IN 5s` → `4s` → `3s` ... 카운트다운 표시.
3. 0초 도달 시 가장 큰 사람을 자동 등록 → 추종 모드 전환.
4. 카운트다운 시점에 사람이 없으면 `WAITING FOR PERSON` 표시, 보이는 첫 프레임에 등록.

카운트다운 시간 조정: `follower_params.yaml` 의 `auto_register_sec` (기본 5.0, 0 = 비활성).

### 수동 등록 (즉시)
```bash
ros2 topic pub /robocart/register std_msgs/Empty "{}" --once
```
→ 다음 프레임의 가장 큰 사람을 즉시 등록. 자동 등록 타이머를 무시한다.

### 등록 정보 초기화 (새 사람 다시 등록)
```bash
ros2 topic pub /robocart/reset std_msgs/Empty "{}" --once
```

특징(가중치 합 1.0):
- HSV 색상 (상/하의)  60%
- 머리 영역 색상      20%
- bbox 가로/세로 비율 10%
- 위치 연속성         10%

매칭 임계값(`features.py`):
- `MATCH_THRESHOLD = 0.72` — 잠금 시작
- `KEEP_THRESHOLD  = 0.60` — 잠금 유지

---

## 점검 단계

### VM에서 (로봇 없이도 가능)
```bash
# YOLO 점검
python3 -c "from ultralytics import YOLO; m=YOLO('yolov8n.pt'); print('OK')"

# features.py 자체 테스트
python3 -m robocart_follower.features
```

### 통합 (로봇 사용 가능 시)
```bash
# 토픽 목록 (RPi4 카메라 노드가 살아있는지)
ros2 topic list | grep robocart

# 발행 주기 확인
ros2 topic hz /robocart/image_raw/compressed

# 소켓 dry-run으로 추론만 테스트 (모터 끄고)
# follower_params.yaml 에서 dry_run_socket: true 로
```

---

## 트러블슈팅

| 증상 | 원인 | 해결 |
|------|------|------|
| 웹캠 안 열림 | `/dev/video0` 권한 | `sudo usermod -aG video $USER` 후 재로그인 |
| 시리얼 안 열림 | `/dev/ttyUSB0` 권한 | `sudo usermod -aG dialout $USER` 후 재로그인 |
| 영상이 끊김 | 무선 대역폭 부족 | `jpeg_quality` 50 으로 ↓ |
| 모터 떨림 | gain 과다 | `motor_node` 의 `gain` 0.3 으로 ↓ |
| 사람 못 잡음 | 임계값 과다 | `MATCH_THRESHOLD` 0.65 로 ↓ |
| YOLO 느림 | CPU 부하 | VM 에 CPU 코어 늘리기, 또는 `conf_threshold` ↑ |
