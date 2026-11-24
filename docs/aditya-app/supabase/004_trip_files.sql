-- =====================================================================
-- Migration 004 (25 Nov 2026): photos and files on each lorry
-- Owner's voice note: "a way to upload the weighbridge (kanta) slip or a
-- receipt photo to the lorry". Files live in a PRIVATE storage bucket;
-- only approved people can see them, through short-lived signed links.
-- Adding or removing a file counts as a change: it is logged in the
-- history and shows the red "Edited" flag to others.
-- =====================================================================

-- 1. Private bucket: photos and PDFs only, up to 10 MB each.
insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values ('lorry-files', 'lorry-files', false, 10485760,
        array['image/jpeg','image/png','image/webp','image/heic','image/heif','application/pdf'])
on conflict (id) do nothing;

-- 2. One row per file, linked to its lorry.
create table public.trip_files (
  id            bigint generated always as identity primary key,
  trip_id       bigint not null references public.trips(id) on delete cascade,
  kind          text not null default 'Other' check (length(trim(kind)) > 0),  -- e.g. Weighbridge slip
  storage_path  text not null unique,                                          -- path inside the bucket
  file_name     text,
  mime_type     text,
  size_bytes    integer,
  note          text,
  created_at    timestamptz not null default now(),
  created_by    uuid default auth.uid() references public.profiles(id) on delete set null
);
create index trip_files_trip_idx on public.trip_files (trip_id);

-- 3. History + red flag, same as costs.
create or replace function public.files_log()
returns trigger language plpgsql security definer set search_path = '' as $$
declare
  skip text[] := array['id','trip_id','storage_path','created_at','created_by'];
  t bigint := coalesce(new.trip_id, old.trip_id);
begin
  if tg_op = 'INSERT' then
    insert into public.change_log (trip_id, table_name, record_id, action, changes, changed_by)
    values (t, 'trip_files', new.id, 'insert', to_jsonb(new) - skip, auth.uid());
  else
    insert into public.change_log (trip_id, table_name, record_id, action, changes, changed_by)
    values (t, 'trip_files', old.id, 'delete', to_jsonb(old) - skip, auth.uid());
  end if;
  update public.trips set last_change_at = now(), last_change_by = auth.uid() where id = t;
  perform public.touch_review(t);
  return coalesce(new, old);
end $$;
revoke execute on function public.files_log() from authenticated, anon, public;

create trigger files_log
  after insert or delete on public.trip_files
  for each row execute function public.files_log();

-- 4. Security: approved people see and add files; only the owner deletes.
alter table public.trip_files enable row level security;
create policy "members read files"  on public.trip_files for select to authenticated using ((select public.is_member()));
create policy "members add files"   on public.trip_files for insert to authenticated with check ((select public.is_member()));
create policy "owner deletes files" on public.trip_files for delete to authenticated using ((select public.is_owner()));
revoke all on public.trip_files from anon;

-- Same rules on the stored files themselves.
create policy "lorry files: members read" on storage.objects for select to authenticated
  using (bucket_id = 'lorry-files' and (select public.is_member()));
create policy "lorry files: members upload" on storage.objects for insert to authenticated
  with check (bucket_id = 'lorry-files' and (select public.is_member()));
create policy "lorry files: owner deletes" on storage.objects for delete to authenticated
  using (bucket_id = 'lorry-files' and (select public.is_owner()));
