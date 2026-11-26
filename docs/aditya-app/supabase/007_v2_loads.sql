-- =====================================================================
-- Migration 007 (26 Nov 2026): Aditya Traders app VERSION 2
-- One place for every load: who changed what, when, why, and the status.
--
-- Owner's answers (26 Nov):
--   * Owner and accountant have the SAME full access ("admins").
--   * ~10 field staff: enter trucks, drivers, mills, quantities, costs,
--     photos and updates. They NEVER see purchase/sale prices, billing
--     or payments. Freight and lorry costs CAN be shown to staff.
--   * A load (truck) can be filled from several mills ("mill lines").
--   * Units used by sawmills: CFT, CBM, Pieces, Tons, Quintal, Kg,
--     Running ft, Sq ft.
--   * Size grade (provisional, editable in settings): small < 4 ft,
--     medium 4–6 ft, large > 6 ft.
--   * Amount = quantity × rate ± adjustment ("small difference").
--   * Billing lives in this app (no billbook): invoice, due date,
--     payments, billing status.
--   * A load can only be "Loaded" when every mill line is done.
--   * Every change records exact time, person, reason and status.
-- The v1 tables (trips …) are left untouched and unused.
-- =====================================================================

-- ---------- 0. Who is an admin (owner or accountant) -------------------
create or replace function public.is_admin()
returns boolean language sql stable security definer set search_path = '' as $$
  select exists (select 1 from public.profiles
                 where id = (select auth.uid()) and active and role in ('owner','accountant'));
$$;
revoke execute on function public.is_admin() from anon, public;
grant  execute on function public.is_admin() to authenticated;

alter table public.profiles add column if not exists phone text;

-- Admins (owner and accountant) manage people.
drop policy if exists "owner manages people" on public.profiles;
create policy "admins manage people" on public.profiles
  for update to authenticated
  using ((select public.is_admin())) with check ((select public.is_admin()));

-- ---------- 1. Masters --------------------------------------------------
alter table public.sawmills add column if not exists area text;
alter table public.sawmills add column if not exists contact_name text;
alter table public.parties  add column if not exists kind text not null default 'buyer'
  check (kind in ('buyer','transporter'));
alter table public.parties  add column if not exists state text;
alter table public.parties  add column if not exists credit_days integer not null default 30
  check (credit_days between 0 and 365);
alter table public.parties  add column if not exists gstin text;

drop policy if exists "owner deletes sawmills" on public.sawmills;
drop policy if exists "owner deletes parties"  on public.parties;
create policy "admins delete sawmills" on public.sawmills for delete to authenticated using ((select public.is_admin()));
create policy "admins delete parties"  on public.parties  for delete to authenticated using ((select public.is_admin()));

-- Editable settings (size grade limits). Readable by all, changed by admins.
create table public.app_settings (
  key    text primary key,
  value  numeric not null,
  label  text
);
insert into public.app_settings (key, value, label) values
  ('size_small_below_ft', 4, 'Small: shorter than (ft)'),
  ('size_large_above_ft', 6, 'Large: longer than (ft)');
alter table public.app_settings enable row level security;
create policy "members read settings"  on public.app_settings for select to authenticated using ((select public.is_member()));
create policy "admins change settings" on public.app_settings for update to authenticated
  using ((select public.is_admin())) with check ((select public.is_admin()));
revoke all on public.app_settings from anon;

-- Grade from length, using the settings above (provisional rule).
create or replace function public.size_grade_for(len numeric)
returns text language sql stable security definer set search_path = '' as $$
  select case
    when len is null then null
    when len < (select value from public.app_settings where key = 'size_small_below_ft') then 'small'
    when len > (select value from public.app_settings where key = 'size_large_above_ft') then 'large'
    else 'medium' end;
$$;
grant execute on function public.size_grade_for(numeric) to authenticated;

-- ---------- 2. Loads (one truck) ---------------------------------------
create sequence public.load_no_seq;
grant usage on sequence public.load_no_seq to authenticated;

