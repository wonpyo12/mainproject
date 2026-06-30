## ros2

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

