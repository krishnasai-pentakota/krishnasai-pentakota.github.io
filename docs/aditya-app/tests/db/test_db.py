"""Strict database tests for Aditya Traders v2.
Runs the real migrations on a local Postgres (see localdb/reset.sh) and checks
every role and business rule. Each statement runs as the given person, exactly
as the app's requests do (role 'authenticated' + JWT claims)."""
import json, sys, time, datetime as dt
import psycopg

DSN = "host=/tmp port=54329 user=postgres dbname=aditya"
U = {  # test people
    "owner": "a0000000-0000-0000-0000-000000000001",
    "acc":   "a0000000-0000-0000-0000-000000000002",
    "staff": "a0000000-0000-0000-0000-000000000003",
    "staff2": "a0000000-0000-0000-0000-000000000005",
    "stranger": "a0000000-0000-0000-0000-000000000004",
}
results = []

def ok(name, cond, detail=""):
    results.append((cond, name, detail))
    print(("PASS " if cond else "FAIL ") + name + ("" if cond else f"  [{detail}]"), flush=True)

conn = psycopg.connect(DSN, autocommit=True)

def run(who, sql, params=None, fetch=True):
    """Run one statement as a person (or as the database owner if who is None)."""
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
            c.execute("reset role")
            c.execute("select set_config('request.jwt.claims', '', false)")

def err(who, sql, params=None):
    try:
        run(who, sql, params); return None
    except Exception as e:
        return str(e).split("\n")[0]

def one(who, sql, params=None):
    r = run(who, sql, params); return r[0][0] if r else None

# ---------------------------------------------------------------- setup
for k, uid in U.items():
    run(None, "insert into auth.users (instance_id, id, aud, role, email) values ('00000000-0000-0000-0000-000000000000', %s, 'authenticated', 'authenticated', %s)", (uid, f"{k}@test.local"), fetch=False)
run(None, "update public.profiles set active = true, role = 'accountant', full_name = 'Accountant' where id = %s", (U["acc"],), fetch=False)
run(None, "update public.profiles set active = true, role = 'staff', full_name = 'Ravi' where id = %s", (U["staff"],), fetch=False)
run(None, "update public.profiles set active = true, role = 'staff', full_name = 'Suresh' where id = %s", (U["staff2"],), fetch=False)
ok("first person becomes the owner automatically", one(None, "select role || active::text from public.profiles where id = %s", (U["owner"],)) == "ownertrue")
ok("later people wait for approval", one(None, "select active from public.profiles where id = %s", (U["stranger"],)) is False)

mill_a = one("staff", "insert into public.sawmills (name, place, area) values ('Sri Lakshmi Saw Mill', 'Rajanagaram', 'Rajanagaram') returning id")
mill_b = one("staff", "insert into public.sawmills (name, place, area) values ('Durga Saw Mill', 'Peddapuram', 'Peddapuram') returning id")
buyer  = one("owner", "insert into public.parties (name, city, state, kind, credit_days) values ('Goel Timber Store', 'Yamunanagar', 'Haryana', 'buyer', 30) returning id")
trans  = one("acc",   "insert into public.parties (name, city, kind) values ('Sri Sai Transport', 'Rajahmundry', 'transporter') returning id")
ok("staff can add a sawmill", mill_a is not None)

# ---------------------------------------------------------------- loads and stages
L1 = run("staff", "insert into public.loads (party_id, destination, change_reason) values (%s, 'Yamunanagar', 'Bharat asked to plan a load') returning id, load_no, truck_stage", (buyer,))[0]
lid = L1[0]
ok("load number is generated (L-0001)", L1[1] == "L-0001", L1[1])
ok("new load starts in Planning", L1[2] == "planning")
e = err("staff", "update public.loads set truck_stage = 'truck_fixed' where id = %s", (lid,))
ok("cannot fix truck without a truck number", e and "truck number" in e, e)
run("staff", "update public.loads set truck_stage = 'truck_fixed', vehicle_no = 'AP39TA1001', capacity_t = 35, driver_name = 'Ramesh', driver_phone = '9000000001', transporter_id = %s, freight_amount = 52000, change_reason = 'Truck confirmed by Sri Sai' where id = %s", (trans, lid), fetch=False)
e = err("staff", "update public.loads set truck_stage = 'loaded' where id = %s", (lid,))
ok("cannot mark Loaded with no mill lines", e and "at least one mill line" in e, e)