create table public.loads (
  id                 bigint generated always as identity primary key,
  load_no            text not null unique default ('L-' || lpad(nextval('public.load_no_seq')::text, 4, '0')),
  load_date          date not null default ((now() at time zone 'Asia/Kolkata')::date),
  truck_stage        text not null default 'planning' check (truck_stage in
                     ('planning','truck_fixed','going_to_load','under_loading','loaded','in_transit','delivered','cancelled')),
  vehicle_no         text,
  capacity_t         numeric(5,1) check (capacity_t > 0),
  driver_name        text,
  driver_phone       text,
  transporter_id     bigint references public.parties(id) on delete restrict,
  freight_amount     numeric(12,2) check (freight_amount >= 0),
  party_id           bigint references public.parties(id) on delete restrict,   -- buyer
  destination        text,
  destination_state  text,
  eway_bill_no       text,
  notes              text,
  change_reason      text,                 -- why the last save was made (goes to the activity log)
  created_at         timestamptz not null default now(),
  created_by         uuid default auth.uid() references public.profiles(id) on delete set null,
  updated_at         timestamptz not null default now(),
  updated_by         uuid references public.profiles(id) on delete set null
);
create index loads_date_idx  on public.loads (load_date desc, id desc);
create index loads_party_idx on public.loads (party_id);
create index loads_trans_idx on public.loads (transporter_id);

-- ---------- 3. Mill lines (where the load was filled) -------------------
create table public.load_lines (
  id            bigint generated always as identity primary key,
  load_id       bigint not null references public.loads(id) on delete cascade,
  sawmill_id    bigint not null references public.sawmills(id) on delete restrict,
  wood_type     text not null check (length(trim(wood_type)) > 0),
  unit          text not null check (unit in ('CFT','CBM','Pieces','Tons','Quintal','Kg','Running ft','Sq ft')),
  quantity      numeric(12,3) check (quantity >= 0),
  length_ft     numeric(6,2) check (length_ft > 0),
  size_grade    text check (size_grade in ('small','medium','large','mixed')),
  line_status   text not null default 'planned' check (line_status in ('planned','loading','done')),
  loaded_on     date,
  notes         text,
  change_reason text,
  created_at    timestamptz not null default now(),
  created_by    uuid default auth.uid() references public.profiles(id) on delete set null,
  updated_at    timestamptz not null default now(),
  updated_by    uuid references public.profiles(id) on delete set null
);
create index load_lines_load_idx on public.load_lines (load_id);
create index load_lines_mill_idx on public.load_lines (sawmill_id);

-- Purchase rate per mill line: ADMINS ONLY.
create table public.line_prices (
  line_id       bigint primary key references public.load_lines(id) on delete cascade,
  rate          numeric(12,2) check (rate >= 0),
  adjustment    numeric(12,2) not null default 0,    -- the "small difference", + or −
  change_reason text,
  updated_at    timestamptz not null default now(),
  updated_by    uuid references public.profiles(id) on delete set null
);

-- ---------- 4. Lorry costs (visible to everyone) ------------------------
create table public.load_costs (
  id            bigint generated always as identity primary key,
  load_id       bigint not null references public.loads(id) on delete cascade,
  cost_type     text not null check (length(trim(cost_type)) > 0),
  amount        numeric(12,2) not null check (amount >= 0),
  paid_to       text,
  paid_on       date,
  note          text,
  change_reason text,
  created_at    timestamptz not null default now(),
  created_by    uuid default auth.uid() references public.profiles(id) on delete set null,
  updated_at    timestamptz not null default now(),
  updated_by    uuid references public.profiles(id) on delete set null
);
create index load_costs_load_idx on public.load_costs (load_id);

-- ---------- 5. Billing (ADMINS ONLY) ------------------------------------
create table public.load_billing (
  load_id         bigint primary key references public.loads(id) on delete cascade,
  invoice_no      text,
  invoice_date    date,
  sale_unit       text check (sale_unit in ('CFT','CBM','Pieces','Tons','Quintal','Kg','Running ft','Sq ft')),
  sale_qty        numeric(12,3) check (sale_qty >= 0),
  sale_rate       numeric(12,2) check (sale_rate >= 0),
  sale_adjustment numeric(12,2) not null default 0,
  gst_amount      numeric(12,2) not null default 0 check (gst_amount >= 0),
  credit_days     integer check (credit_days between 0 and 365),
  change_reason   text,
  updated_at      timestamptz not null default now(),
  updated_by      uuid references public.profiles(id) on delete set null
);

