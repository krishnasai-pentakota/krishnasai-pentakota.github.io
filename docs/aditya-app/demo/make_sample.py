"""Builds the SAMPLE data for the Aditya Traders demo (app 3.2).

Every action runs as a named person through the REAL migrations (001-012) on
the local test Postgres, so history, flags, stage rules, permissions and money
maths are exactly what the live app does. Times are moved onto a realistic
timeline (1 to 26 Nov 2026, IST).

People: one shared owner login (Aditya & Bharat), the accountant Lakshmi, 10 staff.
Owner enters sawmill rates and all freight / charges; the accountant bills and
records payments; staff register trucks, add sawmills and wood items, mark arrival,
finish loading with the weigh slip, and move the truck along.
All names, sawmills, buyers, rates and amounts are invented SAMPLE values.
GST is left at 0: the rate is the accountant's call and is not confirmed.
Output: sample_data.json (rows of every table) for the demo page."""
import json, random, subprocess, datetime as dt
import psycopg

DSN = "host=/tmp port=54329 user=postgres dbname=aditya"
OUT = "/home/claude/aditya-app/demo2/sample_data.json"
IST = dt.timezone(dt.timedelta(hours=5, minutes=30))
random.seed(32)
subprocess.run(["/home/claude/localdb/reset.sh"], check=True, capture_output=True)
conn = psycopg.connect(DSN, autocommit=True)

# ---------------------------------------------------------------- people
P = {}
people = [("owner", "Owner (Aditya & Bharat)", "owner", None, "owner@adityatraders.demo", False),
          ("acc", "Lakshmi (Accountant)", "accountant", None, "accounts@adityatraders.demo", True)]
staff_names = ["Ravi", "Suresh", "Prasad", "Naidu", "Kiran", "Srinu", "Raju", "Venkat", "Murali", "Gopi"]
for i, n in enumerate(staff_names, 1):
    ph = f"98480{i:05d}"; people.append((n.lower(), n, "staff", ph, f"{ph}@staff.adityatraders.in", False))
for i, (k, name, role, phone, email, fin) in enumerate(people, 1):
    uid = f"d0000000-0000-0000-0000-{i:012d}"; P[k] = uid
    conn.execute("insert into auth.users (instance_id,id,aud,role,email) values ('00000000-0000-0000-0000-000000000000',%s,'authenticated','authenticated',%s)", (uid, email))
    conn.execute("update public.profiles set full_name=%s, role=%s, phone=%s, active=true, perm_finance=%s where id=%s", (name, role, phone, fin, uid))
conn.execute("update public.profiles set created_at = '2026-10-30 10:00+05:30'")

CLOCK = [dt.datetime(2026, 11, 1, 9, 0, tzinfo=IST)]
STAMPED = {"activity": ["at"], "load_reviews": ["reviewed_at"], "loads": ["created_at", "updated_at"], "load_allocations": ["created_at", "updated_at"],
           "load_lines": ["created_at", "updated_at"], "line_prices": ["updated_at"], "load_costs": ["created_at", "updated_at"], "load_billing": ["updated_at"],
           "payments": ["created_at", "updated_at"], "load_files": ["created_at"], "sawmill_rates": ["created_at"]}


def fix_times(t):
    for tbl, cols in STAMPED.items():
        for c in cols:
            conn.execute(f"update public.{tbl} set {c} = %s where {c} > now() - interval '10 minutes'", (t,))


def run(who, sql, params=(), t=None):
    t = t or CLOCK[0]
    with conn.cursor() as c:
        c.execute("set role authenticated")
        c.execute("select set_config('request.jwt.claims', %s, false)", (json.dumps({"sub": P[who], "role": "authenticated"}),))
        try:
            c.execute(sql, params); r = c.fetchall() if c.description else None
        finally:
            c.execute("reset role")
    fix_times(t); return r


def one(who, sql, params=()):
    r = run(who, sql, params); return r[0][0] if r else None


