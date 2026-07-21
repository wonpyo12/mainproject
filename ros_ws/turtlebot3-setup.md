# TurtleBot3 Burger — ROS2 Humble 셋업 및 운용 기록

> 담당: HJ · 기간: 2026-06-10 ~ 06-12
> 구성: Raspberry Pi 4 (로봇) + Ubuntu 22.04 VM (Remote PC) + ROS2 Humble

---

## 실행 명령어 (Quick Start)

### 기동 순서
1. 핫스팟 ON (zeeneePhone)
2. 로봇 전원 ON — 핫스팟에 자동 접속됨 (172.20.10.3)
3. VM 부팅 (VMware Fusion, Bridged 네트워크)

### 로봇 Bringup — VM 터미널 ①
```bash
ssh ubuntu@172.20.10.3
ros2 launch turtlebot3_bringup robot.launch.py
```
정상 기동 로그: `LDS-02 started successfully`

### SLAM — VM 터미널 ②
```bash
export TURTLEBOT3_MODEL=burger
ros2 launch turtlebot3_cartographer cartographer.launch.py
```

### 수동 조종 — VM 터미널 ③
```bash
export TURTLEBOT3_MODEL=burger
ros2 run turtlebot3_teleop teleop_keyboard
```

### 지도 저장 — VM 터미널 ④
```bash
ros2 run nav2_map_server map_saver_cli -f ~/map
```

### 종료 순서
teleop 정지(`s`) → 지도 저장 확인 → cartographer 종료 → bringup 종료 → 로봇 `sudo poweroff` → 배터리 분리

---

## 시스템 구성

```
📱 핫스팟 (zeeneePhone)
 ├─ 로봇: TurtleBot3 Burger — RPi4(SSD 부팅) + OpenCR + LDS-02 라이다
 │        172.20.10.3 / Ubuntu 22.04 / Humble
 └─ Mac — VM(VMware Fusion, Bridged): 172.20.10.4 / Ubuntu 22.04 / Humble
          RViz2 · cartographer · teleop 실행
```

| 항목 | 값 |
|------|-----|
| ROS_DOMAIN_ID | 30 (전 기기 공통) |
| 라이다 | LDS-02 — `LDS_MODEL=LDS-02` 필수 |
| /scan 수신율 | 10.4 Hz (무선) |
| 로봇 Wi-Fi 정책 | 핫스팟 우선(priority 100), 사무실망 폴백, 절전 OFF |

---

## 진행 기록

| 날짜 | 내용 |
|------|------|
| 06-10 | ODROID C4 + Foxy 환경에서 초기 셋업. RViz 라이다 미표시 문제 발생 |
| 06-11 | ODROID 하드웨어 이슈로 **RPi4 + Ubuntu 22.04 + Humble로 플랫폼 전환** 결정. Mac VM 구축 및 Humble 설치 완료 |
| 06-12 | PC Setup 완료 → 실물 Bringup 성공 → RViz2 라이다 시각화 → 핫스팟 무선화 → **SLAM 실행 성공** |

---

## 주요 이슈 및 해결

### 1. RViz에 라이다(/scan) 데이터 미표시 — 근본 원인: 라이다 모델 불일치
- 보유 라이다는 **LDS-02**인데 `LDS_MODEL` 미설정 시 bringup이 **LDS-01용 드라이버(hlds)** 를 실행함
- 드라이버가 포트는 열지만 프로토콜 불일치로 데이터가 발행되지 않음 → 토픽은 존재하나 echo 무반응
- **해결**: `export LDS_MODEL=LDS-02` (bashrc 등록)

### 2. VM 부팅 화면 "EFI stub" 정지
- 화면 출력만 멈춘 것이며 OS는 정상 부팅 상태 (IP 할당으로 확인)
- 원인: 22.04 기본 커널(5.15)이 Apple Silicon용 VMware 가상 GPU 미지원
- **해결**: HWE 커널 설치 — `sudo apt install linux-generic-hwe-22.04`

### 3. Bringup 실패 (Failed to open port)
- 원인: 시리얼 포트 접근 권한 부재
- **해결**: `sudo usermod -aG dialout <계정>` 후 **재로그인 필수**

### 4. 핫스팟 환경에서 Mac ↔ 로봇 직접 통신 불가
- 통신사(KT) IPv6 전용 + CLAT 환경에서 Mac이 IPv4를 받지 못함
- **해결**: VM은 브리지로 자체 IPv4(172.20.10.4)를 받으므로 **로봇 제어는 VM 경유**로 일원화

### 5. 로봇 Wi-Fi 설정이 적용되지 않음
- 해당 RPi는 netplan-networkd가 아닌 **NetworkManager** 관리 환경
- **해결**: `nmcli`로 프로파일 생성, `autoconnect-priority 100` 지정

---

## 다음 단계

- [ ] SLAM 지도 저장 (`~/map.pgm/.yaml`) 및 저장소 반영
- [ ] Navigation2 — 저장 지도 기반 자율주행
- [ ] RoboCart 앱/백엔드 ↔ ROS2 연동