-- ---------- 6. Payments in and out (ADMINS ONLY) ------------------------
create table public.payments (
  id            bigint generated always as identity primary key,
  load_id       bigint references public.loads(id) on delete set null,
  party_kind    text not null check (party_kind in ('buyer','mill','transporter')),
  party_id      bigint references public.parties(id) on delete restrict,
  sawmill_id    bigint references public.sawmills(id) on delete restrict,
  amount        numeric(14,2) not null check (amount > 0),
  paid_on       date not null default ((now() at time zone 'Asia/Kolkata')::date),
  mode          text not null default 'bank' check (mode in ('cash','upi','bank','cheque','other')),
  reference     text,
  note          text,
  change_reason text,
  created_at    timestamptz not null default now(),
  created_by    uuid default auth.uid() references public.profiles(id) on delete set null,
  updated_at    timestamptz not null default now(),
  updated_by    uuid references public.profiles(id) on delete set null,
  check ((party_kind = 'mill' and sawmill_id is not null and party_id is null)
      or (party_kind in ('buyer','transporter') and party_id is not null and sawmill_id is null))
);
create index payments_load_idx  on public.payments (load_id);
create index payments_party_idx on public.payments (party_id);
create index payments_mill_idx  on public.payments (sawmill_id);

-- ---------- 7. Photos and files (everyone) ------------------------------
create table public.load_files (
  id            bigint generated always as identity primary key,
  load_id       bigint not null references public.loads(id) on delete cascade,
  kind          text not null default 'Other' check (length(trim(kind)) > 0),
  storage_path  text not null unique,
  file_name     text,
  mime_type     text,
  size_bytes    integer,
  created_at    timestamptz not null default now(),
  created_by    uuid default auth.uid() references public.profiles(id) on delete set null
);
create index load_files_load_idx on public.load_files (load_id);

-- ---------- 8. Activity: the single record of every change -------------
create table public.activity (
  id           bigint generated always as identity primary key,
  load_id      bigint,                      -- no FK: history survives deletes
  entity       text not null,               -- loads, load_lines, line_prices, …, note
  entity_id    text,
  action       text not null check (action in ('insert','update','delete','stage','note')),
  changes      jsonb,                       -- update: {"field": [old, new]}
  reason       text,
  truck_stage  text,                        -- the load's stage at that moment
  visibility   text not null default 'all' check (visibility in ('all','admin')),
  actor        uuid,
  at           timestamptz not null default now()
);
create index activity_load_idx on public.activity (load_id, at desc);
create index activity_at_idx   on public.activity (at desc);

create table public.load_reviews (
  load_id      bigint not null references public.loads(id) on delete cascade,
  user_id      uuid   not null default auth.uid() references public.profiles(id) on delete cascade,
  reviewed_at  timestamptz not null default now(),
  primary key (load_id, user_id)
);

-- ---------- 9. Triggers -------------------------------------------------
-- Stamp who/when on every update.
create or replace function public.v2_stamp()
returns trigger language plpgsql set search_path = '' as $$
begin
  new.updated_at := now();
  new.updated_by := auth.uid();
  return new;
end $$;

create trigger loads_stamp       before update on public.loads        for each row execute function public.v2_stamp();
create trigger load_lines_stamp  before update on public.load_lines   for each row execute function public.v2_stamp();
create trigger load_costs_stamp  before update on public.load_costs   for each row execute function public.v2_stamp();
create trigger payments_stamp    before update on public.payments     for each row execute function public.v2_stamp();
create trigger line_prices_stamp before insert or update on public.line_prices  for each row execute function public.v2_stamp();
create trigger billing_stamp     before insert or update on public.load_billing for each row execute function public.v2_stamp();