def at(t): CLOCK[0] = t


def step(h):
    CLOCK[0] = CLOCK[0] + dt.timedelta(hours=h); return CLOCK[0]

# ---------------------------------------------------------------- masters (owner)
run("owner", "insert into public.wood_types (name, sort) values ('Mango', 4), ('Neem', 5)")
mills = [("Sri Lakshmi Saw Mill", "Rajanagaram", "Appa Rao"), ("Durga Saw Mill", "Peddapuram", "Satyanarayana"), ("Venkateswara Timber Depot", "Peddapuram", "Ramana"),
         ("Sai Ram Saw Mill", "Narsipatnam", "Chinna Rao"), ("Annapurna Saw Mill", "Rajam", "Krishna"), ("Sri Rama Wood Works", "Anandapuram", "Ramu"),
         ("Kanaka Durga Saw Mill", "Yelamanchili", "Nookaraju"), ("Satya Sai Saw Mill", "Pendurthi", "Babji"), ("Padmavathi Saw Mill", "Pithapuram", "Suri Babu"),
         ("Gowri Shankar Saw Mill", "Rajam", "Ganesh")]
M = [one("owner", "insert into public.sawmills (name, place, area, contact_name, phone) values (%s,%s,%s,%s,%s) returning id", (n, pl, pl, c, f"94400{i + 1:05d}")) for i, (n, pl, c) in enumerate(mills)]
buyers = [("Goel Timber Store", "Yamunanagar", "Haryana", 15), ("Shree Balaji Timbers", "Jodhpur", "Rajasthan", 30), ("Mahaveer Wood Traders", "Kishangarh", "Rajasthan", 30),
          ("Jain Plywood & Timber", "Jaipur", "Rajasthan", 21), ("Annapurna Traders", "Koraput", "Odisha", 30)]
B = [one("owner", "insert into public.parties (name, city, state, kind, credit_days, phone) values (%s,%s,%s,'buyer',%s,%s) returning id", (n, c, st, cd, f"98120{i + 1:05d}")) for i, (n, c, st, cd) in enumerate(buyers)]
trans = [("Sri Sai Transport", "Rajahmundry"), ("Godavari Roadlines", "Kakinada"), ("Vizag Golden Carriers", "Visakhapatnam")]
T = [one("owner", "insert into public.parties (name, city, state, kind, phone) values (%s,%s,'Andhra Pradesh','transporter',%s) returning id", (n, c, f"99490{i + 1:05d}")) for i, (n, c) in enumerate(trans)]
BASE = {"small": 340, "medium": 355, "large": 370}
for m in M:
    d = random.choice([-10, -5, 0, 0, 5])
    for g, r in BASE.items():
        run("owner", "insert into public.sawmill_rates (sawmill_id, wood_type, size_grade, unit, rate, effective_from, change_reason) values (%s,'Country Wood',%s,'CFT',%s,'2026-11-01','Agreed on visit')", (m, g, r + d))
    run("owner", "insert into public.sawmill_rates (sawmill_id, wood_type, size_grade, unit, rate, effective_from, change_reason) values (%s,'Acacia',null,'CFT',%s,'2026-11-01','Agreed on visit')", (m, 330 + d))
    run("owner", "insert into public.sawmill_rates (sawmill_id, wood_type, size_grade, unit, rate, effective_from, change_reason) values (%s,'Teak',null,'Tons',%s,'2026-11-01','Agreed on visit')", (m, 40000 + 100 * d))
at(dt.datetime(2026, 11, 15, 10, 0, tzinfo=IST))
for m in M[:2]:
    run("owner", "insert into public.sawmill_rates (sawmill_id, wood_type, size_grade, unit, rate, effective_from, change_reason) values (%s,'Country Wood','large','CFT',380,'2026-11-15','Sawmill raised the large-size rate')", (m,))

