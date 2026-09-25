# 프런트엔드 API 가이드

## 0. 먼저 알아둘 것 3가지

1. **호출 경로가 두 개다.** 대부분은 Supabase SDK(`@supabase/supabase-js`)로 직접 하고, FastAPI 서버는 주간 리포트(와 토큰 확인)에만 쓴다.
2. **로그인하면 받는 `access_token` 하나로 둘 다 쓴다.** Supabase SDK는 알아서 붙이고, FastAPI에는 `Authorization: Bearer <access_token>` 헤더로 직접 붙인다.
3. **코인·레벨·애착도는 직접 못 바꾼다.** 반드시 RPC 함수를 호출해야 한다. 테이블에 직접 쓰면 권한 에러가 난다.

### 접속 정보

| 항목 | 값 |
|---|---|
| FastAPI 베이스 URL | `https://d2g07sp7f6lhnf.cloudfront.net` |
| Supabase URL / anon 키 | 백엔드 담당에게 받기 (대시보드 → Project Settings → API Keys의 `Publishable key`) |

- `service_role`(`Secret key`)은 **절대** 앱에 넣지 않는다. 모든 보안 규칙을 무시하는 관리자 키다.
- `http://` EC2 주소로 직접 호출하지 않는다. Android 9 이상은 평문 HTTP를 막는다.

## 1. 기능별로 뭘 호출하나

