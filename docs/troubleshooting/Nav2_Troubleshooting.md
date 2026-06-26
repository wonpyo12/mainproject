# [이슈 리포트] SLAM/Nav2 사람 추종 및 원점 복귀 자율주행 트러블슈팅

본 문서는 터틀봇3(Burger, ROS2 Humble)을 이용하여 사람 추종 및 원점 복귀 기능을 통합 테스트하는 과정에서 발생한 주요 문제점들과 해결책에 대해 기록한 트러블슈팅 보고서입니다.

---

## 1. 개요 및 구성 환경
* **로봇**: Turtlebot3 Burger (OpenCR + Raspberry Pi 4)
* **제어 PC**: VMware 가상머신 (Ubuntu 22.04 LTS / ROS2 Humble)
* **주요 패키지**: `nav2_bringup`, `turtlebot3_navigation2`, `turtlebot3_bringup`
* **개발 기능**: 2D 카메라 기반 YOLOv8-pose 사람 추종 모드(`FOLLOW`)와 Nav2를 통한 원점 복귀 모드(`RETURN`) 연동

---

## 2. 발생한 주요 이슈 및 트러블슈팅

### Issue 2.1: RViz 상의 Fixed Frame 설정 오류 및 지도 소실
* **현상**: RViz 설정 중 `Fixed Frame`을 `odom`으로 설정 시 지도가 보이지 않고, `map`으로 설정 시 로봇 모델이 보이지 않으며 초기 위치 지정(`2D Pose Estimate`)이 반영되지 않음.
* **원인**: 
  * 전체 TF 트리 구조(`map -> odom -> base_footprint -> base_link`)에서 `map`과 `odom` 사이의 연결고리(AMCL 위치 추정 노드)가 활성화되지 않았기 때문입니다.
  * `Fixed Frame`을 `odom`으로 변경 시, RViz가 지도의 `map` 프레임 데이터를 받지 못해 지도가 소실됩니다.
* **해결책**:
  * RViz의 `Fixed Frame`은 반드시 **`map`**으로 설정해야 합니다. (목록에 없을 시 수동 타이핑)
  * 에러가 발생하는 상태에서 상단의 **`2D Pose Estimate`** 버튼을 클릭하여 지도 상에 로봇의 실제 시작 포즈를 드래그해 지정해 주면 `map -> odom` TF가 활성화되며 모든 경고가 초록색(`Ok`)으로 복구됩니다.

![Fixed Frame odom 설정 시 에러 화면](images/media__1782451634946.png)

---

### Issue 2.2: 멀티 호스트 간 DDS 통신 차단 및 Lidar/Odom 데이터 누락
* **현상**: `ros2 topic info /initialpose` 조회 시 구독자(Subscription count)는 `1`로 잡히나, `2D Pose Estimate` 신호를 입력해도 아무런 반응이 없고 로봇이 움직이지 않음.
* **원인**: 
  * 가상머신(PC)과 라즈베리 파이(로봇)가 서로 다른 DDS 미들웨어(FastDDS vs CycloneDDS)를 사용하고 있어 데이터가 유실되었습니다.
  * 특히 가상머신과 무선 네트워크 환경에서는 기본 FastDDS가 정상적인 패킷 매칭을 해주지 못해 `/tf` 및 `/odom` 데이터가 소실되었습니다.
* **해결책**:
  * 양측 기기 모두 **CycloneDDS (`rmw_cyclonedds_cpp`)**로 미들웨어를 일치시켰습니다.
  * 라즈베리 파이(로봇)에 CycloneDDS 패키지가 설치되어 있지 않아 설치를 진행했습니다:
    ```bash
    sudo apt update
    sudo apt install ros-humble-rmw-cyclonedds-cpp
    ```
  * PC와 로봇의 모든 터미널 창에서 아래 환경변수를 선언하여 통신을 일치시켰습니다:
    ```bash
    export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp
    ```
  * 편리한 사용을 위해 양측 기기의 `~/.bashrc` 파일 하단에 위 환경변수를 추가하여 터미널 시작 시 자동 로드되도록 설정했습니다:
    ```bash
    echo "export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp" >> ~/.bashrc
    echo "export TURTLEBOT3_MODEL=burger" >> ~/.bashrc # (PC 측 추가 설정)
    source ~/.bashrc
    ```

