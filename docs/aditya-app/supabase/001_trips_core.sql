-- =====================================================================
-- Aditya Traders: trips, costs, edit history (migration 001)
-- Applied to Supabase project "aditya-traders" (ap-south-1).
--
-- What this gives the app:
--   * profiles      : who can use the app, their role, and whether the
--                     owner has approved them (active).
--   * sawmills      : where wood is loaded from.
--   * parties       : buyers the lorries go to (Rajasthan).
--   * trips         : one row per lorry trip.
--   * trip_charges  : every cost/payment against a lorry (added any time).
--   * change_log    : automatic history of every add / edit / delete.
--   * trip_reviews  : when each person last "checked" a trip. A trip that
--                     changed after your last check shows a red flag.
--
-- No timber maths here on purpose: CFT and tons are typed in as numbers.
-- The CFT formula waits for the client's Excel template (spec Q-01).
-- =====================================================================

-- ---------- 1. People ------------------------------------------------
create table public.profiles (
  id          uuid primary key references auth.users(id) on delete cascade,
  email       text,
  full_name   text not null default '',
  role        text not null default 'staff'
              check (role in ('owner','accountant','staff')),
  active      boolean not null default false,   -- owner must approve
  created_at  timestamptz not null default now()
);

-- A new login gets a profile automatically.
-- The very first login (when no active owner exists) becomes the owner;
-- everyone after that waits for the owner's approval.
create or replace function public.handle_new_user()
returns trigger language plpgsql security definer set search_path = '' as $$
declare
  has_owner boolean;
begin
  select exists (select 1 from public.profiles where role = 'owner' and active)
    into has_owner;
  insert into public.profiles (id, email, full_name, role, active)
  values (new.id, new.email,
          coalesce(new.raw_user_meta_data->>'full_name', ''),
          case when has_owner then 'staff' else 'owner' end,
          not has_owner);
  return new;
end $$;

create trigger on_auth_user_created
  after insert on auth.users
  for each row execute function public.handle_new_user();

-- Helpers used by the security rules below.
create or replace function public.is_member()
returns boolean language sql stable security definer set search_path = '' as $$
  select exists (select 1 from public.profiles
                 where id = (select auth.uid()) and active);
$$;

create or replace function public.is_owner()
returns boolean language sql stable security definer set search_path = '' as $$
  select exists (select 1 from public.profiles
                 where id = (select auth.uid()) and active and role = 'owner');
$$;

-- ---------- 2. Masters ------------------------------------------------
create table public.sawmills (
  id          bigint generated always as identity primary key,
  name        text not null check (length(trim(name)) > 0),
  place       text,            -- village / town
  phone       text,
  notes       text,
  created_at  timestamptz not null default now(),
  created_by  uuid default auth.uid() references public.profiles(id) on delete set null
);

create table public.parties (
  id          bigint generated always as identity primary key,
  name        text not null check (length(trim(name)) > 0),
  city        text,
  phone       text,
  notes       text,
  created_at  timestamptz not null default now(),
  created_by  uuid default auth.uid() references public.profiles(id) on delete set null
);

-- ---------- 3. Trips --------------------------------------------------
-- Fields are the ones the owner listed on the 24 Nov call:
-- vehicle number, driver phone, loaded from whom, how much, lorry cost,
-- which party. Status values are the three stages he named.
create table public.trips (
  id               bigint generated always as identity primary key,
  trip_date        date not null default ((now() at time zone 'Asia/Kolkata')::date),
  vehicle_no       text not null check (length(trim(vehicle_no)) > 0),
  lorry_capacity_t smallint check (lorry_capacity_t in (30, 35)),
  driver_name      text,
  driver_phone     text,
  transporter      text,
  sawmill_id       bigint references public.sawmills(id) on delete restrict,
  wood_type        text check (wood_type in ('Mango','Teak','Acacia','Other')),
  quantity_cft     numeric(10,2) check (quantity_cft >= 0),
  net_weight_t     numeric(8,3)  check (net_weight_t >= 0),
  freight_amount   numeric(12,2) check (freight_amount >= 0),
  party_id         bigint references public.parties(id) on delete restrict,
  destination      text,
  status           text not null default 'order_taken'
                   check (status in ('order_taken','on_the_way','completed')),
  notes            text,
  created_at       timestamptz not null default now(),
  created_by       uuid default auth.uid() references public.profiles(id) on delete set null,
  updated_at       timestamptz not null default now(),
  updated_by       uuid references public.profiles(id) on delete set null,
  -- last time anything about this lorry changed (trip fields OR its costs)
  last_change_at   timestamptz not null default now(),
  last_change_by   uuid references public.profiles(id) on delete set null
);
create index trips_date_idx    on public.trips (trip_date desc, id desc);
create index trips_sawmill_idx on public.trips (sawmill_id);
create index trips_party_idx   on public.trips (party_id);

