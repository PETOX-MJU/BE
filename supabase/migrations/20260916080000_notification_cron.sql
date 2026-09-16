-- ADR-18: 미션 알림(FR-057) 2단계 — Supabase Cron Jobs가 Edge Function을 매일
-- 06:05(generate_daily_missions, 06:00보다 5분 뒤)에 호출하게 등록한다.
-- https://app.notion.com/p/3dc73962994081e78f5fe45c34bd986a
--
-- service_role 키를 이 파일에 리터럴로 넣으면 git에 시크릿이 박힌다. 그래서 키
-- 자체는 여기 없다 — 운영 DB에 한 번 수동으로 아래를 실행해 Vault에 저장해야
-- 이 cron job이 동작한다(레포에는 안 남는다):
--   select vault.create_secret('<실제 service_role 키>', 'cron_service_role_key');

create extension if not exists pg_net with schema extensions;

select cron.schedule(
  'send-mission-notifications',
  '5 6 * * *',
  $$
  select net.http_post(
    url := 'https://slelskqkitkgekldioly.supabase.co/functions/v1/send-mission-notifications',
    headers := jsonb_build_object(
      'Authorization',
      'Bearer ' || (
        select decrypted_secret from vault.decrypted_secrets
        where name = 'cron_service_role_key'
      ),
      'Content-Type', 'application/json'
    ),
    body := '{}'::jsonb
  )
  $$
);
