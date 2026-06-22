# 스마트 장바구니 바퀴 추종 제어 기획서 (TurtleBot3 Burger)

## 1. 개요

[robocart.md](robocart.md)에서 구현한 **등록 사용자 인식**(ReID 기반, 완료)을 입력으로,
**TurtleBot3 Burger**의 바퀴를 움직여 사용자를 일정 거리에서 따라가는 기능을 단계적으로 구현한다.

진행 순서: **사용자 인식(완료) → 일정 거리 유지 → 사용자 추종**

> 이번 문서 범위에서 **유실 시 카메라 모터 재탐색(pan 서보) 기능은 제외**한다.
> 바퀴 제어는 카메라 모터 제어 파일(raspi_cmd_bridge.py 등)을 건드리지 않고
> **새 파일([wheel_control.py](wheel_control.py))로 분리**해 구현한다.

## 2. 하드웨어 / 통신 전제

- 로봇: **TurtleBot3 Burger** (차동구동 2륜 + OpenCR + 라즈베리파이)
- 주행 명령: ROS2 표준 **`/cmd_vel` (geometry_msgs/Twist)**
  - `linear.x` = 전후진 선속도(m/s), `angular.z` = 회전 각속도(rad/s)
- 모터 구동은 **TurtleBot3 표준 스택(turtlebot3_bringup)**이 `/cmd_vel`을 구독해 처리.
  → 별도 모터 드라이버/시리얼 코드 없이 `/cmd_vel`만 발행하면 된다.
- Burger 속도 한계: 선속도 0.22 m/s, 각속도 2.84 rad/s (코드에서 더 보수적으로 운용)

## 3. 전체 구조

```text
[robocart_main.py 인식]
   draw_bbox(추적 박스) + is_tracking
        ↓  (--follow 시 매 프레임 호출)
[wheel_control.py / WheelFollower]
   거리 추정 + 좌우 편차 → (선속도 v, 각속도 w)
        ↓  ROS2 /cmd_vel (Twist)
[turtlebot3_bringup] → OpenCR → 바퀴
```

- 카메라 pan 서보(`/robocart/cmd`, ESP32, [scan_motor_plan.md](scan_motor_plan.md))와는 **완전히 별개 경로.**

## 4. 거리 추정 (센서 없이 단일 카메라)

깊이 센서 없이, **bbox 높이(픽셀) 비율을 거리의 역지표**로 사용한다.

- `height_ratio = bbox높이 / 화면높이`
- 목표값 `TARGET_HEIGHT_RATIO`(예 0.55)보다 작으면(=멀리, 작게 보임) → 전진
- 크면(=가까이) → 정지 (1차엔 후진 금지)
- 오차가 `HEIGHT_DEADBAND` 이내면 정지 (떨림 방지)

정확도는 낮지만(키·자세 영향) 1차 구현으로 충분. 추후 LDS(라이다)·거리 센서로 보강 검토.

## 5. 추종 제어 로직 (1차, P 제어)

- **전후진(linear.x)**: `err = TARGET_HEIGHT_RATIO − height_ratio` → `v = KP_LIN·err` (상한 클램프)
- **회전(angular.z)**: `err_c = (bbox중심x − 화면중심x)/(화면폭/2)` → `w = −KP_ANG·err_c` (상한 클램프)
  - 대상이 우측(+)이면 시계방향(z 음수)으로 회전해 중앙 정렬
- 두 출력을 Twist로 합쳐 발행 → TurtleBot3가 좌/우 바퀴 속도로 변환
- 진동/오버슈트 시 D항 추가 검토(추후 단계)

## 6. 안전 설계

- **미추적/유실 시 즉시 정지** (`is_tracking=False` → v=w=0) — 추종보다 항상 우선
- 운용 속도 상한(`MAX_LIN`, `MAX_ANG`)을 Burger 하드 한계보다 낮게
- 1차엔 후진 금지(`ALLOW_REVERSE=False`) — 너무 가까우면 정지만
- 프로그램 종료 시 반드시 정지 명령 발행

## 7. 단계별 개발 계획 (하나씩 추가)

### ✅ Phase 0. 인식 (완료)
- robocart_main.py 의 `TrackingState` + `draw_bbox`를 추종 입력으로 사용.

### ▶ Phase 1. 인식 → 바퀴 제어 확인 (이번 작업)
- 새 파일 `wheel_control.py`(WheelFollower) 작성: bbox → `/cmd_vel` 발행.
- robocart_main.py 에 `--follow` 훅만 최소 추가(인식 로직은 그대로).
- **확인 방법**: 8번 참고 (`/cmd_vel` echo 또는 웹 HUD의 v/w 값).

### Phase 2. 거리 유지 정밀화
- 캘리브레이션으로 `TARGET_HEIGHT_RATIO` 보정, 게인/데드밴드 튜닝.

### Phase 3. 좌우 추종 안정화
- 회전 게인 튜닝, 중앙 정렬 확인, 전후진과 합성 안정화.

### Phase 4. 실차 주행 튜닝
- 급출발·급정지 완화(저크 제한), P→PD 보강.

### Phase 5. (추후) 유실 대응
- 유실 시 정지 유지. 카메라 pan 재탐색 연계는 별도 단계에서 재설계.

## 8. 이번 단계(Phase 1) 확인 방법

```bash
# (선택) 인식 없이 배선/구동만 먼저 점검 — 로봇이나 시뮬레이터가 떠 있을 때
source /opt/ros/humble/setup.bash
python3 wheel_control.py --test spin --secs 2     # 2초 제자리 회전 후 정지
python3 wheel_control.py --test forward --secs 1  # 1초 전진 후 정지

# 인식 연동 실행 (영상=MJPEG, 웹 출력 + 바퀴 추종)
bash robocart.sh start --follow

# 다른 터미널에서 발행 명령 확인
source /opt/ros/humble/setup.bash
ros2 topic echo /cmd_vel
```

- 웹 화면(`http://localhost:8080`) 우측 하단에 `WHEEL v=.. w=..` 가 표시됨.
- 등록 사용자가 **멀어지면 v>0(전진), 좌/우로 가면 w 부호가 바뀜**, 유실 시 v=w=0.

## 9. 신규/수정 파일

| 파일 | 내용 |
|------|------|
| `wheel_control.py` (신규) | WheelFollower: bbox→Twist 변환·발행, 단독 `--test` 점검 모드 |
| `robocart_main.py` (최소 수정) | `--follow` 인자 + run_tracking 루프에 `follower.update()` 훅 1곳 |

> 카메라 모터 제어 파일(raspi_cmd_bridge.py / .sh)은 **수정하지 않음.**

## 10. 제외 범위 (이번 단계)

- 유실 시 카메라 pan 재탐색
- 장애물 회피 / 라이다 활용
- 경로 계획(맵 기반 이동)
- 다중 사용자 추종 대상 전환