-- ---------- 4. Costs against a lorry ---------------------------------
create table public.trip_charges (
  id           bigint generated always as identity primary key,
  trip_id      bigint not null references public.trips(id) on delete cascade,
  charge_type  text not null check (length(trim(charge_type)) > 0),
  amount       numeric(12,2) not null check (amount >= 0),
  paid_to      text,
  paid_on      date,
  note         text,
  created_at   timestamptz not null default now(),
  created_by   uuid default auth.uid() references public.profiles(id) on delete set null,
  updated_at   timestamptz not null default now(),
  updated_by   uuid references public.profiles(id) on delete set null
);
create index trip_charges_trip_idx on public.trip_charges (trip_id);

-- ---------- 5. History and "checked" marks ---------------------------
create table public.change_log (
  id          bigint generated always as identity primary key,
  trip_id     bigint,                 -- no FK: history survives a delete
  table_name  text not null,
  record_id   bigint not null,
  action      text not null check (action in ('insert','update','delete')),
  changes     jsonb,                  -- update: {"field": [old, new]}
  changed_by  uuid,
  changed_at  timestamptz not null default now()
);
create index change_log_trip_idx on public.change_log (trip_id, changed_at desc);

create table public.trip_reviews (
  trip_id      bigint not null references public.trips(id) on delete cascade,
  user_id      uuid   not null default auth.uid() references public.profiles(id) on delete cascade,
  reviewed_at  timestamptz not null default now(),
  primary key (trip_id, user_id)
);

-- ---------- 6. Trigger helpers ---------------------------------------
-- Fields that are bookkeeping, not business data: never shown as "edits".
create or replace function public.jsonb_diff(o jsonb, n jsonb, skip text[])
returns jsonb language sql immutable set search_path = '' as $$
  select coalesce(jsonb_object_agg(k, jsonb_build_array(o -> k, n -> k)), '{}'::jsonb)
  from jsonb_object_keys(n) as k
  where k <> all (skip) and (o -> k) is distinct from (n -> k);
$$;

-- Whoever changes a trip has obviously seen it: mark it checked for them.
create or replace function public.touch_review(p_trip bigint)
returns void language plpgsql security definer set search_path = '' as $$
begin
  if auth.uid() is null then return; end if;
  if not exists (select 1 from public.trips where id = p_trip) then return; end if;
  insert into public.trip_reviews (trip_id, user_id, reviewed_at)
  values (p_trip, auth.uid(), now())
  on conflict (trip_id, user_id) do update set reviewed_at = excluded.reviewed_at;
end $$;

-- trips: before update -> stamp who/when, only if business fields changed
create or replace function public.trips_before_update()
returns trigger language plpgsql set search_path = '' as $$
declare
  skip text[] := array['id','created_at','created_by','updated_at','updated_by',
                       'last_change_at','last_change_by'];
begin
  if public.jsonb_diff(to_jsonb(old), to_jsonb(new), skip) <> '{}'::jsonb then
    new.updated_at     := now();
    new.updated_by     := auth.uid();
    new.last_change_at := now();
    new.last_change_by := auth.uid();
  end if;
  return new;
end $$;

create trigger trips_before_update
  before update on public.trips
  for each row execute function public.trips_before_update();

-- trips: after insert/update/delete -> write history
create or replace function public.trips_log()
returns trigger language plpgsql security definer set search_path = '' as $$
declare
  skip text[] := array['id','created_at','created_by','updated_at','updated_by',
                       'last_change_at','last_change_by'];
  d jsonb;
