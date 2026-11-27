-- 013: piece-count tally (from the client's Excel workbook, 26 Nov 2026)
--
-- Staff enter piece counts per thickness on a length x width grid, as in the
-- workbook. The database works out the CFT exactly as the workbook does:
--     CFT = thickness (in) x width (in) x length (ft) x pieces / 144
-- (no rounding inside; the item keeps 3 decimals) and writes one wood item per
-- size: Small / Medium / Large, in CFT, with the piece count.
--
-- Size bands (owner, 26 Nov): the workbook's Mango bands apply to every wood:
--     Small  = 1 ft 6 in to 2 ft 9 in   (shorter than 3 ft)
--     Medium = 3 ft to 4 ft 9 in
--     Large  = 5 ft and longer
-- The workbook's mistakes (1-inch rows of 9 ft+ counted as 1.5 inch, 3-inch
-- widths left out of the piece count) are not copied (owner, 26 Nov).

-- ---------- 1. Settings --------------------------------------------------
update public.app_settings set value = 3, label = 'Small: shorter than (ft)' where key = 'size_small_below_ft';
insert into public.app_settings (key, value, label) values ('size_small_below_ft', 3, 'Small: shorter than (ft)') on conflict (key) do nothing;
insert into public.app_settings (key, value, label) values ('size_large_from_ft', 5, 'Large: from (ft)')
  on conflict (key) do update set value = 5, label = excluded.label;
delete from public.app_settings where key = 'size_large_above_ft';
insert into public.app_settings (key, value, label) values
  ('tally_len_max_ft',   8.5, 'Tally grid: longest length shown (ft)'),
  ('tally_width_min_in', 4,   'Tally grid: narrowest width shown (in)'),
  ('tally_width_max_in', 11,  'Tally grid: widest width shown (in)')
on conflict (key) do nothing;

