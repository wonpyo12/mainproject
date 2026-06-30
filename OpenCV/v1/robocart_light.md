# 스마트 장바구니 경량화 기획서 — RPi4 단독 영상처리 (robocart_light)

## 0. 한 줄 요약

기존 [robocart.md](robocart.md) 인식 파이프라인을 **라즈베리파이4(RPi4)에서 단독 실행**하도록
경량화한다.

- **실제 영상처리·인식 실행 = 100% RPi4 단독** (운영 중 VM 불필요)
- **모델 파일 변환(.pt→.onnx)만 VM에서 1회 준비** → 변환된 파일만 RPi4로 복사
  (RPi4에는 torch 안 깔고 가벼운 onnxruntime만 사용하기 위함)

> 기존 파일(robocart_main.py, wheel_control.py 등)은 **백업용으로 그대로 둔다.**
> 이 문서의 모든 코드는 `robocart_light_*` / `light_*` 새 파일로 분리한다.

## 1. 배경 — 왜 경량화인가

기존 구조는 RPi4가 카메라 영상을 MJPEG로 송출하고 **VM(우분투)이 무거운 연산**
(YOLOv8n + MediaPipe Pose + ResNet50 ReID)을 처리했다. 이를 RPi4 단독으로 옮기면
ResNet50(2048-dim, 25M params) CPU 추론이 ARM Cortex-A72에서 병목이 된다.

## 2. 대상 하드웨어 / 환경 (실측)

- **Raspberry Pi 4 Model B Rev 1.4**, aarch64, 4코어, RAM 8GB, Ubuntu 22.04.5
- 카메라: **Logitech C920 USB 웹캠** → `/dev/video0` (표준 UVC, `cv2.VideoCapture(0)` 직접 가능, libcamera 불필요)
- 이미 apt 설치됨: **`python3-opencv 4.5.4`, `python3-numpy 1.21.5`** (가장 빌드 무거운 둘이 이미 있음)
- pip/venv/ensurepip 없음 → `sudo apt install python3-pip python3-venv` 필요
- 인터넷 가능

## 3. 경량 파이프라인 (기존 대비)

| 단계 | 기존 (VM) | 경량 (RPi4) | 비고 |
|---|---|---|---|
| 사람 검출 | YOLOv8n (PyTorch) | **YOLOv8n → ONNX**, onnxruntime | imgsz 320 |
| ReID 임베딩 | ResNet50 2048-dim | **OSNet-x0.25 → ONNX** (512-dim) | 가장 큰 경량화 |
| 체형/방향 | MediaPipe Pose Lite | **제거** (앞/뒤는 경량 face 검출 보조) | 인식률 떨어지면 추후 추가 |
| 보간 추적 | KCF | KCF (cv2 내장 동일) | |
| 런타임 의존성 | torch+ultralytics+mediapipe | **onnxruntime + apt cv2/numpy 뿐** | torch 없음 |

### 점수 가중치 재배분 (Pose 제거 반영)

- 기존: ReID 0.55 / 색상 0.25 / 체형 0.15 / 위치 0.05
- **경량: ReID 0.65 / 색상 0.30 / 위치 0.05** (체형 0.15를 ReID·색상으로 흡수)

## 4. 모델 변환(Export) — VM에서 1회 수행

[export_models.py](export_models.py) 를 VM에서 실행해 산출물을 만든다 (이 작업에만 torch 필요).

1. **`models_light/yolov8n.onnx`** — `yolov8n.pt` → ONNX (opset 12, imgsz 320 고정)
2. **`models_light/osnet_x0_25.onnx`** — torchreid OSNet-x0.25 → ONNX (입력 256x128, 출력 512-dim)
3. **`models_light/face_detection_yunet.onnx`** — OpenCV YuNet 경량 얼굴 검출(앞/뒤 판별용, 다운로드)

→ 이 3개 파일만 RPi4로 전송. **RPi4는 torch/torchreid/ultralytics 불필요.**

## 5. RPi4 런타임 구성

```text
[C920 USB 카메라]  cv2.VideoCapture(0)
      ↓ (캡처 스레드, latest-only)
[robocart_light_main.py]
   ├─ 메인 루프 (카메라 FPS, 절대 멈추지 않음)
   │    KCF 보간으로 bbox 갱신, 화면 그리기, 8080 송출
   │
   └─ DetectionWorker (백그라운드 스레드, 비동기)
        YOLOv8n-ONNX → 사람 bbox
        OSNet-x0.25-ONNX → 512-dim ReID 임베딩
        HSV 상/하의 히스토그램 → 색상 특징
        YuNet/Haar face → 앞/뒤 방향 보조(가능 시)
        가중 점수 합산 → 등록자 1명 선택 → 결과를 메인에 전달(seq)
      ↓
[MJPEG 웹서버 :8080]  ← PC 브라우저에서 라이브 확인
      ↓ (--follow 시)
[wheel_control.py / WheelFollower]  → ROS2 /cmd_vel (Twist) → turtlebot3_bringup → 바퀴
```

- **검출은 비동기(백그라운드 스레드)로 분리.** 동기 방식은 YOLO 추론(약 0.2~0.7s, RPi4 저전압
  스로틀 시 더 느림) 동안 화면 전체가 멈춰 끊김이 심했음(FPS 1.3) → 비동기 전환 후 FPS 30 회복.
  메인 루프는 최신 검출 결과를 KCF로 보간하며 기다리지 않고 계속 그린다.
