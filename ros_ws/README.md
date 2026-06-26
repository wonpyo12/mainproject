# ros_ws — ROS2 기반 사용자 추종

카메라 영상을 ROS2 토픽으로 받아 노트북(OpenCV)에서 사용자를 인식하고,
구동 명령을 다시 ROS2로 보내 모터를 움직이는 시스템입니다.

전체 설계는 [ros2_tracking_plan.md](ros2_tracking_plan.md) 참고.

## 현재 단계

로봇(카트)이 아직 없으므로 **노트북 단독으로 전체 파이프라인을 검증**한 상태입니다.
Windows에 물린 웹캠·ESP32(MG996R 서보)가 로봇 역할을 대행합니다.

```
[Windows]                         [WSL2 - Ubuntu 22.04 + ROS2 Humble]
  웹캠 ──┐                          ┌→ /image/compressed ─→ tracker_node
         ├─ win_cam_servo_bridge ─TCP─ cam_bridge_node       (사람 인식·매칭)
  ESP32 ─┘   (하드웨어 브리지)       └← /servo_cmd ←──────────────┘
    │                                        ↑
  MG996R 서보                      유실 시 "S"(스캔), 추적 중 "A각도"
```

- 등록된 사용자를 **녹색 박스로 추적**하며 서보가 카메라를 사용자 쪽으로 회전
- 사용자가 사라지면 약 2초 후 **서보가 좌우 스캔하며 재탐색**
- 추적 결과 화면은 `/image/annotated` 토픽으로 돌아와 **Windows 창에 표시** (WSLg 불필요)
- 로봇이 준비되면 브리지 부분만 로봇의 실제 카메라/모터 노드로 교체 (토픽 인터페이스 동일)

## 폴더 구성

| 경로 | 실행 위치 | 내용 |
|---|---|---|
| [ros2_tracking_plan.md](ros2_tracking_plan.md) | - | 전체 설계·구현 순서·진행 현황 |
| [comm_test/cmd_loop_node.py](comm_test/cmd_loop_node.py) | WSL | 통신 검증용 미니 노드 (영상 구독→`/cmd_vel` 발행) |
| [bridge/cam_bridge_node.py](bridge/cam_bridge_node.py) | WSL | TCP ↔ ROS2 토픽 변환 노드 |
| [bridge/win_cam_servo_bridge.py](bridge/win_cam_servo_bridge.py) | Windows | 웹캠 캡처·서보 시리얼·결과 화면 표시 |
| [tracker/tracker_node.py](tracker/tracker_node.py) | WSL | 추적 노드 — 인식 코어를 ROS2에 연결 |
| [tracker/smart_cart_core.py](tracker/smart_cart_core.py) | WSL | 인식 코어 (YOLO+MediaPipe+ReID, **무수정 재사용**) |

`tracker_node.py`는 코어의 카메라 입력(`open_camera`)과 화면 출력(`cv2.imshow`),
서보 출력만 ROS2 토픽으로 갈아끼웁니다. 인식 로직은 한 줄도 수정하지 않았습니다.

## 토픽

| 토픽 | 타입 | 방향 | 내용 |
|---|---|---|---|
| `/image/compressed` | CompressedImage | 카메라 → 추적 | JPEG 영상 (640×480, 20fps) |
| `/image/annotated` | CompressedImage | 추적 → 표시 | 인식 결과 화면 (최대 15fps) |
| `/servo_cmd` | String | 추적 → 서보 | `A각도`(이동)/`S`(스캔)/`H`(정지)/`C`(중앙) |
| `/servo_state` | String | 서보 → 추적 | `P각도` 현재 각도 보고 |

## 환경 준비 (1회)

- WSL2 **Ubuntu-22.04** + ROS2 **Humble** (`ros-humble-ros-base`, `demo-nodes`, `image-tools`)
- WSL에 pip로: `opencv-python mediapipe torch torchvision ultralytics pyserial` (torch는 CPU판)
- WSL에 apt로: `libgl1 libgles2 libegl1` (mediapipe 구동용)
- ESP32에는 `Arduino/camera_servo/camera_servo.ino`(A/S/H/C 프로토콜, 115200bps) 업로드
  - 이 파일은 sh 업데이트로 삭제됨 — `git show 8fcdf13:Arduino/camera_servo/camera_servo.ino` 로 복원
