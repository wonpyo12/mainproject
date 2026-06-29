# 터틀봇3 사람 추종 및 원점 복귀 자율주행 실행 가이드

본 가이드는 실제 터틀봇3(Burger)과 가상머신(PC) 환경에서 2D 카메라 스트리밍 + YOLOv8 사람 추종 + Nav2 원점 복귀 기능을 통합 실행하는 순서와 명령어를 정리한 문서입니다.

---

## 0. 사전 설정 (최초 1회만 수행)
양측 기기 간 멀티캐스트 및 통신 안정성을 위해 **CycloneDDS** 환경변수를 각 기기의 터미널 설정 파일(`.bashrc`)에 등록해야 합니다.

### ① 가상머신(PC) 설정(무조건 하세요)
가상머신 터미널을 열고 아래 명령어를 순서대로 실행합니다:
```bash
echo "export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp" >> ~/.bashrc
echo "export TURTLEBOT3_MODEL=burger" >> ~/.bashrc
source ~/.bashrc
```

### ② 라즈베리 파이(로봇 본체) 설정
라즈베리 파이 터미널을 열고 아래 명령어를 순서대로 실행합니다 (CycloneDDS 미설치 시 설치 병행):
```bash
# CycloneDDS 통신 라이브러리 설치
sudo apt update
sudo apt install ros-humble-rmw-cyclonedds-cpp

# 환경변수 등록(이건 했음)
echo "export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp" >> ~/.bashrc
source ~/.bashrc
```

---

## 1. 실행 프로세스 (기기 기동 및 구동 순서)

반드시 아래에 명시된 **순서대로** 기기를 구동해 주세요.

### [Step 1] 로봇 본체(라즈베리 파이) 구동
로봇 전원을 켜고 라즈베리 파이에 SSH 등으로 접속한 후, 아래 노드들을 각각의 터미널 창에 실행합니다.

* **터미널 1 (모터 및 라이다 구동)**:
  ```bash
  ros2 launch turtlebot3_bringup robot.launch.py
  ```
* **터미널 2 (C920 카메라 스트리밍 서버 가동)**:
  ```bash
  # 프로젝트의 ros_ws 폴더에 있는 pi_camera_streamer.py 실행
  python3 ~/ros_ws/pi_camera_streamer.py
  ```

---

### [Step 2] 가상머신(PC) 네비게이션 구동
가상머신(Ubuntu)에서 터미널을 열어 아래 가이드에 따라 실행합니다.

* **터미널 1 (Nav2 네비게이션 스택 실행)**:
  * 맵 파일 위치를 지정하며, 실기를 사용하므로 **`use_sim_time:=false`**를 꼭 붙여줍니다.
  ```bash
  ros2 launch turtlebot3_navigation2 navigation2.launch.py map:=/mnt/hgfs/mainproject/ros_ws/classroom_v3.yaml use_sim_time:=false
  ```
* **터미널 2 (RViz 시각화 툴 구동)**:
  ```bash
  rviz2
  ```

#### 🚨 중요: RViz 기동 후 초기 위치 지정 (AMCL 정렬)
1. RViz의 `Fixed Frame`이 **`map`**으로 되어 있는지 확인합니다.
2. RViz 상단의 **`2D Pose Estimate`** 버튼(초록색 화살표 모양)을 클릭합니다.
3. 지도 상에서 로봇이 현재 실제로 서 있는 위치를 클릭한 상태로, **로봇 앞방향(카메라 장착 방향)과 일치하도록 마우스를 드래그**하여 화살표를 그린 뒤 놓습니다.
4. 위치 매칭 오류를 완벽히 막기 위해, 별도의 터미널 창을 열고 **키보드 조종기(`ros2 run turtlebot3_teleop teleop_keyboard`)를 켜서 로봇을 좌우로 천천히 회전**시켜 줍니다. 레이저 센서(그린 닷)가 지도 벽선에 완전히 달라붙는 것을 확인하면 준비 완료입니다.

---

### [Step 3] 가상머신(PC) 사람 추종 및 복귀 노드 가동
* **터미널 3 (하이브리드 제어 파이썬 스크립트 실행)**:
  ```bash
  python3 /mnt/hgfs/mainproject/opencv/ros_person_follower_nav2.py
  ```

---

## 2. 테스트 및 제어 명령 요령

추종 노드가 가동되면 실시간 카메라 영상 창과 함께 터미널 창에 제어 모드가 대기 상태가 됩니다.

* **사람 추종 (`FOLLOW` 모드 - 기본값)**:
  * 로봇 전면에 서서 사람이 인식되면, 안전거리와 중심각도를 자동으로 계산해 로봇이 사람을 따라가기 시작합니다.
  * **안정적인 주행 팁**: Lidar 센서 가림 현상을 방지하기 위해 로봇과 항상 **`0.8m ~ 1.2m` 의 적정 거리를 두고** 이동해 주세요.
* **원점 복귀 (`RETURN` 모드)**:
  * 스크립트 터미널 창에 **`복귀`**라고 입력하고 엔터를 누르면 모드가 전환됩니다.
  * 추종 제어를 즉시 중단하고 Nav2 네비게이션이 활성화되어 지도 기준 `(0.0, 0.0)` 위치로 장애물을 피해 스스로 복귀를 시작합니다.
* **추종 모드로 복귀**:
  * 복귀 주행 중 다시 사람을 따라오게 하려면 터미널에 **`추종`**을 입력하고 엔터를 치면 복귀 동작이 취소되고 추종 모드로 들어갑니다.
  * 원점에 도착을 완료하면 자동으로 추종 모드로 전환됩니다.
* **종료**:
  * 비디오 창에서 **`q`**를 누르거나 터미널 창에서 **`Ctrl + C`**를 누르면 안전하게 정지합니다.

---

## 3. 문제 해결 자가 진단 명령어

작동 중 문제가 발생하면 새 터미널 창에 아래 진단 명령어들을 실행하여 체크해 보세요.

* **라이다 데이터 수신 확인 (VM)**:
  `ros2 topic echo /scan --max-count 1` (출력 없이 먹통인 경우 통신 차단 상태)
* **오도메트리 데이터 수신 확인 (VM)**:
  `ros2 topic echo /odom --max-count 1`
* **위치 정보 노드(AMCL) 활성화 확인**:
  `ros2 lifecycle get /amcl` (정상 시 `active [3]` 출력)
* **오도메트리 좌표 연결 상태 확인 (로봇 $\rightarrow$ 바디)**:
  `ros2 run tf2_ros tf2_echo odom base_footprint`

## 4. 실행순서
1. 라즈베리파이에 pi_camera_streamer.py 실행(mainproject/opencv에 위치)
2. 라즈베리에서 robot.launch 파일 실행
3. 가상머신에서 ros2 launch turtlebot3_navigation2 navigation2.launch.py map:=/mnt/hgfs/mainproject/ros_ws/classroom_v3.yaml use_sim_time:=false (rviz 맵가지고오는 것)
4. 가상머신에서 mainproject/opencv/ros_person_follower_nav2.py 실행(사람추종 및 원점복귀하는 것)
