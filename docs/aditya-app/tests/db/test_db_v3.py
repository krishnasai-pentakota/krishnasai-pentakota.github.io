"""Database acceptance tests for the master product requirements (migration 011).
Runs the real migrations on a local Postgres (localdb/reset.sh). Every statement runs
as a given person exactly as the app's requests do (role 'authenticated' + JWT claims).
People: owner, accountant (plan+finance+expenses), freight operator Bharat Sanjay
(expenses only), two staff, and an unapproved stranger."""
import json, sys
import psycopg

DSN = "host=/tmp port=54329 user=postgres dbname=aditya"
U = {"owner": "b0000000-0000-0000-0000-000000000001", "acc": "b0000000-0000-0000-0000-000000000002",
     "freight": "b0000000-0000-0000-0000-000000000003", "staff": "b0000000-0000-0000-0000-000000000004",
     "staff2": "b0000000-0000-0000-0000-000000000005", "stranger": "b0000000-0000-0000-0000-000000000006"}
results = []
conn = psycopg.connect(DSN, autocommit=True)


def ok(name, cond, detail=""):
    results.append(bool(cond))
    print(("PASS " if cond else "FAIL ") + name + ("" if cond else f"  [{detail}]"), flush=True)


def run(who, sql, params=None, fetch=True):
    with conn.cursor() as c:
        if who == "anon":
            c.execute("set role anon")
        elif who:
            c.execute("set role authenticated")
            c.execute("select set_config('request.jwt.claims', %s, false)", (json.dumps({"sub": U[who], "role": "authenticated"}),))
        try:
            c.execute(sql, params)
            return c.fetchall() if fetch and c.description else None
        finally:
            c.execute("reset role"); c.execute("select set_config('request.jwt.claims', '', false)")


def err(who, sql, params=None):
    try:
        run(who, sql, params); return None
    except Exception as e:
        return str(e).split("\n")[0]


def one(who, sql, params=None):
    r = run(who, sql, params); return r[0][0] if r else None


def count(who, sql, params=None):
    return one(who, f"select count(*) from ({sql}) x", params)


# ---------------------------------------------------------------- people
for k, uid in U.items():
    run(None, "insert into auth.users (instance_id, id, aud, role, email) values ('00000000-0000-0000-0000-000000000000', %s, 'authenticated', 'authenticated', %s)", (uid, f"{k}@test.local"), fetch=False)
run(None, "update public.profiles set active=true, role='accountant', full_name='Lakshmi', perm_finance=true where id=%s", (U["acc"],), fetch=False)   # default accountant: bills/payments, views rates and expenses
run(None, "update public.profiles set active=true, role='freight', full_name='Bharat Sanjay', perm_expenses=true where id=%s", (U["freight"],), fetch=False)
run(None, "update public.profiles set active=true, role='staff', full_name='Ravi' where id=%s", (U["staff"],), fetch=False)
run(None, "update public.profiles set active=true, role='staff', full_name='Suresh' where id=%s", (U["staff2"],), fetch=False)
ok("first login becomes the owner", one(None, "select role from public.profiles where id=%s", (U["owner"],)) == "owner")
ok("has_perm: owner has every permission", one("owner", "select public.has_perm('finance') and public.has_perm('plan') and public.has_perm('expenses') and public.has_perm('people')"))
ok("has_perm: staff has none", one("staff", "select public.has_perm('finance') or public.has_perm('plan') or public.has_perm('expenses') or public.has_perm('people')") is False)
ok("has_perm: freight operator has expenses only", one("freight", "select public.has_perm('expenses') and not public.has_perm('finance') and not public.has_perm('plan')"))