-- Mark a load as seen by the current person (their own edits never flag them).
create or replace function public.v2_touch(p_load bigint)
returns void language plpgsql security definer set search_path = '' as $$
begin
  if auth.uid() is null or p_load is null then return; end if;
  if not exists (select 1 from public.loads where id = p_load) then return; end if;
  insert into public.load_reviews (load_id, user_id, reviewed_at) values (p_load, auth.uid(), now())
  on conflict (load_id, user_id) do update set reviewed_at = excluded.reviewed_at;
end $$;
revoke execute on function public.v2_touch(bigint) from authenticated, anon, public;

-- Generic change logger. TG_ARGV[0] = visibility ('all' or 'admin').
create or replace function public.v2_log()
returns trigger language plpgsql security definer set search_path = '' as $$
declare
  skip  text[] := array['id','created_at','created_by','updated_at','updated_by','change_reason'];
  o     jsonb := case when tg_op <> 'INSERT' then to_jsonb(old) end;
  n     jsonb := case when tg_op <> 'DELETE' then to_jsonb(new) end;
  rec   jsonb := coalesce(n, o);
  lid   bigint;
  d     jsonb;
  act   text := lower(tg_op);
  st    text;
begin
  if tg_table_name = 'loads' then lid := (rec->>'id')::bigint;
  elsif tg_table_name = 'line_prices' then
    select load_id into lid from public.load_lines where id = (rec->>'line_id')::bigint;
  else lid := (rec->>'load_id')::bigint;
  end if;

  if tg_op = 'UPDATE' then
    d := public.jsonb_diff(o, n, skip);
    if d = '{}'::jsonb then return new; end if;
    if tg_table_name = 'loads' and d ? 'truck_stage' then act := 'stage'; end if;
  elsif tg_op = 'INSERT' then
    d := jsonb_strip_nulls(n) - skip;
  else
    d := jsonb_strip_nulls(o) - skip;
  end if;

  select truck_stage into st from public.loads where id = lid;
  if st is null and tg_table_name = 'loads' then st := rec->>'truck_stage'; end if;

  insert into public.activity (load_id, entity, entity_id, action, changes, reason, truck_stage, visibility, actor)
  values (lid, tg_table_name, coalesce(rec->>'id', rec->>'line_id', rec->>'load_id'), act, d,
          nullif(trim(coalesce(n->>'change_reason', '')), ''), st, tg_argv[0], auth.uid());
  perform public.v2_touch(lid);
  return coalesce(new, old);
end $$;
revoke execute on function public.v2_log() from authenticated, anon, public;

create trigger loads_log       after insert or update or delete on public.loads        for each row execute function public.v2_log('all');
create trigger load_lines_log  after insert or update or delete on public.load_lines   for each row execute function public.v2_log('all');
create trigger load_costs_log  after insert or update or delete on public.load_costs   for each row execute function public.v2_log('all');
create trigger load_files_log  after insert or delete on public.load_files             for each row execute function public.v2_log('all');
create trigger line_prices_log after insert or update or delete on public.line_prices  for each row execute function public.v2_log('admin');
create trigger billing_log     after insert or update or delete on public.load_billing for each row execute function public.v2_log('admin');
create trigger payments_log    after insert or update or delete on public.payments     for each row execute function public.v2_log('admin');

-- Business rules on the load's stage.
create or replace function public.v2_stage_rules()
returns trigger language plpgsql security definer set search_path = '' as $$
declare
  n_lines int; n_open int;
begin
  if new.truck_stage in ('truck_fixed','going_to_load','under_loading','loaded','in_transit','delivered')
     and coalesce(trim(new.vehicle_no), '') = '' then
    raise exception 'Enter the truck number before moving past Planning.' using errcode = 'P0001';
  end if;
  if new.truck_stage in ('loaded','in_transit','delivered')
     and (tg_op = 'INSERT' or new.truck_stage is distinct from old.truck_stage) then
    select count(*), count(*) filter (where line_status <> 'done')
      into n_lines, n_open from public.load_lines where load_id = new.id;
    if n_lines = 0 then
      raise exception 'Add at least one mill line before marking the load as Loaded.' using errcode = 'P0001';
    end if;
    if n_open > 0 then
      raise exception 'Cannot mark as Loaded: % mill line(s) are not done yet.', n_open using errcode = 'P0001';
    end if;
  end if;
  return new;