l1 = one("staff", "insert into public.load_lines (load_id, sawmill_id, wood_type, unit, quantity, length_ft, line_status) values (%s, %s, 'Mango', 'CFT', 700.5, 3.5, 'done') returning id", (lid, mill_a))
l2 = one("staff", "insert into public.load_lines (load_id, sawmill_id, wood_type, unit, quantity, length_ft, line_status) values (%s, %s, 'Mango', 'CFT', 480, 6.5, 'loading') returning id", (lid, mill_b))
l3 = one("staff", "insert into public.load_lines (load_id, sawmill_id, wood_type, unit, quantity, line_status) values (%s, %s, 'Teak', 'Tons', 2.5, 'loading') returning id", (lid, mill_b))
grades = dict(run(None, "select id, size_grade from public.load_lines where load_id = %s", (lid,)))
ok("size grade from length: 3.5 ft = small", grades[l1] == "small", grades[l1])
ok("size grade from length: 6.5 ft = large", grades[l2] == "large", grades[l2])
ok("no length, no grade (left for the user)", grades[l3] is None)
for ln, exp in [(3.99, "small"), (4, "medium"), (6, "medium"), (6.01, "large")]:
    ok(f"grade boundary {ln} ft = {exp}", one(None, "select public.size_grade_for(%s::numeric)", (ln,)) == exp)

e = err("staff", "update public.loads set truck_stage = 'loaded' where id = %s", (lid,))
ok("cannot mark Loaded while 2 lines are open", e and "2 mill line(s) are not done" in e, e)
run("staff", "update public.load_lines set line_status = 'done', loaded_on = current_date where load_id = %s", (lid,), fetch=False)
run("staff", "update public.loads set truck_stage = 'loaded', change_reason = 'All 3 lines loaded' where id = %s", (lid,), fetch=False)
ok("Loaded allowed once every line is done", one("staff", "select truck_stage from public.loads where id = %s", (lid,)) == "loaded")
e = err("staff", "insert into public.load_lines (load_id, sawmill_id, wood_type, unit, quantity) values (%s, %s, 'Mango', 'CFT', 10)", (lid, mill_a))
ok("cannot add a mill line after Loaded", e and "already loaded" in e, e)
e = err("staff", "update public.load_lines set line_status = 'loading' where id = %s", (l1,))
ok("cannot re-open a mill line after Loaded", e and "already loaded" in e, e)

v = run("staff", "select lines_total, lines_done, mills_count, qty_summary, cft_total from public.v_loads where id = %s", (lid,))[0]
ok("load summary: 3 lines, 3 done, 2 mills", v[:3] == (3, 3, 2), v)
ok("quantity summary per unit", v[3] == "1,180.5 CFT + 2.5 Tons", v[3])
ok("CFT total", float(v[4]) == 1180.5, v[4])

# ---------------------------------------------------------------- prices: admins only
run("owner", "insert into public.line_prices (line_id, rate, adjustment, change_reason) values (%s, 365, -2000, 'Rate agreed on call')", (l1,), fetch=False)
run("acc",   "insert into public.line_prices (line_id, rate) values (%s, 360)", (l2,), fetch=False)
run("acc",   "insert into public.line_prices (line_id, rate) values (%s, 21000)", (l3,), fetch=False)
amt = {r[0]: r[1] for r in run("owner", "select id, amount from public.v_lines where load_id = %s", (lid,))}
ok("amount = qty × rate + adjustment (700.5 × 365 − 2000 = 253,682.50)", float(amt[l1]) == 253682.50, amt[l1])
ok("amount for tons line (2.5 × 21000 = 52,500)", float(amt[l3]) == 52500.00, amt[l3])
ok("purchase total on the load", float(one("acc", "select purchase_total from public.v_loads where id = %s", (lid,))) == 253682.50 + 172800 + 52500)
ok("staff sees no price rows", one("staff", "select count(*) from public.line_prices") == 0)
ok("staff sees no rate/amount on lines", run("staff", "select count(*) filter (where rate is not null or amount is not null) from public.v_lines")[0][0] == 0)
ok("staff sees no purchase total", one("staff", "select purchase_total from public.v_loads where id = %s", (lid,)) is None)
e = err("staff", "insert into public.line_prices (line_id, rate) values (%s, 1)", (l1,))
ok("staff cannot write a price", e is not None and "row-level security" in e, e)
ok("staff cannot change a price (0 rows)", run("staff", "with u as (update public.line_prices set rate = 1 returning 1) select count(*) from u")[0][0] == 0)
ok("accountant can change a price (same access as owner)", run("acc", "with u as (update public.line_prices set rate = 362, change_reason = 'Mill corrected rate' where line_id = %s returning 1) select count(*) from u", (l2,))[0][0] == 1)

