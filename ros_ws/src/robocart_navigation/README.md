# robocart_navigation

자율 매핑 / 자율 주행 패키지. RoboCart 시나리오의 자율매핑(지도 생성)과 wait/return 모드(저장 지도 기반 도킹 복귀)를 담당.

## 세 가지 launch

| launch | 동작 | 환경 |
|--------|------|------|
| `simulation.launch.py` | Gazebo Sim + TB4 시뮬 환경 띄움 | 시뮬 전용 |
| `autonomous_mapping.launch.py` | SLAM + 탐색 (자율매핑) | 시뮬 / 실물 공용 |
| `wait_return.launch.py` | 저장 지도 + Nav2 (도킹 복귀) | 시뮬 / 실물 공용 |

---

## A. 자율매핑

### A-1) 시뮬레이션 환경 (로봇 없이 검증)

🖥️ VM 터미널 ①
```bash
ros2 launch robocart_navigation simulation.launch.py
# 다른 월드: world:=depot 또는 world:=maze
```
Gazebo Sim (Ignition Fortress) + TurtleBot4 warehouse 월드 기동.

🖥️ VM 터미널 ②
```bash
ros2 launch robocart_navigation autonomous_mapping.launch.py use_sim_time:=true
```

> ARM64 Mac VM에서는 Gazebo Classic 부재로 **TurtleBot4 + 새 Gazebo Sim** 사용.
> SLAM 알고리즘 동일, 토픽 인터페이스(`/scan`, `/odom`, `/cmd_vel`) 동일.

### A-2) 실물 환경

🤖 RPi (VM에서 ssh로 접속)
```bash
ssh ubuntu@192.168.0.67
ros2 launch turtlebot3_bringup robot.launch.py
```

🖥️ VM 터미널 ②
```bash
export TURTLEBOT3_MODEL=burger
ros2 launch robocart_navigation autonomous_mapping.launch.py
```

### 3) 지도 저장

🖥️ VM 터미널 ③
```bash
bash $(ros2 pkg prefix robocart_navigation)/share/robocart_navigation/scripts/save_map.sh store_v1
```

띄우는 노드 3개:
1. **cartographer** — SLAM (지도 생성)
2. **nav2 navigation** — 로컬 경로 계획 + 컨트롤 (explore가 명령을 보내려면 필요)
3. **explore_lite** — 프론티어 기반 탐색 (어디로 갈지 결정)

---

## B. wait/return 자율주행

자율매핑으로 저장한 지도가 있어야 동작.

### 1) 로봇 bringup

🤖 RPi
```bash
ssh ubuntu@192.168.0.67
ros2 launch turtlebot3_bringup robot.launch.py
```

### 2) Nav2 + mode_controller 기동

🖥️ VM 터미널 ②
```bash
export TURTLEBOT3_MODEL=burger
ros2 launch robocart_navigation wait_return.launch.py \
    map:=$(ros2 pkg prefix robocart_navigation)/share/robocart_navigation/maps/store_v1/map.yaml
```

### 3) 복귀 트리거 / 취소

🖥️ VM 터미널 ③
```bash
# RFID 입금 등 결제 완료 신호 — 도킹 복귀 시작
ros2 topic pub /robocart/return std_msgs/Empty {} --once

# 복귀 도중 정지 (제자리)
ros2 topic pub /robocart/wait std_msgs/Empty {} --once

# 복귀 취소하고 추종 재개
ros2 topic pub /robocart/resume std_msgs/Empty {} --once
```

### 도킹 좌표 변경

`config/return_params.yaml`:
```yaml
mode_controller:
  ros__parameters:
    home_pose:
      x: 1.2
      y: -0.5
      yaw: 1.57
```

---

## 구성

```
launch/
  autonomous_mapping.launch.py   ─ A 모드 (cartographer + nav2 + explore_lite)
  wait_return.launch.py          ─ B 모드 (nav2_bringup + mode_controller)
config/
  explore_params.yaml             ─ 프론티어 탐색 파라미터
  return_params.yaml              ─ 복귀 좌표
robocart_navigation/
  mode_controller.py              ─ /robocart/return 수신 노드
scripts/
  save_map.sh                     ─ 지도 저장 헬퍼
maps/                              ─ 저장 지도 (`store_v1/map.pgm` 등)
```

## 토픽 정리

| 토픽 | 방향 | 메시지 | 의미 |
|------|------|--------|------|
| `/robocart/return` | sub | `std_msgs/Empty` | return 모드 진입 |
| `/robocart/wait`   | sub | `std_msgs/Empty` | 진행 중 복귀 취소 (정지) |
| `/robocart/resume` | sub | `std_msgs/Empty` | 진행 중 복귀 취소 (추종 재개) |
| `/cmd_vel` | pub (Nav2 경유) | `geometry_msgs/Twist` | 바퀴 명령 |
| `/scan`, `/odom`, `/tf` | sub | — | TB3 bringup이 발행 |

---

## 사전 설치 (VM)

🖥️ VM
```bash
sudo apt install -y \
  ros-humble-turtlebot3-cartographer \
  ros-humble-nav2-bringup \
  ros-humble-nav2-map-server \
  ros-humble-nav2-costmap-2d

# explore_lite 소스 빌드 (apt에 없음)
cd ~/turtlebot3_ws/src
git clone https://github.com/robo-friends/m-explore-ros2.git
cd ~/turtlebot3_ws
colcon build --symlink-install --packages-up-to explore_lite
source install/setup.bash
```

---

## 점검 단계

자율매핑 시작 후 다른 터미널에서:
```bash
ros2 topic hz /scan        # 9~10Hz 정상
ros2 topic hz /map         # 1Hz 내외 (cartographer 갱신)
ros2 node info /explore_node
ros2 topic echo /cmd_vel
```

wait_return 동작 확인:
```bash
ros2 action list | grep navigate_to_pose
ros2 node info /mode_controller
ros2 topic info /robocart/return
```

## 회피 경로

| 증상 | 조치 |
|------|------|
| explore가 한 곳에서 멈춤 | `progress_timeout` 줄이기 (현재 30초) |
| 좁은 통로 못 들어감 | nav2 `inflation_radius` 축소 |
| 복귀 goal 거절 | RViz로 home_pose가 지도 안쪽인지 확인 |
| 시간 부족 | teleop 매핑으로 폴백 |

## 향후 (v2)

- 시뮬레이션 통합 (ARM64 Webots/Gazebo Classic 빌드 후)
- 매핑 완료 자동 감지 → 지도 자동 저장
- 키오스크/RFID 시스템 ↔ `/robocart/return` 자동 연동
