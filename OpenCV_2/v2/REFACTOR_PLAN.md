# ros_person_follower_nav2_v5.py 리팩토링 계획서

> 작성일: 2026-07-22 · 대상: `OpenCV_2/v2/ros_person_follower_nav2_v5.py` (1,570줄)
> **대전제: 로봇의 동작(주행·인식 결과)은 1도 바뀌지 않는다.** 구조만 정리한다.

---

## 1. 왜 지금 리팩토링인가

이 파일은 실제 로봇을 움직이는 코드이고, 주석 곳곳에 **실측 로그 근거**(07-13 주행 로그, 07-15 전원 상황 등)로 튜닝한 상수가 박혀 있습니다. 기능은 잘 동작하지만 **파일 하나에 모든 게 들어 있어** 다음 문제가 있습니다:

- 어디를 고쳐야 할지 찾는 데 시간이 걸림 (1,570줄 단일 파일)
- 한 곳을 고치면 다른 곳이 깨질까 두려움 (전역 상태·중복 코드)
- 새 사람이 구조를 파악하기 어려움 (문서와 실제가 불일치)

---

## 2. 현황 진단 — 실제로 발견한 문제

### A. 문서·이름이 실제와 불일치 (혼란 유발)

| 위치 | 현재 | 실제 |
|---|---|---|
| 파일 상단 docstring (3행) | `ros_person_follower_nav2_v4` | 파일은 **v5** |
| 실행 예시 (27행) | `v4.py --pi-ip 192.168.0.23` | v5, IP도 옛날 값 |
| ROS 노드 이름 (280행) | `person_follower_nav2_v3` | v5 |
| 화면 창 제목 (82행) | `robocart v3 - ...` | v5 |
| docstring "v2 대비 변경" | v2→v3 얘기만 | v4·v5 변경점 누락 |

→ **로그·rqt에서 노드명이 v3로 보여** 어떤 버전이 도는지 헷갈립니다.

### B. 죽은 코드

- `just_registered` 파라미터 (1013행): 받기만 하고 **본문에서 안 씀**. 호출부는 항상 `False`
- `import sys`, `PoseStamped` import: **한 번도 사용 안 함**

### C. 중복 코드

- **KCF 보간 블록이 두 곳에 똑같이 존재** (1227~1236행, 1250~1257행) — 9줄이 통째로 중복. 한쪽만 고치면 버그

### D. 전역 가변 상태 (`global` 문으로 조작)

`DBG`, `RECORD_SEC`, `_REC`, `REID_MODEL_NAME` 4개가 모듈 전역이고 `main()`/`run_tracking()`에서 `global`로 덮어씁니다. 테스트·재사용이 어렵고, 실행 중 어디서 바뀌는지 추적이 힘듭니다.

### E. 거대 함수

| 함수 | 줄 수 | 문제 |
|---|---|---|
| `run_tracking()` | **370줄** | 등록 트리거 · 프레임 수신 · 매칭 판정 · 온라인 수확 · 화면 그리기 · 주행 결정 · 녹화가 **한 함수에** |
| `register()` | 145줄 | 내부에 55줄짜리 중첩 `_worker()` 함수 |
| `RobotController` | 340줄 | ROS 콜백 + 주행계산 + 라이다 + Nav2가 한 클래스 |

### F. 매직 넘버 (이름 없는 숫자가 코드 중간에)

- `0.63` (1317행) — 소프트 매치 기준. `light_features`의 임계값들과 따로 놀아 **튜닝 시 놓치기 쉬움**
- `60.0` (1119행) — 자동 복귀 대기 시간
- `5.0` (1064행) — 촬영 후 출발 대기
- `2.0` (195행) — 프레임 신선도 한계

→ 다른 튜닝 상수 30여 개는 상단에 `SEARCH_ANG` 등으로 잘 정리돼 있는데, **이 4개만 코드 속에 숨어** 있습니다.

---

## 3. 목표와 원칙

