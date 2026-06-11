# SmartCart — 서보 기반 사용자 추적/탐색 카메라

등록 사용자 인식 시스템(YOLO + ReID + 색상 + 체형)에
**MG996R 팬 서보 제어**를 연동한 버전입니다.

- 사용자가 보이면 → 서보가 사용자를 **화면 중앙에 유지** (P제어)
- 잠깐 가려지면(lost, ~20프레임) → 그 자리에서 **대기**
- 완전히 사라지면(searching, 2초 경과) → 서보가 **0°↔180° 스윕하며 탐색**
- 탐색 중 재발견 → 즉시 정지 후 추적 재개

## 하드웨어 구성

```
[PC] ──USB 시리얼(115200)── [ESP32] ──GPIO 26── [MG996R] ──장착── [카메라]
```

- MG996R 전원은 별도 5~6V 공급 권장 (ESP32 5V 핀으로는 전류 부족으로 리셋 발생 가능)
- GND는 ESP32와 서보 전원 공통 연결

## 설정 순서

1. **ESP32 펌웨어 업로드**
   - Arduino IDE에서 [`Arduino/camera_servo/camera_servo.ino`](../../Arduino/camera_servo/camera_servo.ino) 업로드
   - 라이브러리: `ESP32Servo` 필요

2. **PC 의존성 설치**
   ```
   pip install -r requirements.txt
   ```

3. **실행**
   ```
   python smart_cart_main.py                    # ESP32 포트 자동탐지
   python smart_cart_main.py --serial-port COM3 # 포트 직접 지정
   python smart_cart_main.py --no-servo         # 서보 없이 인식만
   python smart_cart_main.py --register         # 사용자 신규 등록
   ```

## 시리얼 프로토콜 (PC → ESP32)

| 명령 | 동작 |
|---|---|
| `A<각도>\n` | 지정 각도로 부드럽게 이동 (추적) |
| `S\n` | 탐색 스윕 시작 (ESP32 자체 왕복) |
| `H\n` | 스윕 정지, 현재 각도 유지 |
| `C\n` | 중앙(90°) 복귀 |

ESP32는 100ms마다 `P<현재각도>`를 보고합니다.

## 튜닝 파라미터

`smart_cart_main.py` 상단:

| 상수 | 기본값 | 설명 |
|---|---|---|
| `SERVO_HFOV_DEG` | 60.0 | 카메라 수평 화각. 카메라 스펙에 맞게 조정 |
| `SERVO_GAIN` | 0.5 | 추적 반응 속도. 떨리면 낮추고, 느리면 높임 |
| `SERVO_DIRECTION` | 1 | **서보가 사용자 반대 방향으로 돌면 -1로 변경** |
| `SERVO_DEAD_ZONE` | 40 | 중앙 ±N px 이내 정지 (떨림 방지) |
| `SEARCH_GRACE_SEC` | 2.0 | 유실 후 스윕 시작까지 대기 시간 |

`camera_servo.ino` 상단:

| 상수 | 기본값 | 설명 |
|---|---|---|
| `TRACK_STEP_MS` | 15 | 추적 이동 속도 (1도당 ms, 작을수록 빠름) |
| `SWEEP_STEP_MS` | 40 | 탐색 스윕 속도 — 너무 빠르면 인식 전에 지나침 |