mill_a = one("owner", "insert into public.sawmills (name, place, contact_name) values ('Sawmill A', 'Rajanagaram', 'Appa Rao') returning id")
mill_b = one("staff", "insert into public.sawmills (name, place, contact_name) values ('Sawmill B', 'Peddapuram', 'Ramana') returning id")
mill_c = one("staff", "insert into public.sawmills (name, place) values ('Sawmill C', 'Rajam') returning id")
buyer = one("owner", "insert into public.parties (name, city, state, kind, credit_days) values ('Goel Timber Store','Yamunanagar','Haryana','buyer',15) returning id")
trans = one("owner", "insert into public.parties (name, city, kind) values ('Sri Sai Transport','Rajahmundry','transporter') returning id")
ok("wood types start as Country Wood, Acacia, Teak, Mango, Other", [r[0] for r in run("staff", "select name from public.wood_types order by sort")] == ["Country Wood", "Acacia", "Teak", "Mango", "Other"])
e = err("staff", "insert into public.wood_types (name) values ('Neem')")
ok("staff cannot add wood types", e and "row-level security" in e, e)
run("owner", "insert into public.wood_types (name, sort) values ('Neem', 5)", fetch=False)
ok("owner adds a wood type everyone can pick", one("staff", "select count(*) from public.wood_types where name='Neem'") == 1)

# ---------------------------------------------------------------- Test 6: Planning and Truck fixed are owner-only
e = err("staff", "insert into public.loads (party_id, change_reason) values (%s, 'x')", (buyer,))
ok("T6 staff cannot create a load in Planning", e and ("row-level security" in e or "Only the owner" in e), e)
L1 = one("owner", "insert into public.loads (party_id, destination, capacity_t, change_reason) values (%s,'Yamunanagar',35,'Goel order') returning id", (buyer,))
ok("T6 staff does not receive Planning loads", count("staff", "select * from public.v_loads where id=%s", (L1,)) == 0)
ok("T6 freight operator does not receive Planning loads", count("freight", "select * from public.loads where id=%s", (L1,)) == 0)
ok("T6 Planning is owner-only: the accountant does not see it by default", count("acc", "select * from public.v_loads where id=%s", (L1,)) == 0)
ok("T6 staff cannot change a Planning load (0 rows)", one("staff", "with u as (update public.loads set notes='x' where id=%s returning 1) select count(*) from u", (L1,)) == 0)
e = err("staff", "select public.v2_post_note(%s, 'hello', false)", (L1,))
ok("T6 staff cannot post updates on a Planning load", e and "not allowed" in e, e)
run("owner", "update public.loads set vehicle_no='AP39TA1234', driver_name='Ramesh', transporter_id=%s, truck_stage='truck_fixed', change_reason='Truck booked' where id=%s", (trans, L1), fetch=False)
ok("T6 staff still cannot see it at Truck fixed", count("staff", "select * from public.loads where id=%s", (L1,)) == 0)
ok("T6 staff sees no history from Planning / Truck fixed", count("staff", "select * from public.activity where load_id=%s", (L1,)) == 0)
run("owner", "update public.loads set truck_stage='going_to_load', change_reason='Driver started' where id=%s", (L1,), fetch=False)
ok("T6 staff sees the load once it is Going to load", count("staff", "select * from public.v_loads where id=%s", (L1,)) == 1)
ok("T6 ...but still none of its Planning / Truck fixed history", count("staff", "select * from public.activity where load_id=%s and truck_stage in ('planning','truck_fixed')", (L1,)) == 0)
for st in ["truck_fixed", "planning", "cancelled"]:
    e = err("staff", "update public.loads set truck_stage=%s, change_reason='x' where id=%s", (st, L1))
    ok(f"T6 staff cannot move a load to {st}", e and ("Only the owner" in e or "row-level security" in e), e)