# ---------------------------------------------------------------- activity: who, when, why, status
acts = run("owner", "select entity, action, reason, truck_stage, visibility from public.activity where load_id = %s order by id", (lid,))
ok("load creation logged with its reason", acts[0][:3] == ("loads", "insert", "Bharat asked to plan a load"), acts[0])
stage_rows = [a for a in acts if a[1] == "stage"]
ok("stage changes logged as 'stage' with reason", len(stage_rows) == 2 and stage_rows[-1][2] == "All 3 lines loaded", stage_rows)
ok("each entry carries the load's status at that moment", stage_rows[-1][3] == "loaded")
ok("price changes are admin-only entries", all(a[4] == "admin" for a in acts if a[0] == "line_prices") and any(a[0] == "line_prices" for a in acts))
ok("staff never sees admin-only entries", one("staff", "select count(*) from public.activity where visibility = 'admin'") == 0)
ok("accountant sees admin-only entries", one("acc", "select count(*) from public.activity where visibility = 'admin'") >= 4)
e = err("staff", "insert into public.activity (load_id, entity, action) values (%s, 'x', 'note')", (lid,))
ok("nobody writes the history directly", e is not None, e)
run("staff", "select public.v2_post_note(%s, 'Truck reached Durga mill, loading started')", (lid,), fetch=False)
ok("staff can post an update note", one("acc", "select reason from public.activity where load_id = %s and action = 'note' order by id desc limit 1", (lid,)) == "Truck reached Durga mill, loading started")
e = err("staff", "select public.v2_post_note(%s, 'secret', true)", (lid,))
ok("staff cannot post an admin-only note", e is not None and "not allowed" in e, e)
run("owner", "select public.v2_post_note(%s, 'Collect 4 lakh before next load', true)", (lid,), fetch=False)
ok("admin-only note hidden from staff", one("staff", "select count(*) from public.activity where reason like 'Collect 4 lakh%%'") == 0)
upd = run("owner", "select changes, reason from public.activity where load_id = %s and entity = 'loads' and action = 'stage' order by id limit 1", (lid,))[0]
ok("update keeps old → new values", upd[0]["truck_stage"] == ["planning", "truck_fixed"] and upd[0]["vehicle_no"] == [None, "AP39TA1001"], upd[0])

# ---------------------------------------------------------------- red flags (separate moments in time)
L2 = one("owner", "insert into public.loads (party_id, vehicle_no, truck_stage) values (%s, 'AP05TD4004', 'truck_fixed') returning id", (buyer,))
ok("new load shows New for staff", one("staff", "select my_flag from public.v_loads where id = %s", (L2,)) == "new")
ok("own new load is not flagged for its creator", one("owner", "select my_flag from public.v_loads where id = %s", (L2,)) == "ok")
run("staff", "select public.v2_mark_checked(array[%s]::bigint[])", (L2,), fetch=False); time.sleep(0.05)
ok("after check: ok", one("staff", "select my_flag from public.v_loads where id = %s", (L2,)) == "ok")
lnx = one("staff", "insert into public.load_lines (load_id, sawmill_id, wood_type, unit, quantity) values (%s, %s, 'Mango', 'CFT', 100) returning id", (L2, mill_a))
run("staff", "select public.v2_mark_checked(array[%s]::bigint[])", (L2,), fetch=False)
run("acc", "select public.v2_mark_checked(array[%s]::bigint[])", (L2,), fetch=False); time.sleep(0.05)
run("owner", "insert into public.line_prices (line_id, rate) values (%s, 370)", (lnx,), fetch=False); time.sleep(0.05)
ok("price change does NOT flag staff", one("staff", "select my_flag from public.v_loads where id = %s", (L2,)) == "ok")
ok("price change flags the accountant", one("acc", "select my_flag from public.v_loads where id = %s", (L2,)) == "edited")
run("owner", "update public.loads set driver_phone = '9111111111', change_reason = 'Driver changed' where id = %s", (L2,), fetch=False); time.sleep(0.05)
ok("truck change flags staff", one("staff", "select my_flag from public.v_loads where id = %s", (L2,)) == "edited")
lr = run("staff", "select last_reason, last_by from public.v_loads where id = %s", (L2,))[0]
ok("list shows last reason and who", lr == ("Driver changed", __import__("uuid").UUID(U["owner"])), lr)
run("staff2", "select public.v2_post_note(%s, 'Driver will reach by 6pm')", (L2,), fetch=False); time.sleep(0.05)
ok("a note from a colleague flags others", one("staff", "select my_flag from public.v_loads where id = %s", (L2,)) == "edited")

