-- 이슈 #14: 온보딩 캐릭터 생성 플로우가 사진을 올릴 Storage 버킷이 없었다.
-- pets.source_photo_url/pixel_image_url 컬럼은 이미 있지만(초기 스키마),
-- 실제 파일을 받을 곳이 없어서 업로드 자체가 불가능했다.
--
-- 변환(ML Kit)은 온디바이스에서 끝나므로(SRS 확인됨) 여기선 저장소만 준비한다.
-- 얼굴 사진이라 민감한 개인정보라, public 버킷이 아니라 RLS로 본인 파일만
-- 접근 가능하게 한다. 경로 규칙은 {user_id}/{파일명} — storage.foldername()의
-- 첫 세그먼트가 곧 소유자 확인 기준이 된다(이슈에서 제안한 방식 그대로).

insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values ('pet-photos', 'pet-photos', false, 5242880, array['image/jpeg', 'image/png', 'image/webp'])
on conflict (id) do nothing;

create policy "own pet photos select" on storage.objects for select
  using (bucket_id = 'pet-photos' and (storage.foldername(name))[1] = auth.uid()::text);

create policy "own pet photos insert" on storage.objects for insert
  with check (bucket_id = 'pet-photos' and (storage.foldername(name))[1] = auth.uid()::text);

create policy "own pet photos update" on storage.objects for update
  using (bucket_id = 'pet-photos' and (storage.foldername(name))[1] = auth.uid()::text);

create policy "own pet photos delete" on storage.objects for delete
  using (bucket_id = 'pet-photos' and (storage.foldername(name))[1] = auth.uid()::text);