# ---------------------------------------------------------------- Test 1/2: driver photo mandatory, licence/C-book optional
ok("T1 driver photo with truck is compulsory by default (owner, 26 Nov)", one("staff", "select public.v2_setting('driver_photo_required')") == 1)
e = err("staff", "insert into public.load_allocations (load_id, sawmill_id) values (%s,%s)", (L1, mill_a))
ok("T1 no sawmill can be added before the driver-with-truck photo", e and "Driver photo with truck is mandatory" in e, e)
e = err("staff", "update public.loads set truck_stage='under_loading', change_reason='x' where id=%s", (L1,))
ok("T1 loading cannot start without the driver-with-truck photo", e and "Driver photo with truck is mandatory" in e, e)
ok("staff cannot switch the compulsory photo off", one("staff", "with u as (update public.app_settings set value=0 where key='driver_photo_required' returning 1) select count(*) from u") == 0)
run("owner", "update public.app_settings set value=0 where key='driver_photo_required'", fetch=False)
L1A = one("staff", "insert into public.load_allocations (load_id, sawmill_id) values (%s,%s) returning id", (L1, mill_a))
ok("if the owner switches the photo rule off, sawmills can be added without it", L1A is not None)
e = err("staff", "update public.loads set truck_stage='under_loading', change_reason='x' where id=%s", (L1,))
ok("Under loading is refused until the truck has reached a sawmill", e and "reached first" in e, e)
run("owner", "update public.app_settings set value=1 where key='driver_photo_required'", fetch=False)
L2 = one("staff", "insert into public.loads (load_date, vehicle_no, capacity_t, capacity_cft, driver_name, truck_stage, change_reason) values ('2026-11-26','AP39TB5678',35,1300,'Sankar','going_to_load','Truck arrived at yard') returning id")
ok("T1 staff registers a truck (starts at Going to load)", one("staff", "select truck_stage from public.loads where id=%s", (L2,)) == "going_to_load")
ok("T2 optional documents are reported as not provided", run("staff", "select coalesce(driver_photo,false), coalesce(licence_doc,false), coalesce(cbook_doc,false) from public.v_loads where id=%s", (L2,))[0] == (False, False, False))
run("staff", "insert into public.load_files (load_id, kind, storage_path) values (%s,'Driver with truck','v3/l2/driver.jpg')", (L2,), fetch=False)
ok("T1 after the photo, the load shows the driver photo", one("staff", "select driver_photo from public.v_loads where id=%s", (L2,)) is True)
ok("T2 licence and C-Book still 'not provided' and nothing blocks", run("staff", "select coalesce(licence_doc,false), coalesce(cbook_doc,false) from public.v_loads where id=%s", (L2,))[0] == (False, False))

# ---------------------------------------------------------------- Test 3: three sawmills, several items each
A = one("staff", "insert into public.load_allocations (load_id, sawmill_id, party_name, change_reason) values (%s,%s,'Sri Lakshmi Timbers','Mill A loading') returning id", (L2, mill_a))
B = one("staff", "insert into public.load_allocations (load_id, sawmill_id) values (%s,%s) returning id", (L2, mill_b))
C = one("staff", "insert into public.load_allocations (load_id, sawmill_id) values (%s,%s) returning id", (L2, mill_c))
ok("T3 sawmill owner name is prefilled from the mill (kept separate from party name)", run("staff", "select owner_name, party_name from public.load_allocations where id=%s", (A,))[0] == ("Appa Rao", "Sri Lakshmi Timbers"))
e = err("staff", "insert into public.load_allocations (load_id, sawmill_id) values (%s,%s)", (L2, mill_a))
ok("T3 the same sawmill is not added twice to one trip (add items instead)", e and "duplicate key" in e, e)
items = [(A, "Country Wood", "large", 300, "CFT", None, '3" x 3" x 6\''), (A, "Country Wood", "medium", 200, "CFT", None, None),
         (A, "Teak", "small", 100, "Pieces", 100, '4" x 4" x 7\''), (B, "Acacia", "medium", 200, "CFT", None, None), (C, "Teak", "small", 400, "CFT", None, None)]
