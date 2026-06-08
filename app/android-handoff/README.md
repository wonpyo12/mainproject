# CartMe · Calm 리디자인 — 안드로이드 스튜디오 적용 가이드

깔끔·모던(쿨 그레이 + 트러스트 블루) 방향으로 다시 그린 Compose 화면입니다.
**ViewModel(`CartViewModel`)·상태·내비게이션은 그대로** 두고 화면(UI)만 교체하면 됩니다.

---

## 1. 화면 파일 교체

`android-handoff/CartScreens.kt` 의 내용으로 프로젝트의
`app/src/main/java/com/example/ui/screens/CartScreens.kt` 를 **통째로 덮어쓰기** 하세요.

- 진입점 `CartAppContent(viewModel, innerPadding)` 시그니처가 동일해 `MainActivity` 는 수정 불필요
- 색상 토큰은 파일 상단 `Ink / Point / PointSoft …` 에 모여 있어요. 여기만 바꾸면 전체 톤이 함께 바뀝니다.

## 2. 아이콘 라이브러리 활성화 (필수, 한 줄)

새 디자인은 배터리·실드·QR·일시정지 등 **확장 아이콘**을 사용합니다.
`app/build.gradle.kts` 의 dependencies 에서 주석 한 줄만 풀어주세요:

```kotlin
implementation(libs.androidx.compose.material.icons.core)
implementation(libs.androidx.compose.material.icons.extended)   // ← 주석(//) 제거
```

→ 우측 상단 **Sync Now** 클릭. (`libs.versions.toml` 에 라이브러리는 이미 정의돼 있어 별도 추가 불필요)

> 확장 아이콘을 쓰기 싫다면, 코드에서 다음 아이콘만 core 세트로 바꾸면 됩니다:
> `Pause→Clear`, `Shield→CheckCircle`, `BatteryFull→KeyboardArrowUp`,
> `QrCodeScanner→(leadingIcon 제거)`, `VolumeUp→Notifications`,
> `NearMe→LocationOn`, `DeleteOutline→Delete`

## 3. (선택) Pretendard 폰트

지금은 시스템 기본 폰트로 동작합니다. 프로토타입과 동일한 Pretendard 를 쓰려면:

1. [Pretendard 릴리스](https://github.com/orioncactus/pretendard/releases) 에서 `.ttf`(또는 `.otf`) 받기
2. `app/src/main/res/font/` 폴더에 `pretendard_regular.ttf`, `pretendard_medium.ttf`, `pretendard_bold.ttf`, `pretendard_extrabold.ttf` 로 추가 (파일명은 소문자·언더스코어만)
3. `ui/theme/Type.kt` 에 FontFamily 정의 후 `Typography` 에 적용:

```kotlin
val Pretendard = FontFamily(
    Font(R.font.pretendard_regular, FontWeight.Normal),
    Font(R.font.pretendard_medium, FontWeight.Medium),
    Font(R.font.pretendard_bold, FontWeight.Bold),
    Font(R.font.pretendard_extrabold, FontWeight.ExtraBold),
)
```
그 후 `MaterialTheme(typography = Typography...)` 의 본문 스타일 `fontFamily` 를 `Pretendard` 로 지정하면 전 화면에 적용됩니다.

---

## 무엇이 바뀌었나

| | 변경 |
|---|---|
| **정리** | ROS2 로그·QA 시뮬레이터·수동 조종(▲▼◀▶) 패널 → 제거. 대신 깔끔한 **‘상품 담기’ 바텀시트**로 RFID 담기를 시뮬레이션 |
| **상태** | 로봇 상태를 한 카드로: 연결 ID·배터리·추종/정지 세그먼트·상태 배너 (추종/정지/인식실패/통신지연 색 구분) |
| **흐름** | 스플래시 → 로그인/회원가입 → 카트 연결(QR) → 쇼핑 → 결제 명세 → 완료. 기존 `Screen` enum 그대로 |
| **유지** | 음성 안내 토스트, 교통약자 안심 정보, RFID 자동 담기, 48dp+ 터치 영역, 큰 글씨 |

## 동작 그대로 쓰는 ViewModel 함수
`login` · `signUp` · `logout` · `matchCart` · `setTrackingState` · `simulateRfidScan` · `removeItem` · `navigateTo` · `formatPrice` — 호출부 동일.
(`publishManualControl` · `toggleSimulationPanel` 은 새 UI에서 호출하지 않지만, 남겨둬도 무방합니다.)

> 웹 인터랙티브 시안: 프로젝트의 `CartMe Final.html` (이 디자인 그대로) / `CartMe Redesign.html` (3가지 스타일 비교)
