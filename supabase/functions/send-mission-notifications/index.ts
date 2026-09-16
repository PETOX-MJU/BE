// ADR-18(FR-057): 매일 미션 생성(generate_daily_missions, 06:00) 직후
// Supabase Cron Jobs가 이 함수를 호출해(06:05) 알림 대상자에게 FCM을 보낸다.
// https://app.notion.com/p/3dc73962994081e78f5fe45c34bd986a
//
// npm:firebase-admin이 Deno(Supabase Edge Function 런타임)에서 실제로 동작하는지는
// ADR-18 작성 시점엔 미검증이었다 — 스파이크로 확인 완료(OAuth2 JWT 서명 → 구글
// 토큰 교환 → FCM 요청까지 전 구간이 정상 동작, 가짜 서비스 계정이라 마지막에
// invalid_grant로만 실패함). 그래서 OAuth2 직접 서명 fallback은 구현하지 않는다.
import { createClient } from "https://esm.sh/@supabase/supabase-js@2";
import admin from "npm:firebase-admin@12";

const supabase = createClient(
  Deno.env.get("SUPABASE_URL")!,
  Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!,
);

const serviceAccount = JSON.parse(Deno.env.get("FCM_SERVICE_ACCOUNT_JSON")!);
const app = admin.initializeApp({
  credential: admin.credential.cert(serviceAccount),
});
const messaging = admin.messaging(app);

Deno.serve(async () => {
  const { data: recipients, error } = await supabase.rpc(
    "users_to_notify_today",
  );
  if (error) {
    return Response.json({ error: error.message }, { status: 500 });
  }

  let sent = 0;
  let failed = 0;
  // 유저 하나가 실패해도(토큰 만료 등) 나머지는 계속 — generate_daily_missions()의
  // 유저별 루프와 같은 톤(한 명의 실패가 배치 전체를 막지 않는다).
  for (const { fcm_token } of recipients ?? []) {
    try {
      await messaging.send({
        token: fcm_token,
        notification: {
          title: "오늘의 미션이 도착했어요",
          body: "앱을 열어 오늘의 목표를 확인해보세요.",
        },
      });
      sent++;
    } catch (_e) {
      failed++;
    }
  }

  return Response.json({ sent, failed });
});