| 하고 싶은 것 | 방법 | 자세히 |
|---|---|---|
| 회원가입 | Supabase Auth SDK `signUp` | [2.1](#21-회원가입) |
| 로그인 / 로그아웃 | Supabase Auth SDK | [2.2](#22-로그인--로그아웃) |
| 내 프로필 조회·수정 (닉네임, 목표 시간, FCM 토큰 등) | 테이블 `profiles` | [3.1](#31-프로필) |
| 펫 목록·생성·이름 변경·삭제 | 테이블 `pets` | [3.2](#32-펫) |
| 펫 사진 업로드 | Storage 버킷 `pet-photos` | [3.3](#33-펫-사진) |
| 펫 쓰다듬기 (하트) | RPC `pet_interact` | [4](#4-rpc-함수) |
| 펫 부르기 기록 | RPC `record_pet_call` | [4](#4-rpc-함수) |
| 출석 체크 | RPC `check_in` | [4](#4-rpc-함수) |
| 미션 판정 | 폰 분석기 (`Missions.kt`) | [3.4](#34-미션) |
| 미션 보상 받기 | RPC `claim_mission_reward` | [3.4](#34-미션) |
| 코인 잔액 | RPC `coin_balance` | [3.5](#35-코인) |
| 상점 목록 | 테이블 `items` | [3.6](#36-상점--내-아이템) |
| 아이템 구매 | RPC `buy_item` | [4](#4-rpc-함수) |
| 아이템 장착/해제 | 테이블 `user_items`의 `is_equipped` | [3.6](#36-상점--내-아이템) |
| 알림 설정 | 테이블 `notification_settings` | [3.8](#38-알림-설정) |
| 주간 리포트 | FastAPI `GET /reports/weekly` | [5.3](#53-get-reportsweekly) |

## 2. 인증

### 2.1 회원가입

Supabase SDK로 직접 한다. FastAPI `POST /auth/signup`은 로그인 세션을 돌려주지 않아서, 가입 직후 프로필 저장 같은 호출을 할 수 없다. 쓰지 않는다.

```ts
const { data, error } = await supabase.auth.signUp({
  email,
  password,
  options: { data: { nickname } }, // 닉네임을 계정 정보에 같이 실어 보낸다
});
// data.session이 null이면 이메일 인증을 기다리는 상태다 (Supabase의 Confirm email 설정이 켜진 경우)
```

- 가입하면 `profiles` 행은 서버가 자동으로 만든다. `options.data.nickname`도 이때 `profiles.nickname`에 같이 저장된다. 이메일 인증 때문에 세션이 없어도 저장되므로, 가입 직후 닉네임을 따로 update할 필요가 없다.
- 카카오로 가입하면 `nickname` 대신 카카오 프로필 이름(`preferred_username`, 없으면 `name`)이 `profiles.nickname`에 들어간다.
- 세션이 있으면(`data.session`이 있으면) 바로 로그인된 상태다.

### 2.2 로그인 / 로그아웃

Supabase SDK로 직접 한다.

```ts
await supabase.auth.signInWithPassword({ email, password });
await supabase.auth.signOut();

// FastAPI 호출 시 붙일 토큰
const { data } = await supabase.auth.getSession();
const token = data.session?.access_token;
```

## 3. 테이블 직접 읽고 쓰기

모든 테이블은 **내 데이터만** 보이고 바뀐다. 다른 사람 행은 조회해도 빈 결과가 나온다. 그래서 `user_id`로 필터를 걸 필요는 없지만, insert할 때는 `user_id`에 내 id를 넣어야 한다.

표의 "쓸 수 있는 컬럼"에 없는 컬럼을 바꾸려 하면 `permission denied` 에러가 난다.

`profiles`와 `pets`에는 `upsert`를 쓰지 않는다. upsert는 `id`까지 update하려고 해서 권한 에러가 난다. 새로 만들 때는 `insert`, 바꿀 때는 `update`를 쓴다.

### 3.1 프로필

테이블 `profiles` (행의 `id` = 내 user id)

| 동작 | 가능 여부 |
|---|---|
| 조회 | O |
| 수정 | `nickname`, `goal_minutes`, `focus_start`, `focus_end`, `bedtime`, `fcm_token`만 |
| 생성 | 필요 없음 (가입 시 자동 생성) |

- `goal_minutes`: 하루 목표 사용시간(분), 기본값 60
- `focus_start`, `focus_end`, `bedtime`: `"HH:MM:SS"` 형식 시간
- `fcm_token`: 푸시 토큰 저장 칸. 서버 미션 알림은 꺼져 있어(ADR-37) 지금은 쓰이지 않는다
- `pet_slot_limit`: 읽기 전용, 보유 가능한 펫 수

```ts
const { data: me } = await supabase.from('profiles').select().single();
await supabase.from('profiles').update({ nickname: '새닉네임' }).eq('id', userId);
```

### 3.2 펫

테이블 `pets`

| 동작 | 가능 여부 |
|---|---|
| 조회 / 삭제 | O |
| 생성 | `user_id`, `name`, `is_default`, `source_photo_url`, `pixel_image_url`만 넣을 수 있음 |
| 수정 | `name`, `is_default`, `source_photo_url`, `pixel_image_url`만 |

- `level`, `affection`(애착도 0~100)은 읽기 전용이다. 애착도는 `pet_interact` RPC로만 오른다.
- 펫 수가 `profiles.pet_slot_limit`에 이미 찼으면 생성할 때 `pet slot limit reached` 에러가 난다. 슬롯은 상점의 `pet_slot` 아이템을 사면 늘어난다.

### 3.3 펫 사진

Storage 버킷 `pet-photos` (비공개)

- 경로는 반드시 `{내 user_id}/{파일명}` 형식. 다른 경로에는 업로드가 거부된다.
- jpeg / png / webp, 최대 5MB
- 비공개 버킷이라 공개 URL이 없다. 화면에 띄울 때는 `createSignedUrl`로 임시 URL을 만든다.

```ts
const path = `${userId}/${Date.now()}.png`;
// React Native에서는 파일을 ArrayBuffer로 바꿔서 올린다
await supabase.storage.from('pet-photos').upload(path, arrayBuffer, { contentType: 'image/png' });
// pets.source_photo_url 등에는 path를 저장한다
const { data } = await supabase.storage.from('pet-photos').createSignedUrl(path, 3600);
// data.signedUrl을 <Image>에 쓴다 (1시간 유효)
```

### 3.4 미션

**미션은 폰이 판정하고, 서버는 코인만 준다** (ADR-37). 사용시간은 서버로 보내지 않는다.

- 미션 목표·판정은 폰 분석기(AI 레포 `kotlin_port`의 `Missions.kt`)가 한다. 미션 종류는 하루(`daily`)와 야간(`night`) 두 가지다.
- 분석기가 미션을 **성공(SUCCEEDED)**으로 판정하면 `claim_mission_reward`를 부른다.

```ts
const { data: coins } = await supabase.rpc('claim_mission_reward', {
  p_kind: 'daily',        // 'daily' 또는 'night'
  p_date: '2026-09-24',   // 그 미션의 날짜 (KST, YYYY-MM-DD)
});
// coins: 이번에 받은 코인 (20, 이미 받았으면 0)
```

- 한 번에 **20코인**. 같은 `p_kind`·`p_date`는 **한 번만** 받는다. 다시 불러도 에러 없이 `0`이 온다. 그래서 재시도해도 안전하다.
- `p_date`는 **최근 7일 이내(오늘 포함)이면서 가입일 이후**만 받는다. 벗어나면 `mission date out of range` 에러가 난다.
- 야간 미션처럼 자정을 넘는 미션은 어느 날짜로 보낼지 앱에서 하나로 정해 두고 계속 같은 기준을 쓴다. 서버는 범위만 검사한다.
- 서버 테이블 `missions`·`user_missions`는 남아 있지만 **새 미션은 더 이상 만들지 않는다.** 대시보드 미션 카드는 폰 분석기 결과로 그린다.

### 3.5 코인

**잔액은 `coin_balance` RPC로 받는다.** 숫자 하나가 온다.

```ts
const { data: balance } = await supabase.rpc('coin_balance'); // number
```

획득·사용 내역 화면이 필요하면 테이블 `coin_ledger`(조회만)를 읽는다. 코인이 들고 날 때마다 한 줄씩 쌓인다.

| 필드 | 설명 |
|---|---|
| `amount` | 양수 = 획득, 음수 = 사용 |
| `reason` | 획득/사용 이유 (예: `attendance`, `mission_reward`, `item_purchase`) |

### 3.6 상점 / 내 아이템

- `items` (상점 목록, 조회만): `name`, `type`, `price_coins`, `image_url`, `theme_id`, `sort_order`
  - `theme_id`: 이 아이템이 속한 테마의 `items.id`. 테마 자신과 테마 없는 아이템은 `null`
  - `sort_order`: 테마 안에서의 단계(1부터). `theme_id`가 `null`이면 같이 `null`
  - `name`은 중복되지 않는다. 앱은 이름으로 서버 아이템과 짝을 짓는다
  - `type`: `clothing`(옷) / `furniture`(가구) / `theme`(방 배경) / `pet_slot`(펫 슬롯 +1)
- `user_items` (내가 산 것): 조회 가능, `is_equipped`만 수정 가능
  - 장착/해제는 `is_equipped`를 `true`/`false`로 바꾼다. 같은 종류를 하나만 장착하게 하는 처리는 앱에서 한다.
  - 구매는 반드시 `buy_item` RPC로 한다. `pet_slot`은 `user_items`에 생기지 않고 `profiles.pet_slot_limit`가 1 늘어난다.
- **구매 규칙** (서버가 막는다. `pet_slot`은 예외라 여러 번 살 수 있다)
  1. 이미 가진 테마·아이템은 다시 살 수 없다.
  2. 테마에 속한 아이템은 그 테마를 먼저 사야 살 수 있다.
  3. 같은 테마 안에서는 `sort_order`가 앞선 아이템을 모두 가져야 다음 것을 살 수 있다.

### 3.7 사용시간 업로드 (쓰지 않음)

사용시간은 폰 안에서만 분석하고 서버로 보내지 않는다(ADR-37). 테이블 `daily_usage`는 남아 있지만 올릴 필요가 없다.

- 감지 앱 목록 `detected_apps`(조회만)와 켜고 끄는 설정 `user_detected_apps`(`app_id`, `is_enabled`)는 그대로 쓸 수 있다.

### 3.8 알림 설정

테이블 `notification_settings`: `mission_alert`, `report_alert` (둘 다 기본 `true`)

행이 자동으로 생기지 않는다. 처음 저장할 때 `user_id`를 넣어 upsert한다. 행이 없으면 둘 다 켜진 것으로 본다.

## 4. RPC 함수

코인·애착도처럼 조작되면 안 되는 값은 이 함수들로만 바뀐다. 모두 로그인 상태에서만 호출할 수 있고, 서버가 알아서 "나"를 대상으로 하므로 user id는 넘기지 않는다.

```ts
const { data, error } = await supabase.rpc('check_in'); // data: [{ streak, coins_awarded }]

await supabase.rpc('buy_item', {
  p_item_id: itemId,
  p_request_id: requestId, // UUID v4
});
```

| 함수 | 넘길 값 | 돌려받는 값 | 하는 일 |
|---|---|---|---|
| `check_in` | 없음 | `[{streak, coins_awarded}]` | 출석. 5코인, 연속 7일마다 +30코인. 같은 날 다시 불러도 코인은 한 번만 들어온다(`coins_awarded` = 0) |
| `pet_interact` | `p_pet_id` | `[{new_affection, hearts_gained}]` | 애착도 +5. 펫당 하루 최대 +50, 최대 100 |
| `record_pet_call` | 없음 | 숫자 (오늘 누적 호출 수) | 펫을 부를 때마다 호출 |
| `coin_balance` | 없음 | 숫자 (현재 코인 잔액) | 잔액 조회 |
| `claim_mission_reward` | `p_kind`, `p_date` | 숫자 (받은 코인, 이미 받았으면 0) | 폰이 성공 판정한 미션의 보상 받기 ([3.4](#34-미션)) |
| `buy_item` | `p_item_id`, `p_request_id` | 없음 | 아이템 구매 |

**`p_request_id`란?** 네트워크 재시도로 같은 요청이 두 번 가도 코인이 두 번 처리되지 않게 하는 값이다. **버튼을 누를 때마다 새 UUID를 만들고, 재시도할 때는 같은 UUID를 다시 쓴다.**

### RPC 에러 메시지

실패하면 `{ error }`가 오고, `error.message`에 아래 문구가 들어 있다.

| 함수 | message | 의미 / 화면 처리 |
|---|---|---|
| `buy_item` | `코인이 부족합니다` | 잔액 부족 |
| `buy_item` | `item not found` | 없는 아이템 id |
| `buy_item` | `이미 보유한 아이템입니다` | 중복 구매 |
| `buy_item` | `테마를 먼저 구매해야 합니다` | 테마 없이 그 테마 아이템 구매 |
| `buy_item` | `앞 단계 아이템을 먼저 구매해야 합니다` | 순서 건너뜀 |
| `claim_mission_reward` | `mission date out of range` | 미래 날짜, 7일보다 오래된 날짜, 가입 전 날짜 |
| `claim_mission_reward` | `invalid mission kind` | `p_kind`가 `daily`·`night`가 아님 (소문자만) |
| `pet_interact` | `pet not found` | 내 펫이 아님 |

### 부르면 안 되는 함수

`complete_mission`, `mission_achieved`, `settle_missions`, `generate_daily_missions`, `users_to_notify_today`, `weekly_report*`: 서버 전용이거나 서버 미션을 끈 뒤 쓰지 않는 함수다(`complete_mission`은 서버 미션용이라 호출해도 받을 미션이 없다). 권한이 없어서 에러가 나거나, 주간 리포트처럼 FastAPI가 이미 가공해서 주는 것들이다.

## 5. FastAPI 엔드포인트

베이스 URL: `https://d2g07sp7f6lhnf.cloudfront.net`

| 메서드 | 경로 | 로그인 필요 | 용도 |
|---|---|---|---|
| GET | `/health` | X | 서버 살아있는지 확인 |
| POST | `/auth/signup` | X | 쓰지 않음. 회원가입은 SDK로 한다 ([2.1](#21-회원가입)) |
| GET | `/me` | O | 토큰 확인, 내 user id |
| GET | `/reports/weekly` | O | 주간 리포트 |

로그인 필요한 요청에는 헤더 `Authorization: Bearer <access_token>`을 붙인다. 토큰이 없거나 만료되면 **401** `{ "detail": "invalid token: ..." }`이 오고, 이때는 다시 로그인시킨다.

### 5.1 `GET /health`

```json
{ "status": "ok" }
```

### 5.2 `GET /me`

```json
{ "user_id": "uuid" }
```

### 5.3 `GET /reports/weekly`

쿼리 `week_offset`: `0` = 이번 주(기본값), `-1` = 지난 주, `-2` = 2주 전 … (0 이하만 허용, 양수를 넣으면 422)

```
GET /reports/weekly?week_offset=0
Authorization: Bearer <access_token>
```

```json
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
    { "app_name": "인스타그램", "minutes": 120 }
  ]
}
```

| 필드 | 설명 |
|---|---|
| `last_week_minutes` / `this_week_minutes` | 지난주 / 이번 주 총 사용시간(분) |
| `change_pct` | 증감률(%). 음수면 줄어든 것. 비교할 기록이 없으면 `null` |
| `days_compared` | 비교에 쓴 일수 |
| `message` | 화면에 그대로 띄우는 문구 (`change_pct`가 `null`일 때도 알맞은 문구가 옴) |
| `daily` | 일별 사용시간. `week`는 `"이번주"` / `"지난주"` |
| `by_app` | 앱별 사용시간 |

**502**가 오면 서버 내부 조회 실패다. 잠시 후 재시도한다.
