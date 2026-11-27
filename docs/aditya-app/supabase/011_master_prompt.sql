-- =====================================================================
-- Migration 011 (26 Nov 2026): master product requirements.
--   * Per-person permissions (owner sets them): plan, finance, expenses, people.
--     New role 'freight' (freight and travel expense operator).
--   * Planning and Truck fixed are hidden from anyone without the 'plan'
--     permission (the database does not send those loads to staff phones).
--   * Freight and all costs become restricted "expenses" (load_costs), with
--     categories; staff never receive them. loads.freight_amount is moved
--     into expenses and dropped.
--   * Sawmill allocations: one truck trip -> many sawmill allocations ->
--     many wood items (load_lines). Owner name and party name per allocation.
--   * Driver photo standing beside the truck is mandatory before loading.
--     Driving licence and C-Book are optional.
--   * Weigh slips belong to a sawmill allocation (several per allocation OK).
--   * Sawmill rate cards with history: insert-only, never overwritten.
--   * Wood types list; units RFT and SFT; size grade chosen by hand unless
--     the owner switches automatic grading on.
-- =====================================================================

-- ---------- 1. Roles and permissions --------------------------------
do $$ declare c text; begin
  for c in select conname from pg_constraint where conrelid = 'public.profiles'::regclass and contype = 'c'
            and pg_get_constraintdef(oid) ilike '%role%' loop
    execute format('alter table public.profiles drop constraint %I', c);
  end loop;
end $$;
alter table public.profiles add constraint profiles_role_check check (role in ('owner','accountant','freight','staff'));
alter table public.profiles add column if not exists perm_plan     boolean not null default false;   -- Planning + Truck fixed
alter table public.profiles add column if not exists perm_finance  boolean not null default false;   -- rates, bills, payments, balances
alter table public.profiles add column if not exists perm_expenses boolean not null default false;   -- freight + travel expenses
alter table public.profiles add column if not exists perm_people   boolean not null default false;   -- logins, permissions, settings
-- Defaults for people who already exist. The owner always has everything.
update public.profiles set perm_plan = true, perm_finance = true, perm_expenses = true where role = 'accountant';

create or replace function public.has_perm(p text)
returns boolean language sql stable security definer set search_path = '' as $$
  select exists (select 1 from public.profiles pr
                  where pr.id = (select auth.uid()) and pr.active
                    and (pr.role = 'owner' or case p when 'plan' then pr.perm_plan when 'finance' then pr.perm_finance
                                                     when 'expenses' then pr.perm_expenses when 'people' then pr.perm_people
                                                     else false end));
$$;
revoke execute on function public.has_perm(text) from anon, public;
grant  execute on function public.has_perm(text) to authenticated;

-- is_admin() now means "can see money" (finance). Kept for older code paths.
create or replace function public.is_admin()
returns boolean language sql stable security definer set search_path = '' as $$ select public.has_perm('finance'); $$;

-- Only the owner can create another owner or hand out the 'people' permission.
create or replace function public.v2_profile_guard()
returns trigger language plpgsql security definer set search_path = '' as $$
begin
  if auth.uid() is null then return new; end if;   -- server-side (login service, which checks the caller itself)
  if not public.is_owner() and (new.role = 'owner' or old.role = 'owner' or new.perm_people is distinct from old.perm_people) then
    raise exception 'Only the owner can change owner accounts or the people permission.' using errcode = 'P0001';
  end if;
  return new;
end $$;
revoke execute on function public.v2_profile_guard() from authenticated, anon, public;
drop trigger if exists profiles_guard on public.profiles;
create trigger profiles_guard before update on public.profiles for each row execute function public.v2_profile_guard();

drop policy if exists "admins manage people" on public.profiles;
create policy "people managers manage people" on public.profiles for update to authenticated
  using ((select public.has_perm('people'))) with check ((select public.has_perm('people')));
drop policy if exists "admins change settings" on public.app_settings;
create policy "people managers change settings" on public.app_settings for update to authenticated
  using ((select public.has_perm('people'))) with check ((select public.has_perm('people')));
create policy "people managers add settings" on public.app_settings for insert to authenticated
  with check ((select public.has_perm('people')));