STAFF = ["ravi", "suresh", "prasad", "naidu", "kiran", "srinu", "raju"]
DRIVERS = ["Ramesh", "Sankar", "Yadagiri", "Balu", "Raju Singh", "Mohan Lal", "Appala Naidu", "Sattibabu", "Harpal", "Govind"]
ORDER = ["planning", "truck_fixed", "going_to_load", "under_loading", "loaded", "in_transit", "delivered"]


def plate():
    return f"AP{random.choice(['39', '05', '31', '37'])}T{random.choice('ABUVWX')}{random.randint(1000, 9999)}"


def card_rate(mill, wood, grade, unit, day):
    return one("owner", "select rate from public.sawmill_rates where sawmill_id=%s and wood_type=%s and unit=%s and (size_grade=%s or size_grade is null) and effective_from <= %s order by (size_grade is null), effective_from desc, id desc limit 1", (mill, wood, unit, grade, day))


def build(target, start, bill=None, cancel=False, single=False, staff_registered=False):
    at(start)
    s1, s2 = random.sample(STAFF, 2)
    buyer = random.choice(B); dest = buyers[B.index(buyer)]; cap = random.choice([30, 35, 35])
    tgt = ORDER.index(target)
    if staff_registered and tgt >= 2 and not cancel:   # staff registers a truck that arrived; the owner fixes the party
        lid = one(s1, "insert into public.loads (load_date, vehicle_no, capacity_t, driver_name, driver_phone, truck_stage, change_reason) values (%s,%s,%s,%s,%s,'going_to_load','Truck reached the yard') returning id",
                  (start.date(), plate(), cap, random.choice(DRIVERS), f"9{random.randint(100000000, 999999999)}"))
        run(s1, "insert into public.load_files (load_id, kind, storage_path, file_name, mime_type) values (%s,'Driver with truck',%s,'driver.jpg','image/svg+xml')", (lid, f"demo/driver-{lid}.svg"))
        step(2); run("owner", "update public.loads set party_id=%s, destination=%s, destination_state=%s, change_reason='Party fixed' where id=%s", (buyer, dest[1], dest[2], lid))
        run("owner", "insert into public.load_costs (load_id, cost_type, amount, paid_on, change_reason) values (%s,'Truck Freight',%s,%s,'Freight agreed')", (lid, random.choice([88000, 95000, 99000]), CLOCK[0].date()))
    else:
        lid = one("owner", "insert into public.loads (load_date, capacity_t, party_id, destination, destination_state, change_reason) values (%s,%s,%s,%s,%s,%s) returning id",
                  (start.date(), cap, buyer, dest[1], dest[2], random.choice([f"{dest[0]} asked for one load", "Order taken on call", "Regular order"])))
        if random.random() < .6:
            step(2); run("owner", "select public.v2_post_note(%s,%s,false)", (lid, random.choice(["Asked Sri Lakshmi and Durga: about 700 CFT ready by Thursday", "Two sawmills have stock, checking a third", "Sawmill says wood ready after 2 days"])))
        if cancel:
            step(20); run("owner", "update public.loads set truck_stage='cancelled', change_reason='Party postponed the order' where id=%s", (lid,)); return lid
        if tgt < 1: return lid
        step(random.randint(5, 20)); tr = random.choice(T)
        run("owner", "update public.loads set vehicle_no=%s, driver_name=%s, driver_phone=%s, transporter_id=%s, truck_stage='truck_fixed', change_reason=%s where id=%s",
            (plate(), random.choice(DRIVERS), f"9{random.randint(100000000, 999999999)}", tr, f"Truck booked with {trans[T.index(tr)][0]}", lid))
        run("owner", "insert into public.load_costs (load_id, cost_type, amount, paid_to, paid_on, change_reason) values (%s,'Truck Freight',%s,%s,%s,'Freight agreed')",
            (lid, random.choice([85000, 92000, 95000, 98000, 105000]), trans[T.index(tr)][0], CLOCK[0].date()))
        if tgt < 2: return lid
        step(random.randint(3, 12)); run("owner", "update public.loads set truck_stage='going_to_load', change_reason='Driver started from Rajahmundry' where id=%s", (lid,))
        step(1); run(s1, "insert into public.load_files (load_id, kind, storage_path, file_name, mime_type) values (%s,'Driver with truck',%s,'driver.jpg','image/svg+xml')", (lid, f"demo/driver-{lid}.svg"))
        if random.random() < .5:
            run(s1, "insert into public.load_files (load_id, kind, storage_path, file_name, mime_type) values (%s,'Driving licence',%s,'dl.jpg','image/svg+xml')", (lid, f"demo/doc-{lid}.svg"))
    step(random.randint(2, 6))
    n_m = 1 if single else random.choice([1, 2, 2, 3]); mm = random.sample(M, n_m)
    guide = 1350 if cap == 35 else 1150
    allocs = []
    for mid in mm:
        a = one(s1, "insert into public.load_allocations (load_id, sawmill_id, change_reason) values (%s,%s,'Sawmill booked for this truck') returning id", (lid, mid))
        allocs.append((a, mid)); step(.3)
    if tgt < 3: return lid
    for j, (a, mid) in enumerate(allocs):
        who = s1 if j == 0 else s2
        step(random.uniform(1, 4))
        run(who, "update public.load_allocations set reached_at=%s, change_reason=%s where id=%s", (CLOCK[0], f"Truck reached {mills[M.index(mid)][0]}", a))
        if j == 0: run(who, "update public.loads set truck_stage='under_loading', change_reason=%s where id=%s", (f"Truck reached {mills[M.index(mid)][0]}", lid))
        share = guide / n_m
        if random.random() < .15:
            items = [("Teak", "small", round(random.uniform(4, 9), 2), "Tons", None, None)]
        else:
            big = round(share * random.uniform(.55, .7))
            items = [("Country Wood", "large", big, "CFT", None, random.choice(['3" x 3" x 6\'', '4" x 4" x 7\'', None])),
                     (random.choice(["Country Wood", "Acacia", "Mango"]), random.choice(["medium", "small"]), round(share - big + random.uniform(-30, 20)), "CFT", None, None)]
            if random.random() < .25: items.append(("Country Wood", "small", (q := random.choice([400, 600, 800])), "Pieces", q, '3" x 3" x 4\''))
        for (w, g, q, u, pcs, dims) in items:
            step(.4)
            ln = one(who, "insert into public.load_lines (allocation_id, wood_type, size_grade, quantity, unit, pieces, dimensions, line_status, change_reason) values (%s,%s,%s,%s,%s,%s,%s,'loading','Tally at sawmill') returning id",
                     (a, w, g, q, u, pcs, dims))
            r = 45 if u == "Pieces" else card_rate(mid, "Country Wood" if w == "Mango" else w, g, u, start.date())
            run("owner", "insert into public.line_prices (line_id, rate, adjustment, change_reason) values (%s,%s,%s,'From rate card')", (ln, r or 350, random.choice([0, 0, -500, 250])))
        if tgt < 4 and j == len(allocs) - 1:
            return lid        # still loading at the last sawmill
        step(random.uniform(2, 5))
        run(who, "insert into public.load_files (load_id, allocation_id, kind, storage_path, file_name, mime_type) values (%s,%s,'Weigh slip',%s,'slip.jpg','image/svg+xml')", (lid, a, f"demo/kata-{lid}-{a}.svg"))
        run(who, "update public.load_lines set line_status='done', loaded_on=%s, change_reason=%s where allocation_id=%s", (CLOCK[0].date(), "Loading done at this sawmill", a))
        run(who, "update public.load_allocations set loading_done_at=%s, slip_net_weight_t=%s, change_reason='Loading done, weigh slip taken' where id=%s",
            (CLOCK[0], round(cap / n_m - random.uniform(.2, 1.2), 2), a))
        run("owner", "insert into public.load_costs (load_id, allocation_id, cost_type, amount, paid_to, paid_on, change_reason) values (%s,%s,'Hamali / Loading',%s,'Loading gang',%s,'Paid loading gang')",
            (lid, a, random.choice([3000, 3500, 4000, 6000]), CLOCK[0].date()))
    step(.5); kata = round(cap - random.uniform(.2, 1.4), 2)
    run(s1, "update public.loads set truck_stage='loaded', net_weight_t=%s, change_reason=%s where id=%s", (kata, f"All sawmills loaded, kata {kata} T", lid))
    run("owner", "insert into public.load_costs (load_id, cost_type, amount, paid_to, paid_on, change_reason) values (%s,'Weighbridge Charges',%s,'Kata',%s,'Final kata')", (lid, random.choice([200, 250, 300]), CLOCK[0].date()))
    if tgt < 5: return lid
    step(random.randint(2, 6)); run("acc", "update public.loads set eway_bill_no=%s, change_reason='E-way bill generated' where id=%s", (str(random.randint(321000000000, 321999999999)), lid))
    step(1); run(s1, "update public.loads set truck_stage='in_transit', change_reason='Truck left with e-way bill' where id=%s", (lid,))
    if random.random() < .6:
        step(random.randint(20, 40)); run(s2, "select public.v2_post_note(%s,%s,false)", (lid, random.choice(["Driver called: crossed Nagpur", "Driver called: near Indore, 2 days more", "Truck at Hyderabad, tyre changed, moving"])))
        run("owner", "insert into public.load_costs (load_id, cost_type, amount, paid_on, change_reason) values (%s,'Toll',%s,%s,'Toll paid on the way')", (lid, random.choice([1800, 2400, 3100]), CLOCK[0].date()))
    if tgt < 6: return lid
    step(random.randint(40, 70)); run(random.choice(["owner", s1]), "update public.loads set truck_stage='delivered', change_reason='Party confirmed unloading' where id=%s", (lid,))
    for (a, mid) in allocs:
        if random.random() < .7:
            step(2); amt = one("acc", "select sum(amount) from public.v_lines where allocation_id=%s", (a,))
            run("acc", "insert into public.payments (load_id, party_kind, sawmill_id, amount, paid_on, mode, reference, change_reason) values (%s,'mill',%s,%s,%s,'bank',%s,'Sawmill paid after loading')",
                (lid, mid, amt, CLOCK[0].date(), f"UTR{random.randint(100000, 999999)}"))
    if bill is None: return lid
    step(random.randint(3, 20))
    qty = one("acc", "select cft_total from public.v_loads where id=%s", (lid,)) or 1
    inv_date = CLOCK[0].date() if bill != "overdue" else (CLOCK[0] - dt.timedelta(days=40)).date()
    run("acc", "insert into public.load_billing (load_id, invoice_no, invoice_date, sale_unit, sale_qty, sale_rate, sale_adjustment, gst_amount, change_reason) values (%s,%s,%s,'CFT',%s,%s,%s,0,'Bill made')",
        (lid, f"INV/26-27/{100 + lid}", inv_date, qty, random.choice([420, 425, 430, 440, 450]), random.choice([0, 0, -1000, -500])))
    total = one("acc", "select invoice_total from public.v_loads where id=%s", (lid,))
    if bill in ("part", "paid"):
        step(random.randint(24, 60)); first = round(float(total) * (1 if bill == "paid" else random.choice([.4, .5, .6])), 0)
        run("acc", "insert into public.payments (load_id, party_kind, party_id, amount, paid_on, mode, reference, change_reason) values (%s,'buyer',%s,%s,%s,'bank',%s,'Payment received')",
            (lid, buyer, first, CLOCK[0].date(), f"UTR{random.randint(100000, 999999)}"))
    return lid