![Initialpose 토픽 정보](images/media__1782451700035.png)
![Odom TF 프레임이 가상머신에 도달하지 못해 발생하는 오류](images/media__1782456539395.png)

---

### Issue 2.3: FastDDS 대형 액션 메시지 페이로드 크기 한계 오류
* **현상**: 추종 스크립트 실행 중 터미널에 `복귀` 명령어를 입력하자마자 아래와 같은 에러가 출력됨:
  > `[RTPS_READER_HISTORY Error] Change payload size of '32' bytes is larger than the history payload size of '19' bytes and cannot be resized. -> Function can_change_be_added_nts`
* **원인**: 
  * `NavigateToPose` 자율주행 목표(Action Goal)는 크기가 크며, 추종 노드가 실행된 터미널에 `export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp` 환경변수가 누락되어 기본 FastDDS로 동작했기 때문입니다.
* **해결책**:
  * 추종 노드를 실행하는 터미널에서도 동일하게 CycloneDDS가 선언되어 있는지 확인한 후 실행합니다. (또는 `.bashrc` 등록 후 터미널 재실행)

![라즈베리 파이 측 CycloneDDS 미설치로 인한 RMW 로드 실패 에러](images/media__1782456646393.png)

---

### Issue 2.4: 주행 중 로컬 코스트맵 및 레이저 스캔 뒤틀림 (위치 추정 손실)
* **현상**: 복귀 자율주행 시도 시 로봇이 `(0, 0)`으로 가지 못하고 엉뚱한 벽으로 돌진하거나 회전함. RViz 확인 시 레이저 점들(그린 닷)과 코스트맵이 실제 지도와 약 30도 이상 비뚤어지게 정렬되어 있음.
* **원인**:
  1. **사람 추종 시 Lidar 가림 현상**: 사람을 쫓아갈 때 대상자가 로봇과 너무 가까이(0.5m 이하) 위치하여 센서 시야의 넓은 부분을 가렸습니다. 이로 인해 AMCL이 지도와 매칭할 외곽벽을 확인하지 못해 위치 추정을 잃어버렸습니다(Kidnapped Robot).
  2. **바퀴 슬립 및 급회전**: 추종 시 급격한 회전으로 인해 바퀴가 헛돌면서(Slip) 오도메트리 누적 오차가 커졌습니다.
* **해결책**:
  1. **감도 완화 및 속도 제한**: 급회전과 슬립을 방지하도록 추종 노드(`ros_person_follower_nav2.py`)의 최고 선속도를 `0.08 m/s`, 각속도를 `0.2 rad/s`로 대폭 제한하고 민감도를 낮추었습니다.
  2. **추종 거리 유지**: 추종 시 대상자는 센서 시야 방해를 최소화하기 위해 로봇과 최소 `0.8m ~ 1.2m` 거리를 두고 이동하도록 테스트 가이드를 수립했습니다.
  3. **초기 회전 정렬**: 주행 시작 전 `2D Pose Estimate`를 찍고, **키보드 제어기(teleop)로 제자리 회전을 1~2바퀴 시켜서** 센서 라인과 벽면이 완전히 일치하는 것을 확인한 후 작동하는 절차를 준수합니다.

![자율주행 복귀 명령 및 Goal 수락 확인 로그](images/media__1782457528803.png)
![주행 중 맵 위치 손실 및 스캔 뒤틀림 현상 (Lidar 미스매칭)](images/media__1782457882748.png)

---

## 3. 관련 스크린샷 기록 (프로젝트 내 보관)
모든 관련 분석 스크린샷과 로그 이미지는 저장소 내 아래 경로에 저장되어 있습니다:
* **이미지 저장 위치**: `docs/troubleshooting/images/`

---
보고자: wonpyo12 (Google DeepMind Antigravity Pair-Programming Project)
작성일: 2026-06-26