### 지킬 것
1. **동작 불변** — 주행 파라미터, 임계값, 판정 순서를 **한 글자도 안 바꿈**
2. **실측 주석 보존** — "07-13 로그 근거", "이슈 #48" 같은 튜닝 이력 주석은 그대로 이동
3. **실행법 불변** — `python3 ros_person_follower_nav2_v5.py --pi-ip ... --register` 그대로
4. **단계별 커밋** — 각 단계마다 커밋해서 문제 생기면 즉시 되돌리기

### 안 할 것
- 알고리즘 개선, 임계값 조정, 새 기능 추가 → **별도 작업으로 분리**

---

## 4. 단계별 계획

### Phase 1 — 저위험 정리 (파일 하나 안에서)
> 위험도: ★☆☆ · 되돌리기 쉬움

1. docstring을 v5 기준으로 갱신 (v4→v5 변경 이력 추가, 실행 예시 현행화)
2. 노드 이름·창 제목을 v5로 통일
3. 죽은 코드 제거 (`just_registered`, `import sys`, `PoseStamped`)
4. 중복된 KCF 보간 블록 → 함수 하나로 추출
5. 매직 넘버 4개를 상단 상수로 승격 (`SOFT_MATCH_THR`, `AUTO_RETURN_SEC`, `POST_REGISTER_WAIT_SEC`, `FRAME_STALE_SEC`)

**검증**: 문법 검사 + `--no-drive`로 인식만 실행해 화면·로그 정상 확인

---

### Phase 2 — 모듈 분리 (코드는 그대로, 위치만 이동)
> 위험도: ★★☆ · 순수 이동이라 diff로 검증 가능

```
OpenCV_2/v2/
├── ros_person_follower_nav2_v5.py   ← 진입점만 (main·parse_args, ~150줄)
└── follower/
    ├── __init__.py
    ├── config.py        주행·인식·등록 튜닝 상수 전부 (실측 주석 포함)
    ├── camera.py        MjpegCamera
    ├── debug_log.py     DebugLog
    ├── notify.py        speak_on_pi · set_robot_led (음성·LED)
    ├── profile.py       프로필 저장/로드 · 임베딩 유틸
    ├── detection.py     DetectionWorker · MosseBoxTracker · score_multi_emb
    ├── registration.py  register() (촬영 등록)
    ├── robot.py         RobotController (ROS2 주행·Nav2)
    └── tracking.py      run_tracking()
```

- 실행 방법은 그대로 (`v5.py`가 같은 폴더의 `follower/` 패키지를 import)
- VM은 hgfs 공유폴더로 읽으므로 **`__pycache__` 정리 필요** (이전에 캐시 때문에 구버전이 실행된 이력 있음)

**검증**: 각 파일 문법 검사 + import 스모크 테스트 + 실제 실행

---

### Phase 3 — `run_tracking` 분해 (370줄 → 역할별)
> 위험도: ★★★ · 가장 신중하게, 마지막에

```python
class TrackingSession:      # 흩어진 지역변수 20여 개를 상태로 묶음
    def handle_register_trigger()   # 앱 QR → 촬영 등록
    def update_match(det)           # 매칭·구제·온라인 수확 판정
    def decide_drive()              # 추종/정지/탐색회전 결정
    def draw_overlay(frame)         # 박스·HUD 그리기
    def record(frame)               # mp4 녹화
```

**핵심 판정 순서(임계값 적용 → 매칭 → 구제 → confirm)는 그대로 유지.** 코드 이동만.

**검증**: 실제 로봇으로 등록→추종→유실→재획득→복귀 전체 시나리오 1회

---

## 5. 검증 방법

| 단계 | 검증 |
|---|---|
| 매 커밋 | `python -m ast` 문법 검사 |
| Phase 1·2 | `--no-drive` 인식 전용 실행 → 화면·점수 로그 정상 |
| Phase 3 | 실제 로봇: 등록 → 추종 → 유실/재획득 → 복귀 시나리오 |
| 최종 | `debug_logs/*.jsonl` 로그를 리팩토링 전후 비교 (판정 결과 동일한지) |

