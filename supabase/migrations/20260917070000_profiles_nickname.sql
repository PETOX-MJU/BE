-- 이슈 #12: 회원가입·마이페이지 화면에 닉네임 입력/수정 UI가 있는데 저장할 컬럼이 없었다.
-- 기존 "own profile update"/"own profile insert" RLS 정책(id = auth.uid())이 그대로 커버한다.

alter table profiles add column nickname text;
