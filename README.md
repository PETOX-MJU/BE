# 펫톡스 (peTox)

나만의 반려동물 캐릭터와 함께하는 숏폼 디톡스 서비스

> 클로드 코드 기반 VIBE CODING 실전활용 경진대회 출품작

## 팀 소개

| 역할 | 학과 | 학번 | 이름 | 담당 |
|---|---|---|---|---|
| 팀장 | 정보통신공학전공 | 60235280 | 최수빈 | PM, 디자인 |
| 팀원 | 정보통신공학전공 | 60235272 | 김민형 | 개발(BE) |
| 팀원 | 정보통신공학전공 | 60235273 | 박민규 | 개발(FE) |
| 팀원 | 정보통신공학전공 | 60211930 | 박현식 | 개발(AI) |

## 제안 배경

틱톡·유튜브 숏츠·인스타그램 릴스 시청 시간이 늘면서, 스스로 그만두기 어려운 숏폼 중독이 청소년부터 중장년층까지 폭넓게 나타나고 있습니다. 저희 팀도 자기 전 잠깐 보려다 한두 시간을 흘려보내고, 늦게 잠들어 다음 날 집중력이 떨어지는 경험을 반복하며 이 문제를 체감했습니다.

기존 대응 방식은 두 가지로 나뉘지만 모두 한계가 있습니다.

- **차단형** (iOS 스크린 타임, Android 디지털 웰빙): 사용자가 언제든 스스로 해제할 수 있어 실질적인 강제력이 없고, 우회 방법도 널리 공유되어 있습니다.
- **통계 제시형**: 사용 시간을 리포트로 보여줄 뿐, 사용 시간을 줄여야 할 이유는 만들어주지 못합니다.

두 방식 모두 절제에 대한 보상이 없어 사용자는 며칠 안에 원래 패턴으로 되돌아갑니다. 즉, 기존 서비스는 '막는 것'에 집중할 뿐 '스스로 멈추고 싶게 만드는 것'에는 접근하지 못하고 있습니다.

## 핵심 아이디어

펫톡스는 사용자가 설정한 시간대에 숏폼 앱을 실행하면, 미리 등록해 둔 동물 캐릭터가 화면 위에 나타나 영상을 가리는 서비스입니다. 앱을 강제로 종료시키는 것이 아니라 캐릭터가 시야를 가려 '잠깐 멈추는 순간'을 만들어, 사용자가 스스로 화면에서 벗어나도록 유도합니다.

**차단이 아닌 개입, 통제가 아닌 유도**가 펫톡스의 출발점입니다.

## 동작 방식

1. **초기 설정**: 최초 실행 시 목표 사용 시간, 집중 시간대(학습 시간·취침 전 등), 취침 시간을 설정하고 함께할 캐릭터를 선택합니다. 별도로 선택하지 않으면 기본 캐릭터가 지정되며, 반려동물 사진을 등록하면 이를 변환한 캐릭터를 쓸 수 있습니다.
2. **개입 트리거**: 릴스·쇼츠 시청이 설정 기준을 넘어 지속되면 캐릭터가 화면에 나타나 시청을 방해합니다.
3. **단계적 강화**: 처음에는 캐릭터가 화면 한쪽에 작게 등장하지만, 시청이 계속될수록 크기가 커져 화면을 더 많이 가립니다. 지속 시청이 감지되면 햅틱 피드백도 함께 발생시켜 시청을 불편하게 만듭니다.
4. **개인화 미션**: 사용자의 실제 스크린 타임 로그를 분석해 일일/주간 미션을 추천합니다. (예: 전날 사용량 42분 → "오늘은 30분 이내로 줄이기")
5. **보상**: 미션을 달성할 때마다 코인이 쌓이고, 이 코인으로 캐릭터를 꾸미는 아이템을 구매할 수 있습니다. 참는 행위가 손실이 아니라 눈에 보이는 보상으로 돌아오면서, 한 번의 절제가 다음 절제로 이어집니다.

## 기존 방식과의 차별성

1. **강제 차단이 아닌 자발적 중단** — 캐릭터에 대한 애착을 이용해 사용자가 스스로 앱에서 벗어나도록 돕습니다.
2. **나만의 캐릭터** — 기본 캐릭터뿐 아니라, 반려동물 사진을 픽셀 캐릭터로 변환해 '남의 캐릭터'가 아닌 '나의 반려동물'로 친숙함과 유대감을 높입니다.
3. **보상이 있는 절제** — 사용 시간 감소가 캐릭터 성장과 아이템 확장으로 이어져, 통계 제시형 서비스가 주지 못한 '줄여야 할 이유'를 제공합니다.

