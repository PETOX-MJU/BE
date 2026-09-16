-- ADR-18: 미션 알림(FR-057) 1단계 — 기기 토큰 저장소 + 발송 대상자 선정 쿼리.
-- https://app.notion.com/p/3dc73962994081e78f5fe45c34bd986a
--
-- fcm_token: 클라이언트가 앱 실행 시 직접 채운다. profiles에 이미 있는
-- "own profile update" RLS 정책(id = auth.uid())이 그대로 커버하므로
-- 새 정책이나 엔드포인트가 필요 없다.

alter table profiles add column fcm_token text;

-- 오늘 daily 미션이 막 생긴(generate_daily_missions, ADR-005) 유저 중
-- 알림을 받을 유저만 골라낸다. notification_settings는 가입 시 자동
-- 생성되지 않으므로(profiles와 다름) row가 없는 유저가 있을 수 있다 —
-- 그 경우 컬럼 기본값(true)을 존중해야 해서 INNER JOIN이 아니라
-- LEFT JOIN + coalesce를 쓴다. 이게 없으면 알림 설정을 한 번도 안 건드린
-- 유저(=기본값 그대로 켜져 있어야 할 유저)가 조용히 통째로 빠진다.
create or replace function users_to_notify_today()
returns table(user_id uuid, fcm_token text)
language sql
stable
as $$
  select p.id, p.fcm_token
  from profiles p
  join user_missions um on um.user_id = p.id
  join missions m on m.id = um.mission_id
    and m.type = 'daily' and m.valid_date = current_date
  left join notification_settings ns on ns.user_id = p.id
  where coalesce(ns.mission_alert, true)
    and p.fcm_token is not null
$$;

-- authenticated에게 주면 다른 유저의 fcm_token을 노출하는 IDOR가 된다.
-- Edge Function은 service_role 키로 호출해 RLS 자체를 우회하므로
-- security definer가 필요 없고(ADR-011의 invoker 원칙과 동일), 이 grant는
-- 일반 유저가 PostgREST RPC 경로로 못 부르게 막는 역할만 한다.
grant execute on function users_to_notify_today() to service_role;
