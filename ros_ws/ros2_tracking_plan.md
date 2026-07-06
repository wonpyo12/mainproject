# ROS2 기반 사용자 추종 구동 기획서

## 개요

지금까지는 **노트북에 직접 연결된 카메라**로 사용자를 추적하고 서보(카메라 pan)만 움직였다.
이번 단계는 카메라와 모터를 **로봇(카트) 쪽 ROS2**로 옮기고, 노트북은 **영상 수신 → OpenCV 계산 → 구동 명령 회신**만 담당한다.

```
[로봇(카트)]                                   [노트북]
 카메라 ──→ 카메라 노드 ──/camera/image_raw/compressed──→ 추적 노드 (robocart 로직 재사용)
                              (Wi-Fi, ROS2 DDS)              │ 사람 인식 + 본인 매칭
 모터 ←── 모터 노드 ←──────────/cmd_vel───────────────────────┘ 화면 오프셋 → 회전/전진 명령
```

- 영상은 로봇 → 노트북, 구동 명령(`cmd_vel`)은 노트북 → 로봇
- 양쪽이 **같은 Wi-Fi + 같은 `ROS_DOMAIN_ID`** 면 DDS가 자동으로 서로를 발견 (브로커/IP 설정 불필요)

---

## 역할 분담

| 위치 | 노드 | 하는 일 |
|---|---|---|
| 로봇 (라즈베리파이 등 SBC) | `camera_node` | USB 카메라 캡처 → JPEG 압축 영상 발행 (기성 패키지 사용, 코드 작성 없음) |
| 로봇 | `motor_node` | `/cmd_vel` 구독 → 모터 드라이버 PWM (또는 시리얼로 ESP32 전달) |
| 노트북 | `tracker_node` | 영상 구독 → 디코딩 → **robocart_main.py의 인식/매칭 로직 그대로 호출** → `/cmd_vel` 발행 |

핵심: OpenCV 계산 코드는 새로 짜지 않는다. `robocart_main.py`에서 카메라 입력부(`cv2.VideoCapture`)와
출력부(화면 표시)만 ROS2 토픽으로 바꿔 끼우는 구조.

---

## 토픽 설계

| 토픽 | 타입 | 방향 | 비고 |
|---|---|---|---|
| `/camera/image_raw/compressed` | `sensor_msgs/CompressedImage` | 로봇→노트북 | JPEG, 640×480, 15fps (Wi-Fi 대역폭 ≈ 1~2MB/s) |
| `/cmd_vel` | `geometry_msgs/Twist` | 노트북→로봇 | `angular.z` 회전, `linear.x` 전진/정지 |
| `/robocart/status` | `std_msgs/String` | 노트북→로봇 | `tracking` / `searching` / `idle` (디버그·LED 표시용, 선택) |

- **Raw 영상 금지**: 640×480 raw는 약 13MB/s라 Wi-Fi에서 끊긴다. 반드시 `compressed` 사용
- 영상 QoS: `best_effort`, `depth=1` — 늦은 프레임은 버리고 항상 최신 프레임만 처리 (지연 누적 방지)

---

## 제어 로직 (tracker_node)

기존 추적 상태(`tracking` / `searching`)를 그대로 쓰되, 서보 각도 대신 차체 구동 명령으로 변환:

```python
# tracking 상태: P제어
err_x = (bbox_center_x - frame_w/2) / (frame_w/2)   # -1 ~ +1
twist.angular.z = -K_ROT * err_x                     # 사용자가 오른쪽이면 우회전

dist = K_DIST / bbox_height                          # 박스 높이로 거리 추정
twist.linear.x = clamp(K_FWD * (dist - TARGET_DIST), 0, MAX_SPEED)
# 목표 거리(예: 1.2m)보다 멀면 전진, 가까우면 정지

# searching 상태: 제자리 회전 탐색 (서보 스캔의 차체 버전)
twist.angular.z = SEARCH_SPIN   # 천천히 한 방향 회전
twist.linear.x  = 0.0
```

### 안전장치 (필수)