## 기술 스택

| 영역 | 기술 |
|---|---|
| 앱 | React Native (Android 전용) |
| 화면 오버레이 | 다른 앱 위에 캐릭터를 띄우는 오버레이 기능 |
| 사용시간 감지 | 숏폼 앱 실행 및 사용 시간 확인 |
| 이미지 변환 | ML Kit Subject Segmentation (반려동물 사진 → 픽셀 캐릭터, On-device 처리, 외부 생성형 AI API 미사용) |
| 데이터베이스 | PostgreSQL (캐릭터 성장 단계, 주간 리포트 근거 저장) |
| 개발 프로세스 | Claude Code (설계·구현·테스트 전 과정 활용) |

## 기대 효과

**사회적 효과**: 강제 차단 대신 캐릭터와의 유대감으로 스스로 화면에서 벗어나도록 유도하기 때문에, 차단형 앱에 거부감을 느끼던 사용자도 부담 없이 시작할 수 있습니다. 자발적 중단이 반복되면 자극적인 콘텐츠에 계속 노출되던 뇌에 휴식 시간이 생기고, 알고리즘에 이끌려 흘려보내던 시간을 아낄 수 있습니다.

**일상생활 개선**: 자기 전 무심코 이어지던 시청이 줄어들면서 잠드는 시간이 앞당겨지고 수면의 질이 회복됩니다. 학습·업무 중 습관적으로 휴대폰을 보는 횟수가 줄어 집중력을 되찾고, 절제한 시간이 캐릭터의 성장이라는 눈에 보이는 결과로 쌓이면서 지속적인 사용 습관 변화로 이어질 수 있습니다.

---

## 아키텍처 — BE 레이어 구성

### 전체 그림

```
React Native 앱 (Android, 박민규)
  │
  │ ① Supabase Auth SDK 직접 호출 (로그인/회원가입/로그아웃)
  │ ② supabase-js로 본인 데이터 CRUD (profiles, pets, usage_logs 등)
  │ ③ Row-Level Security(RLS)가 본인 데이터만 노출하도록 격리
  │
  ↓ HTTPS (JWT Bearer 토큰)
FastAPI (김민형) — 진짜 하는 일 딱 2개
  │ ① JWT 검증 (Supabase JWKS에서 공개키를 가져와 로컬에서 ES256 서명 검증 — ADR-010)
  │ ② 주간 리포트 집계 + 해석 (Supabase RPC 3개 호출 → 전주 대비 % 계산 → 문구 생성 — ADR-011)
  │
  ↓ (JWT Bearer + service_role key 이중 인증으로 RPC 호출)
Supabase (PostgreSQL + Auth + RPC + Edge Function + Cron Jobs)
  │ ① 인증: Supabase Auth (JWT 발급/검증, RS256 비대칭키)
  │ ② 신뢰 로직: security definer RPC (코인 지급, 아이템 구매 — ADR-004)
  │ ③ 집계: weekly_report / weekly_report_daily / weekly_report_by_app SQL 함수
  │ ④ 스케줄링: daily_mission_generation(06:00) + send-mission-notifications(06:05)
```

### 핵심 설계 결정 — FastAPI를 작게 만든 이유 (ADR-002)

이 프로젝트에서 FastAPI가 하는 일은 생각보다 적다. 엔드포인트는 `/health`, `/auth/signup`, `/me`, `/reports/weekly` 정도고, 그중 실질적으로 의미가 있는 건 **JWT 검증(`/me`)** 과 **주간 리포트(`/reports/weekly`)** 둘뿐이다. 프로필·반려동물·사용 로그·미션·코인·상점 CRUD는 FastAPI를 거치지 않는다.

이유를 소급해서 정리하면:

1. **Supabase Auth + RLS만으로 보안 모델이 완성된다.** 로그인 세션 토큰(JWT)만 있으면 클라이언트가 직접 DB를 호출할 수 있고, RLS가 `auth.uid()` 기준으로 본인 데이터만 노출한다. 이걸 FastAPI가 중간에서 프록시할 이유가 없어지므로, CRUD는 클라이언트가 Supabase를 직접 호출한다.