begin
  if tg_op = 'INSERT' then
    insert into public.change_log (trip_id, table_name, record_id, action, changes, changed_by)
    values (new.id, 'trips', new.id, 'insert', to_jsonb(new) - skip, auth.uid());
    perform public.touch_review(new.id);
    return new;
  elsif tg_op = 'UPDATE' then
    d := public.jsonb_diff(to_jsonb(old), to_jsonb(new), skip);
    if d <> '{}'::jsonb then
      insert into public.change_log (trip_id, table_name, record_id, action, changes, changed_by)
      values (new.id, 'trips', new.id, 'update', d, auth.uid());
      perform public.touch_review(new.id);
    end if;
    return new;
  else
    insert into public.change_log (trip_id, table_name, record_id, action, changes, changed_by)
    values (old.id, 'trips', old.id, 'delete', to_jsonb(old) - skip, auth.uid());
    return old;
  end if;
end $$;

create trigger trips_log
  after insert or update or delete on public.trips
  for each row execute function public.trips_log();

-- trip_charges: before update -> stamp who/when
create or replace function public.charges_before_update()
returns trigger language plpgsql set search_path = '' as $$
begin
  new.updated_at := now();
  new.updated_by := auth.uid();
  return new;
end $$;

create trigger charges_before_update
  before update on public.trip_charges
  for each row execute function public.charges_before_update();

-- trip_charges: after change -> history + mark the parent lorry as changed
create or replace function public.charges_log()
returns trigger language plpgsql security definer set search_path = '' as $$
declare
  skip text[] := array['id','trip_id','created_at','created_by','updated_at','updated_by'];
  d jsonb;
  t bigint := coalesce(new.trip_id, old.trip_id);
begin
  if tg_op = 'INSERT' then
    insert into public.change_log (trip_id, table_name, record_id, action, changes, changed_by)
    values (t, 'trip_charges', new.id, 'insert', to_jsonb(new) - skip, auth.uid());
  elsif tg_op = 'UPDATE' then
    d := public.jsonb_diff(to_jsonb(old), to_jsonb(new), skip);
    if d = '{}'::jsonb then return new; end if;
    insert into public.change_log (trip_id, table_name, record_id, action, changes, changed_by)
    values (t, 'trip_charges', new.id, 'update', d, auth.uid());
  else
    insert into public.change_log (trip_id, table_name, record_id, action, changes, changed_by)
    values (t, 'trip_charges', old.id, 'delete', to_jsonb(old) - skip, auth.uid());
  end if;

  update public.trips
     set last_change_at = now(), last_change_by = auth.uid()
   where id = t;
  perform public.touch_review(t);
  return coalesce(new, old);
end $$;

create trigger charges_log
  after insert or update or delete on public.trip_charges
  for each row execute function public.charges_log();