end $$;
revoke execute on function public.v2_stage_rules() from authenticated, anon, public;
create trigger loads_stage_rules before insert or update on public.loads
  for each row execute function public.v2_stage_rules();

-- A mill line cannot be re-opened (or added) after the truck is loaded.
create or replace function public.v2_line_rules()
returns trigger language plpgsql security definer set search_path = '' as $$
declare st text;
begin
  select truck_stage into st from public.loads where id = coalesce(new.load_id, old.load_id);
  if st in ('loaded','in_transit','delivered') then
    if tg_op = 'INSERT' or tg_op = 'DELETE' or new.line_status <> 'done' then
      raise exception 'This load is already %. Move it back to Under loading first to change its mill lines.', replace(st, '_', ' ')
        using errcode = 'P0001';
    end if;
  end if;
  if tg_op <> 'DELETE' and new.size_grade is null and new.length_ft is not null then
    new.size_grade := public.size_grade_for(new.length_ft);
  end if;
  return coalesce(new, old);
end $$;
revoke execute on function public.v2_line_rules() from authenticated, anon, public;
create trigger load_lines_rules before insert or update or delete on public.load_lines
  for each row execute function public.v2_line_rules();

-- ---------- 10. Actions the app calls ----------------------------------
create or replace function public.v2_mark_checked(p_load_ids bigint[])
returns void language plpgsql security definer set search_path = '' as $$
begin
  if not public.is_member() then raise exception 'not allowed'; end if;
  insert into public.load_reviews (load_id, user_id, reviewed_at)
  select l.id, auth.uid(), now() from public.loads l where l.id = any (p_load_ids)
  on conflict (load_id, user_id) do update set reviewed_at = excluded.reviewed_at;
end $$;
revoke execute on function public.v2_mark_checked(bigint[]) from anon, public;
grant  execute on function public.v2_mark_checked(bigint[]) to authenticated;

-- Post an update on a load (replaces phone calls / WhatsApp chatter).
-- Admins may post an admin-only note.
create or replace function public.v2_post_note(p_load bigint, p_message text, p_admin_only boolean default false)
returns void language plpgsql security definer set search_path = '' as $$
declare st text;
begin
  if not public.is_member() then raise exception 'not allowed'; end if;
  if coalesce(trim(p_message), '') = '' then raise exception 'Write the update first.'; end if;
  if p_admin_only and not public.is_admin() then raise exception 'not allowed'; end if;
  select truck_stage into st from public.loads where id = p_load;
  if st is null then raise exception 'Load not found.'; end if;
  insert into public.activity (load_id, entity, entity_id, action, changes, reason, truck_stage, visibility, actor)
  values (p_load, 'note', null, 'note', null, left(trim(p_message), 2000), st,
          case when p_admin_only then 'admin' else 'all' end, auth.uid());
  perform public.v2_touch(p_load);
end $$;
revoke execute on function public.v2_post_note(bigint, text, boolean) from anon, public;
grant  execute on function public.v2_post_note(bigint, text, boolean) to authenticated;

-- ---------- 11. Security rules -----------------------------------------
alter table public.loads        enable row level security;
alter table public.load_lines   enable row level security;
alter table public.line_prices  enable row level security;
alter table public.load_costs   enable row level security;
alter table public.load_billing enable row level security;
alter table public.payments     enable row level security;
alter table public.load_files   enable row level security;
alter table public.activity     enable row level security;
alter table public.load_reviews enable row level security;

-- Everyone approved: loads, mill lines, costs, files.
create policy "members read loads"   on public.loads for select to authenticated using ((select public.is_member()));
create policy "members add loads"    on public.loads for insert to authenticated with check ((select public.is_member()));
create policy "members edit loads"   on public.loads for update to authenticated using ((select public.is_member())) with check ((select public.is_member()));
create policy "admins delete loads"  on public.loads for delete to authenticated using ((select public.is_admin()));