I = [one("staff", "insert into public.load_lines (allocation_id, load_id, sawmill_id, wood_type, size_grade, quantity, unit, pieces, dimensions, line_status) values (%s, 0, 0, %s,%s,%s,%s,%s,%s,'loading') returning id",
         (a, w, s, q, u, p, d)) for (a, w, s, q, u, p, d) in items]
ok("T3 one trip holds 3 sawmills and 5 items", (one("staff", "select mills_count from public.v_loads where id=%s", (L2,)), one("staff", "select lines_total from public.v_loads where id=%s", (L2,))) == (3, 5))
ok("T3 items take their load and mill from the allocation (ignores wrong ids)", run("staff", "select load_id, sawmill_id from public.load_lines where id=%s", (I[3],))[0] == (L2, mill_b))
ok("T3 units are never added together (CFT and Pieces kept apart)", one("staff", "select qty_summary from public.v_loads where id=%s", (L2,)) == "1,100 CFT + 100 Pieces")
ok("T3 pieces count and dimensions are kept per item", run("staff", "select pieces, dimensions from public.load_lines where id=%s", (I[2],))[0] == (100, '4" x 4" x 7\''))
ok("T3 one load only — no duplicate truck records", count("owner", "select * from public.loads where vehicle_no='AP39TB5678'") == 1)
ok("units RFT and SFT are accepted", err("staff", "insert into public.load_lines (allocation_id, wood_type, quantity, unit) values (%s,'Other',10,'RFT')", (C,)) is None and err("staff", "insert into public.load_lines (allocation_id, wood_type, quantity, unit) values (%s,'Other',10,'SFT')", (C,)) is None)
run(None, "delete from public.load_lines where unit in ('RFT','SFT')", fetch=False)
x = one("staff", "insert into public.load_lines (allocation_id, wood_type, quantity, unit, length_ft) values (%s,'Other',5,'CFT',3.5) returning id", (C,))
ok("size grade is NOT set from length unless the owner switches it on", one("staff", "select size_grade from public.load_lines where id=%s", (x,)) is None)
run("owner", "update public.app_settings set value=1 where key='size_auto'", fetch=False)
y = one("staff", "insert into public.load_lines (allocation_id, wood_type, quantity, unit, length_ft) values (%s,'Other',5,'CFT',3.5) returning id", (C,))
ok("...and is set (3.5 ft → medium, the workbook's bands) once switched on", one("staff", "select size_grade from public.load_lines where id=%s", (y,)) == "medium")
ok("workbook bands: 2.75 ft small, 3 ft medium, 4.75 ft medium, 5 ft large", [one("staff", "select public.size_grade_for(%s::numeric)", (v,)) for v in (2.75, 3, 4.75, 5)] == ["small", "medium", "medium", "large"])
run("owner", "update public.app_settings set value=0 where key='size_auto'", fetch=False)
ok("staff cannot switch automatic grading on", one("staff", "with u as (update public.app_settings set value=1 where key='size_auto' returning 1) select count(*) from u") == 0)
run(None, "delete from public.load_lines where id in (%s,%s)", (x, y), fetch=False)

# ---------------------------------------------------------------- Test 5: weigh slips per sawmill
e = err("staff", "insert into public.load_files (load_id, kind, storage_path) values (%s,'Weigh slip','v3/l2/ws0.jpg')", (L2,))
ok("T5 a weigh slip must name its sawmill", e and "Choose the sawmill" in e, e)
A1 = None
e = err("staff", "insert into public.load_files (load_id, allocation_id, kind, storage_path) values (%s,%s,'Weigh slip','v3/x.jpg')", (L1, A))
ok("T5 a slip cannot be attached to a sawmill of another truck", e and "not on this load" in e, e)
ok("T5 three sawmills → three upload sections, all 'not uploaded'", run("staff", "select count(*), sum(weigh_slips) from public.v_allocations where load_id=%s", (L2,))[0] == (3, 0) and one("staff", "select allocs_without_slip from public.v_loads where id=%s", (L2,)) == 3)
for path, al in [("v3/l2/wsA1.jpg", A), ("v3/l2/wsA2.jpg", A), ("v3/l2/wsB1.jpg", B)]:
    run("staff", "insert into public.load_files (load_id, allocation_id, kind, storage_path) values (%s,%s,'Weigh slip',%s)", (L2, al, path), fetch=False)
