// 이슈 #13: 회원탈퇴. auth.users 삭제는 service_role(관리자 키)로만 가능해서
// 클라이언트가 직접 못 지운다 — service_role 키를 클라이언트에 노출하면 IDOR가
// 된다. 로그인한 본인만 자기 계정을 지울 수 있어야 하므로, FR-057(ADR-18)에서
// 검증한 withSupabase 패턴을 그대로 쓰되 이번엔 auth: 'user' 모드를 쓴다 —
// 플랫폼이 이미 검증한 ctx.userClaims.id(위조 불가)로만 삭제 대상을 정하고,
// 요청 바디의 어떤 값도 대상 결정에 쓰지 않는다.
//
// profiles/pets/daily_usage/user_missions/user_items/coin_ledger/
// notification_settings/user_detected_apps 전부 auth.users FK가
// on delete cascade라(마이그레이션에서 확인) deleteUser() 한 번으로
// 연쇄 삭제된다 — 여기서 따로 지울 테이블이 없다.
import { withSupabase } from "npm:@supabase/server";

export default {
  fetch: withSupabase({ auth: "user" }, async (_req, ctx) => {
    const { error } = await ctx.supabaseAdmin.auth.admin.deleteUser(
      ctx.userClaims!.id,
    );
    if (error) {
      console.error("delete-account failed:", error.message);
      return Response.json({ error: "account deletion failed" }, {
        status: 500,
      });
    }
    return Response.json({ ok: true });
  }),
};
