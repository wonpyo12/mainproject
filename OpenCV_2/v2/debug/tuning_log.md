# light_features.py 임계값 튜닝 로그

각 컬럼은 그 시점에 적용된 값. "원본"은 "진입 엄격 / 유지 느슨" 작업 직전 상태.

## 임계값

| 상수 | 원본 | 1차 | 2차 | 3차(현재) | 의도 |
|---|---|---|---|---|---|
| `MATCH_THRESHOLD` | 0.72 | 0.74 | 0.74 | 0.74 | 진입 엄격 |
| `SEARCH_MATCH_THR` | 0.70 | 0.65 | 0.60 | 0.68 | 재획득 |
| `KEEP_THRESHOLD` | 0.62 | 0.56 | 0.60 | 0.60 | 유지 느슨 폭 조절 |
| `REID_FLOOR` | 0.55 | 0.55 | 0.55 | 0.55 | 진입 ReID 하한 (고정) |
| `KEEP_REID_FLOOR` | 없음 | 0.45 (신규) | 0.52 | 0.52 | 유지 중 ReID 하한 — 타인 차단 핵심 |
| `COLOR_FLOOR` | 0.15 | 0.15 | 0.15 | 0.15 | 색상 하한 (유지 중 미적용) |
| `LOST_MAX` | 20 | 35 | 30 | 30 | 유실 유예 프레임 |
| `MIN_CONFIRM_FRAMES` | 3 | 4 | 4 | 4 | 진입 확인 프레임 |
| `SEARCH_CONFIRM_FRAMES` | 3 | 3 | 3 | 3 | 재획득 확인 프레임 (고정) |

## 로직 변경 (값이 아닌 구조, 1차 도입 · 2차 유지)

- **KCF 보간 유지**: 한 프레임 리젝돼도 `is_tracking`이면 초록 유지, 실제 유실 때만 KCF 폐기.
  (`ros_person_follower_nav2_v4.py` matched-else 블록)
- **추적 중 하드게이트 분리**: `is_tracking` 중엔 `KEEP_REID_FLOOR` 적용 + 색상 게이트 생략,
  진입/탐색 중엔 `REID_FLOOR`+`COLOR_FLOOR` 그대로 적용.

## 이력 요약

- **1차** — "진입 엄격 / 유지 느슨" 플랜 적용. 초록 유지가 잘 되기 시작했으나 타인도 초록으로 잡히는 부작용 발생.
- **2차** — 타인 오인식 대응: `KEEP_REID_FLOOR` 0.45→0.52, `KEEP_THRESHOLD` 0.56→0.60, `LOST_MAX` 35→30 (유지를 다시 조임), `SEARCH_MATCH_THR` 0.65→0.60.
- **3차** — `SEARCH_MATCH_THR` 0.60→0.68.

## 탐색 회전 파라미터 (`ros_person_follower_nav2_v4.py`)

기존엔 좌우로 짧게(약 31°) 진자운동하듯 교대 회전 → 좌우 180도씩 크게 훑도록 변경.

| 상수 | 원본 | 변경(현재) | 의도 |
|---|---|---|---|
| `SEARCH_ANG` | 0.18 | 0.20 | 탐색 회전 각속도(rad/s) |
| `SEARCH_HALF_PERIOD` | 3.0 | 15.7 | 한 방향 회전 지속(초). π/SEARCH_ANG ≈ 15.7초 → 좌우 180도(π rad) 회전 |

## 다음 조정 시 참고

- 타인이 계속 잡히면: `KEEP_REID_FLOOR`를 0.55(진입값)까지 올리거나, 위치 연속성 게이트 추가 검토.
- 본인인데 자주 놓치면: `KEEP_THRESHOLD`를 다시 낮추거나 `KEEP_REID_FLOOR`를 살짝 완화.
- 판단 근거는 터미널 `[score]` 로그(reid/color/total 실측치) 또는 `debug/analyze_debug.py` 분석.
