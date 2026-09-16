-- ADR-18(FR-057) 후속 수정: 이 프로젝트는 새 API 키 체계(publishable/secret)를
-- 쓰는데, secret key는 JWT가 아니라서 원래 마이그레이션(20260916080000)처럼
-- Authorization: Bearer로 보내면 Edge Function의 verify_jwt 게이트를 통과하지
-- 못한다. Supabase 공식 문서: 서비스-투-서비스 호출은 secret key를 apikey
-- 헤더에 실어야 하고, 함수 쪽은 verify_jwt를 끄고 auth: 'secret'으로 직접
-- 검증해야 한다(index.ts/config.toml도 같이 고쳤다). 여기선 cron job이 보내는
-- 헤더만 apikey로 바꾼다.
--
-- 이미 머지된 20260916080000 마이그레이션 파일은 수정하지 않는다(과거 상태
-- 기록 보존) — cron.schedule은 같은 job 이름으로 다시 부르면 정의를 덮어쓰므로
-- 이 파일이 사실상 그 job을 고치는 마이그레이션이다.
--
-- Vault 시크릿 이름도 cron_service_role_key → cron_secret_key로 바꿨다(더 이상
-- service_role JWT가 아니라 secret key이므로). 운영 DB에 다음을 실행해야 한다
-- (레포에는 안 남는다):
--   select vault.create_secret('<Settings > API Keys에서 "cron" 이름으로 만든 secret key>', 'cron_secret_key');
--   select vault.create_secret(
--     'https://slelskqkitkgekldioly.supabase.co/functions/v1/send-mission-notifications',
--     'send_mission_notifications_url'
--   );
-- (send_mission_notifications_url은 20260916080000에서 이미 만들었다면 그대로 재사용된다.)

select cron.schedule(
  'send-mission-notifications',
  '5 6 * * *',
  $$
  select net.http_post(
    url := (
      select decrypted_secret from vault.decrypted_secrets
      where name = 'send_mission_notifications_url'
    ),
    headers := jsonb_build_object(
      'apikey',
      (
        select decrypted_secret from vault.decrypted_secrets
        where name = 'cron_secret_key'
      ),
      'Content-Type', 'application/json'
    ),
    body := '{}'::jsonb
  )
  $$
);