drop policy if exists "admins delete sawmills" on public.sawmills;
drop policy if exists "admins delete parties"  on public.parties;
create policy "owner deletes sawmills v2" on public.sawmills for delete to authenticated using ((select public.is_owner()));
create policy "owner deletes parties v2"  on public.parties  for delete to authenticated using ((select public.is_owner()));

-- Size grade: chosen by hand unless the owner switches automatic grading on (0 = off).
insert into public.app_settings (key, value, label) values ('size_auto', 0, 'Set size grade from length automatically (1 = on)')
on conflict (key) do nothing;

-- ---------- 2. Masters: wood types, expense categories ----------------
create table if not exists public.wood_types (
  name   text primary key check (length(trim(name)) > 0),
  sort   integer not null default 100,
  active boolean not null default true
);
insert into public.wood_types (name, sort) values ('Country Wood', 1), ('Acacia', 2), ('Teak', 3), ('Other', 99)
on conflict (name) do nothing;
alter table public.wood_types enable row level security;
create policy "members read wood types" on public.wood_types for select to authenticated using ((select public.is_member()));
create policy "planners add wood types" on public.wood_types for insert to authenticated with check ((select public.has_perm('plan')));
create policy "planners edit wood types" on public.wood_types for update to authenticated using ((select public.has_perm('plan'))) with check ((select public.has_perm('plan')));
revoke all on public.wood_types from anon;

create table if not exists public.expense_categories (
  name   text primary key check (length(trim(name)) > 0),
  sort   integer not null default 100,
  active boolean not null default true
);
insert into public.expense_categories (name, sort) values
  ('Truck Freight', 1), ('Fuel', 2), ('Toll', 3), ('Hamali / Loading', 4), ('Unloading', 5),
  ('Weighbridge Charges', 6), ('Other Travel Expenses', 99)
on conflict (name) do nothing;
alter table public.expense_categories enable row level security;
create policy "money people read categories" on public.expense_categories for select to authenticated
  using ((select public.has_perm('expenses')) or (select public.has_perm('finance')));
create policy "expense people add categories" on public.expense_categories for insert to authenticated with check ((select public.has_perm('expenses')));
revoke all on public.expense_categories from anon;

-- ---------- 3. Loads: capacity in CFT, freight moves to expenses ------
drop view if exists public.v_balances;
drop view if exists public.v_loads;
drop view if exists public.v_lines;

alter table public.loads add column if not exists capacity_cft numeric(8,1) check (capacity_cft > 0);

-- Expenses (was "costs"): restricted, with category, optional sawmill link and receipt.
alter table public.load_costs add column if not exists allocation_id bigint;
alter table public.load_costs add column if not exists receipt_path text;
insert into public.load_costs (load_id, cost_type, amount, paid_to, note, change_reason, created_at, created_by)
select l.id, 'Truck Freight', l.freight_amount, t.name, 'Moved from the load''s freight field', 'Freight moved to expenses (migration 011)', l.created_at, l.created_by
  from public.loads l left join public.parties t on t.id = l.transporter_id
 where l.freight_amount is not null and l.freight_amount > 0;
alter table public.loads drop column if exists freight_amount;

-- ---------- 4. Sawmill allocations -> items ---------------------------
create table if not exists public.load_allocations (
  id            bigint generated always as identity primary key,
  load_id       bigint not null references public.loads(id) on delete cascade,
  sawmill_id    bigint not null references public.sawmills(id) on delete restrict,
  owner_name    text,          -- sawmill owner (prefilled from the mill, editable)
  party_name    text,          -- party name as the mill bills it (kept separate on purpose)
  notes         text,
  change_reason text,
  created_at    timestamptz not null default now(),
  created_by    uuid default auth.uid() references public.profiles(id) on delete set null,
  updated_at    timestamptz not null default now(),
  updated_by    uuid references public.profiles(id) on delete set null,
  unique (load_id, sawmill_id)
);
create index if not exists load_allocations_load_idx on public.load_allocations (load_id);
-- Existing lines get an allocation for their (load, mill).
insert into public.load_allocations (load_id, sawmill_id, owner_name, created_at, created_by)
select distinct on (ll.load_id, ll.sawmill_id) ll.load_id, ll.sawmill_id, s.contact_name, ll.created_at, ll.created_by
  from public.load_lines ll join public.sawmills s on s.id = ll.sawmill_id
 order by ll.load_id, ll.sawmill_id, ll.id
