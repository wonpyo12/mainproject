# 유실 시 모터 스캔 기능 기획서

## 개요

사용자 유실(`searching`) 상태 진입 시, ESP32가 MG996R 서보모터를 좌우로 회전시켜 재탐색한다.  
모터 위에 카메라가 달려 있으며, **이번 단계는 모터 좌우 이동만 구현한다.**

---

## 구성

```
[robocart_main.py]
  status == "searching"
        ↓ 시리얼(USB)
[ESP32]  →  [MG996R 서보]  →  카메라 pan
```

---

## 스캔 동작

- 정면 기본값: **90°**
- 스캔 범위: **45° ↔ 135°** (좌우 각 45° 범위)
- 사이클: 좌 → 우 → 정면 반복
- 재발견 시: 즉시 중단 후 정면(90°) 복귀

---

## 통신 (Python → ESP32, 시리얼 9600 baud)

| 명령 | 시점 |
|------|------|
| `SCAN_START\n` | 유실 확정(`lost_count > LOST_MAX`) |
| `SCAN_STOP\n`  | 사용자 재발견 |
| `CENTER\n`     | 재발견 후 정면 복귀 |

---

## Python 수정 포인트 (robocart_main.py)

```python
import serial
esp = serial.Serial('COM?', 9600, timeout=1)  # COM 포트는 장치관리자 확인
```

`TrackingState.update()` 안에 2곳 추가:

```python
# 유실 확정 시
self.status = "searching"
esp.write(b"SCAN_START\n")

# 재발견 시
esp.write(b"SCAN_STOP\n")
esp.write(b"CENTER\n")
```

---

## ESP32 코드

```cpp
#include <ESP32Servo.h>

Servo motor;
const int PIN = 13;
int angle = 90, dir = -1;
bool scanning = false;

void setup() {
  Serial.begin(9600);
  motor.attach(PIN);
  motor.write(90);
}

void loop() {
  if (Serial.available()) {
    String cmd = Serial.readStringUntil('\n');
    cmd.trim();
    if      (cmd == "SCAN_START") scanning = true;
    else if (cmd == "SCAN_STOP")  scanning = false;
    else if (cmd == "CENTER")     { angle = 90; motor.write(90); }
  }

  if (scanning) {
    angle += dir * 2;
    if (angle <= 45)  dir =  1;
    if (angle >= 135) dir = -1;
    motor.write(angle);
    delay(20);  // 속도 조절: 값 키우면 느려짐
  }
}
```

---

## 구현 순서

1. ESP32 코드 업로드 → 시리얼 모니터에서 명령어 직접 입력해 모터 동작 확인
2. `pip install pyserial`
3. `robocart_main.py` 수정 (시리얼 연결 + 2곳 훅 추가)
4. 유실 상황 만들어서 모터 스캔 확인
5. `delay` 값으로 스캔 속도 조정

---

## 주의

- MG996R 전원은 **외부 5V** 공급 (ESP32 핀 직결 시 전류 부족)
- `lost_count > LOST_MAX` 이후에만 스캔 시작 → 짧은 유실(가림 등)엔 반응 안 함
