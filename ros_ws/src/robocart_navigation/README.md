# robocart_navigation

자율 매핑 / 네비게이션 패키지. 사람 조작 없이 로봇이 알아서 돌아다니며 SLAM 지도를 생성한다.

## 실행 명령어

### 1) 로봇 bringup (라파에서 ssh로)
```bash
ssh ubuntu@192.168.0.67
ros2 launch turtlebot3_bringup robot.launch.py
```

### 2) 자율 매핑 (VM에서)
```bash
export TURTLEBOT3_MODEL=burger
ros2 launch robocart_navigation autonomous_mapping.launch.py
```

### 3) 지도 저장 (매핑 완료 후 VM에서)
```bash
# 라벨 자동 (타임스탬프)
bash $(ros2 pkg prefix robocart_navigation)/share/robocart_navigation/scripts/save_map.sh

# 라벨 지정
bash $(ros2 pkg prefix robocart_navigation)/share/robocart_navigation/scripts/save_map.sh store_v1
```

## 구성

```
launch/autonomous_mapping.launch.py   ─┐
config/explore_params.yaml             │  3개 노드를 한 번에 띄움
scripts/save_map.sh                    │
maps/                                  └─ 저장된 지도 (gitignore 권장)
```

`autonomous_mapping.launch.py` 가 띄우는 노드 3개:
1. **cartographer** — SLAM (지도 생성)
2. **nav2 navigation** — 로컬 경로 계획 + 컨트롤 (explore가 명령을 보내려면 필요)
3. **explore_lite** — 프론티어 기반 탐색 (어디로 갈지 결정)

## 사전 설치 (VM)

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
colcon build --symlink-install --packages-select explore_lite
source install/setup.bash
```

## 점검 단계

매핑 시작 후 다른 터미널에서:

```bash
# 1) 토픽 들어오는지
ros2 topic hz /scan        # 9~10Hz 정상
ros2 topic hz /map         # 1Hz 내외 (cartographer 갱신)

# 2) explore 노드 동작 확인
ros2 node info /explore_node
ros2 topic echo /cmd_vel   # 자동으로 명령 발행되는지

# 3) RViz로 시각화
rviz2 -d $(ros2 pkg prefix turtlebot3_cartographer)/share/turtlebot3_cartographer/rviz/tb3_cartographer.rviz
```

## 회피 경로

| 증상 | 조치 |
|------|------|
| explore가 한 곳에서 멈춤 | `progress_timeout` 줄이기 (현재 30초) |
| 좁은 통로 못 들어감 | nav2 `inflation_radius` 축소 |
| 시간 부족 | teleop 매핑으로 폴백 |

## 향후 (자율매핑 v2)

- 시뮬레이션 통합 (ARM64 Webots/Gazebo Classic 빌드 후)
- 매핑 완료 자동 감지 → 지도 자동 저장
- Nav2 자율주행 (저장 지도 기반 wait/return 모드)