2. **Stateless JWT → 세션 스토어가 필요 없다.** FastAPI가 세션을 관리할 필요가 없다. 매 요청마다 Supabase JWKS 엔드포인트에서 공개키를 가져와 로컬에서 서명만 검증하면 된다(ES256, ADR-010).

3. **FastAPI는 Supabase 서비스 롤 키를 노출하지 않고 쓸 수 있는 기능만 남긴다.** `SUPABASE_KEY`(서비스 롤)는 RLS를 우회할 수 있는 키라서 클라이언트에 절대 주면 안 된다. 이 키로 할 수 있는 일 — 사용자의 JWT를 실어 RPC를 호출하거나, RLS 제약을 넘는 집계를 실행하거나 — 이 FastAPI 존재의 실질적 근거가 된다.

### 데이터가 어디서 생성되고 어디로 흐르는가

#### A. 온보딩/회원가입

```
FE: Supabase Auth SDK → auth.sign_up(email, password)
        ↓
Supabase Auth: JWT 발급 + auth.users 행 생성
        ↓ (트리거 handle_new_user)
profiles 행 자동 생성 (goal_minutes 등 기본값 포함)
        ↓
FE: profiles, pets 등 본인 데이터 직접 upsert (RLS가 본인만 접근 허용)
```

FastAPI는 이 흐름에서 아무 역할도 하지 않는다. `POST /auth/signup` 엔드포인트가 있긴 하지만, Supabase Auth SDK를 랩퍼하는 수준이고 클라이언트에서 직접 해도 되는 작업이다.

#### B. 사용 시간 로깅 (ADR-003)

```
FE: UsageStatsManager / AccessibilityService로 숏폼 앱 사용 감지
        ↓
FE: daily_usage 테이블에 직접 upsert (RLS insert 정책 허용)
        ↓
Supabase: (user_id, app_id, usage_date) 복합 PK로 "조합당 행 하나" 보장 → 멱등 동기화
```

`daily_usage`는 클라이언트가 **직접 INSERT할 수 있다**. 복합 PK `(user_id, app_id, usage_date)`가 upsert를 멱등하게 만든다. 세션 단위의 개별 사용 내역은 저장하지 않고, 일·앱 단위 집계(`minutes`)로만 저장한다 — 읽는 화면이 없기 때문이다.

#### C. 주간 리포트 조회 (ADR-011) — FastAPI가 실제로 쓰이는 유일한 본격 엔드포인트

```
FE: GET /reports/weekly (JWT Bearer 첨부)
        ↓
FastAPI: get_current_user_id → JWKS 공개키로 JWT 검증 → user_id 추출
        ↓
FastAPI: _call_report_rpc("weekly_report", user_jwt)
              → Supabase RPC 호출 (service_role key + user JWT 이중 인증)
              → weekly_report_daily(), weekly_report_by_app()도 동일한 패턴으로 호출
        ↓
Supabase: auth.uid() = 본인 → 본인 주간 합계/일별/앱별 집계 반환
        ↓
FastAPI: 3개 RPC 결과 → 전주 대비 % 계산 + 긍정/중립/경고 문구 생성 → 응답 조립
```

이 흐름에서 FastAPI가 하는 일은 **Supabase RPC가 날것의 숫자를 던져주면, 그걸 해석해서 프론트가 바로 쓸 수 있는 형태로 만드는 것**이다. RPC 자체는 집계만 하고, "32.5% 줄였어요!" 같은 사용자-facing 문구는 FastAPI가 생성한다.

### 신뢰 경계 — 코인은 클라이언트 마음대로 못 건드린다 (ADR-004)

코인 관련 테이블은 **클라이언트가 직접 INSERT할 수 없다**:

- `coin_ledger` — 쓰기 RLS 정책 없음. 읽기만 허용 (`own coin_ledger select`).
- `user_items` — 쓰기는 `is_equipped` 토글용 update만 허용. 구매로 인한 insert는 불가.

대신 `security definer` PostgreSQL 함수 두 개가 유일한 쓰기 경로다:

| 함수 | 역할 | 신뢰 보장을 위해 넣은 것 |
|---|---|---|
| `complete_mission(p_user_mission_id, p_request_id)` | 미션 완료 → 코인 지급 | request_id 멱등키, status 조건 update, RLS 우회 |
| `buy_item(p_item_id, p_request_id)` | 아이템 구매 → 코인 차감 + 아이템/슬롯 지급 | request_id 멱등키, 잔액 부족 시 예외, pet_slot이면 profiles.pet_slot_limit 증가 |

