-- =====================================================================
-- Migration 012 (26 Nov 2026): owner's answers of 26 Nov evening.
--   1. Under loading starts only when the truck has REACHED a sawmill
--      (load_allocations.reached_at). The database refuses it otherwise.
--   2. Driver photo with the truck is compulsory (setting driver_photo_required = 1,
--      which the owner can switch off).
--   3. Weigh slip is taken when loading finishes at each sawmill
--      (load_allocations.loading_done_at, optional net weight from the slip).
--      "Loaded" needs a slip for every sawmill while weigh_slip_required = 1.
--      A full load from a single sawmill is fine.
--   4. One owner login shared by Aditya and Bharat. Sawmill rates and all
--      freight / other charges are entered from the owner login only:
--      new permission 'rates' (owner only unless granted). The accountant keeps
--      bills and payments and can VIEW rates and expenses.
-- =====================================================================
insert into public.app_settings (key, value, label) values
  ('driver_photo_required', 1, 'Driver photo with truck is compulsory (1 = yes)'),
  ('weigh_slip_required',   1, 'Every sawmill needs a weigh slip before Loaded (1 = yes)')
on conflict (key) do nothing;

alter table public.load_allocations add column if not exists reached_at      timestamptz;   -- truck reached this sawmill
alter table public.load_allocations add column if not exists loading_done_at timestamptz;   -- loading finished at this sawmill
alter table public.load_allocations add column if not exists slip_net_weight_t numeric(7,3) check (slip_net_weight_t > 0 and slip_net_weight_t < 100);

create or replace function public.v2_setting(p_key text)
returns numeric language sql stable security definer set search_path = '' as $$
  select coalesce((select value from public.app_settings where key = p_key), 0);
$$;
revoke execute on function public.v2_setting(text) from anon, public;
grant  execute on function public.v2_setting(text) to authenticated;

-- Stage rules (replaces 011): truck number; owner-only stages; reached a sawmill;
-- optional compulsory driver photo; Loaded needs every item done and (by setting) every sawmill's slip.
create or replace function public.v2_stage_rules()
returns trigger language plpgsql security definer set search_path = '' as $$
declare n_lines int; n_open int; n_noslip int; moved boolean := (tg_op = 'INSERT' or new.truck_stage is distinct from old.truck_stage);
begin
  if new.truck_stage in ('truck_fixed','going_to_load','under_loading','loaded','in_transit','delivered')
     and coalesce(trim(new.vehicle_no), '') = '' then
    raise exception 'Enter the truck number before moving past Planning.' using errcode = 'P0001';
  end if;
  if moved and new.truck_stage in ('planning','truck_fixed','cancelled') and not public.has_perm('plan') then
    raise exception 'Only the owner can use Planning, Truck fixed or Cancel.' using errcode = 'P0001';
  end if;
  if moved and new.truck_stage in ('under_loading','loaded','in_transit','delivered')
     and public.v2_setting('driver_photo_required') = 1 and not public.v2_has_driver_photo(new.id) then
    raise exception 'Driver photo with truck is mandatory.' using errcode = 'P0001';
  end if;
  if moved and new.truck_stage = 'under_loading'
     and not exists (select 1 from public.load_allocations where load_id = new.id and reached_at is not null) then
    raise exception 'Mark the sawmill the truck has reached first. Under loading starts only at the sawmill.' using errcode = 'P0001';
  end if;
  if moved and new.truck_stage in ('loaded','in_transit','delivered') then
    select count(*), count(*) filter (where line_status <> 'done') into n_lines, n_open from public.load_lines where load_id = new.id;
    if n_lines = 0 then raise exception 'Add at least one sawmill item before marking the load as Loaded.' using errcode = 'P0001'; end if;
    if n_open > 0 then raise exception 'Cannot mark as Loaded: % item(s) are not done yet.', n_open using errcode = 'P0001'; end if;
    if public.v2_setting('weigh_slip_required') = 1 then
      select count(*) into n_noslip from public.load_allocations a
       where a.load_id = new.id and not exists (select 1 from public.load_files f where f.allocation_id = a.id and f.kind = 'Weigh slip');
      if n_noslip > 0 then raise exception 'Cannot mark as Loaded: % sawmill(s) have no weigh slip yet.', n_noslip using errcode = 'P0001'; end if;
    end if;
  end if;
  return new;
