-- 미션 알림 cron을 끈다. 운영 Vault에 send_mission_notifications_url이 없어 06:05 job이 매일
-- 실패 로그만 남기고, 앱에 FCM이 아직 없어 알림은 원래 나가지 않는다.
-- FCM을 붙일 때 Vault에 URL을 넣고 20260928090000의 schedule을 다시 부르면 된다.
select cron.unschedule('send-mission-notifications');
