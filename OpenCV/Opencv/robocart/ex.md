# 작업 기록 — 2단계 tracking-by-detection 최적화 (2026-06-18)

이 세션에서 진행한 작업과 대화 내용을 정리한 문서입니다.

---

## 1. 목표

영상=MJPEG 하이브리드 전환(이전 작업) 이후 남은 과제 중 **2단계 tracking-by-detection**을 구현.

> 무거운 검출(YOLO+ReID)을 N프레임마다 + KCF 경량 추적 보간
> → VM 렉 감소, 추종 부드럽게 (신원 재확인은 주기/재획득 시 ReID로 유지)

대상 파일: `robocart_main.py`

---

## 2. 기존 구조 파악

- 이미 `DetectionWorker`(백그라운드 스레드)가 YOLO+Pose+ReID를 비동기 처리.
- 메인 루프는 매 프레임 워커에 제출하고 최신 결과를 논블로킹으로 받아 그림.
- **문제점**
  1. 무거운 검출이 끝날 때까지 박스가 그 자리에 멈춰 끊겨 보임.
  2. 매 프레임 제출로 워커가 코어를 계속 점유 → VM 렉.

---

## 3. 구현 내용 (`robocart_main.py`)

### 3-1. 상수 추가
```python
DETECT_INTERVAL = 6     # 추종 중 무거운 검출 제출 주기 (1=매 프레임)
KCF_MAX_AGE     = 45    # KCF 단독 보간 허용 최대 프레임 (초과 시 매 프레임 재검출)
```

### 3-2. KCF 경량 추적기 — `BoxTracker` 클래스 신설
- `cv2.TrackerKCF`(빌드 따라 `cv2.legacy` 폴백) 래퍼.
- `init`/`update`/`deinit`, 추적 실패 시 `ok=False` → 메인 루프가 즉시 재검출.

### 3-3. `DetectionWorker`에 `seq` 추가
- 워커가 새 결과를 낼 때마다 `seq++`.
- 메인 루프가 `seq` 변동(=새 검출 도착)을 감지해 그때만 KCF를 재고정.

### 3-4. `run_tracking` 메인 루프 재구성 (핵심)
프레임마다:
1. **검출 제출 여부 결정**
   - 추종 안정 + KCF 살아있음 → `DETECT_INTERVAL`마다만 제출 (그 사이는 보간).
   - 탐색·확인·소실·KCF실패·`KCF_MAX_AGE` 초과 → 매 프레임 제출(빠른 재획득/신원 재확인).
2. **새 검출(fresh) 도착 시** → ReID로 신원 (재)확인, 매칭이면 KCF를 검출 위치에 재고정.
3. **검출 사이 프레임** → `kcf.update()`로 bbox 보간.
4. **그리기** → 검출이든 KCF든 `draw_bbox` 하나로 통일, 보간 프레임은 라벨에 `~` 표기.
5. **HUD** → 현재 프레임이 `DET`(검출) / `KCF`(보간) 중 무엇인지 표시.

---

## 4. 검증 중 발견·수정한 버그 (별개 잠복 버그)

```python
# Before (무한 재귀 → 종료 시마다 RecursionError)
def destroy_windows() -> None:
    if not _web_enabled:
        destroy_windows()        # 자기 자신 호출!

# After
def destroy_windows() -> None:
    if not _web_enabled:
        cv2.destroyAllWindows()
```

---

## 5. 실행 검증 (카메라 없이 합성 영상 end-to-end)

카메라가 없어 **등록 프로필 + 실제 모델(YOLO·MediaPipe·ResNet50)** 을 그대로 쓰고,
등록 샘플(front)을 움직이는 합성 영상으로 `run_tracking`을 헤드리스 구동.
(하니스: `verify_tracking.py`, 결과 이미지: `verify_out.jpg`)

| 항목 | 값 | 의미 |
|---|---|---|
| 메인 루프 프레임 | 131 | — |
| 무거운 검출 실행 | 5 (0.4/s) | 매 프레임 아님 |
| **검출/메인 비율** | **0.04** | 1.0=매프레임 → 약 96% 절감 |
| KCF update | 10 | 검출 사이 보간 동작 |
| KCF 재고정(ReID 매칭) | 4 | 신원 주기적 재확인 |

→ **PASS**: 무거운 검출은 드물게만 돌고 그 사이를 KCF가 메우며, 검출마다 ReID로 신원 재확인.
점수 Total 0.83 / ReID 0.84, 박스 정렬·HUD(`KCF`)·패널 렌더 정상.

**한계**
- 이 PC는 CPU-only라 검출이 ~1.6초/회로 느림 → 빠른 합성 이동에선 낡은 bbox에 KCF가
  재고정돼 박스가 인물 밖으로 밀림(검출 지연 큰 환경의 실제 약점). 이동 속도를 보행
  수준으로 낮추면 깔끔히 추종.
- 실제 카메라/ROS2 경로(라파 MJPEG · `/robocart/cmd`)는 이 환경에 카메라·rclpy가 없어
  미검증. VM에서 직접 띄워 확인 필요.

---

## 6. 눈으로 확인하는 방법 (웹 브라우저, VMware 검은 창 회피)

### 1단계 — 라즈베리파이에서 카메라 송출
```bash
cd ~/<robocart 경로>
bash raspi_mjpeg_launch.sh        # 켜둔 채로 둠
# 라파 IP 확인: hostname -I  → 맨 앞 주소 (예: 192.168.0.67)
```

### 2단계 — VM에서 인식 프로그램 실행
```bash
cd /home/seohee/mainproject/OpenCV/Opencv/robocart
./venv/bin/python robocart_main.py --mjpeg http://<라파IP>:8090/stream --web
# 콘솔에 "[웹] 실행 화면: http://localhost:8080" 뜨면 준비 완료
```

### 3단계 — 브라우저로 확인
```
http://localhost:8080
```
- 좌상단 HUD: `KCF`(보간) ↔ `DET`(검출) 전환
- 녹색 박스: 검출 사이에도 KCF로 부드럽게 추종 (라벨 끝 `~` = 보간 중)
- 우측 패널: ReID/Color/Shape 점수, TRACKING 상태

### 종료
VM 터미널 `Ctrl+C`. (라파 송출도 끄려면 라파 터미널 `Ctrl+C`)

**문제 시 점검**: ① 라파 송출 켜짐 ② IP 일치 ③ `curl -I http://<라파IP>:8090/stream` 연결 확인

---

## 7. 튜닝 가이드

- VM에서 검출이 빠르면 `DETECT_INTERVAL`(현재 6)을 **낮춰** 정밀도↑.
- 렉이 심하면 `DETECT_INTERVAL`을 **올려**(8~10) 부드러움↑.

---

## 8. 변경 파일 요약

| 파일 | 변경 |
|---|---|
| `robocart_main.py` | `BoxTracker` 신설, `DetectionWorker.seq` 추가, `run_tracking` 2단계 재구성, `destroy_windows` 무한재귀 버그 수정, 상수 2개 추가 |
| `verify_tracking.py` | (신규) 카메라 없이 합성 영상으로 end-to-end 검증하는 하니스 |
| `verify_out.jpg` | (신규) 검증 어노테이션 결과 캡처 |

---

## 9. 남은 작업 (이후 과제)

- [ ] 바퀴(주행) 제어 명령 신설 — 현재 서보 스캔(`SCAN_START`/`STOP`/`CENTER`)만 있음
- [ ] ESP32 end-to-end 실모터 구동 검증
- [ ] 실제 라파+카메라 환경에서 2단계 추종 라이브 확인 및 `DETECT_INTERVAL` 튜닝