ok("T5 several slips for one sawmill are allowed (A has 2, B has 1, C none)", [r[0] for r in run("staff", "select weigh_slips from public.v_allocations where load_id=%s order by id", (L2,))] == [2, 1, 0])
ok("T5 the load reports 1 sawmill still without a slip", one("staff", "select allocs_without_slip from public.v_loads where id=%s", (L2,)) == 1)

# ---------------------------------------------------------------- loading
run("staff", "update public.load_allocations set reached_at=now(), change_reason='Truck reached Sawmill A' where id=%s", (A,), fetch=False)
run("staff", "update public.loads set truck_stage='under_loading', change_reason='Truck reached Sawmill A' where id=%s", (L2,), fetch=False)
ok("Under loading once the truck reached Sawmill A", one("staff", "select truck_stage from public.loads where id=%s", (L2,)) == "under_loading")
ok("arrival at the sawmill is in the history", count("owner", "select * from public.activity where entity='load_allocations' and action='update' and changes ? 'reached_at'") == 1)
e = err("staff", "update public.loads set truck_stage='loaded', change_reason='x' where id=%s", (L2,))
ok("Loaded is refused while items are not done", e and "not done" in e, e)
run("staff", "update public.load_lines set quantity=600, change_reason='Re-measured', line_status='done' where id=%s", (I[0],), fetch=False)
for i in I[1:]:
    run("staff", "update public.load_lines set line_status='done', change_reason='done' where id=%s", (i,), fetch=False)
e = err("staff", "update public.loads set truck_stage='loaded', change_reason='x' where id=%s", (L2,))
ok("Loaded is refused while a sawmill has no weigh slip (Sawmill C)", e and "no weigh slip" in e, e)
run("staff", "insert into public.load_files (load_id, allocation_id, kind, storage_path) values (%s,%s,'Weigh slip','v3/l2/wsC1.jpg')", (L2, C), fetch=False)
run("staff", "update public.load_allocations set loading_done_at=now(), slip_net_weight_t=6.2, change_reason='Loading done at Sawmill C' where id=%s", (C,), fetch=False)
ok("slip net weight per sawmill is kept", float(one("staff", "select slip_net_weight_t from public.v_allocations where id=%s", (C,))) == 6.2)
run("staff", "update public.loads set truck_stage='loaded', net_weight_t=34.5, change_reason='All mills loaded' where id=%s", (L2,), fetch=False)
ok("Loaded once every item is done", one("staff", "select truck_stage from public.loads where id=%s", (L2,)) == "loaded")
e = err("staff", "insert into public.load_allocations (load_id, sawmill_id) values (%s,%s)", (L2, one(None, "insert into public.sawmills (name) values ('Sawmill D') returning id")))
ok("no sawmill can be added after Loaded", e and "already loaded" in e, e)