on conflict (load_id, sawmill_id) do nothing;

alter table public.load_lines add column if not exists allocation_id bigint references public.load_allocations(id) on delete cascade;
alter table public.load_lines add column if not exists dimensions text;          -- e.g. 3" x 3" x 6'
alter table public.load_lines add column if not exists pieces integer check (pieces >= 0);
update public.load_lines ll set allocation_id = a.id from public.load_allocations a
 where a.load_id = ll.load_id and a.sawmill_id = ll.sawmill_id and ll.allocation_id is null;
alter table public.load_lines alter column allocation_id set not null;
create index if not exists load_lines_alloc_idx on public.load_lines (allocation_id);
alter table public.load_costs add constraint load_costs_allocation_fk foreign key (allocation_id) references public.load_allocations(id) on delete set null;

-- Units: RFT and SFT (old names renamed), plus the others already used.
do $$ declare c text; begin
  for c in select conname from pg_constraint where conrelid = 'public.load_lines'::regclass and contype = 'c' and pg_get_constraintdef(oid) ilike '%unit%' loop
    execute format('alter table public.load_lines drop constraint %I', c); end loop;
  for c in select conname from pg_constraint where conrelid = 'public.load_billing'::regclass and contype = 'c' and pg_get_constraintdef(oid) ilike '%sale_unit%' loop
    execute format('alter table public.load_billing drop constraint %I', c); end loop;
end $$;
update public.load_lines set unit = 'RFT' where unit = 'Running ft';
update public.load_lines set unit = 'SFT' where unit = 'Sq ft';
update public.load_billing set sale_unit = 'RFT' where sale_unit = 'Running ft';
update public.load_billing set sale_unit = 'SFT' where sale_unit = 'Sq ft';
alter table public.load_lines   add constraint load_lines_unit_check check (unit in ('CFT','CBM','RFT','SFT','Tons','Pieces','Quintal','Kg'));
alter table public.load_billing add constraint load_billing_sale_unit_check check (sale_unit in ('CFT','CBM','RFT','SFT','Tons','Pieces','Quintal','Kg'));

-- ---------- 5. Files: driver documents and per-sawmill weigh slips -----
alter table public.load_files add column if not exists allocation_id bigint references public.load_allocations(id) on delete cascade;
update public.load_files set kind = 'Weigh slip' where kind = 'Weighbridge (kata) slip';

-- ---------- 6. Sawmill rate cards (history kept, never overwritten) -----
create table if not exists public.sawmill_rates (
  id             bigint generated always as identity primary key,
  sawmill_id     bigint not null references public.sawmills(id) on delete restrict,
  wood_type      text not null,
  size_grade     text check (size_grade in ('small','medium','large')),   -- null = any size
  unit           text not null check (unit in ('CFT','CBM','RFT','SFT','Tons','Pieces','Quintal','Kg')),
  rate           numeric(12,2) not null check (rate >= 0),
  effective_from date not null default ((now() at time zone 'Asia/Kolkata')::date),
  change_reason  text,
  created_at     timestamptz not null default now(),
  created_by     uuid default auth.uid() references public.profiles(id) on delete set null
);
create index if not exists sawmill_rates_idx on public.sawmill_rates (sawmill_id, wood_type, unit, effective_from desc);
alter table public.sawmill_rates enable row level security;
create policy "finance reads rate cards" on public.sawmill_rates for select to authenticated using ((select public.has_perm('finance')));
create policy "finance adds rate cards"  on public.sawmill_rates for insert to authenticated with check ((select public.has_perm('finance')));
-- No update or delete policy: a rate change is a new row, so history stays exact.
revoke all on public.sawmill_rates from anon;

-- ---------- 7. Triggers ------------------------------------------------
-- Keep an item's load and mill in step with its allocation.
create or replace function public.v2_item_alloc()
returns trigger language plpgsql security definer set search_path = '' as $$
declare a record;
begin
  select load_id, sawmill_id into a from public.load_allocations where id = new.allocation_id;
  if not found then raise exception 'Sawmill allocation not found.' using errcode = 'P0001'; end if;
  new.load_id := a.load_id; new.sawmill_id := a.sawmill_id;
  return new;
end $$;
revoke execute on function public.v2_item_alloc() from authenticated, anon, public;
drop trigger if exists load_lines_alloc on public.load_lines;
create trigger load_lines_alloc before insert or update of allocation_id, load_id, sawmill_id on public.load_lines
  for each row execute function public.v2_item_alloc();