create policy "members read lines"   on public.load_lines for select to authenticated using ((select public.is_member()));
create policy "members add lines"    on public.load_lines for insert to authenticated with check ((select public.is_member()));
create policy "members edit lines"   on public.load_lines for update to authenticated using ((select public.is_member())) with check ((select public.is_member()));
create policy "members delete lines" on public.load_lines for delete to authenticated using ((select public.is_member()));

create policy "members read costs"   on public.load_costs for select to authenticated using ((select public.is_member()));
create policy "members add costs"    on public.load_costs for insert to authenticated with check ((select public.is_member()));
create policy "members edit costs"   on public.load_costs for update to authenticated using ((select public.is_member())) with check ((select public.is_member()));
create policy "members delete costs" on public.load_costs for delete to authenticated using ((select public.is_member()));

create policy "members read files"   on public.load_files for select to authenticated using ((select public.is_member()));
create policy "members add files"    on public.load_files for insert to authenticated with check ((select public.is_member()));
create policy "admins delete files"  on public.load_files for delete to authenticated using ((select public.is_admin()));

-- Admins only: prices, billing, payments.
create policy "admins all prices"   on public.line_prices  for all to authenticated using ((select public.is_admin())) with check ((select public.is_admin()));
create policy "admins all billing"  on public.load_billing for all to authenticated using ((select public.is_admin())) with check ((select public.is_admin()));
create policy "admins all payments" on public.payments     for all to authenticated using ((select public.is_admin())) with check ((select public.is_admin()));

-- Activity: staff see only 'all' rows; nobody writes directly.
create policy "read activity" on public.activity for select to authenticated
  using ((select public.is_member()) and (visibility = 'all' or (select public.is_admin())));

create policy "my checks: read"   on public.load_reviews for select to authenticated using (user_id = (select auth.uid()));
create policy "my checks: add"    on public.load_reviews for insert to authenticated with check (user_id = (select auth.uid()) and (select public.is_member()));
create policy "my checks: update" on public.load_reviews for update to authenticated using (user_id = (select auth.uid())) with check (user_id = (select auth.uid()));

revoke all on public.loads, public.load_lines, public.line_prices, public.load_costs, public.load_billing,
              public.payments, public.load_files, public.activity, public.load_reviews from anon;
revoke insert, update, delete on public.activity from authenticated;

-- ---------- 12. Views the app reads ------------------------------------
-- Mill lines with purchase amount (null for staff: line_prices is hidden).
create view public.v_lines with (security_invoker = true) as
select ll.*, s.name as sawmill_name, s.place as sawmill_place, s.area as sawmill_area,
       lp.rate, lp.adjustment,
       case when lp.rate is null then null
            else round(coalesce(ll.quantity, 0) * lp.rate + coalesce(lp.adjustment, 0), 2) end as amount
  from public.load_lines ll
  join public.sawmills s on s.id = ll.sawmill_id
  left join public.line_prices lp on lp.line_id = ll.id;