# ---------------------------------------------------------------- Test 8: activity
r = run("owner", "select changes->'quantity', reason, truck_stage, actor from public.activity where entity='load_lines' and entity_id=%s and action='update' and changes ? 'quantity'", (str(I[0]),))
ok("T8 quantity 300 → 600 recorded with who, reason and stage", r and r[0][0] == [300, 600] and r[0][1] == "Re-measured" and r[0][2] == "under_loading" and str(r[0][3]) == U["staff"], r)
ok("T8 sawmill added is recorded", count("owner", "select * from public.activity where entity='load_allocations' and action='insert' and load_id=%s", (L2,)) == 3)
ok("T8 every weigh slip upload is recorded (4)", count("owner", "select * from public.activity where entity='load_files' and load_id=%s and changes->>'kind'='Weigh slip'", (L2,)) == 4)
ok("T8 stage change recorded with exact time and reason", one("owner", "select reason from public.activity where load_id=%s and action='stage' and changes->'truck_stage'->>1='loaded'", (L2,)) == "All mills loaded")
ok("T8 nobody can edit or delete history", err("owner", "delete from public.activity") is not None or count(None, "select * from public.activity") > 0)
ok("T8 review status is per person: staff2 sees the load as new", one("staff2", "select my_flag from public.v_loads where id=%s", (L2,)) == "new")
run("staff2", "select public.v2_mark_checked(array[%s]::bigint[])", (L2,), fetch=False)
run("staff", "update public.loads set notes='Tarpaulin tied', change_reason='Note' where id=%s", (L2,), fetch=False)
ok("T8 after staff's edit, staff2 sees it as changed; staff (the editor) does not", (one("staff2", "select my_flag from public.v_loads where id=%s", (L2,)), one("staff", "select my_flag from public.v_loads where id=%s", (L2,))) == ("edited", "ok"))

# ---------------------------------------------------------------- Test 7: expenses (freight operator), finance
ok("freight is no longer a column staff could read on loads", one(None, "select count(*) from information_schema.columns where table_name='loads' and column_name='freight_amount'") == 0)
run("freight", "insert into public.load_costs (load_id, cost_type, amount, paid_to, change_reason) values (%s,'Truck Freight',95000,'Sri Sai Transport','Freight agreed')", (L2,), fetch=False)
run("freight", "insert into public.load_costs (load_id, allocation_id, cost_type, amount, change_reason) values (%s,%s,'Hamali / Loading',6000,'Paid gang at Sawmill A')", (L2, A), fetch=False)
e = err("freight", "insert into public.load_costs (load_id, allocation_id, cost_type, amount) values (%s,%s,'Toll',100)", (L1, A))
ok("T7 an expense cannot point at another truck's sawmill", e and "not on this load" in e, e)
ok("T7 a person given only the expenses permission sees expenses and the freight total", one("freight", "select freight_total from public.v_loads where id=%s", (L2,)) == 95000 and one("freight", "select costs_total from public.v_loads where id=%s", (L2,)) == 101000)
for t in ["line_prices", "load_billing", "payments", "sawmill_rates", "v_balances"]:
    ok(f"T7 freight operator gets nothing from {t}", one("freight", f"select count(*) from public.{t}") == 0)
ok("T7 freight operator sees no bill status", one("freight", "select bill_stage from public.v_loads where id=%s", (L2,)) is None)
for t in ["load_costs", "line_prices", "load_billing", "payments", "sawmill_rates", "v_balances", "expense_categories"]:
    ok(f"T6 staff gets nothing from {t}", one("staff", f"select count(*) from public.{t}") == 0)
ok("T6 staff's view of the load carries no freight, costs or bill values", run("staff", "select freight_total, costs_total, transport_total, purchase_total, invoice_total, bill_stage from public.v_loads where id=%s", (L2,))[0] == (None,) * 6)
ok("T6 staff history has no expense or finance entries", count("staff", "select * from public.activity where visibility <> 'all'") == 0)
e = err("staff", "insert into public.load_costs (load_id, cost_type, amount) values (%s,'Fuel',500)", (L2,))
ok("T6 staff cannot add expenses", e and "row-level security" in e, e)
ok("T7 accountant views expenses", one("acc", "select count(*) from public.load_costs") == 2)
e = err("acc", "insert into public.load_costs (load_id, cost_type, amount) values (%s,'Fuel',500)", (L2,))
ok("freight and other charges are entered from the owner login only (accountant refused)", e and "row-level security" in e, e)
run("owner", "insert into public.load_costs (load_id, cost_type, amount, change_reason) values (%s,'Toll',850,'Toll on NH16')", (L2,), fetch=False)
ok("owner enters charges", one("acc", "select count(*) from public.load_costs") == 3)