-- Manual size grade unless the owner switched automatic grading on.
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
  if tg_op <> 'DELETE' and new.size_grade is null and new.length_ft is not null
     and coalesce((select value from public.app_settings where key = 'size_auto'), 0) = 1 then
    new.size_grade := public.size_grade_for(new.length_ft);
  end if;
  return coalesce(new, old);
end $$;

-- Does this load have the mandatory driver-with-truck photo?
create or replace function public.v2_has_driver_photo(p_load bigint)
returns boolean language sql stable security definer set search_path = '' as $$
  select exists (select 1 from public.load_files where load_id = p_load and kind = 'Driver with truck');
$$;
revoke execute on function public.v2_has_driver_photo(bigint) from anon, public;
grant  execute on function public.v2_has_driver_photo(bigint) to authenticated;

-- Stage rules: truck number; owner-only stages; mandatory driver photo; Loaded needs every item done.
create or replace function public.v2_stage_rules()
returns trigger language plpgsql security definer set search_path = '' as $$
declare n_lines int; n_open int;
begin
  if new.truck_stage in ('truck_fixed','going_to_load','under_loading','loaded','in_transit','delivered')
     and coalesce(trim(new.vehicle_no), '') = '' then
    raise exception 'Enter the truck number before moving past Planning.' using errcode = 'P0001';
  end if;
  if (tg_op = 'INSERT' or new.truck_stage is distinct from old.truck_stage)
     and new.truck_stage in ('planning','truck_fixed','cancelled') and not public.has_perm('plan') then
    raise exception 'Only the owner can use Planning, Truck fixed or Cancel.' using errcode = 'P0001';
  end if;
  if (tg_op = 'INSERT' or new.truck_stage is distinct from old.truck_stage)
     and new.truck_stage in ('under_loading','loaded','in_transit','delivered')
     and not public.v2_has_driver_photo(new.id) then
    raise exception 'Driver photo with truck is mandatory.' using errcode = 'P0001';
  end if;
  if new.truck_stage in ('loaded','in_transit','delivered')
     and (tg_op = 'INSERT' or new.truck_stage is distinct from old.truck_stage) then
    select count(*), count(*) filter (where line_status <> 'done') into n_lines, n_open from public.load_lines where load_id = new.id;
    if n_lines = 0 then raise exception 'Add at least one sawmill item before marking the load as Loaded.' using errcode = 'P0001'; end if;
    if n_open > 0 then raise exception 'Cannot mark as Loaded: % item(s) are not done yet.', n_open using errcode = 'P0001'; end if;
  end if;
  return new;
end $$;

-- Allocations: no new/removed sawmill after Loaded; driver photo first once the truck is out of planning.
create or replace function public.v2_alloc_rules()
returns trigger language plpgsql security definer set search_path = '' as $$
declare st text; lid bigint := coalesce(new.load_id, old.load_id);
begin
  select truck_stage into st from public.loads where id = lid;
  if st in ('loaded','in_transit','delivered') and tg_op in ('INSERT','DELETE') then
    raise exception 'This load is already %. Move it back to Under loading first to change its sawmills.', replace(st, '_', ' ') using errcode = 'P0001';
  end if;
  if tg_op = 'INSERT' and st not in ('planning','truck_fixed') and not public.v2_has_driver_photo(lid) then
    raise exception 'Driver photo with truck is mandatory.' using errcode = 'P0001';
  end if;
  if tg_op = 'UPDATE' and new.load_id <> old.load_id then raise exception 'An allocation cannot move to another load.' using errcode = 'P0001'; end if;
  if tg_op = 'INSERT' and new.owner_name is null then
    select contact_name into new.owner_name from public.sawmills where id = new.sawmill_id;
  end if;
  return coalesce(new, old);
end $$;
revoke execute on function public.v2_alloc_rules() from authenticated, anon, public;
create trigger load_allocations_rules before insert or update or delete on public.load_allocations
  for each row execute function public.v2_alloc_rules();
create trigger load_allocations_stamp before update on public.load_allocations for each row execute function public.v2_stamp();
create trigger load_allocations_log after insert or update or delete on public.load_allocations for each row execute function public.v2_log('all');