| 항목 | 내용 |
|---|---|
| 워치독 | motor_node에서 `/cmd_vel`이 **0.5초간 안 오면 즉시 정지** (Wi-Fi 끊김 대비) |
| 속도 상한 | `linear.x ≤ 0.5 m/s`, `angular.z ≤ 1.0 rad/s` 하드코딩 |
| 근접 정지 | bbox 높이가 화면의 80% 이상(너무 가까움)이면 무조건 정지 |

---

## 노트북 ROS2 실행 환경 (Windows 노트북 기준)

**확정: WSL2 + Ubuntu 22.04 + ROS2 Humble**

- 노트북 내부 검증 완료 (아래 진행 현황 참고)
- 로봇과의 통신(다른 PC와 DDS)을 위해서는 Win11 `.wslconfig`에 `networkingMode=mirrored` 설정 필요
- mirrored 모드가 안 되는 환경이면 차선책으로 `rosbridge_suite`(웹소켓) 우회 가능

로봇 쪽도 **ROS2 Humble (Ubuntu 22.04)** 로 통일.

### 진행 현황 (노트북 단독 검증, 로봇 도착 전)

| 검증 항목 | 결과 |
|---|---|
| 노드 간 pub/sub (talker↔listener) | ✅ 정상 수신 |
| 영상 토픽 스트리밍 (`image_tools` 테스트 패턴) | ✅ 30fps 안정 |
| 영상 구독 → 계산 → `/cmd_vel` 발행 루프 ([comm_test/cmd_loop_node.py](comm_test/cmd_loop_node.py)) | ✅ Twist 명령 수신 확인 |

남은 것: 로봇 도착 후 **두 기기 간 DDS 통신**(구현 순서 1단계의 크로스 머신 부분)부터 재개.

---

## 구현 순서 (단계마다 검증 후 다음 진행)

1. **통신 검증** — 양쪽에 ROS2 설치, 같은 `ROS_DOMAIN_ID` 설정 후
   `ros2 run demo_nodes_cpp talker` (로봇) ↔ `listener` (노트북) 확인
2. **영상 전송** — 로봇에서 `v4l2_camera` 또는 `usb_cam` 실행 →
   노트북 `rqt_image_view`로 영상·fps·지연 확인 (목표: 15fps, 지연 0.3초 이내)
3. **추적 노드 포팅** — `robocart_main.py`를 rclpy 노드로 감싸기
   (입력: image callback / 출력: `/cmd_vel` 발행 + 디버그 화면은 그대로 imshow)
   → 이 단계에서는 모터 없이 **`/cmd_vel` 값만 `ros2 topic echo`로 확인**
4. **모터 연동** — motor_node 작성 (`/cmd_vel` → 모터 드라이버), 워치독 포함.
   바퀴를 띄운 상태에서 먼저 확인 후 지상 주행
5. **탐색·튜닝** — 유실 시 제자리 회전 탐색 확인, `K_ROT`/`K_FWD`/`TARGET_DIST` 튜닝

---

## 예상 이슈

- **처리 속도**: 노트북 CPU에서 YOLO+mediapipe가 15fps를 못 따라가면 프레임 스킵 (`depth=1` QoS로 자동 해결)
- **Wi-Fi 끊김**: 워치독으로 정지. 공유기와 거리가 멀면 5GHz 대역 사용
- **카메라 pan 서보와의 관계**: 차체가 직접 회전하므로 1차 구현에서는 서보 고정(정면).
  이후 "차체는 천천히, 서보는 빠르게" 2단 추적으로 확장 가능
- **시간 동기화 불필요**: 프레임 타임스탬프는 참고용일 뿐, 제어는 최신 프레임 기준

---

## 이 계획서의 결정 필요 사항 (팀 확인)

1. 로봇 쪽 보드가 무엇인지 (라즈베리파이4/5? Jetson?) → ROS2 설치 방법 결정
2. 구동 모터/드라이버 종류 (DC모터+L298N? 모터 직결 ESP32?) → motor_node 출력 방식 결정
3. ROS2 배포판 통일 (Humble 권장 — Ubuntu 22.04 LTS)