# ---------------------------------------------------------------- Test 9: rate cards keep history; recorded prices never change
run("owner", "insert into public.sawmill_rates (sawmill_id, wood_type, size_grade, unit, rate, effective_from, change_reason) values (%s,'Country Wood','large','CFT',350,'2026-11-01','Agreed on visit')", (mill_a,), fetch=False)
rate_now = one("owner", "select rate from public.sawmill_rates where sawmill_id=%s and wood_type='Country Wood' and size_grade='large' and unit='CFT' and effective_from <= '2026-11-26' order by effective_from desc, id desc limit 1", (mill_a,))
run("owner", "insert into public.line_prices (line_id, rate, adjustment, change_reason) values (%s,%s,-500,'From rate card')", (I[0], rate_now), fetch=False)
ok("T9 item amount = quantity × rate ± adjustment (600 × 350 − 500 = 2,09,500)", one("acc", "select amount from public.v_lines where id=%s", (I[0],)) == 209500)
e = err("acc", "insert into public.sawmill_rates (sawmill_id, wood_type, size_grade, unit, rate, effective_from) values (%s,'Country Wood','large','CFT',999,'2026-11-27')", (mill_a,))
ok("rates are entered from the owner login only (accountant refused)", e and "row-level security" in e, e)
e = err("acc", "update public.line_prices set rate=1 where line_id=%s", (I[0],))
ok("accountant cannot change an item's purchase rate (0 rows)", e is None and one("acc", "select rate from public.line_prices where line_id=%s", (I[0],)) == 350)
run("owner", "insert into public.sawmill_rates (sawmill_id, wood_type, size_grade, unit, rate, effective_from, change_reason) values (%s,'Country Wood','large','CFT',365,'2026-11-27','Mill raised rate')", (mill_a,), fetch=False)
ok("T9 a new current rate does NOT change the recorded transaction", one("acc", "select amount from public.v_lines where id=%s", (I[0],)) == 209500 and one("acc", "select rate from public.line_prices where line_id=%s", (I[0],)) == 350)
ok("T9 old and new rates both kept, with dates and who set them", [tuple(map(str, r)) for r in run("acc", "select rate, effective_from, created_by from public.sawmill_rates where sawmill_id=%s order by effective_from", (mill_a,))] == [("350.00", "2026-11-01", U["owner"]), ("365.00", "2026-11-27", U["owner"])])
ok("T9 rate cards cannot be overwritten (0 rows updated)", one("owner", "with u as (update public.sawmill_rates set rate=1 returning 1) select count(*) from u") == 0)
ok("T9 rate cards cannot be deleted (0 rows)", one("owner", "with d as (delete from public.sawmill_rates returning 1) select count(*) from d") == 0)
ok("T9 rate changes are in the money-only history", count("acc", "select * from public.activity where entity='sawmill_rates' and visibility='finance'") == 2)

# ---------------------------------------------------------------- billing through to paid
run("staff", "update public.loads set truck_stage='in_transit', change_reason='Left' where id=%s", (L2,), fetch=False)
run("staff", "update public.loads set truck_stage='delivered', party_id=%s, transporter_id=%s, change_reason='Unloaded' where id=%s", (buyer, trans, L2), fetch=False)
ok("delivered load is Ready to bill (for finance)", one("acc", "select bill_stage from public.v_loads where id=%s", (L2,)) == "ready_to_bill")
run("acc", "insert into public.load_billing (load_id, invoice_no, invoice_date, sale_unit, sale_qty, sale_rate, change_reason) values (%s,'INV/26-27/200',(now() at time zone 'Asia/Kolkata')::date,'CFT',1000,450,'Bill made')", (L2,), fetch=False)
ok("billed, not yet due → Billed", one("acc", "select bill_stage from public.v_loads where id=%s", (L2,)) == "billed")
run("acc", "insert into public.payments (load_id, party_kind, party_id, amount, change_reason) values (%s,'buyer',%s,200000,'Part')", (L2, buyer), fetch=False)
ok("part paid → Payment pending", one("acc", "select bill_stage from public.v_loads where id=%s", (L2,)) == "payment_pending")
run("acc", "insert into public.payments (load_id, party_kind, party_id, amount, change_reason) values (%s,'buyer',%s,250000,'Rest')", (L2, buyer), fetch=False)
ok("fully paid → Paid", one("acc", "select bill_stage from public.v_loads where id=%s", (L2,)) == "paid")
ok("transporter balance comes from Truck Freight expenses (95,000 due)", float(one("acc", "select total_due from public.v_balances where party_kind='transporter' and party_id=%s", (trans,))) == 95000)