-- Files: a weigh slip must name its sawmill allocation, and that allocation must be on the same load.
create or replace function public.v2_file_rules()
returns trigger language plpgsql security definer set search_path = '' as $$
begin
  if new.kind = 'Weigh slip' and new.allocation_id is null then
    raise exception 'Choose the sawmill this weigh slip belongs to.' using errcode = 'P0001';
  end if;
  if new.allocation_id is not null and not exists (select 1 from public.load_allocations where id = new.allocation_id and load_id = new.load_id) then
    raise exception 'This sawmill is not on this load.' using errcode = 'P0001';
  end if;
  return new;
end $$;
revoke execute on function public.v2_file_rules() from authenticated, anon, public;
create trigger load_files_rules before insert or update on public.load_files for each row execute function public.v2_file_rules();

-- Expenses: an allocation link must be on the same load.
create or replace function public.v2_expense_rules()
returns trigger language plpgsql security definer set search_path = '' as $$
begin
  if new.allocation_id is not null and not exists (select 1 from public.load_allocations where id = new.allocation_id and load_id = new.load_id) then
    raise exception 'This sawmill is not on this load.' using errcode = 'P0001';
  end if;
  return new;
end $$;
revoke execute on function public.v2_expense_rules() from authenticated, anon, public;
create trigger load_costs_rules before insert or update on public.load_costs for each row execute function public.v2_expense_rules();

-- Expense history is visible only to money people.
drop trigger if exists load_costs_log on public.load_costs;
create trigger load_costs_log after insert or update or delete on public.load_costs for each row execute function public.v2_log('expenses');
create trigger sawmill_rates_log after insert on public.sawmill_rates for each row execute function public.v2_log('finance');

-- Activity visibility: all / finance / expenses ('admin' becomes 'finance').
alter table public.activity drop constraint if exists activity_visibility_check;
update public.activity set visibility = 'finance' where visibility = 'admin';
alter table public.activity add constraint activity_visibility_check check (visibility in ('all','finance','expenses'));
drop trigger if exists line_prices_log on public.line_prices;
drop trigger if exists billing_log on public.load_billing;
drop trigger if exists payments_log on public.payments;
create trigger line_prices_log after insert or update or delete on public.line_prices  for each row execute function public.v2_log('finance');
create trigger billing_log     after insert or update or delete on public.load_billing for each row execute function public.v2_log('finance');
create trigger payments_log    after insert or update or delete on public.payments     for each row execute function public.v2_log('finance');

-- Notes: "money only" notes need finance; nobody posts on loads they cannot see.
create or replace function public.v2_post_note(p_load bigint, p_message text, p_admin_only boolean default false)
returns void language plpgsql security definer set search_path = '' as $$
declare st text;
begin
  if not public.is_member() then raise exception 'not allowed'; end if;
  if coalesce(trim(p_message), '') = '' then raise exception 'Write the update first.'; end if;
  if p_admin_only and not public.has_perm('finance') then raise exception 'not allowed'; end if;
  select truck_stage into st from public.loads where id = p_load;
  if st is null then raise exception 'Load not found.'; end if;
  if st in ('planning','truck_fixed') and not public.has_perm('plan') then raise exception 'not allowed'; end if;
  insert into public.activity (load_id, entity, entity_id, action, changes, reason, truck_stage, visibility, actor)
  values (p_load, 'note', null, 'note', null, left(trim(p_message), 2000), st,
          case when p_admin_only then 'finance' else 'all' end, auth.uid());
  perform public.v2_touch(p_load);
end $$;

-- ---------- 8. Row-level security ---------------------------------------
-- Loads in Planning / Truck fixed only for 'plan' people.
drop policy if exists "members read loads"  on public.loads;
drop policy if exists "members add loads"   on public.loads;
drop policy if exists "members edit loads"  on public.loads;
drop policy if exists "admins delete loads" on public.loads;
create policy "read visible loads" on public.loads for select to authenticated
  using ((select public.is_member()) and (truck_stage not in ('planning','truck_fixed') or (select public.has_perm('plan'))));
create policy "add loads" on public.loads for insert to authenticated
  with check ((select public.is_member()) and (truck_stage not in ('planning','truck_fixed') or (select public.has_perm('plan'))));
