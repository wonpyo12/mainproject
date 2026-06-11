# 아두이노 (ESP32 모터 스캔)

사용자 유실(`searching`) 상태 진입 시, ESP32가 MG996R 서보모터를 좌우로 회전시켜 카메라를 pan하며 재탐색하는 코드입니다.

- 코드: [mg996r_control/mg996r_control.ino](mg996r_control/mg996r_control.ino)
- 기획서: `OpenCV/Opencv/robocart/scan_motor_plan.md`

## 전체 흐름

```
[robocart_main.py]
  status == "searching"
        ↓ 시리얼(USB, 9600 baud)
[ESP32]  →  [MG996R 서보]  →  카메라 pan
```

Python(`robocart_main.py`)이 사용자 추적 상태를 판단하고, 유실/재발견 시점에 시리얼로 명령을 보내면 ESP32가 서보를 제어합니다.

## 코드 동작 설명

### 전역 변수

| 변수 | 초기값 | 역할 |
|------|--------|------|
| `PIN` | 26 | 서보 신호선이 연결된 ESP32 핀 |
| `angle` | 90 | 현재 서보 각도 (90° = 정면) |
| `dir` | -1 | 스캔 진행 방향 (-1: 좌측으로, +1: 우측으로) |
| `scanning` | false | 스캔 모드 on/off 플래그 |

### setup()

1. 시리얼 통신을 9600 baud로 시작
2. 26번 핀에 서보를 연결(`motor.attach`)
3. 서보를 정면(90°)으로 초기화

### loop() — 두 부분으로 동작

**1) 시리얼 명령 처리**

매 루프마다 시리얼 버퍼를 확인하고, 개행(`\n`)까지 한 줄을 읽어 명령으로 해석합니다.

| 명령 | 동작 | 보내는 시점 (Python 쪽) |
|------|------|------------------------|
| `SCAN_START\n` | `scanning = true` → 스캔 시작 | 유실 확정 (`lost_count > LOST_MAX`) |
| `SCAN_STOP\n` | `scanning = false` → 스캔 중단 | 사용자 재발견 |
| `CENTER\n` | 각도를 90°로 리셋하고 정면 복귀 | 재발견 직후 |

**2) 스캔 동작** (`scanning == true`일 때만)

- 매 루프마다 `angle`을 현재 방향(`dir`)으로 2°씩 이동
- **45°에 도달하면** 방향을 +1로 반전 (우측으로 전환)
- **135°에 도달하면** 방향을 -1로 반전 (좌측으로 전환)
- 즉, 정면(90°) 기준 좌우 45° 범위를 **45° ↔ 135°로 왕복**
- `delay(100)`으로 한 스텝당 100ms 대기 → 값을 키우면 스캔이 느려짐

`SCAN_STOP`을 받으면 왕복을 멈추고, 이어서 `CENTER`를 받으면 정면(90°)으로 복귀합니다.

## 통신 테스트

업로드 후 Arduino IDE 시리얼 모니터(9600 baud, 개행 문자 "새 줄")에서 `SCAN_START`, `SCAN_STOP`, `CENTER`를 직접 입력해 모터 동작을 확인할 수 있습니다.

## 주의사항

- MG996R 전원은 **외부 5V** 공급 필요 (ESP32 핀 직결 시 전류 부족)
- `ESP32Servo` 라이브러리 설치 필요 (Arduino IDE 라이브러리 매니저)
- 짧은 유실(가림 등)에는 반응하지 않음 — Python 쪽에서 `lost_count > LOST_MAX` 이후에만 `SCAN_START`를 보냄