# ---------------------------------------------------------------- people and permissions
ok("accountant cannot manage people by default", one("acc", "with u as (update public.profiles set full_name='X' where id=%s returning 1) select count(*) from u", (U["staff"],)) == 0)
run("owner", "update public.profiles set perm_people=true where id=%s", (U["acc"],), fetch=False)
ok("owner grants 'people' → accountant can now manage staff", one("acc", "with u as (update public.profiles set full_name='Ravi K' where id=%s returning 1) select count(*) from u", (U["staff"],)) == 1)
e = err("acc", "update public.profiles set role='owner' where id=%s", (U["staff"],))
ok("only the owner can create another owner", e and "Only the owner" in e, e)
e = err("acc", "update public.profiles set perm_people=true where id=%s", (U["freight"],))
ok("only the owner can hand out the people permission", e and "Only the owner" in e, e)
ok("staff cannot give themselves permissions", one("staff", "with u as (update public.profiles set perm_finance=true where id=%s returning 1) select count(*) from u", (U["staff"],)) == 0)

# ---------------------------------------------------------------- files and stored objects
f_other = one("staff2", "insert into public.load_files (load_id, kind, storage_path) values (%s,'Other','v3/l2/other.jpg') returning id", (L2,))
ok("staff cannot remove someone else's upload", one("staff", "with d as (delete from public.load_files where id=%s returning 1) select count(*) from d", (f_other,)) == 0)
ok("staff can remove their own wrong upload", one("staff2", "with d as (delete from public.load_files where id=%s returning 1) select count(*) from d", (f_other,)) == 1)
run(None, "insert into storage.objects (bucket_id, name, owner) values ('lorry-files','expenses/l2/receipt.jpg',%s), ('lorry-files','v3/l2/driver.jpg',%s)", (U["freight"], U["staff"]), fetch=False)
ok("expense receipts are hidden from staff in storage", one("staff", "select count(*) from storage.objects where name like 'expenses/%%'") == 0 and one("staff", "select count(*) from storage.objects where name='v3/l2/driver.jpg'") == 1)
ok("expense receipts readable by the freight operator", one("freight", "select count(*) from storage.objects where name like 'expenses/%%'") == 1)

# ---------------------------------------------------------------- Test 10 (database part): one shared record
ok("T10 a change by staff is immediately what the owner reads", one("owner", "select notes from public.loads where id=%s", (L2,)) == "Tarpaulin tied")

# ---------------------------------------------------------------- outsiders
for t in ["loads", "load_allocations", "load_lines", "load_files", "load_costs", "line_prices", "payments", "activity", "v_loads", "v_allocations", "wood_types", "sawmill_rates"]:
    ok(f"unapproved login sees nothing in {t}", one("stranger", f"select count(*) from public.{t}") == 0)
    ok(f"anonymous has no access to {t}", one(None, "select has_table_privilege('anon', %s, 'select')", (f"public.{t}",)) is False)

print(f"\n{sum(results)} passed, {len(results) - sum(results)} failed")
sys.exit(0 if all(results) else 1)