# ---------------------------------------------------------------- billing and payments
run("staff", "update public.loads set truck_stage = 'in_transit', change_reason = 'Left Rajahmundry' where id = %s", (lid,), fetch=False)
ok("bill stage: not ready while in transit", one("acc", "select bill_stage from public.v_loads where id = %s", (lid,)) == "not_ready")
ok("staff sees no bill stage", one("staff", "select bill_stage from public.v_loads where id = %s", (lid,)) is None)
run("staff", "update public.loads set truck_stage = 'delivered', change_reason = 'Reached Yamunanagar' where id = %s", (lid,), fetch=False)
ok("bill stage: ready to bill after delivery", one("acc", "select bill_stage from public.v_loads where id = %s", (lid,)) == "ready_to_bill")
today = dt.date.today()
run("acc", "insert into public.load_billing (load_id, invoice_no, invoice_date, sale_unit, sale_qty, sale_rate, sale_adjustment, gst_amount) values (%s, 'AT/26-27/001', %s, 'CFT', 1180.5, 420, -500, 24771.50)", (lid, today), fetch=False)
b = run("acc", "select invoice_total, due_date, bill_stage from public.v_loads where id = %s", (lid,))[0]
ok("invoice total = qty × rate + adj + GST (1180.5×420 − 500 + 24,771.50 = 520,081.50)", float(b[0]) == 520081.50, b[0])
ok("due date = invoice date + buyer's 30 credit days", b[1] == today + dt.timedelta(days=30), b[1])
ok("bill stage: billed", b[2] == "billed", b[2])
ok("staff cannot read billing", one("staff", "select count(*) from public.load_billing") == 0 and one("staff", "select invoice_total from public.v_loads where id = %s", (lid,)) is None)
run("acc", "insert into public.payments (load_id, party_kind, party_id, amount, mode, reference, change_reason) values (%s, 'buyer', %s, 200000, 'bank', 'UTR123', 'First part payment')", (lid, buyer), fetch=False)
ok("bill stage: payment pending after part payment", one("acc", "select bill_stage from public.v_loads where id = %s", (lid,)) == "payment_pending")
run("owner", "insert into public.payments (load_id, party_kind, party_id, amount, mode) values (%s, 'buyer', %s, 320081.50, 'upi')", (lid, buyer), fetch=False)
ok("bill stage: paid when fully received", one("owner", "select bill_stage from public.v_loads where id = %s", (lid,)) == "paid")
L3 = one("owner", "insert into public.loads (party_id, vehicle_no, truck_stage) values (%s, 'AP37TB2002', 'truck_fixed') returning id", (buyer,))
run("owner", "insert into public.load_billing (load_id, invoice_no, invoice_date, sale_qty, sale_rate, credit_days) values (%s, 'AT/26-27/002', %s, 100, 400, 15)", (L3, today - dt.timedelta(days=20)), fetch=False)
ok("overdue bill (20 days, 15 credit) = payment pending", one("owner", "select bill_stage from public.v_loads where id = %s", (L3,)) == "payment_pending")
ok("per-bill credit days override the buyer's", one("owner", "select due_date from public.v_loads where id = %s", (L3,)) == today - dt.timedelta(days=5))
e = err("acc", "insert into public.payments (party_kind, amount) values ('mill', 100)")
ok("mill payment must name the mill", e is not None and "check" in e.lower(), e)
run("acc", "insert into public.payments (party_kind, sawmill_id, amount, change_reason) values ('mill', %s, 100000, 'Advance before loading')", (mill_a,), fetch=False)
run("acc", "insert into public.payments (party_kind, party_id, amount) values ('transporter', %s, 20000)", (trans,), fetch=False)
e = err("staff", "insert into public.payments (party_kind, sawmill_id, amount) values ('mill', %s, 1)", (mill_a,))
ok("staff cannot record payments", e is not None and "row-level security" in e, e)

