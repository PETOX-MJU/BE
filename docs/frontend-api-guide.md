# 프런트엔드 연동 가이드

이 프로젝트는 API 호출 경로가 두 갈래다 (ADR-002). 프로필·반려동물·미션·코인·상점 CRUD와 로그인/로그아웃은 **Supabase를 직접** 호출하고, FastAPI는 회원가입·본인 확인·주간 리포트 3가지만 담당한다. 섞어 쓰지 않도록 아래 구분을 지켜야 한다.

## 1. Supabase 직접 연결

### 1.1 접속 정보

- `SUPABASE_URL`, `anon`(public) 키만 클라이언트에 넣는다. `service_role`(secret) 키는 절대 넣지 않는다 — RLS를 우회하는 관리자 키다.
- Supabase 대시보드 → Project Settings → API Keys에서 확인한다. 새 대시보드는 `Publishable key`(= `anon`)와 `Secret keys`(= `service_role`)로 이름이 바뀌었지만 이 레포는 레거시 이름(`anon`)을 기준으로 문서화돼 있다.

### 1.2 로그인/로그아웃/세션

FastAPI를 거치지 않는다. Supabase Auth SDK(`supabase-flutter` 등)로 직접 처리한다:

- 로그인: `supabase.auth.signInWithPassword(email, password)`
- 로그아웃: `supabase.auth.signOut()`
- 세션 토큰(`access_token`)은 SDK가 관리하며, FastAPI의 `/me`, `/reports/weekly` 호출 시 `Authorization: Bearer <access_token>` 헤더로 그대로 재사용한다.

### 1.3 테이블 직접 접근

프로필·반려동물·사용 로그·미션·코인·상점 등은 Supabase 클라이언트로 테이블을 직접 읽고 쓴다. 접근 가능 범위는 RLS 정책이 결정하며(본인 행만 접근 가능), 마이그레이션 파일(`supabase/migrations/`)이 스키마의 소스오브트루스다. 정확한 타입이 필요하면 `supabase gen types typescript --local`로 생성해 공유한다.

### 1.4 RPC 함수 (프런트가 직접 호출)

전부 로그인 세션(`authenticated` 역할) 필요. `p_request_id`가 있는 함수는 **멱등성 키**다 — 호출마다 새 UUID를 생성해서 넣어야 중복 요청이 막힌다. 모든 함수가 `auth.uid()`로 본인만 대상으로 하므로 `user_id`는 파라미터로 받지 않는다.

| 함수 | 파라미터 | 리턴 | 설명 |
|---|---|---|---|
| `buy_item` | `p_item_id uuid, p_request_id uuid` | `void` | 상점 아이템 구매 |
| `complete_mission` | `p_user_mission_id uuid, p_request_id uuid` | `void` | 미션 완료 처리 |
| `check_in` | 없음 | `table(streak int, coins_awarded int)` | 출석 체크 |
| `pet_interact` | `p_pet_id uuid` | `table(new_affection int, hearts_gained int)` | 펫 상호작용(쓰다듬기 등) |
| `record_pet_call` | 없음 | `int` | 펫 부르기 기록 |
| `weekly_report` | `p_week_offset int default 0` | `table(week text, total_minutes int, days_compared int)` | 주간 리포트 합계 (FastAPI `/reports/weekly`가 이미 조합해서 주므로, 프런트가 직접 쓸 필요는 보통 없음) |
| `weekly_report_daily` | `p_week_offset int default 0` | `table(week text, usage_date date, total_minutes int)` | 주간 리포트 일별 (위와 동일) |
| `weekly_report_by_app` | `p_week_offset int default 0` | `table(app_name text, total_minutes int)` | 주간 리포트 앱별 (위와 동일) |

**호출하면 안 되는 함수** (내부/서버 전용, 호출 권한 없음): `mission_achieved`(부정 수령 방지로 명시적 차단), `users_to_notify_today`(알림 Edge Function 전용), `settle_missions`·`generate_daily_missions`(cron 전용), `handle_new_user`·`enforce_pet_slot_limit`(DB 트리거).

## 2. FastAPI

베이스 URL: `https://d2g07sp7f6lhnf.cloudfront.net`

(CloudFront가 EC2 앞단에서 HTTPS를 종단한다. `http://` 원본 EC2 주소로 직접 호출하지 말 것 — Android 9+는 평문 HTTP를 기본 차단한다.)

인증이 필요한 엔드포인트는 Supabase 로그인 세션의 `access_token`을 `Authorization: Bearer <access_token>` 헤더로 보낸다. 로그인 자체는 위 1.2의 Supabase Auth SDK로 한다.

### `GET /health`
인증 불필요.
```json
// 200
{ "status": "ok" }
```

### `POST /auth/signup`
인증 불필요. 이메일/비밀번호로 Supabase Auth 계정을 생성한다.
```json
// request
{ "email": "user@example.com", "password": "········" }

// 200
{ "user_id": "uuid 또는 null" }

// 400 (가입 실패, 예: 이미 가입된 이메일)
{ "detail": "에러 메시지" }
```

### `GET /me`
인증 필요.
```json
// 200
{ "user_id": "uuid" }

// 401 (토큰 없음/만료/서명 불일치)
{ "detail": "invalid token: ..." }
```

### `GET /reports/weekly?week_offset=0`
인증 필요. `week_offset`은 0 이하 정수만 허용(0=이번 주, -1=지난 주 …).
```json
// 200
{
  "last_week_minutes": 420,
  "this_week_minutes": 300,
  "change_pct": -28.6,
  "days_compared": 7,
  "message": "지난주보다 28.6% 줄였어요!",
  "daily": [
    { "week": "이번주", "date": "2026-09-21", "minutes": 45 }
  ],
  "by_app": [
    { "app_name": "Instagram", "minutes": 120 }
  ]
}
```
- `change_pct`는 지난주 기록이 없거나 이번 주가 막 시작됐으면 `null`이고, 그에 맞는 `message`가 온다.
- 502는 Supabase RPC 호출 자체가 실패한 경우다.

인증 실패(401) 응답 형식은 `/me`와 동일하다.
