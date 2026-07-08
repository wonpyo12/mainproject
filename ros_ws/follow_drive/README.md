# robocart — 사람 추종 스마트카트 (Raspberry Pi + ESP32 + TurtleBot3 Burger)

라즈베리파이 카메라 영상을 같은 Wi-Fi의 노트북으로 보내 OpenCV(YOLO/MediaPipe/ReID)로
등록된 사람을 인식하고, 그 결과로 두 액추에이터를 제어한다.

- **사람 인식(추적)** → TurtleBot3 바퀴(`/cmd_vel`)로 사람을 향해 회전·전진
- **사람 없음(검색)** → ESP32 서보(mg996r)로 좌우 스캔, 바퀴는 정지

> 인식/매칭 두뇌는 기존 `wonpyo12/mainproject` `ks` 브랜치의 `smart_cart_core.py`를
> **무수정 재사용**한다. 이 워크스페이스는 카메라 송출·액추에이터 분배·안전장치만 새로 짠다.

## 아키텍처

```
[Raspberry Pi  ROS_DOMAIN_ID=0]                  [Notebook  ROS2 Humble, DOMAIN_ID=0]
 /dev/video0
   └ camera_node ──/image/compressed(JPEG)─────────▶ tracker_node
                                                       ├ smart_cart_core.run_tracking()  (무수정)
 /dev/ttyUSB0 ESP32                                    │     입력=RosCamera  출력=FollowActuator
   └ esp32_motor_node ◀── /robocart/servo (String) ─── ├ FollowActuator
                                                       │     추적: /robocart/cmd_vel + servo "CENTER"
 /dev/ttyACM0 OpenCR                                   │     검색: servo "SCAN_START", cmd_vel 0
   └ turtlebot3 robot.launch.py                        └ /image/annotated (디버그)
   └ cmd_vel_relay_node ◀ /robocart/cmd_vel ─(watchdog 0.5s)─┘
        └ /cmd_vel ─▶ 바퀴 구동
```

## 토픽

| 토픽 | 타입 | 방향 | 비고 |
|---|---|---|---|
| `/image/compressed` | sensor_msgs/CompressedImage | Pi→노트북 | JPEG, BEST_EFFORT depth1 |
| `/robocart/cmd_vel` | geometry_msgs/Twist | 노트북→Pi | 추적 시 추종 명령 |
| `/cmd_vel` | geometry_msgs/Twist | Pi 내부 | relay가 중계, watchdog/상한 적용 |
| `/robocart/servo` | std_msgs/String | 노트북→Pi | `SCAN_START`/`SCAN_STOP`/`CENTER` |
| `/image/annotated` | sensor_msgs/CompressedImage | 노트북→ | 추적 화면 디버그 |

## 구성

```
test0615/
├── src/robocart_pi/         # 라즈베리파이용 패키지
│   └── robocart_pi/ camera_node.py · esp32_motor_node.py · cmd_vel_relay_node.py
│   └── launch/ pi_bringup.launch.py
├── src/robocart_tracker/    # 노트북용 패키지
│   └── robocart_tracker/ tracker_node.py · follow_actuator.py
└── firmware/esp32_scan_motor/esp32_scan_motor.ino   # ESP32 펌웨어
```

## 배선

- **카메라** → Pi `/dev/video0`
- **ESP32** → Pi USB(`/dev/ttyUSB0`). 서보 신호선 → ESP32 GPIO26, 서보 전원 외부 5V(공통 GND)
- **OpenCR(TurtleBot3)** → Pi USB(`/dev/ttyACM0`) — turtlebot3 브링업이 사용

## 1) ESP32 펌웨어 업로드

Arduino IDE에서 `firmware/esp32_scan_motor/esp32_scan_motor.ino` 열기 →
라이브러리 매니저에서 **ESP32Servo** 설치 → 보드=ESP32 선택 → 업로드 (9600bps).

## 2) 라즈베리파이 (이 머신)