-- Mango is the main wood measured by tally (owner's guide: 1,350 CFT per 35 T lorry).
insert into public.wood_types (name, sort) values ('Mango', 4) on conflict (name) do nothing;

create or replace function public.size_grade_for(len numeric)
returns text language sql stable security definer set search_path = '' as $$
  select case
    when len is null then null
    when len < coalesce((select value from public.app_settings where key = 'size_small_below_ft'), 3) then 'small'
    when len >= coalesce((select value from public.app_settings where key = 'size_large_from_ft'), 5) then 'large'
    else 'medium' end;
$$;
revoke execute on function public.size_grade_for(numeric) from anon, public;
grant execute on function public.size_grade_for(numeric) to authenticated;

-- ---------- 2. Tally table -------------------------------------------------
-- counts: {"<thickness in>": {"<length ft>|<width in>": pieces, ...}, ...}
--   e.g. {"2": {"1.5|4": 229, "2.25|5": 31}, "1": {"3|4": 32}}
create table if not exists public.load_tallies (
  id            bigint generated always as identity primary key,
  load_id       bigint not null references public.loads(id) on delete cascade,
  allocation_id bigint not null references public.load_allocations(id) on delete cascade,
  sawmill_id    bigint not null references public.sawmills(id) on delete restrict,
  wood_type     text not null check (length(trim(wood_type)) > 0),
  counts        jsonb not null default '{}'::jsonb,
  notes         text,
  change_reason text,
  created_at    timestamptz not null default now(),
  created_by    uuid default auth.uid() references public.profiles(id) on delete set null,
  updated_at    timestamptz not null default now(),
  updated_by    uuid references public.profiles(id) on delete set null,
  unique (allocation_id, wood_type)
);
create index if not exists load_tallies_load_idx on public.load_tallies (load_id);

alter table public.load_lines add column if not exists tally_id bigint references public.load_tallies(id) on delete cascade;
create unique index if not exists load_lines_tally_size_idx on public.load_lines (tally_id, size_grade) where tally_id is not null;

-- ---------- 3. Checking and summing counts --------------------------------
-- Validates the counts and returns them tidy: known thickness, length 1 ft 6 in to 11 ft
-- in 3-inch steps, width 3 to 18 inches, whole piece counts; zero cells dropped.
create or replace function public.v2_tally_clean(p jsonb)
returns jsonb language plpgsql immutable set search_path = '' as $$
declare t text; cells jsonb; k text; v jsonb; lw text[]; len numeric; w numeric; n numeric; o jsonb; res jsonb := '{}'::jsonb; tk text; ck text;
begin
  if p is null then return res; end if;
  if jsonb_typeof(p) <> 'object' then raise exception 'The tally is not in the right form.' using errcode = 'P0001'; end if;
  for t, cells in select key, value from jsonb_each(p) loop
    if t !~ '^[0-9]+(\.[0-9]+)?$' or t::numeric not in (1, 1.5, 2) then
      raise exception 'Thickness % inch is not on the tally (1, 1.5 or 2 inch).', t using errcode = 'P0001';
    end if;
    if jsonb_typeof(cells) <> 'object' then raise exception 'The tally is not in the right form.' using errcode = 'P0001'; end if;
    tk := trim_scale(t::numeric)::text;
    o := coalesce(res -> tk, '{}'::jsonb);
    for k, v in select key, value from jsonb_each(cells) loop
      lw := regexp_match(k, '^([0-9]+(?:\.[0-9]+)?)\|([0-9]+)$');
      if lw is null then raise exception 'Tally cell "%" is not a length|width.', k using errcode = 'P0001'; end if;
      len := lw[1]::numeric; w := lw[2]::numeric;
      if len < 1.5 or len > 11 or len * 4 <> trunc(len * 4) then
        raise exception 'Length % ft is not on the tally (1 ft 6 in to 11 ft, in 3-inch steps).', len using errcode = 'P0001';
      end if;
      if w < 3 or w > 18 then raise exception 'Width % inch is not on the tally (3 to 18 inches).', w using errcode = 'P0001'; end if;
      if jsonb_typeof(v) <> 'number' then raise exception 'Piece counts must be numbers.' using errcode = 'P0001'; end if;
      n := (v #>> '{}')::numeric;
      if n < 0 or n > 100000 or n <> trunc(n) then raise exception 'Piece counts must be whole numbers (0 to 100000).' using errcode = 'P0001'; end if;
      ck := trim_scale(len)::text || '|' || w::int::text;
      if n > 0 then o := o || jsonb_build_object(ck, n::int); else o := o - ck; end if;
    end loop;
    if o = '{}'::jsonb then res := res - tk; else res := res || jsonb_build_object(tk, o); end if;
  end loop;
  return res;
end $$;
grant execute on function public.v2_tally_clean(jsonb) to authenticated;

-- CFT and pieces per thickness and size. Same formula as the workbook.
create or replace function public.v2_tally_totals(p jsonb)
returns table (thickness numeric, size_grade text, pieces bigint, cft numeric)
language sql stable set search_path = '' as $$
  select t.key::numeric,
         public.size_grade_for(split_part(c.key, '|', 1)::numeric),
         sum((c.value #>> '{}')::bigint),
         sum(t.key::numeric * split_part(c.key, '|', 2)::numeric * split_part(c.key, '|', 1)::numeric * (c.value #>> '{}')::numeric / 144)
    from jsonb_each(coalesce(p, '{}'::jsonb)) t, jsonb_each(t.value) c
   group by 1, 2
$$;
grant execute on function public.v2_tally_totals(jsonb) to authenticated;

-- ---------- 4. Rules ------------------------------------------------------------
create or replace function public.v2_tally_rules()
returns trigger language plpgsql security definer set search_path = '' as $$
declare a record; st text;
begin
  if tg_op <> 'DELETE' then
    if tg_op = 'UPDATE' and new.allocation_id <> old.allocation_id then
      raise exception 'A tally cannot move to another sawmill.' using errcode = 'P0001';
    end if;
    select load_id, sawmill_id into a from public.load_allocations where id = new.allocation_id;
    if not found then raise exception 'Sawmill allocation not found.' using errcode = 'P0001'; end if;
    new.load_id := a.load_id; new.sawmill_id := a.sawmill_id;
    new.wood_type := trim(new.wood_type);
    new.counts := public.v2_tally_clean(new.counts);
  end if;
  select truck_stage into st from public.loads where id = coalesce(new.load_id, old.load_id);
  if st in ('loaded','in_transit','delivered') then
    raise exception 'This load is already %. Move it back to Under loading first to change its tally.', replace(st, '_', ' ')
      using errcode = 'P0001';
  end if;
  return coalesce(new, old);
end $$;
revoke execute on function public.v2_tally_rules() from authenticated, anon, public;
create trigger load_tallies_rules before insert or update or delete on public.load_tallies
  for each row execute function public.v2_tally_rules();
create trigger load_tallies_stamp before update on public.load_tallies for each row execute function public.v2_stamp();

-- Writes the Small / Medium / Large wood items of a tally (CFT, with pieces).
create or replace function public.v2_tally_items()
returns trigger language plpgsql security definer set search_path = '' as $$
declare g text; pcs bigint; cf numeric; th text; lid bigint; dims text;
begin
  perform set_config('app.tally_write', '1', true);
  foreach g in array array['small','medium','large'] loop
    select coalesce(sum(x.pieces), 0), round(coalesce(sum(x.cft), 0), 3),
           string_agg(trim_scale(x.thickness)::text || '"', ', ' order by x.thickness)
      into pcs, cf, th
      from public.v2_tally_totals(new.counts) x where x.size_grade = g;
    dims := 'Piece tally, ' || coalesce(th, '') || ' thick';
    select id into lid from public.load_lines where tally_id = new.id and size_grade = g;
    if pcs > 0 then
      if lid is null then
        insert into public.load_lines (allocation_id, wood_type, unit, quantity, pieces, size_grade, dimensions, tally_id, change_reason)
        values (new.allocation_id, new.wood_type, 'CFT', cf, pcs, g, dims, new.id, new.change_reason);
      else
        update public.load_lines set wood_type = new.wood_type, quantity = cf, pieces = pcs, dimensions = dims, change_reason = new.change_reason
         where id = lid and (wood_type, quantity, pieces, dimensions) is distinct from (new.wood_type, cf, pcs::int, dims);
      end if;
    elsif lid is not null then
      delete from public.load_lines where id = lid;
    end if;
  end loop;
  perform set_config('app.tally_write', '', true);
  return null;
end $$;
revoke execute on function public.v2_tally_items() from authenticated, anon, public;
create trigger load_tallies_items after insert or update on public.load_tallies
  for each row execute function public.v2_tally_items();
create trigger load_tallies_log after insert or update or delete on public.load_tallies
  for each row execute function public.v2_log('all');

-- Items made by a tally change only through the tally (status and notes stay editable).
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
  if coalesce(current_setting('app.tally_write', true), '') <> '1' then
    if tg_op = 'INSERT' and new.tally_id is not null then
      raise exception 'Items from a piece tally are made by the tally.' using errcode = 'P0001';
    end if;
    if tg_op = 'UPDATE' and (old.tally_id is not null or new.tally_id is not null)
       and (new.quantity, new.pieces, new.size_grade, new.wood_type, new.unit, new.tally_id, new.allocation_id, new.dimensions, new.length_ft)
           is distinct from (old.quantity, old.pieces, old.size_grade, old.wood_type, old.unit, old.tally_id, old.allocation_id, old.dimensions, old.length_ft) then
      raise exception 'This item comes from the piece tally. Change the tally instead.' using errcode = 'P0001';
    end if;
    if tg_op = 'DELETE' and old.tally_id is not null
       and exists (select 1 from public.load_tallies where id = old.tally_id)
       and exists (select 1 from public.load_allocations where id = old.allocation_id) then
      raise exception 'This item comes from the piece tally. Remove the tally instead.' using errcode = 'P0001';
    end if;
  end if;
  if tg_op <> 'DELETE' and new.size_grade is null and new.length_ft is not null
     and coalesce((select value from public.app_settings where key = 'size_auto'), 0) = 1 then
    new.size_grade := public.size_grade_for(new.length_ft);
  end if;
  return coalesce(new, old);
end $$;

-- ---------- 5. Access: same as wood items (only on loads you can see) --------
alter table public.load_tallies enable row level security;
create policy "read tallies"   on public.load_tallies for select to authenticated using ((select public.is_member()) and exists (select 1 from public.loads l where l.id = load_id));
create policy "add tallies"    on public.load_tallies for insert to authenticated with check ((select public.is_member()) and exists (select 1 from public.loads l where l.id = load_id));
create policy "edit tallies"   on public.load_tallies for update to authenticated using ((select public.is_member()) and exists (select 1 from public.loads l where l.id = load_id)) with check ((select public.is_member()));
create policy "delete tallies" on public.load_tallies for delete to authenticated using ((select public.is_member()) and exists (select 1 from public.loads l where l.id = load_id));
revoke all on public.load_tallies from anon;
grant select, insert, update, delete on public.load_tallies to authenticated;

-- ---------- 6. Items view: add tally_id (at the end, so dependent views stay) --
create or replace view public.v_lines with (security_invoker = true) as
select ll.id, ll.load_id, ll.sawmill_id, ll.wood_type, ll.unit, ll.quantity, ll.length_ft, ll.size_grade, ll.line_status,
       ll.loaded_on, ll.notes, ll.change_reason, ll.created_at, ll.created_by, ll.updated_at, ll.updated_by,
       ll.allocation_id, ll.dimensions, ll.pieces,
       s.name as sawmill_name, s.place as sawmill_place, s.area as sawmill_area,
       a.owner_name, a.party_name,
       lp.rate, lp.adjustment,
       case when lp.rate is null then null
            else round(coalesce(ll.quantity, 0) * lp.rate + coalesce(lp.adjustment, 0), 2) end as amount,
       ll.tally_id
  from public.load_lines ll
  join public.load_allocations a on a.id = ll.allocation_id
  join public.sawmills s on s.id = ll.sawmill_id
  left join public.line_prices lp on lp.line_id = ll.id;