bal = {(r[0], r[1]): r for r in run("acc", "select party_kind, name, total_due, total_paid from public.v_balances")}
ok("buyer balance: billed 5,20,081.50 + 40,000, paid 5,20,081.50", float(bal[("buyer", "Goel Timber Store")][2]) == 560081.50 and float(bal[("buyer", "Goel Timber Store")][3]) == 520081.50, bal[("buyer", "Goel Timber Store")])
ok("mill balance: purchases − payments (Sri Lakshmi 253,682.50 + 37,000 due, 1,00,000 paid)", float(bal[("mill", "Sri Lakshmi Saw Mill")][2]) == 253682.50 + 37000 and float(bal[("mill", "Sri Lakshmi Saw Mill")][3]) == 100000, bal[("mill", "Sri Lakshmi Saw Mill")])
ok("transporter balance: freight − payments", float(bal[("transporter", "Sri Sai Transport")][2]) == 52000 and float(bal[("transporter", "Sri Sai Transport")][3]) == 20000)
ok("staff sees no balances", one("staff", "select count(*) from public.v_balances") == 0)

# ---------------------------------------------------------------- people, settings, deletes
ok("staff cannot approve people", run("staff", "with u as (update public.profiles set active = true where id = %s returning 1) select count(*) from u", (U["stranger"],))[0][0] == 0)
ok("accountant can approve people", run("acc", "with u as (update public.profiles set active = true, role = 'staff' where id = %s returning 1) select count(*) from u", (U["stranger"],))[0][0] == 1)
run(None, "update public.profiles set active = false where id = %s", (U["stranger"],), fetch=False)
ok("staff cannot change size settings", run("staff", "with u as (update public.app_settings set value = 5 where key = 'size_small_below_ft' returning 1) select count(*) from u")[0][0] == 0)
run("acc", "update public.app_settings set value = 5 where key = 'size_small_below_ft'", fetch=False)
ok("admin can change size settings (4.5 ft now small)", one(None, "select public.size_grade_for(4.5::numeric)") == "small")
run("acc", "update public.app_settings set value = 4 where key = 'size_small_below_ft'", fetch=False)
ok("staff cannot delete a load (0 rows)", run("staff", "with d as (delete from public.loads where id = %s returning 1) select count(*) from d", (L3,))[0][0] == 0)
ok("accountant can delete a load", run("acc", "with d as (delete from public.loads where id = %s returning 1) select count(*) from d", (L3,))[0][0] == 1)
ok("deleted load keeps its history", one("owner", "select count(*) from public.activity where load_id = %s and action = 'delete' and entity = 'loads'", (L3,)) == 1)

# ---------------------------------------------------------------- outsiders
for t in ["loads", "load_lines", "line_prices", "load_costs", "load_billing", "payments", "load_files", "activity", "v_loads", "v_lines", "v_balances", "app_settings"]:
    ok(f"stranger (not approved) sees nothing in {t}", one("stranger", f"select count(*) from public.{t}") == 0)
    ok(f"anonymous has no access to {t}", one(None, f"select has_table_privilege('anon', 'public.{t}', 'select')") is False)
e = err("stranger", "insert into public.loads (vehicle_no) values ('X')")
ok("stranger cannot add a load", e is not None and "row-level security" in e, e)

passed = sum(1 for r in results if r[0]); failed = [r for r in results if not r[0]]
print(f"\n{passed} passed, {len(failed)} failed")
sys.exit(1 if failed else 0)
