-- 사용시간 동기화가 없는 날은 미션을 성공으로 보지 않는다. 그리고 detected_apps의
-- 이름을 실제로 측정 가능한 단위에 맞춘다.
--
-- 배경: FE(PETOX-MJU/FE)에 사용시간 수집이 아직 없다. INTERNET 권한도, supabase
-- 클라이언트도, PACKAGE_USAGE_STATS도 없는 상태다. 그래서 daily_usage에 행이 하나도
-- 안 들어오고, mission_achieved의 coalesce(..., 0)이 항상 0을 돌려줘서
-- 0 <= target이 참이 된다 — 아무것도 안 해도 매일 미션 3장이 전부 성공하고
-- 60코인이 나간다. 정산이 KST 00:05라 매일 새벽에 그렇게 된다.

-- ── 1. 동기화 기록을 성공 판정의 전제로 삼는다 ──────────────────────────
--
-- "그날 이 사용자의 daily_usage 행이 하나라도 있는가"를 앞에 건다. 0분짜리 행이라도
-- 있으면 통과한다 — 중요한 건 분 수가 아니라 그날 앱이 살아서 보고했다는 사실이다.
--
-- pet_calls 미션도 같은 조건을 쓴다. record_pet_call()은 사용자가 실제로 펫을 불렀을
-- 때만 행을 만들어서 "행 없음"이 진짜 0회일 수 있고, 그래서 daily_pet_calls 자체는
-- 동기화 신호가 못 된다. daily_usage 행의 존재를 두 metric 공통의 신호로 쓴다.
--
-- 대가: 폰을 하루 종일 안 켜서 진짜로 0분인 사용자도 실패 처리된다. 사용자가 손해
-- 보는 방향이지만, 수집이 안 붙은 채로 아무나 매일 60코인을 받는 것보다 낫다.
--
-- create or replace는 grant를 리셋하지 않으므로 기존 revoke(public, anon,
-- authenticated)가 그대로 유지된다.
create or replace function mission_achieved(p_user_id uuid, p_mission_id uuid)
returns boolean
language sql
stable
as $$
  select exists (
           select 1 from daily_usage
           where user_id = p_user_id and usage_date = m.valid_date
         )
     and case m.metric
           when 'pet_calls' then
             coalesce((select calls from daily_pet_calls
                       where user_id = p_user_id and usage_date = m.valid_date), 0)
               <= m.target_count
           else
             coalesce((select sum(minutes) from daily_usage du
                       where du.user_id = p_user_id and du.usage_date = m.valid_date
                         and (m.app_id is null or du.app_id = m.app_id)), 0)
               <= m.target_minutes
         end
  from missions m
  where m.id = p_mission_id
$$;

-- ── 2. 측정할 수 없는 이름을 쓰지 않는다 ────────────────────────────────
--
-- UsageStatsManager는 패키지 단위로만 포그라운드 시간을 준다. 같은
-- com.google.android.youtube 안에서 쇼츠와 일반 영상을 구분할 방법이 없다.
-- 그런데 display_name은 "유튜브 쇼츠", "인스타그램 릴스"로 적혀 있어서, 실제로는
-- 앱 전체 시간인 값에 쇼츠만 잰 것 같은 이름이 붙어 있었다.
--
-- 데이터는 바뀌지 않는다. 처음부터 부정확했던 라벨을 고치는 것이다. 과거
-- daily_usage 행도 app_id로 조인되므로 weekly_report_by_app에서 함께 올바른 이름으로
-- 나온다. 이미 생성된 미션의 title은 생성 시점 문자열이 박혀 있어 그대로 남고,
-- 새로 생성되는 미션부터 바뀐 이름을 쓴다.
--
-- 틱톡은 앱 전체가 숏폼이라 이름을 건드리지 않는다.
update detected_apps set display_name = '유튜브'
  where package_name = 'com.google.android.youtube';
update detected_apps set display_name = '인스타그램'
  where package_name = 'com.instagram.android';