- **출력은 8080 MJPEG로 결정.** 파일 저장 대비: 디스크 I/O·파일 전송 없음, 원격 라이브 확인 가능,
  클라이언트 없을 때/저FPS로 인코딩 throttle 가능 → 실사용에서 더 가벼움.
- **단계별 `cv2.TickMeter` 계측**(검출/ReID ms)을 HUD와 콘솔 로그에 출력
  (참고: https://opencv-master.tistory.com/37 — 30fps 기준 프레임당 33ms 목표).
- **바퀴 추종(`--follow`)은 [robocart2.md](robocart2.md) 설계·[wheel_control.py](wheel_control.py)를
  그대로 재사용** — robocart_main 내부 구조에 의존하지 않는 범용 모듈(bbox·frame 크기·is_tracking만
  입력)이라 새 파일을 만들지 않고 import 한다. `turtlebot3_bringup`이 라파 자신에게서 `/cmd_vel`을
  구독하므로 VM↔Pi DDS 통신은 필요 없다(보류했던 비대칭 멀티캐스트 이슈와 무관).

## 6. 신규 파일 구조

| 파일 | 위치 | 내용 |
|---|---|---|
| `robocart_light.md` | VM | 본 설계 문서 |
| `export_models.py` | VM | 모델 → ONNX 변환 (1회, torch 필요) |
| `robocart_light_main.py` | VM 작성 → Pi 실행 | 메인 루프(캡처·추론·점수·KCF·8080·계측·등록) |
| `light_models.py` | 〃 | OnnxYolo / OnnxReID / FaceOrient 래퍼 (onnxruntime) |
| `light_features.py` | 〃 | 색상 히스토그램·점수 합산·추적상태·KCF (torch 무관 순수 함수) |
| `requirements_pi.txt` | 〃 | Pi 런타임 의존성 (onnxruntime; cv2/numpy는 apt) |
| `robocart_light.sh` | 〃 | Pi 실행 스크립트 (venv --system-site-packages + 실행, ROS2 source, follow/wheeltest) |
| `wheel_control.py` | 기존 파일 재사용 (수정 없음) | bbox→`/cmd_vel`(Twist) 변환·발행. `--test`로 단독 배선 점검 |

- **Pi 작업 폴더 규칙:** SSH 접속 시 `~/robocart_light_sh/` (`_sh` 접미사) 안에서만 생성/실행.

## 7. 단계별 계획

- **✅ Phase 0**: 경량 파이프라인 골격 + RPi4 단독 실행 + 8080 확인 + 단계별 ms 계측
- **✅ Phase 0.5**: 검출 비동기화(DetectionWorker) — 동기 방식의 화면 끊김(FPS 1.3) 해결 → FPS 30
- **▶ Phase 1 (이번 작업)**: 바퀴 추종 연계 — `--follow` 옵션 + `wheel_control.py`(기존 파일 재사용)
  로 인식 bbox → `/cmd_vel` 발행. 확인: `robocart_light.sh wheeltest --test spin`(배선 단독 점검) →
  `robocart_light.sh follow`(인식 연동) → 8080 HUD `WHEEL v=.. w=..` / `ros2 topic echo /cmd_vel`
- **Phase 2**: 정확도 튜닝(임계값·가중치), 필요 시 입력 해상도/DETECT_INTERVAL 조정
- **Phase 3**: 인식률 부족 시 체형(Pose) 또는 더 강한 ReID 가중 추가 검토

## 8. 성능 목표 / 폴백

- 1차 목표: 검출+ReID 포함 **프레임당 처리 ≤ 150ms** (KCF 보간 프레임은 수 ms), 체감 5~10fps.
- 미달 시 폴백 순서: imgsz 320→256, DETECT_INTERVAL↑, onnxruntime 스레드 수 조정,
  (추후) onnx → **ncnn** 변환으로 ARM NEON 가속.

## 9. 제외 범위 (이번 단계)

- 유실 시 카메라 pan 서보 재탐색 — [robocart2.md](robocart2.md) §10과 동일하게 제외, 별도 과제
- 거리/회전 게인 실차 튜닝, 저크 제한(PD 보강) — Phase 1에서 안전 동작만 확인 후 추후 튜닝
- 체형(MediaPipe) — 제거 상태, 추후 선택적 복원

## 10. 바퀴 추종 안전 설계 (robocart2.md 동일 원칙)

- **미추적/유실 시 즉시 정지** (`is_tracking=False` → v=w=0) — 추종보다 항상 우선
- 운용 속도 상한(`MAX_LIN=0.12`, `MAX_ANG=1.0`)을 Burger 하드 한계(0.22 / 2.84)보다 보수적으로
- 1차엔 후진 금지(`ALLOW_REVERSE=False`) — 너무 가까우면 정지만
- 프로그램 종료(Ctrl+C 포함) 시 반드시 정지 명령 발행 — `finally`에서 `follower.destroy()`
- KCF 보간 프레임도 bbox가 있으면 그 위치로 계속 추종(검출 주기에만 끊기지 않도록)