end $$;

-- Allocation rules (replaces 011): driver photo only when the owner made it compulsory.
create or replace function public.v2_alloc_rules()
returns trigger language plpgsql security definer set search_path = '' as $$
declare st text; lid bigint := coalesce(new.load_id, old.load_id);
begin
  select truck_stage into st from public.loads where id = lid;
  if st in ('loaded','in_transit','delivered') and tg_op in ('INSERT','DELETE') then
    raise exception 'This load is already %. Move it back to Under loading first to change its sawmills.', replace(st, '_', ' ') using errcode = 'P0001';
  end if;
  if tg_op = 'INSERT' and st not in ('planning','truck_fixed') and public.v2_setting('driver_photo_required') = 1 and not public.v2_has_driver_photo(lid) then
    raise exception 'Driver photo with truck is mandatory.' using errcode = 'P0001';
  end if;
  if tg_op = 'UPDATE' and new.load_id <> old.load_id then raise exception 'An allocation cannot move to another load.' using errcode = 'P0001'; end if;
  if tg_op = 'INSERT' and new.owner_name is null then
    select contact_name into new.owner_name from public.sawmills where id = new.sawmill_id;
  end if;
  return coalesce(new, old);
end $$;

-- v_allocations lists a.*: rebuild it to include the new columns.
drop view if exists public.v_allocations;
create view public.v_allocations with (security_invoker = true) as
select a.*, s.name as sawmill_name, s.place as sawmill_place, s.area as sawmill_area, s.phone as sawmill_phone,
       (select count(*) from public.load_lines x where x.allocation_id = a.id) as items_total,
       (select count(*) from public.load_lines x where x.allocation_id = a.id and x.line_status = 'done') as items_done,
       (select count(*) from public.load_files f where f.allocation_id = a.id and f.kind = 'Weigh slip') as weigh_slips
  from public.load_allocations a join public.sawmills s on s.id = a.sawmill_id;
revoke all on public.v_allocations from anon;
grant select on public.v_allocations to authenticated;

-- ---------- rates entry is its own permission (owner only by default) ----------
alter table public.profiles add column if not exists perm_rates boolean not null default false;
create or replace function public.has_perm(p text)
returns boolean language sql stable security definer set search_path = '' as $$
  select exists (select 1 from public.profiles pr
                  where pr.id = (select auth.uid()) and pr.active
                    and (pr.role = 'owner' or case p when 'plan' then pr.perm_plan when 'finance' then pr.perm_finance
                                                     when 'expenses' then pr.perm_expenses when 'people' then pr.perm_people
                                                     when 'rates' then pr.perm_rates else false end));
$$;
-- Accountant default: bills, payments, balances; views rates and expenses; enters neither.
update public.profiles set perm_plan = false, perm_expenses = false, perm_rates = false, perm_finance = true where role = 'accountant';

drop policy if exists "finance all prices" on public.line_prices;
create policy "finance reads item rates" on public.line_prices for select to authenticated using ((select public.has_perm('finance')) or (select public.has_perm('rates')));
create policy "rates people add item rates" on public.line_prices for insert to authenticated with check ((select public.has_perm('rates')));
create policy "rates people edit item rates" on public.line_prices for update to authenticated using ((select public.has_perm('rates'))) with check ((select public.has_perm('rates')));
create policy "rates people remove item rates" on public.line_prices for delete to authenticated using ((select public.has_perm('rates')));
drop policy if exists "finance reads rate cards" on public.sawmill_rates;
drop policy if exists "finance adds rate cards" on public.sawmill_rates;
create policy "finance reads rate cards" on public.sawmill_rates for select to authenticated using ((select public.has_perm('finance')) or (select public.has_perm('rates')));
create policy "rates people add rate cards" on public.sawmill_rates for insert to authenticated with check ((select public.has_perm('rates')));
