// ADR-18(FR-057): 매일 미션 생성(generate_daily_missions, 06:00) 직후
// Supabase Cron Jobs가 이 함수를 호출해(06:05) 알림 대상자에게 FCM을 보낸다.
// https://app.notion.com/p/3dc73962994081e78f5fe45c34bd986a
//
// npm:firebase-admin이 Deno(Supabase Edge Function 런타임)에서 실제로 동작하는지는
// ADR-18 작성 시점엔 미검증이었다 — 스파이크로 확인 완료(OAuth2 JWT 서명 → 구글
// 토큰 교환 → FCM 요청까지 전 구간이 정상 동작, 가짜 서비스 계정이라 마지막에
// invalid_grant로만 실패함). 그래서 OAuth2 직접 서명 fallback은 구현하지 않는다.
//
// 인증: 이 프로젝트는 새 API 키 체계(publishable/secret)를 쓴다 — secret key는
// JWT가 아니라서 기본 verify_jwt(Authorization을 JWT로 파싱) 게이트를 통과 못
// 한다(Supabase 공식 문서: "Service-to-service calls... make calls with a
// secret key on the apikey header... Disable verify_jwt and use auth: 'secret'").
// 그래서 config.toml에서 verify_jwt=false로 끄고, withSupabase({auth:
// 'secret:cron'})가 apikey 헤더의 키를 직접 검증한다 — pg_cron 전용으로 이름
// 붙인 secret key만 받아서, 다른 secret key로도 이 함수가 호출되지 않게 한다.
import { withSupabase } from "npm:@supabase/server";
import admin from "npm:firebase-admin@12";

// FCM_SERVICE_ACCOUNT_JSON이 비어있거나 깨져있으면(설정 실수) JSON.parse가
// 여기서 예외를 던진다. try/catch 없이 두면 워커 자체가 모듈 로드 단계에서
// 죽어서 모든 요청이 InvalidWorkerResponse(우리가 스파이크 중 실제로 본 실패
// 모양)로 실패한다 — 원인을 알 수 없는 깨진 상태. 대신 초기화는 콜드 스타트에
// 한 번만(요청마다 안 함) 시도하고, 실패하면 깔끔한 500으로 돌려준다.
let messaging: admin.messaging.Messaging | null = null;
let initError: string | null = null;
try {
  const serviceAccount = JSON.parse(Deno.env.get("FCM_SERVICE_ACCOUNT_JSON") ?? "");
  const app = admin.initializeApp({
    credential: admin.credential.cert(serviceAccount),
  });
  messaging = admin.messaging(app);
} catch (e) {
  initError = e instanceof Error ? e.message : String(e);
}

export default {
  fetch: withSupabase({ auth: "secret:cron" }, async (_req, ctx) => {
    if (!messaging) {
      return Response.json({ error: `FCM 초기화 실패: ${initError}` }, {
        status: 500,
      });
    }

    const { data, error } = await ctx.supabaseAdmin.rpc(
      "users_to_notify_today",
    );
    if (error) {
      return Response.json({ error: error.message }, { status: 500 });
    }
    // withSupabase의 클라이언트는 DB 타입 제네릭이 없어 rpc() 반환이 never로
    // 추론된다 — 실제 런타임 shape은 users_to_notify_today()의 SQL 반환
    // 타입(user_id uuid, fcm_token text) 그대로다.
    const recipients = (data ?? []) as { fcm_token: string }[];

    let sent = 0;
    let failed = 0;
    // 유저 하나가 실패해도(토큰 만료 등) 나머지는 계속 — generate_daily_missions()의
    // 유저별 루프와 같은 톤(한 명의 실패가 배치 전체를 막지 않는다). 원인은
    // 로그로 남긴다 — 안 남기면 "sent=100, failed=5"만 보이고 왜 실패했는지
    // 알 방법이 없어진다.
    for (const { fcm_token } of recipients) {
      try {
        await messaging.send({
          token: fcm_token,
          notification: {
            title: "오늘의 미션이 도착했어요",
            body: "앱을 열어 오늘의 목표를 확인해보세요.",
          },
        });
        sent++;
      } catch (e) {
        console.error("FCM 발송 실패:", fcm_token, e);
        failed++;
      }
    }

    return Response.json({ sent, failed });
  }),
};
