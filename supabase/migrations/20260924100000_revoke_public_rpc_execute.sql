-- CREATE FUNCTION은 PUBLIC에 execute를 자동으로 준다. 아래 함수들은 authenticated(또는
-- service_role)에만 grant하고 PUBLIC 회수를 빠뜨려서 anon도 호출할 수 있었다.
-- check_in·coin_balance 등과 같은 패턴으로 맞춘다.

-- auth.uid()가 NULL이라 coin_ledger NOT NULL 위반으로 실패하던 것에 기대고 있었다.
revoke execute on function buy_item(uuid, uuid) from public, anon;
revoke execute on function complete_mission(uuid, uuid) from public, anon;

-- invoker라 anon은 빈 결과만 받지만, FastAPI는 사용자 JWT(authenticated)로 부른다.
revoke execute on function weekly_report(int) from public, anon;
revoke execute on function weekly_report_daily(int) from public, anon;
revoke execute on function weekly_report_by_app(int) from public, anon;

-- 20260916070000 주석의 의도(Edge Function의 service_role 전용)대로 일반 유저를 막는다.
-- 지금은 RLS가 본인 행만 보여줘서 남의 fcm_token이 새지는 않는다.
revoke execute on function users_to_notify_today() from public, anon, authenticated;
