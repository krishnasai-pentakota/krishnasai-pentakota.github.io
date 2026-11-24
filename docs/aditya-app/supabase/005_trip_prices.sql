-- =====================================================================
-- Migration 005 (25 Nov 2026): purchase and sale price, OWNER ONLY
-- Owner's voice note: "next to the CFT there should be the price, and it
-- should open only for the owner". Kept in its own table so the database
-- itself hides it: staff and accountant get no rows at all.
-- Deliberately NOT written to change_log (everyone can read the history)
-- and NOT part of v_trips (everyone can read the list).
-- The app does not calculate amounts: the owner types rate and amount,
-- because the rate basis is still open (spec Q-17, Q-18).
-- =====================================================================
create table public.trip_prices (
  trip_id          bigint primary key references public.trips(id) on delete cascade,
  purchase_rate    numeric(12,2) check (purchase_rate >= 0),
  purchase_basis   text check (purchase_basis in ('per CFT','per ton','per lorry')),
  purchase_amount  numeric(14,2) check (purchase_amount >= 0),
  purchase_note    text,                        -- e.g. the "small difference" agreed
  sale_rate        numeric(12,2) check (sale_rate >= 0),
  sale_basis       text check (sale_basis in ('per CFT','per ton','per lorry')),
  sale_amount      numeric(14,2) check (sale_amount >= 0),
  sale_note        text,
  updated_at       timestamptz not null default now(),
  updated_by       uuid default auth.uid() references public.profiles(id) on delete set null
);

create or replace function public.prices_touch()
returns trigger language plpgsql set search_path = '' as $$
begin
  new.updated_at := now();
  new.updated_by := auth.uid();
  return new;
end $$;
create trigger prices_touch before insert or update on public.trip_prices
  for each row execute function public.prices_touch();

alter table public.trip_prices enable row level security;
create policy "owner reads prices"   on public.trip_prices for select to authenticated using ((select public.is_owner()));
create policy "owner adds prices"    on public.trip_prices for insert to authenticated with check ((select public.is_owner()));
create policy "owner changes prices" on public.trip_prices for update to authenticated using ((select public.is_owner())) with check ((select public.is_owner()));
create policy "owner removes prices" on public.trip_prices for delete to authenticated using ((select public.is_owner()));
revoke all on public.trip_prices from anon;
