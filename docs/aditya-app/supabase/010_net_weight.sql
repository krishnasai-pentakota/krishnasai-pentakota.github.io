-- Migration 010 (26 Nov 2026): kata (weighbridge) net weight on each load, in tons.
-- Workflow step 3: the weighbridge confirms the 30 T / 35 T fill. Optional; typed by staff.
-- v_loads lists l.* so it must be rebuilt to show the new column (v_balances depends on it).
alter table public.loads add column if not exists net_weight_t numeric(7,3) check (net_weight_t > 0 and net_weight_t < 100);

drop view if exists public.v_balances;
drop view if exists public.v_loads;

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
             (select string_agg(rtrim(to_char(q.total, 'FM999G999G990D999'), '.') || ' ' || q.unit, ' + ' order by q.unit)
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

revoke all on public.v_loads, public.v_balances from anon;
grant select on public.v_loads, public.v_balances to authenticated;