create policy "edit visible loads" on public.loads for update to authenticated
  using ((select public.is_member()) and (truck_stage not in ('planning','truck_fixed') or (select public.has_perm('plan'))))
  with check ((select public.is_member()) and (truck_stage not in ('planning','truck_fixed') or (select public.has_perm('plan'))));
create policy "owner deletes loads" on public.loads for delete to authenticated using ((select public.is_owner()));

-- Items, allocations, files: only on loads you can see.
drop policy if exists "members read lines"   on public.load_lines;
drop policy if exists "members add lines"    on public.load_lines;
drop policy if exists "members edit lines"   on public.load_lines;
drop policy if exists "members delete lines" on public.load_lines;
create policy "read items"   on public.load_lines for select to authenticated using ((select public.is_member()) and exists (select 1 from public.loads l where l.id = load_id));
create policy "add items"    on public.load_lines for insert to authenticated with check ((select public.is_member()) and exists (select 1 from public.loads l where l.id = load_id));
create policy "edit items"   on public.load_lines for update to authenticated using ((select public.is_member()) and exists (select 1 from public.loads l where l.id = load_id)) with check ((select public.is_member()));
create policy "delete items" on public.load_lines for delete to authenticated using ((select public.is_member()) and exists (select 1 from public.loads l where l.id = load_id));

alter table public.load_allocations enable row level security;
create policy "read allocations"   on public.load_allocations for select to authenticated using ((select public.is_member()) and exists (select 1 from public.loads l where l.id = load_id));
create policy "add allocations"    on public.load_allocations for insert to authenticated with check ((select public.is_member()) and exists (select 1 from public.loads l where l.id = load_id));
create policy "edit allocations"   on public.load_allocations for update to authenticated using ((select public.is_member()) and exists (select 1 from public.loads l where l.id = load_id)) with check ((select public.is_member()));
create policy "delete allocations" on public.load_allocations for delete to authenticated using ((select public.is_member()) and exists (select 1 from public.loads l where l.id = load_id));
revoke all on public.load_allocations from anon;

drop policy if exists "members read files"  on public.load_files;
drop policy if exists "members add files"   on public.load_files;
drop policy if exists "admins delete files" on public.load_files;
create policy "read files" on public.load_files for select to authenticated using ((select public.is_member()) and exists (select 1 from public.loads l where l.id = load_id));
create policy "add files"  on public.load_files for insert to authenticated with check ((select public.is_member()) and exists (select 1 from public.loads l where l.id = load_id));
create policy "remove own files or owner" on public.load_files for delete to authenticated
  using ((select public.is_owner()) or (created_by = (select auth.uid()) and (select public.is_member())));

-- Expenses: only expense or finance people; only expense people change them.
drop policy if exists "members read costs"   on public.load_costs;
drop policy if exists "members add costs"    on public.load_costs;
drop policy if exists "members edit costs"   on public.load_costs;
drop policy if exists "members delete costs" on public.load_costs;
create policy "money people read expenses" on public.load_costs for select to authenticated
  using ((select public.has_perm('expenses')) or (select public.has_perm('finance')));
create policy "expense people add expenses" on public.load_costs for insert to authenticated with check ((select public.has_perm('expenses')));
create policy "expense people edit expenses" on public.load_costs for update to authenticated
  using ((select public.has_perm('expenses'))) with check ((select public.has_perm('expenses')));
create policy "expense people delete expenses" on public.load_costs for delete to authenticated using ((select public.has_perm('expenses')));

-- Prices, bills, payments: finance only.
drop policy if exists "admins all prices"   on public.line_prices;
drop policy if exists "admins all billing"  on public.load_billing;
drop policy if exists "admins all payments" on public.payments;
create policy "finance all prices"   on public.line_prices  for all to authenticated using ((select public.has_perm('finance'))) with check ((select public.has_perm('finance')));
create policy "finance all billing"  on public.load_billing for all to authenticated using ((select public.has_perm('finance'))) with check ((select public.has_perm('finance')));
create policy "finance all payments" on public.payments     for all to authenticated using ((select public.has_perm('finance'))) with check ((select public.has_perm('finance')));