`security definer`라서 함수 실행 주체는 호출자이지만, 함수 내부에서는 RLS를 우회해 `coin_ledger`, `user_items`, `profiles`에 쓸 수 있다. 그래서 이 함수들이 해당 테이블들의 **구조적 유일한 쓰기 경로**가 된다 — 클라이언트가 "코인 확인 없이 코인 지급"을 시도할 수 없게 만든다.

### 멱등성과 동시성 (ADR-008)

`request_id` unique 제약은 **같은 요청의 재시도**만 막는다. 하지만 request_id가 다른 두 요청이 동시에 들어오면 막지 못한다 — 실제 동시성 테스트(`tests/test_rpc_trust.py`)에서 실증되었다:

- `buy_item`: 잔액 100에 60짜리 두 건 동시 → 둘 다 잔액을 100으로 읽고 통과 → 잔액 -20
- `complete_mission`: 같은 미션 두 건 동시 → 둘 다 `in_progress`를 읽고 각자 보상 지급 → 보상 이중 지급

이 문제의 해법이 **사용자 단위 advisory lock**이다 (`pg_advisory_xact_lock(hashtextextended(auth.uid()::text, 0))`). 함수 진입 직후 걸어서, 같은 사용자의 코인 변경만 직렬화하고 다른 사용자는 막지 않는다. 트랜잭션 끝나면 자동 해제되므로 해제를 잊을 수 없다. 단, advisory lock은 DB 인스턴스 범위라서 읽기 레플리카로 쓰기를 분산하거나 샤딩하면 무효가 된다 — 지금 규모(단일 인스턴스, ADR-001)에서는 유효하고, 그 전제가 바뀌면 재검토 대상이다.

### JWT 검증 방식 (ADR-010)

Supabase가 JWT 서명 방식을 대칭키에서 비대칭키(RS256)로 전환했기 때문에, 새 시크릿을 공유받을 필요 없이 Supabase JWKS 공개 엔드포인트(`/auth/v1/.well-known/jwks.json`)에서 공개키를 가져와 로컬에서 서명을 검증한다. 알고리즘은 ES256만 허용하고, `aud`는 Supabase가 로그인 세션 토큰에 항상 넣는 `"authenticated"`로 고정한다.

`/me` 엔드포인트는 이 검증을 거쳐 `sub`를 그대로 반환한다 — "이 JWT가 유효하고 누구 것인지"만 확인하는 용도다. `get_current_user_id` 의존성으로 추출돼 있고, 테스트에서 `app.dependency_overrides`로 갈아끼울 수 있게 돼 있다.

### daily_mission_generation과 알림 (Supabase 측)

일일 미션 생성(`20260911070000_daily_mission_generation.sql`)과 미션 알림 발송은 **FastAPI를 거치지 않는다**:

- `generate_daily_missions()` 함수가 매일 06:00에 실행되어 그날 미션을 `missions` / `user_missions`에 생성
- Supabase Cron Jobs가 06:05에 Supabase Edge Function `send-mission-notifications`를 호출하여 FCM 발송

FR-057(푸시 알림: 미션, P0)은 원래 FastAPI에 엔드포인트가 있을 예정이었지만, ADR-18에 따라 Supabase Edge Function + Cron Jobs로 구현됐다.

---

## 기대 효과

**사회적 효과**: 강제 차단 대신 캐릭터와의 유대감으로 스스로 화면에서 벗어나도록 유도하기 때문에, 차단형 앱에 거부감을 느끼던 사용자도 부담 없이 시작할 수 있습니다. 자발적 중단이 반복되면 자극적인 콘텐츠에 계속 노출되던 뇌에 휴식 시간이 생기고, 알고리즘에 이끌려 흘려보내던 시간을 아낄 수 있습니다.

**일상생활 개선**: 자기 전 무심코 이어지던 시청이 줄어들면서 잠드는 시간이 앞당겨지고 수면의 질이 회복됩니다. 학습·업무 중 습관적으로 휴대폰을 보는 횟수가 줄어 집중력을 되찾고, 절제한 시간이 캐릭터의 성장이라는 눈에 보이는 결과로 쌓이면서 지속적인 사용 습관 변화로 이어질 수 있습니다.

---

각주: [2025년 스마트폰 과의존 실태조사](https://www.nia.or.kr/site/nia_kor/ex/bbs/View.do?cbIdx=659)