-- ---------- 7. Actions the app calls ---------------------------------
-- "Mark as checked" for one or many lorries (the accountant's daily tick).
create or replace function public.mark_checked(p_trip_ids bigint[])
returns void language plpgsql security definer set search_path = '' as $$
begin
  if not public.is_member() then raise exception 'not allowed'; end if;
  insert into public.trip_reviews (trip_id, user_id, reviewed_at)
  select t.id, auth.uid(), now()
    from public.trips t where t.id = any (p_trip_ids)
  on conflict (trip_id, user_id) do update set reviewed_at = excluded.reviewed_at;
end $$;

-- ---------- 8. List view used by the app -----------------------------
-- my_flag: 'new'     = I have never checked this lorry
--          'edited'  = something changed after I last checked it
--          'ok'      = nothing new for me
create view public.v_trips with (security_invoker = true) as
select t.*,
       s.name  as sawmill_name,
       s.place as sawmill_place,
       p.name  as party_name,
       p.city  as party_city,
       coalesce(c.charges_total, 0)                                as charges_total,
       coalesce(t.freight_amount, 0) + coalesce(c.charges_total, 0) as total_cost,
       r.reviewed_at                                               as my_reviewed_at,
       case when r.reviewed_at is null            then 'new'
            when t.last_change_at > r.reviewed_at then 'edited'
            else 'ok' end                                          as my_flag,
       (select count(*) from public.change_log l
         where l.trip_id = t.id
           and not (l.table_name = 'trips' and l.action = 'insert'))  as change_count
  from public.trips t
  left join public.sawmills s on s.id = t.sawmill_id
  left join public.parties  p on p.id = t.party_id
  left join (select trip_id, sum(amount) as charges_total
               from public.trip_charges group by trip_id) c on c.trip_id = t.id
  left join public.trip_reviews r
         on r.trip_id = t.id and r.user_id = (select auth.uid());

-- ---------- 9. Security rules (Row-Level Security) -------------------
-- Rule of thumb for version 1 (spec Q-12 still open):
--   * only approved people (active) see or change anything;
--   * everyone approved can add/edit trips and costs (all logged);
--   * only the owner deletes trips/masters and approves people.
alter table public.profiles     enable row level security;
alter table public.sawmills     enable row level security;
alter table public.parties      enable row level security;
alter table public.trips        enable row level security;
alter table public.trip_charges enable row level security;
alter table public.change_log   enable row level security;
alter table public.trip_reviews enable row level security;

create policy "see own or team profiles" on public.profiles
  for select to authenticated
  using (id = (select auth.uid()) or (select public.is_member()));
create policy "owner manages people" on public.profiles
  for update to authenticated
  using ((select public.is_owner())) with check ((select public.is_owner()));

create policy "members read sawmills"   on public.sawmills for select to authenticated using ((select public.is_member()));
create policy "members add sawmills"    on public.sawmills for insert to authenticated with check ((select public.is_member()));
create policy "members edit sawmills"   on public.sawmills for update to authenticated using ((select public.is_member())) with check ((select public.is_member()));
create policy "owner deletes sawmills"  on public.sawmills for delete to authenticated using ((select public.is_owner()));

create policy "members read parties"    on public.parties for select to authenticated using ((select public.is_member()));
create policy "members add parties"     on public.parties for insert to authenticated with check ((select public.is_member()));
create policy "members edit parties"    on public.parties for update to authenticated using ((select public.is_member())) with check ((select public.is_member()));
create policy "owner deletes parties"   on public.parties for delete to authenticated using ((select public.is_owner()));

create policy "members read trips"      on public.trips for select to authenticated using ((select public.is_member()));
create policy "members add trips"       on public.trips for insert to authenticated with check ((select public.is_member()));
create policy "members edit trips"      on public.trips for update to authenticated using ((select public.is_member())) with check ((select public.is_member()));
create policy "owner deletes trips"     on public.trips for delete to authenticated using ((select public.is_owner()));

create policy "members read charges"    on public.trip_charges for select to authenticated using ((select public.is_member()));
create policy "members add charges"     on public.trip_charges for insert to authenticated with check ((select public.is_member()));
create policy "members edit charges"    on public.trip_charges for update to authenticated using ((select public.is_member())) with check ((select public.is_member()));
create policy "members delete charges"  on public.trip_charges for delete to authenticated using ((select public.is_member()));

create policy "members read history"    on public.change_log for select to authenticated using ((select public.is_member()));
-- no insert/update/delete policy: only the triggers write history.

create policy "my checks: read"   on public.trip_reviews for select to authenticated
  using (user_id = (select auth.uid()) and (select public.is_member()));
create policy "my checks: add"    on public.trip_reviews for insert to authenticated
  with check (user_id = (select auth.uid()) and (select public.is_member()));
create policy "my checks: update" on public.trip_reviews for update to authenticated
  using (user_id = (select auth.uid())) with check (user_id = (select auth.uid()));

-- ---------- 10. Lock out anonymous access ----------------------------
revoke all on all tables    in schema public from anon;
revoke all on all sequences in schema public from anon;
revoke execute on all functions in schema public from anon, public;
grant  execute on function public.is_member(), public.is_owner(),
                           public.mark_checked(bigint[]) to authenticated;
-- history is append-only, even for signed-in users
revoke insert, update, delete on public.change_log from authenticated;

-- ---------- Migration 002: internal helpers not callable via the API ----
revoke execute on function public.charges_log(), public.trips_log(),
                           public.handle_new_user(), public.touch_review(bigint)
  from authenticated, anon, public;