```bash
cd ~/ros2_ws/test0615
colcon build --packages-select robocart_pi
source install/setup.bash
export ROS_DOMAIN_ID=0          # 노트북과 동일해야 함

# 카메라 + ESP32 + cmd_vel relay + 터틀봇 브링업 한 번에
ros2 launch robocart_pi pi_bringup.launch.py
```

개별 실행이 필요하면:
```bash
ros2 run robocart_pi camera_node
ros2 run robocart_pi esp32_motor_node --ros-args -p port:=/dev/ttyUSB0 -p baud:=9600
ros2 run robocart_pi cmd_vel_relay_node
ros2 launch turtlebot3_bringup robot.launch.py
```

## 3) 노트북

`smart_cart_core.py`, `data/`(등록 프로필), `yolov8n.pt` 를 한 폴더에 둔다
(저장소 `ros_ws/tracker/`, `OpenCV/Opencv/` 에서 복사). 의존성:
`pip install ultralytics mediapipe torch torchvision opencv-python numpy`.

```bash
source /opt/ros/humble/setup.bash
source ~/ros2_ws/test0615/install/setup.bash   # robocart_tracker 빌드한 경우
export ROS_DOMAIN_ID=0
cd <smart_cart_core.py 있는 폴더>               # core/data/yolov8n.pt 가 import path 에
ros2 run robocart_tracker tracker_node
```

> 프로필이 없으면 먼저 Windows/PC에서 등록 후 `data/` 를 복사한다.

## 단계별 검증

1. **카메라**: 노트북에서 `ros2 topic hz /image/compressed` (≈15fps), `rqt_image_view`.
2. **ESP32**: `ros2 topic pub --once /robocart/servo std_msgs/msg/String "{data: 'SCAN_START'}"`
   → 서보 좌우 스윙. `"{data: 'CENTER'}"` → 90도 복귀.
3. **바퀴+워치독 (바퀴 들고)**:
   `ros2 topic pub -r 10 /robocart/cmd_vel geometry_msgs/msg/Twist "{linear: {x: 0.1}}"`
   → 바퀴 회전, 발행 중단 0.5초 후 자동 정지(watchdog).
4. **통합**: 노트북 `tracker_node` 실행 → 사람 없을 때 서보 스캔+바퀴 정지,
   등록된 사람 인식 시 바퀴가 사람 향해 회전·전진. **반드시 바퀴를 든 상태로 먼저** 확인.

## 튜닝 파라미터 (tracker_node)

| 파라미터 | 기본 | 설명 |
|---|---|---|
| `k_rot` | 1.0 | 회전 P 게인. **회전 방향이 반대면 부호 반전**(`-1.0`) |
| `center_angle` | 90.0 | core 가 쓰는 서보 중앙각 규약과 맞출 것 |
| `forward_speed` | 0.12 | 추적 시 고정 전진 속도(m/s) |
| `max_angular` | 1.0 | 회전 상한(rad/s) |
| `deadband_deg` | 5.0 | 중앙 근처 회전 무시 폭(도) |

예: `ros2 run robocart_tracker tracker_node --ros-args -p k_rot:=-1.0 -p forward_speed:=0.1`

Pi의 `cmd_vel_relay_node` 는 `max_linear`(0.22)/`max_angular`(1.0)/`timeout`(0.5)
파라미터로 안전 상한·워치독을 강제한다.

## 안전

- 첫 통합 테스트는 **바퀴를 든 상태**로. Wi-Fi가 끊기면 0.5초 내 자동 정지.
- 속도 상한은 Pi relay에서 하드 클램프되어 노트북 버그가 있어도 폭주하지 않는다.

## 가정 / 다음 단계

- ESP32가 노트북에 연결돼 있다면 `esp32_motor_node` 를 노트북에서 실행하면 된다.
- 전진은 현재 **고정 속도**. 추후 bbox 높이로 거리를 추정해 목표거리 유지(감속/후진)하는
  거리 제어로 확장 가능(`smart_cart_core` 에서 bbox 정보 연동 필요).