-- One row per load for lists and dashboards. Money columns are null for staff.
create view public.v_loads with (security_invoker = true) as
select l.*,
       b.name  as party_name, b.city as party_city, b.state as party_state, b.phone as party_phone,
       tr.name as transporter_name, tr.phone as transporter_phone,
       coalesce(ln.n_lines, 0)  as lines_total,
       coalesce(ln.n_done, 0)   as lines_done,
       coalesce(ln.n_mills, 0)  as mills_count,
       ln.qty_summary,
       ln.cft_total,
       ln.purchase_total,
       coalesce(cs.costs_total, 0) as costs_total,
       coalesce(l.freight_amount, 0) + coalesce(cs.costs_total, 0) as transport_total,
       bl.invoice_no, bl.invoice_date,
       case when bl.sale_rate is null then null
            else round(coalesce(bl.sale_qty, 0) * bl.sale_rate + bl.sale_adjustment + bl.gst_amount, 2) end as invoice_total,
       case when bl.invoice_date is null then null
            else bl.invoice_date + coalesce(bl.credit_days, b.credit_days, 30) end as due_date,
       pin.received,
       case when not public.is_admin() then null
            when bl.invoice_no is null then case when l.truck_stage = 'delivered' then 'ready_to_bill' else 'not_ready' end
            when coalesce(pin.received, 0) >= round(coalesce(bl.sale_qty, 0) * coalesce(bl.sale_rate, 0) + bl.sale_adjustment + bl.gst_amount, 2)
                 and coalesce(bl.sale_rate, 0) > 0 then 'paid'
            when coalesce(pin.received, 0) > 0
                 or bl.invoice_date + coalesce(bl.credit_days, b.credit_days, 30) < (now() at time zone 'Asia/Kolkata')::date
                 then 'payment_pending'
            else 'billed' end as bill_stage,
       r.reviewed_at as my_reviewed_at,
       la.at     as last_at,
       la.actor  as last_by,
       la.reason as last_reason,
       la.action as last_action,
       case when r.reviewed_at is null then 'new'
            when la.at > r.reviewed_at then 'edited'
            else 'ok' end as my_flag
  from public.loads l
  left join public.parties b  on b.id  = l.party_id
  left join public.parties tr on tr.id = l.transporter_id
  left join lateral (
      select count(*) as n_lines,
             count(*) filter (where vl.line_status = 'done') as n_done,
             count(distinct vl.sawmill_id) as n_mills,
             (select string_agg(trim(to_char(q.total, 'FM999G999G990D999')) || ' ' || q.unit, ' + ' order by q.unit)
                from (select unit, sum(quantity) as total from public.load_lines
                       where load_id = l.id and quantity is not null group by unit) q) as qty_summary,
             sum(vl.quantity) filter (where vl.unit = 'CFT') as cft_total,
             sum(vl.amount) as purchase_total
        from public.v_lines vl where vl.load_id = l.id) ln on true
  left join lateral (select sum(amount) as costs_total from public.load_costs c where c.load_id = l.id) cs on true
  left join public.load_billing bl on bl.load_id = l.id
  left join lateral (select sum(amount) as received from public.payments p
                      where p.load_id = l.id and p.party_kind = 'buyer') pin on true
  left join public.load_reviews r on r.load_id = l.id and r.user_id = (select auth.uid())
  left join lateral (select a.at, a.actor, a.reason, a.action from public.activity a
                      where a.load_id = l.id order by a.at desc, a.id desc limit 1) la on true;

-- Balances per buyer, mill and transporter: admins only.
create view public.v_balances with (security_invoker = true) as
select 'buyer'::text as party_kind, p.id as party_id, null::bigint as sawmill_id, p.name, p.city as place, p.phone,
       coalesce(sum(vl.invoice_total), 0) as total_due,
       coalesce((select sum(amount) from public.payments x where x.party_kind = 'buyer' and x.party_id = p.id), 0) as total_paid,
       count(vl.id) filter (where vl.invoice_no is not null) as bills,
       min(vl.due_date) filter (where vl.bill_stage in ('billed','payment_pending')) as oldest_due
  from public.parties p left join public.v_loads vl on vl.party_id = p.id
 where p.kind = 'buyer' and public.is_admin()
 group by p.id
union all
select 'mill', null, s.id, s.name, s.place, s.phone,
       coalesce((select sum(amount) from public.v_lines z where z.sawmill_id = s.id), 0),
       coalesce((select sum(amount) from public.payments x where x.party_kind = 'mill' and x.sawmill_id = s.id), 0),
       (select count(distinct load_id) from public.load_lines z where z.sawmill_id = s.id),
       null
  from public.sawmills s where public.is_admin()
union all
select 'transporter', p.id, null, p.name, p.city, p.phone,
       coalesce((select sum(coalesce(freight_amount, 0)) from public.loads z where z.transporter_id = p.id), 0),
       coalesce((select sum(amount) from public.payments x where x.party_kind = 'transporter' and x.party_id = p.id), 0),
       (select count(*) from public.loads z where z.transporter_id = p.id),
       null
  from public.parties p where p.kind = 'transporter' and public.is_admin();

revoke all on public.v_lines, public.v_loads, public.v_balances from anon;
