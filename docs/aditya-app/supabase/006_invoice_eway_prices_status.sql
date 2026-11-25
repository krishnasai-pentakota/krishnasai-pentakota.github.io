-- =====================================================================
-- Migration 006 (25 Nov 2026), from the owner's answers:
--   1. Two more boxes on a lorry: invoice number and e-way bill number.
--   2. The accountant may SEE purchase/sale prices (only the owner changes them).
--   3. Every change is flagged with its exact time and the lorry's status
--      at that moment, including price changes (for owner + accountant).
-- =====================================================================

-- 1. Invoice and e-way bill numbers ------------------------------------
alter table public.trips add column invoice_no   text;
alter table public.trips add column eway_bill_no text;

-- 2. Accountant can read prices ----------------------------------------
create or replace function public.can_see_prices()
returns boolean language sql stable security definer set search_path = '' as $$
  select exists (select 1 from public.profiles
                 where id = (select auth.uid()) and active and role in ('owner','accountant'));
$$;
revoke execute on function public.can_see_prices() from anon, public;
grant  execute on function public.can_see_prices() to authenticated;

drop policy "owner reads prices" on public.trip_prices;
create policy "owner and accountant read prices" on public.trip_prices
  for select to authenticated using ((select public.can_see_prices()));

-- 3a. Lorry status at the moment of each change (shared history) -------
alter table public.change_log add column trip_status text;

create or replace function public.change_log_fill_status()
returns trigger language plpgsql security definer set search_path = '' as $$
begin
  if new.trip_status is null then
    select status into new.trip_status from public.trips where id = new.trip_id;
    if new.trip_status is null and new.table_name = 'trips' then
      new.trip_status := new.changes ->> 'status';     -- a deleted lorry
    end if;
  end if;
  return new;
end $$;
revoke execute on function public.change_log_fill_status() from authenticated, anon, public;
create trigger change_log_fill_status before insert on public.change_log
  for each row execute function public.change_log_fill_status();

-- 3b. Price history: seen only by owner + accountant (never staff) -------
create table public.price_log (
  id           bigint generated always as identity primary key,
  trip_id      bigint not null,
  action       text not null check (action in ('insert','update','delete')),
  changes      jsonb,                       -- {"field": [old, new]}
  changed_by   uuid,
  changed_at   timestamptz not null default now(),
  trip_status  text
);
create index price_log_trip_idx on public.price_log (trip_id, changed_at desc);
alter table public.price_log enable row level security;
create policy "owner and accountant read price history" on public.price_log
  for select to authenticated using ((select public.can_see_prices()));
revoke all on public.price_log from anon;
revoke insert, update, delete on public.price_log from authenticated;

create or replace function public.prices_log()
returns trigger language plpgsql security definer set search_path = '' as $$
declare
  skip text[] := array['trip_id','updated_at','updated_by'];
  t  bigint := coalesce(new.trip_id, old.trip_id);
  d  jsonb;
  st text;
begin
  select status into st from public.trips where id = t;
  if tg_op = 'INSERT' then
    d := public.jsonb_diff('{}'::jsonb, jsonb_strip_nulls(to_jsonb(new)), skip);
  elsif tg_op = 'UPDATE' then
    d := public.jsonb_diff(to_jsonb(old), to_jsonb(new), skip);
  else
    d := jsonb_strip_nulls(to_jsonb(old)) - skip;
  end if;
  if d = '{}'::jsonb and tg_op = 'UPDATE' then return new; end if;
  insert into public.price_log (trip_id, action, changes, changed_by, trip_status)
  values (t, lower(tg_op), d, auth.uid(), st);
  perform public.touch_review(t);              -- the editor has seen it
  return coalesce(new, old);
end $$;
revoke execute on function public.prices_log() from authenticated, anon, public;
create trigger prices_log after insert or update or delete on public.trip_prices
  for each row execute function public.prices_log();

-- 3c. List view: price changes also raise the red flag, but only for the
--     people who can see prices (for staff, trip_prices returns no row).
--     Same columns as before, in the same order, plus new ones at the end.
create or replace view public.v_trips with (security_invoker = true) as
select t.id, t.trip_date, t.vehicle_no, t.lorry_capacity_t, t.driver_name, t.driver_phone,
       t.transporter, t.sawmill_id, t.wood_type, t.quantity_cft, t.net_weight_t, t.freight_amount,
       t.party_id, t.destination, t.status, t.notes, t.created_at, t.created_by, t.updated_at,
       t.updated_by, t.last_change_at, t.last_change_by,
       s.name  as sawmill_name,
       s.place as sawmill_place,
       p.name  as party_name,
       p.city  as party_city,
       coalesce(c.charges_total, 0)                                as charges_total,
       coalesce(t.freight_amount, 0) + coalesce(c.charges_total, 0) as total_cost,
       r.reviewed_at                                               as my_reviewed_at,
       case when r.reviewed_at is null                                then 'new'
            when greatest(t.last_change_at, pr.updated_at) > r.reviewed_at then 'edited'
            else 'ok' end                                          as my_flag,
       (select count(*) from public.change_log l
         where l.trip_id = t.id
           and not (l.table_name = 'trips' and l.action = 'insert'))  as change_count,
       t.invoice_no,
       t.eway_bill_no,
       greatest(t.last_change_at, pr.updated_at)                   as my_change_at,
       case when pr.updated_at > t.last_change_at then pr.updated_by
            else t.last_change_by end                              as my_change_by
  from public.trips t
  left join public.sawmills s on s.id = t.sawmill_id
  left join public.parties  p on p.id = t.party_id
  left join (select trip_id, sum(amount) as charges_total
               from public.trip_charges group by trip_id) c on c.trip_id = t.id
  left join public.trip_prices pr on pr.trip_id = t.id
  left join public.trip_reviews r
         on r.trip_id = t.id and r.user_id = (select auth.uid());