> **비교 기준 확보**: 작업 전 현재 코드로 한 번 주행해 `run_*.jsonl`을 남겨두면, 리팩토링 후 같은 상황에서 판정이 동일한지 수치로 확인할 수 있습니다.

---

## 6. 리스크와 대응

| 리스크 | 대응 |
|---|---|
| VM이 옛 파일 캐시로 실행 | 각 단계 후 `__pycache__` 삭제 |
| 분리 중 상수 오타 → 주행 이상 | Phase 2는 **복사-이동만**, 값 변경 금지. diff로 전수 확인 |
| 중간에 문제 발견 | 단계별 커밋 → `git revert` 한 번으로 복구 |
| 데모/시연 일정과 충돌 | Phase 1만 해도 효과 있음. **원하는 단계까지만 진행 가능** |

---

## 7. 권장 진행 방식

**Phase 1 → 검증 → Phase 2 → 검증 → Phase 3** 순서.

시연이 임박했다면 **Phase 1까지만** 해도 문서 불일치·중복·매직넘버가 정리되어 충분히 효과가 있습니다. Phase 2·3은 여유 있을 때 진행을 권합니다.

---

## 8. 실행 결과 (2026-07-22 완료)

세 단계 모두 완료했습니다. 되돌림 기준점으로 `pre-refactor-v5` 태그를 남겨 뒀습니다.

| 단계 | 커밋 | 내용 |
|---|---|---|
| Phase 1 | `e5dae30` | 문서·이름 v5 통일, 죽은 코드(`just_registered`·미사용 import) 제거, 중복 보간 블록 → `interp_step()`, 매직넘버 4개 상수화 |
| Phase 2 | `73d1436` | 1,589줄 단일 파일 → `follower/` 11개 모듈 + 진입점 210줄 |
| Phase 3 | `5d9c470` | `run_tracking` 358줄 → `TrackingSession` 역할별 메서드 |

### 최종 구조

```
ros_person_follower_nav2_v5.py  210줄   진입점(인자 파싱·초기화)
follower/config.py              101줄   튜닝 상수
        util.py                  16줄   clamp · 쿼터니언 변환
        debug_log.py             50줄   DBG 싱글톤
        camera.py                95줄   MJPEG 수신
        notify.py                55줄   음성 · LED
        profile.py               62줄   프로필 · 특징 집계
        detection.py            145줄   MOSSE · 스코어링 · 검출 워커
        registration.py         167줄   등록 촬영
        robot.py                371줄   주행 · Nav2 복귀
        tracking.py             531줄   TrackingSession(추종 루프)
        console.py               45줄   터미널 명령
```

### 검증 결과

- 전 모듈 문법 OK, 미정의 이름 0개, import 스모크 통과
- 원본 대비 **함수/클래스 유실 0**, **튜닝 상수 43개 값 전부 동일**
- **동등성 시뮬레이션**: 리팩토링 전 코드와 같은 검출 시퀀스를 주입해 비교 →
  진입(confirm 3연속) · 추적 · 유실(lost 16단계) · 재획득 전 구간에서
  추적 상태 전이와 주행 명령 **1,840개 이벤트가 프레임 단위로 완전 일치**

### 남은 확인 (실기 필요)

시뮬레이션은 로직 동등성까지만 보장합니다. **실제 로봇으로 한 번은 확인**해 주세요:

1. 앱 QR → 촬영 등록 → 추종 시작
2. 유실 → 재획득 → 복귀
3. VM은 hgfs 캐시 때문에 옛 파일이 실행될 수 있으므로, 첫 실행 전
   `rm -rf /mnt/hgfs/mainproject/OpenCV_2/v2/__pycache__ .../follower/__pycache__`

문제가 생기면 되돌리기: `git revert 5d9c470`(3단계만) 또는 `git reset --hard pre-refactor-v5`(전체).