END = dt.datetime(2026, 11, 26, 10, 45, tzinfo=IST)
plan = []
plan += [("delivered", "paid", d) for d in (1, 2, 3, 4, 5)]
plan += [("delivered", "part", d) for d in (4, 5, 6, 7)] + [("delivered", "overdue", 3)]
plan += [("delivered", "billed", d) for d in (9, 10, 11, 12, 13)]
plan += [("delivered", None, d) for d in (13, 14, 15, 16, 17)]
plan += [("in_transit", None, d) for d in (18, 19, 19, 20, 21, 21)]
plan += [("loaded", None, d) for d in (20, 21, 22, 22, 23)]
plan += [("under_loading", None, d) for d in (22, 23, 23, 24, 24, 25)]
plan += [("going_to_load", None, d) for d in (24, 24, 25, 25, 25)]
plan += [("truck_fixed", None, d) for d in (24, 25, 25, 25, 26)]
plan += [("planning", None, d) for d in (25, 25, 26, 26, 26)]
plan.append(("cancel", None, 8))
plan.sort(key=lambda x: x[2])
for i, (stage, bill, day) in enumerate(plan):
    start = dt.datetime(2026, 11, day, random.randint(8, 11), random.choice([5, 20, 35, 50]), tzinfo=IST) if day < 26 else dt.datetime(2026, 11, 26, 8, 10 + i % 40, tzinfo=IST)
    build("planning" if stage == "cancel" else stage, start, bill, cancel=(stage == "cancel"), single=(i % 4 == 0), staff_registered=(i % 5 == 2))