- `tracker/` 폴더에 필요 (git 미포함, 직접 복사):
  - `yolov8n.pt` ← `OpenCV/Opencv/yolov8n.pt`
  - `data/pose_landmarker_lite.task` ← `OpenCV/Opencv/robocart/data/`
  - `data/smart_cart_profile.json` ← 사용자 등록 프로필 (Windows 버전으로 등록한 것 재사용)

## 실행 방법 (터미널 3개)

```bash
# ① WSL — 카메라 브리지 노드
wsl -d Ubuntu-22.04
source /opt/ros/humble/setup.bash
cd /mnt/d/YH/ros_ws/bridge
python3 cam_bridge_node.py

# ② WSL — 추적 노드 (모델 로드 약 30초)
wsl -d Ubuntu-22.04
source /opt/ros/humble/setup.bash
cd /mnt/d/YH/ros_ws/tracker
python3 tracker_node.py
```

```powershell
# ③ Windows PowerShell — 하드웨어 브리지 (실행하면 추적 창이 뜸)
cd d:\YH\ros_ws\bridge
d:\YH\OpenCV\smart_cart\.venv\Scripts\python.exe win_cam_servo_bridge.py
```

종료: ③의 추적 창에서 **ESC**

토픽 흐름 확인 (선택):
```bash
ros2 topic echo /servo_cmd    # 유실 시 S, 추적 시 A각도가 찍힘
ros2 topic hz /image/compressed
```

⚠️ Arduino IDE 시리얼 모니터가 열려 있으면 ③이 서보 연결에 실패합니다 (영상은 동작).

## 검증 완료 항목

| 항목 | 결과 |
|---|---|
| ROS2 노드 간 pub/sub (talker↔listener) | ✅ |
| 영상 토픽 스트리밍 30fps | ✅ |
| 영상 구독→계산→`/cmd_vel` 발행 루프 | ✅ |
| 실카메라 영상 → ROS2 → 사용자 인식 → `/servo_cmd` → ESP32 서보 | ✅ |

## 다음 단계 (로봇 도착 후)

1. 두 기기 간 DDS 통신 (`ROS_DOMAIN_ID` 통일, Win11 `.wslconfig`에 `networkingMode=mirrored`)
2. 로봇 카메라 노드(`v4l2_camera`)로 `/image/compressed` 대체
3. `/cmd_vel` 기반 차체 구동 motor_node 작성 (워치독 0.5초 필수)
4. 차체 회전 탐색 + 게인 튜닝

---

## TurtleBot3 ROS2 환경 설정 및 빌드

```bash
#작업 공간 생성
mkdir -p ~/robot_ws/src
cd ~/robot_ws/src
```

```bash
#소스코드 다운
git clone -b humble https://github.com/ROBOTIS-GIT/turtlebot3.git
```

```bash
# 의존성 설치 및 빌드
cd ~/robot_ws
rosdep install --from-paths src --ignore-src -r -y
colcon build --symlink-install
```

```bash
# 빌드 환경 적용
source ~/robot_ws/install/setup.bash
echo 'source ~/robot_ws/install/setup.bash' >> ~/.bashrc
```

```bash
# 하드웨어 환경 변수 설정

# 1. 터틀봇 모델을 'burger'로 지정
echo 'export TURTLEBOT3_MODEL=burger' >> ~/.bashrc

# 2. 신형 라이다(LDS-02 / 기판명 LDS08) 드라이버 강제 지정 (에러 방지 핵심 🚨)
echo 'export LDS_MODEL=LDS-02' >> ~/.bashrc

# 3. 변경된 설정 즉시 반영
source ~/.bashrc
```

```bash
# 통신 권한 설정
sudo chmod 777 /dev/ttyACM* /dev/ttyUSB*
```

```bash
# 실행
ros2 launch turtlebot3_bringup robot.launch.py

# 토픽 확인
ros2 topic list

# 하나의 토픽 값만 확인
ros2 topic echo /scan
```