-- History: what you may see, and nothing from owner-only stages unless you plan.
drop policy if exists "read activity" on public.activity;
create policy "read activity" on public.activity for select to authenticated using (
  (select public.is_member())
  and (coalesce(truck_stage, '') not in ('planning','truck_fixed') or (select public.has_perm('plan')))
  and (visibility = 'all'
       or (visibility = 'finance'  and (select public.has_perm('finance')))
       or (visibility = 'expenses' and ((select public.has_perm('expenses')) or (select public.has_perm('finance'))))));

-- Stored files: expense receipts (path expenses/...) only for money people; uploaders may remove their own files.
drop policy if exists "lorry files: members read" on storage.objects;
create policy "lorry files: members read" on storage.objects for select to authenticated
  using (bucket_id = 'lorry-files' and (select public.is_member())
         and (name not like 'expenses/%' or (select public.has_perm('expenses')) or (select public.has_perm('finance'))));
drop policy if exists "lorry files: owner deletes" on storage.objects;
create policy "lorry files: owner or uploader deletes" on storage.objects for delete to authenticated
  using (bucket_id = 'lorry-files' and ((select public.is_owner()) or (owner = (select auth.uid()) and (select public.is_member()))));

revoke all on public.load_costs, public.sawmill_rates from anon;

-- ---------- 9. Views ----------------------------------------------------
create view public.v_lines with (security_invoker = true) as
select ll.*, s.name as sawmill_name, s.place as sawmill_place, s.area as sawmill_area,
       a.owner_name, a.party_name,
       lp.rate, lp.adjustment,
       case when lp.rate is null then null
            else round(coalesce(ll.quantity, 0) * lp.rate + coalesce(lp.adjustment, 0), 2) end as amount
  from public.load_lines ll
  join public.load_allocations a on a.id = ll.allocation_id
  join public.sawmills s on s.id = ll.sawmill_id
  left join public.line_prices lp on lp.line_id = ll.id;

create view public.v_allocations with (security_invoker = true) as
select a.*, s.name as sawmill_name, s.place as sawmill_place, s.area as sawmill_area, s.phone as sawmill_phone,
       (select count(*) from public.load_lines x where x.allocation_id = a.id) as items_total,
       (select count(*) from public.load_lines x where x.allocation_id = a.id and x.line_status = 'done') as items_done,
       (select count(*) from public.load_files f where f.allocation_id = a.id and f.kind = 'Weigh slip') as weigh_slips
  from public.load_allocations a join public.sawmills s on s.id = a.sawmill_id;

