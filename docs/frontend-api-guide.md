# 프런트엔드 API 가이드

## 0. 먼저 알아둘 것 3가지

1. **호출 경로가 두 개다.** 대부분은 Supabase SDK로 직접 하고, FastAPI 서버는 3가지(회원가입, 본인 확인, 주간 리포트)만 쓴다.
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
| 회원가입 | FastAPI `POST /auth/signup` | [2.1](#21-회원가입) |
| 로그인 / 로그아웃 | Supabase Auth SDK | [2.2](#22-로그인--로그아웃) |
| 내 프로필 조회·수정 (닉네임, 목표 시간, FCM 토큰 등) | 테이블 `profiles` | [3.1](#31-프로필) |
| 펫 목록·생성·이름 변경·삭제 | 테이블 `pets` | [3.2](#32-펫) |
| 펫 사진 업로드 | Storage 버킷 `pet-photos` | [3.3](#33-펫-사진) |
| 펫 쓰다듬기 (하트) | RPC `pet_interact` | [4](#4-rpc-함수) |
| 펫 부르기 기록 | RPC `record_pet_call` | [4](#4-rpc-함수) |
| 출석 체크 | RPC `check_in` | [4](#4-rpc-함수) |
| 오늘의 미션 보기 | 테이블 `user_missions` + `missions` | [3.4](#34-미션) |
| 미션 보상 받기 | RPC `complete_mission` | [4](#4-rpc-함수) |
| 코인 잔액 | RPC `coin_balance` | [3.5](#35-코인) |
| 상점 목록 | 테이블 `items` | [3.6](#36-상점--내-아이템) |
| 아이템 구매 | RPC `buy_item` | [4](#4-rpc-함수) |
| 아이템 장착/해제 | 테이블 `user_items`의 `is_equipped` | [3.6](#36-상점--내-아이템) |
| 앱 사용시간 업로드 | 테이블 `daily_usage` upsert | [3.7](#37-사용시간-업로드) |
| 알림 설정 | 테이블 `notification_settings` | [3.8](#38-알림-설정) |
| 주간 리포트 | FastAPI `GET /reports/weekly` | [5.3](#53-get-reportsweekly) |

## 2. 인증

### 2.1 회원가입

FastAPI로 한다 (Supabase SDK의 `signUp` 아님).

```
POST https://d2g07sp7f6lhnf.cloudfront.net/auth/signup
Content-Type: application/json

{ "email": "user@example.com", "password": "비밀번호" }
```

| 응답 | 본문 | 의미 |
|---|---|---|
| 200 | `{ "user_id": "uuid" }` | 가입 성공 (`user_id`가 `null`일 수도 있음) |
| 400 | `{ "detail": "에러 메시지" }` | 가입 실패 (이미 가입된 이메일 등) |

가입하면 `profiles` 행은 서버가 자동으로 만든다. 가입 후 바로 2.2의 로그인을 호출한다.

### 2.2 로그인 / 로그아웃

Supabase SDK로 직접 한다.

```dart
await supabase.auth.signInWithPassword(email: email, password: password);
await supabase.auth.signOut();

// FastAPI 호출 시 붙일 토큰
final token = supabase.auth.currentSession?.accessToken;
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
- `fcm_token`: 앱 실행 시마다 FCM 토큰으로 갱신한다 (미션 알림 발송에 쓰임)
- `pet_slot_limit`: 읽기 전용, 보유 가능한 펫 수

```dart
final me = await supabase.from('profiles').select().single();
await supabase.from('profiles')
    .update({'nickname': '새닉네임'})
    .eq('id', supabase.auth.currentUser!.id);
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

```dart
final uid = supabase.auth.currentUser!.id;
final path = '$uid/${DateTime.now().millisecondsSinceEpoch}.png';
await supabase.storage.from('pet-photos').uploadBinary(path, bytes);
// pets.source_photo_url 등에는 path를 저장한다
final url = await supabase.storage.from('pet-photos').createSignedUrl(path, 3600);
```

### 3.4 미션

테이블 `user_missions` (내 미션 상태) + `missions` (미션 내용). 둘 다 조회만 가능하다.

미션은 서버가 매일 자동으로 만든다. 날짜 기준은 한국 시간(KST)이다.

```dart
final missions = await supabase
    .from('user_missions')
    .select('id, status, coins_earned, missions(title, metric, target_minutes, target_count, reward_coins, valid_date)');
```

| 필드 | 설명 |
|---|---|
| `user_missions.id` | 보상 받을 때 `complete_mission`에 넘기는 id |
| `status` | `in_progress` / `completed` / `failed` |
| `missions.metric` | `usage_minutes`(사용시간 N분 이하) 또는 `pet_calls`(펫 호출 N회 이하) |
| `missions.target_minutes` / `target_count` | metric에 따라 둘 중 하나만 값이 있음 |
| `missions.valid_date` | 미션 날짜 |

**보상은 미션 날짜가 지난 뒤에 받을 수 있다.** 오늘 미션은 오늘 받을 수 없고, 다음 날부터 `complete_mission`으로 받는다. 받지 않아도 서버가 자정 넘어 자동으로 정산한다.

**그날 사용시간이 한 번도 업로드되지 않았으면(3.7) 미션은 실패로 처리된다.**

### 3.5 코인

**잔액은 `coin_balance` RPC로 받는다.** 숫자 하나가 온다.

```dart
final int balance = await supabase.rpc('coin_balance');
```

획득·사용 내역 화면이 필요하면 테이블 `coin_ledger`(조회만)를 읽는다. 코인이 들고 날 때마다 한 줄씩 쌓인다.

| 필드 | 설명 |
|---|---|
| `amount` | 양수 = 획득, 음수 = 사용 |
| `reason` | 획득/사용 이유 (예: `attendance`, `mission_complete`) |

### 3.6 상점 / 내 아이템

- `items` (상점 목록, 조회만): `name`, `type`, `price_coins`, `image_url`
  - `type`: `clothing`(옷) / `furniture`(가구) / `theme`(방 배경) / `pet_slot`(펫 슬롯 +1)
- `user_items` (내가 산 것): 조회 가능, `is_equipped`만 수정 가능
  - 장착/해제는 `is_equipped`를 `true`/`false`로 바꾼다. 같은 종류를 하나만 장착하게 하는 처리는 앱에서 한다.
  - 구매는 반드시 `buy_item` RPC로 한다. `pet_slot`은 `user_items`에 생기지 않고 `profiles.pet_slot_limit`가 1 늘어난다.

### 3.7 사용시간 업로드

테이블 `daily_usage`. 앱이 측정한 사용시간을 **하루·앱마다 한 줄**로 올린다. 같은 날 다시 올리면 덮어쓰도록 upsert를 쓴다.

```dart
await supabase.from('daily_usage').upsert({
  'user_id': uid,
  'app_id': appId,          // detected_apps.id
  'usage_date': '2026-09-23', // 기기 날짜 (KST)
  'minutes': 42,             // 그날 누적 분
});
```

- `app_id`는 테이블 `detected_apps`(조회만)에서 가져온다. 현재 틱톡, 인스타그램, 유튜브가 있고, 앱 전체 사용시간 기준이다.
- 사용자가 추적할 앱을 켜고 끄는 설정은 `user_detected_apps`(`app_id`, `is_enabled`)에 저장한다.

### 3.8 알림 설정

테이블 `notification_settings`: `mission_alert`, `report_alert` (둘 다 기본 `true`)

행이 자동으로 생기지 않는다. 처음 저장할 때 `user_id`를 넣어 upsert한다. 행이 없으면 둘 다 켜진 것으로 본다.

## 4. RPC 함수

코인·애착도처럼 조작되면 안 되는 값은 이 함수들로만 바뀐다. 모두 로그인 상태에서만 호출할 수 있고, 서버가 알아서 "나"를 대상으로 하므로 user id는 넘기지 않는다.

```dart
final result = await supabase.rpc('check_in');
await supabase.rpc('buy_item', params: {
  'p_item_id': itemId,
  'p_request_id': const Uuid().v4(),
});
```

| 함수 | 넘길 값 | 돌려받는 값 | 하는 일 |
|---|---|---|---|
| `check_in` | 없음 | `[{streak, coins_awarded}]` | 출석. 5코인, 연속 7일마다 +30코인. 같은 날 다시 불러도 코인은 한 번만 들어온다(`coins_awarded` = 0) |
| `pet_interact` | `p_pet_id` | `[{new_affection, hearts_gained}]` | 애착도 +5. 펫당 하루 최대 +50, 최대 100 |
| `record_pet_call` | 없음 | 숫자 (오늘 누적 호출 수) | 펫을 부를 때마다 호출 |
| `coin_balance` | 없음 | 숫자 (현재 코인 잔액) | 잔액 조회 |
| `complete_mission` | `p_user_mission_id`, `p_request_id` | 없음 | 미션 보상 받기 |
| `buy_item` | `p_item_id`, `p_request_id` | 없음 | 아이템 구매 |

**`p_request_id`란?** 네트워크 재시도로 같은 요청이 두 번 가도 코인이 두 번 처리되지 않게 하는 값이다. **버튼을 누를 때마다 새 UUID를 만들고, 재시도할 때는 같은 UUID를 다시 쓴다.**

### RPC 에러 메시지

에러는 `PostgrestException`으로 오고, `message`에 아래 문구가 들어 있다.

| 함수 | message | 의미 / 화면 처리 |
|---|---|---|
| `buy_item` | `코인이 부족합니다` | 잔액 부족 |
| `buy_item` | `item not found` | 없는 아이템 id |
| `complete_mission` | `mission not finished` | 아직 미션 날짜가 안 지남 (오늘 미션) |
| `complete_mission` | `mission target not met` | 목표 달성 실패 |
| `complete_mission` | `mission not found` | 없는 미션 id |
| `complete_mission` | `mission not found or already completed` | 이미 실패 처리된 미션 등 |
| `complete_mission` | `only daily missions can be claimed` | 주간 미션은 아직 미지원 |
| `pet_interact` | `pet not found` | 내 펫이 아님 |

이미 보상을 받은(자동 정산 포함) 미션에 `complete_mission`을 다시 부르면 에러 없이 조용히 성공한다.

### 부르면 안 되는 함수

`mission_achieved`, `settle_missions`, `generate_daily_missions`, `users_to_notify_today`, `weekly_report*`: 서버 전용이다. 권한이 없어서 에러가 나거나, 주간 리포트처럼 FastAPI가 이미 가공해서 주는 것들이다.

## 5. FastAPI 엔드포인트

베이스 URL: `https://d2g07sp7f6lhnf.cloudfront.net`

| 메서드 | 경로 | 로그인 필요 | 용도 |
|---|---|---|---|
| GET | `/health` | X | 서버 살아있는지 확인 |
| POST | `/auth/signup` | X | 회원가입 ([2.1](#21-회원가입)) |
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