late = conn.execute("select count(*) from public.activity where at > %s", (END,)).fetchone()[0]
conn.execute("update public.activity set at = %s - (random() * interval '40 minutes') where at > %s", (END, END))
for tbl, cols in STAMPED.items():
    for c in cols:
        if c != "at": conn.execute(f"update public.{tbl} set {c} = %s where {c} > %s", (END, END))
for c in ["reached_at", "loading_done_at"]:
    conn.execute(f"update public.load_allocations set {c} = %s where {c} > %s", (END, END))
for who, when in [("owner", "2026-11-25 20:30+05:30"), ("acc", "2026-11-25 19:00+05:30"), ("ravi", "2026-11-24 18:00+05:30")]:
    conn.execute("""insert into public.load_reviews (load_id, user_id, reviewed_at) select id, %s, %s from public.loads where created_at < %s
                    on conflict (load_id, user_id) do update set reviewed_at = greatest(public.load_reviews.reviewed_at, excluded.reviewed_at)""", (P[who], when, when))

tables = ["profiles", "sawmills", "parties", "app_settings", "wood_types", "expense_categories", "loads", "load_allocations", "load_lines", "line_prices", "load_costs",
          "load_billing", "payments", "load_files", "sawmill_rates", "activity", "load_reviews"]
data = {"generated": dt.datetime.now(IST).isoformat(), "now": END.isoformat(), "people": P, "tables": {}}
for t in tables:
    data["tables"][t] = conn.execute(f"select coalesce(json_agg(r order by 1), '[]') from (select * from public.{t}) r").fetchone()[0]
json.dump(data, open(OUT, "w"), ensure_ascii=False, separators=(",", ":"))
print("late activity squeezed:", late)
print("loads by stage:", conn.execute("select truck_stage, count(*) from public.loads group by 1 order by 1").fetchall())
with conn.cursor() as c:
    c.execute("set role authenticated"); c.execute("select set_config('request.jwt.claims', %s, false)", (json.dumps({"sub": P["owner"]}),))
    print("bill stages:", c.execute("select bill_stage, count(*) from public.v_loads group by 1 order by 1").fetchall())
    print("owner flags:", c.execute("select my_flag, count(*) from public.v_loads group by 1").fetchall())
    print("single-sawmill loads:", c.execute("select count(*) from public.v_loads where mills_count = 1").fetchone()[0])
    c.execute("reset role")
print("activity rows:", conn.execute("select count(*) from public.activity").fetchone()[0], " size:", round(len(json.dumps(data)) / 1024), "KB")