create view public.v_loads with (security_invoker = true) as
select l.*,
       b.name  as party_name, b.city as party_city, b.state as party_state, b.phone as party_phone,
       tr.name as transporter_name, tr.phone as transporter_phone,
       coalesce(ln.n_lines, 0)  as lines_total,
       coalesce(ln.n_done, 0)   as lines_done,
       coalesce(ln.n_mills, 0)  as mills_count,
       ln.qty_summary, ln.cft_total, ln.purchase_total,
       case when public.has_perm('expenses') or public.has_perm('finance') then coalesce(cs.costs_total, 0) end as costs_total,
       case when public.has_perm('expenses') or public.has_perm('finance') then cs.freight_total end as freight_total,
       case when public.has_perm('expenses') or public.has_perm('finance') then coalesce(cs.costs_total, 0) end as transport_total,
       fl.driver_photo, fl.licence_doc, fl.cbook_doc, fl.weigh_slips,
       coalesce(al.allocs_without_slip, 0) as allocs_without_slip,
       bl.invoice_no, bl.invoice_date,
       case when bl.sale_rate is null then null
            else round(coalesce(bl.sale_qty, 0) * bl.sale_rate + bl.sale_adjustment + bl.gst_amount, 2) end as invoice_total,
       case when bl.invoice_date is null then null
            else bl.invoice_date + coalesce(bl.credit_days, b.credit_days, 30) end as due_date,
       pin.received,
       case when not public.has_perm('finance') then null
            when bl.invoice_no is null then case when l.truck_stage = 'delivered' then 'ready_to_bill' else 'not_ready' end
            when coalesce(pin.received, 0) >= round(coalesce(bl.sale_qty, 0) * coalesce(bl.sale_rate, 0) + bl.sale_adjustment + bl.gst_amount, 2)
                 and coalesce(bl.sale_rate, 0) > 0 then 'paid'
            when coalesce(pin.received, 0) > 0
                 or bl.invoice_date + coalesce(bl.credit_days, b.credit_days, 30) < (now() at time zone 'Asia/Kolkata')::date
                 then 'payment_pending'
            else 'billed' end as bill_stage,
       r.reviewed_at as my_reviewed_at,
       la.at as last_at, la.actor as last_by, la.reason as last_reason, la.action as last_action,
       case when r.reviewed_at is null then 'new' when la.at > r.reviewed_at then 'edited' else 'ok' end as my_flag
  from public.loads l
  left join public.parties b  on b.id  = l.party_id
  left join public.parties tr on tr.id = l.transporter_id
  left join lateral (
      select count(*) as n_lines,
             count(*) filter (where vl.line_status = 'done') as n_done,
             count(distinct vl.sawmill_id) as n_mills,
             (select string_agg(rtrim(to_char(q.total, 'FM999G999G990D999'), '.') || ' ' || q.unit, ' + ' order by q.unit)
                from (select unit, sum(quantity) as total from public.load_lines
                       where load_id = l.id and quantity is not null group by unit) q) as qty_summary,
             sum(vl.quantity) filter (where vl.unit = 'CFT') as cft_total,
             sum(vl.amount) as purchase_total
        from public.v_lines vl where vl.load_id = l.id) ln on true
  left join lateral (select sum(amount) as costs_total, sum(amount) filter (where cost_type = 'Truck Freight') as freight_total
                       from public.load_costs c where c.load_id = l.id) cs on true
  left join lateral (select bool_or(f.kind = 'Driver with truck') as driver_photo,
                            bool_or(f.kind = 'Driving licence') as licence_doc,
                            bool_or(f.kind = 'C-Book / RC') as cbook_doc,
                            count(*) filter (where f.kind = 'Weigh slip') as weigh_slips
                       from public.load_files f where f.load_id = l.id) fl on true
  left join lateral (select count(*) as allocs_without_slip from public.load_allocations a
                      where a.load_id = l.id and not exists (select 1 from public.load_files f where f.allocation_id = a.id and f.kind = 'Weigh slip')) al on true
  left join public.load_billing bl on bl.load_id = l.id
  left join lateral (select sum(amount) as received from public.payments p where p.load_id = l.id and p.party_kind = 'buyer') pin on true
  left join public.load_reviews r on r.load_id = l.id and r.user_id = (select auth.uid())
  left join lateral (select a.at, a.actor, a.reason, a.action from public.activity a
                      where a.load_id = l.id order by a.at desc, a.id desc limit 1) la on true;

create view public.v_balances with (security_invoker = true) as
select 'buyer'::text as party_kind, p.id as party_id, null::bigint as sawmill_id, p.name, p.city as place, p.phone,
       coalesce(sum(vl.invoice_total), 0) as total_due,
       coalesce((select sum(amount) from public.payments x where x.party_kind = 'buyer' and x.party_id = p.id), 0) as total_paid,
       count(vl.id) filter (where vl.invoice_no is not null) as bills,
       min(vl.due_date) filter (where vl.bill_stage in ('billed','payment_pending')) as oldest_due
  from public.parties p left join public.v_loads vl on vl.party_id = p.id
 where p.kind = 'buyer' and public.has_perm('finance')
 group by p.id
union all
select 'mill', null, s.id, s.name, s.place, s.phone,
       coalesce((select sum(amount) from public.v_lines z where z.sawmill_id = s.id), 0),
       coalesce((select sum(amount) from public.payments x where x.party_kind = 'mill' and x.sawmill_id = s.id), 0),
       (select count(distinct load_id) from public.load_lines z where z.sawmill_id = s.id),
       null
  from public.sawmills s where public.has_perm('finance')
union all
select 'transporter', p.id, null, p.name, p.city, p.phone,
       coalesce((select sum(c.amount) from public.load_costs c join public.loads z on z.id = c.load_id
                  where z.transporter_id = p.id and c.cost_type = 'Truck Freight'), 0),
       coalesce((select sum(amount) from public.payments x where x.party_kind = 'transporter' and x.party_id = p.id), 0),
       (select count(*) from public.loads z where z.transporter_id = p.id),
       null
  from public.parties p where p.kind = 'transporter' and public.has_perm('finance');

revoke all on public.v_lines, public.v_loads, public.v_balances, public.v_allocations from anon;
grant select on public.v_lines, public.v_loads, public.v_balances, public.v_allocations to authenticated;
