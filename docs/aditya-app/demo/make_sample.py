"""Builds the SAMPLE data for the Aditya Traders demo.

Every action runs as a named person (owner, accountant or one of 10 staff)
through the REAL migrations on the local test Postgres, so the history,
red flags, stage rules and money maths are exactly what the live app does.
Times are then moved onto a realistic timeline (1 to 26 Nov 2026, IST).

All names, mills, buyers, rates and amounts are invented SAMPLE values.
GST is left at 0: the rate is the accountant's call and is not confirmed.
Output: sample_data.json (rows of every table) for the demo page.
"""
import json, random, subprocess, datetime as dt
import psycopg

DSN = "host=/tmp port=54329 user=postgres dbname=aditya"
OUT = "/home/claude/aditya-app/demo2/sample_data.json"
IST = dt.timezone(dt.timedelta(hours=5, minutes=30))
random.seed(26)

subprocess.run(["/home/claude/localdb/reset.sh"], check=True, capture_output=True)
conn = psycopg.connect(DSN, autocommit=True)

# ---------------------------------------------------------------- people
P = {}
people = [("owner", "Bharat (Owner)", "owner", None, "owner@adityatraders.demo"),
          ("acc", "Lakshmi (Accountant)", "accountant", None, "accounts@adityatraders.demo")]
staff_names = ["Ravi", "Suresh", "Prasad", "Naidu", "Kiran", "Srinu", "Raju", "Venkat", "Murali", "Gopi"]
for i, n in enumerate(staff_names, 1):
    ph = f"98480{i:05d}"
    people.append((n.lower(), n, "staff", ph, f"{ph}@staff.adityatraders.in"))
for i, (k, name, role, phone, email) in enumerate(people, 1):
    uid = f"d0000000-0000-0000-0000-{i:012d}"
    P[k] = uid
    conn.execute("insert into auth.users (instance_id,id,aud,role,email) values ('00000000-0000-0000-0000-000000000000',%s,'authenticated','authenticated',%s)", (uid, email))
    conn.execute("update public.profiles set full_name=%s, role=%s, phone=%s, active=true where id=%s", (name, role, phone, uid))
conn.execute("update public.profiles set created_at = '2026-10-30 10:00+05:30'")

# ---------------------------------------------------------------- clock
CLOCK = [dt.datetime(2026, 11, 1, 9, 0, tzinfo=IST)]


def at(t):
    CLOCK[0] = t


def fix_times(t):
    """Move everything the last statement stamped (real 'now') onto sample time t."""
    for tbl, cols in {"activity": ["at"], "load_reviews": ["reviewed_at"], "loads": ["created_at", "updated_at"],
                      "load_lines": ["created_at", "updated_at"], "line_prices": ["updated_at"], "load_costs": ["created_at", "updated_at"],
                      "load_billing": ["updated_at"], "payments": ["created_at", "updated_at"], "load_files": ["created_at"]}.items():
        for c in cols:
            conn.execute(f"update public.{tbl} set {c} = %s where {c} > now() - interval '10 minutes'", (t,))


def run(who, sql, params=(), t=None):
    """Run one statement as a person at sample time t (default: current clock)."""
    t = t or CLOCK[0]
    with conn.cursor() as c:
        c.execute("set role authenticated")
        c.execute("select set_config('request.jwt.claims', %s, false)", (json.dumps({"sub": P[who], "role": "authenticated"}),))
        try:
            c.execute(sql, params)
            r = c.fetchall() if c.description else None
        finally:
            c.execute("reset role")
    fix_times(t)
    return r


def one(who, sql, params=(), t=None):
    r = run(who, sql, params, t)
    return r[0][0] if r else None


def step(hours):
    CLOCK[0] = CLOCK[0] + dt.timedelta(hours=hours)
    return CLOCK[0]

# ---------------------------------------------------------------- masters
mills = [("Sri Lakshmi Saw Mill", "Rajanagaram", "Rajanagaram", "Appa Rao"), ("Durga Saw Mill", "Peddapuram", "Peddapuram", "Satyanarayana"),
         ("Venkateswara Timber Depot", "Peddapuram", "Peddapuram", "Ramana"), ("Sai Ram Saw Mill", "Narsipatnam", "Narsipatnam", "Chinna Rao"),
         ("Annapurna Saw Mill", "Rajam", "Rajam", "Krishna"), ("Sri Rama Wood Works", "Anandapuram", "Anandapuram", "Ramu"),
         ("Kanaka Durga Saw Mill", "Yelamanchili", "Yelamanchili", "Nookaraju"), ("Satya Sai Saw Mill", "Pendurthi", "Pendurthi", "Babji"),
         ("Padmavathi Saw Mill", "Pithapuram", "Pithapuram", "Suri Babu"), ("Gowri Shankar Saw Mill", "Rajam", "Rajam", "Ganesh")]
M = []
for i, (n, place, area, contact) in enumerate(mills):
    M.append(one("owner", "insert into public.sawmills (name, place, area, contact_name, phone) values (%s,%s,%s,%s,%s) returning id",
                 (n, place, area, contact, f"94400{i + 1:05d}")))
buyers = [("Goel Timber Store", "Yamunanagar", "Haryana", 15), ("Shree Balaji Timbers", "Jodhpur", "Rajasthan", 30),
          ("Mahaveer Wood Traders", "Kishangarh", "Rajasthan", 30), ("Jain Plywood & Timber", "Jaipur", "Rajasthan", 21),
          ("Agarwal Timber Mart", "Bikaner", "Rajasthan", 30)]
B = [one("owner", "insert into public.parties (name, city, state, kind, credit_days, phone) values (%s,%s,%s,'buyer',%s,%s) returning id",
         (n, c, s, cd, f"98120{i + 1:05d}")) for i, (n, c, s, cd) in enumerate(buyers)]
trans = [("Sri Sai Transport", "Rajahmundry"), ("Godavari Roadlines", "Kakinada"), ("Vizag Golden Carriers", "Visakhapatnam")]
T = [one("acc", "insert into public.parties (name, city, state, kind, phone) values (%s,%s,'Andhra Pradesh','transporter',%s) returning id",
         (n, c, f"99490{i + 1:05d}")) for i, (n, c) in enumerate(trans)]

STAFF = [s.lower() for s in staff_names[:7]]          # 7 staff active in the sample; 3 just have logins
DRIVERS = ["Ramesh", "Sankar", "Yadagiri", "Balu", "Raju Singh", "Mohan Lal", "Appala Naidu", "Sattibabu", "Harpal", "Govind"]
STAGES = ["planning", "truck_fixed", "going_to_load", "under_loading", "loaded", "in_transit", "delivered"]


def plate():
    return f"AP{random.choice(['39', '05', '31', '37'])}T{random.choice('ABUVWX')}{random.randint(1000, 9999)}"


def build(target, start, bill=None, cancel=False):
    """Walk one load through the real stages up to `target`, as different people."""
    at(start)
    s1, s2 = random.sample(STAFF, 2)
    buyer = random.choice(B); cap = random.choice([30, 35, 35])
    dest = buyers[B.index(buyer)]
    creator = random.choice(["owner", s1])
    lid = one(creator, """insert into public.loads (load_date, capacity_t, party_id, destination, destination_state, change_reason)
                           values (%s,%s,%s,%s,%s,%s) returning id""",
              (start.date(), cap, buyer, dest[1], dest[2], random.choice([f"{dest[0]} asked for one load of Mango", "Planned on owner's call", "Regular order"])))
    if random.random() < .6:
        step(2); run(s1, "select public.v2_post_note(%s,%s,false)", (lid, random.choice(["Asked Sri Lakshmi and Durga mills, about 700 CFT ready by Thursday", "Two mills have stock, checking third", "Mill says wood ready after 2 days"])))
    if cancel:
        step(20); run("owner", "update public.loads set truck_stage='cancelled', change_reason=%s where id=%s", ("Party postponed the order", lid)); return lid
    if STAGES.index(target) < 1: return lid
    step(random.randint(5, 20)); tr = random.choice(T)
    run(s1, """update public.loads set vehicle_no=%s, driver_name=%s, driver_phone=%s, transporter_id=%s, freight_amount=%s,
               truck_stage='truck_fixed', change_reason=%s where id=%s""",
        (plate(), random.choice(DRIVERS), f"9{random.randint(100000000, 999999999)}", tr, random.choice([85000, 92000, 95000, 98000, 105000]),
         f"Truck booked with {trans[T.index(tr)][0]}", lid))
    if STAGES.index(target) < 2: return lid
    step(random.randint(3, 12)); run(s1, "update public.loads set truck_stage='going_to_load', change_reason=%s where id=%s", ("Driver started from Rajahmundry", lid))
    if STAGES.index(target) < 3: return lid
    # mill lines
    step(random.randint(4, 10))
    n_m = random.choice([1, 2, 2, 3]); mm = random.sample(M, n_m)
    guide = 1350 if cap == 35 else 1150
    lines = []
    for j, mid in enumerate(mm):
        teak = random.random() < .15
        unit, wood = ("Tons", "Teak") if teak else ("CFT", random.choice(["Mango", "Mango", "Mango", "Acacia"]))
        q = round(random.uniform(4, 9), 2) if teak else round(guide / n_m + random.uniform(-60, 40))
        ln_ft = random.choice([3, 3.5, 4, 4.5, 5, 5.5, 6, 6.5, 7])
        lid_line = one(s2 if j else s1, """insert into public.load_lines (load_id, sawmill_id, wood_type, unit, quantity, length_ft, line_status, change_reason)
                                           values (%s,%s,%s,%s,%s,%s,'loading',%s) returning id""", (lid, mid, wood, unit, q, ln_ft, "Loading started at this mill"))
        lines.append((lid_line, unit, q))
        step(.5)
    run(s1, "update public.loads set truck_stage='under_loading', change_reason=%s where id=%s", ("Truck reached first mill, loading started", lid))
    step(1)
    for (ln, unit, q) in lines:      # owner fixes the purchase rate (staff never see it)
        rate = random.choice([350, 355, 360, 365, 370]) if unit == "CFT" else random.choice([38000, 40000, 42000])
        run("owner", "insert into public.line_prices (line_id, rate, adjustment, change_reason) values (%s,%s,%s,%s)",
            (ln, rate, random.choice([0, 0, -500, -1000, 250]), "Rate agreed with mill on visit"))
        step(.3)
    if random.random() < .35:
        ln = lines[0][0]; step(2)
        run("owner", "update public.line_prices set rate = rate - 5, change_reason=%s where line_id=%s", ("Mill agreed ₹5 less after quality check", ln))
    if STAGES.index(target) < 4:
        if random.random() < .5:     # one line already done
            step(4); run(s1, "update public.load_lines set line_status='done', loaded_on=%s, change_reason=%s where id=%s", (CLOCK[0].date(), "Loading finished at this mill", lines[0][0]))
        return lid
    for (ln, unit, q) in lines:
        step(random.uniform(3, 6))
        fq = q + (random.choice([-12, -6, 0, 8, 15]) if unit == "CFT" else 0)
        run(random.choice([s1, s2]), "update public.load_lines set line_status='done', quantity=%s, loaded_on=%s, change_reason=%s where id=%s",
            (fq, CLOCK[0].date(), random.choice(["Final tally done", "Loading finished, tally checked", "Final count after re-measure"]), ln))
    step(1)
    run(s1, "insert into public.load_costs (load_id, cost_type, amount, paid_to, paid_on, change_reason) values (%s,'Hamali / loading',%s,'Loading gang',%s,'Paid to loading gang')",
        (lid, random.choice([5000, 6000, 6500, 7000]), CLOCK[0].date()))
    run(s1, "insert into public.load_costs (load_id, cost_type, amount, paid_to, paid_on, change_reason) values (%s,'Weighbridge',%s,'Kata',%s,'Kata slip taken')",
        (lid, random.choice([200, 250, 300]), CLOCK[0].date()))
    run(s1, "insert into public.load_files (load_id, kind, storage_path, file_name, mime_type, size_bytes) values (%s,'Weighbridge (kata) slip',%s,'kata.jpg','image/svg+xml',2000)",
        (lid, f"demo/kata-{lid}.svg"))
    step(.5)
    kata = round(cap - random.uniform(0.2, 1.4), 2)
    run(s1, "update public.loads set truck_stage='loaded', net_weight_t=%s, change_reason=%s where id=%s", (kata, f"All mills loaded, kata {kata} T", lid))
    if random.random() < .3:
        step(2); run("owner", "select public.v2_post_note(%s,%s,true)", (lid, "Pay Durga mill only after kata copy reaches office"))
    if STAGES.index(target) < 5: return lid
    step(random.randint(2, 6))
    run("acc", "update public.loads set eway_bill_no=%s, change_reason=%s where id=%s", (str(random.randint(321000000000, 321999999999)), "E-way bill generated", lid))
    step(1); run(s1, "update public.loads set truck_stage='in_transit', change_reason=%s where id=%s", ("Truck left with e-way bill", lid))
    if random.random() < .6:
        step(random.randint(20, 40)); run(s2, "select public.v2_post_note(%s,%s,false)", (lid, random.choice(["Driver called: crossed Nagpur", "Driver called: near Indore, 2 days more", "Truck at Hyderabad, tyre changed, moving"])))
    if STAGES.index(target) < 6: return lid
    step(random.randint(40, 70)); run(random.choice(["owner", s1]), "update public.loads set truck_stage='delivered', change_reason=%s where id=%s", ("Party confirmed unloading", lid))
    # mill + transporter payments for most delivered loads
    for (ln, unit, q) in lines:
        if random.random() < .7:
            step(2)
            amt = one("acc", "select amount from public.v_lines where id=%s", (ln,))
            mill = one("acc", "select sawmill_id from public.load_lines where id=%s", (ln,))
            run("acc", "insert into public.payments (load_id, party_kind, sawmill_id, amount, paid_on, mode, reference, change_reason) values (%s,'mill',%s,%s,%s,'bank',%s,'Mill paid after loading')",
                (lid, mill, amt, CLOCK[0].date(), f"UTR{random.randint(100000, 999999)}"))
    if bill is None: return lid
    step(random.randint(3, 20))
    qty = one("acc", "select cft_total from public.v_loads where id=%s", (lid,)) or 1
    inv_date = CLOCK[0].date() if bill != "overdue" else (CLOCK[0] - dt.timedelta(days=40)).date()
    run("acc", """insert into public.load_billing (load_id, invoice_no, invoice_date, sale_unit, sale_qty, sale_rate, sale_adjustment, gst_amount, change_reason)
                  values (%s,%s,%s,'CFT',%s,%s,%s,0,'Bill made')""",
        (lid, f"AT/26-27/{300 + lid}", inv_date, qty, random.choice([420, 425, 430, 440, 450]), random.choice([0, 0, -1000, -500])))
    total = one("acc", "select invoice_total from public.v_loads where id=%s", (lid,))
    if bill in ("part", "paid"):
        step(random.randint(24, 60))
        first = round(float(total) * (1 if bill == "paid" else random.choice([.4, .5, .6])), 0)
        run("acc", "insert into public.payments (load_id, party_kind, party_id, amount, paid_on, mode, reference, change_reason) values (%s,'buyer',%s,%s,%s,'bank',%s,'Payment received')",
            (lid, buyer, first, CLOCK[0].date(), f"UTR{random.randint(100000, 999999)}"))
        if bill == "paid" and random.random() < .5:
            tr = one("acc", "select transporter_id from public.loads where id=%s", (lid,)); fr = one("acc", "select freight_amount from public.loads where id=%s", (lid,))
            step(3); run("acc", "insert into public.payments (load_id, party_kind, party_id, amount, paid_on, mode, change_reason) values (%s,'transporter',%s,%s,%s,'bank','Freight settled')",
                         (lid, tr, fr, CLOCK[0].date()))
    return lid


# ---------------------------------------------------------------- the loads
END = dt.datetime(2026, 11, 26, 10, 45, tzinfo=IST)
plan = []   # (target stage, bill, start day)
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

made = []
for i, (stage, bill, day) in enumerate(plan):
    start = dt.datetime(2026, 11, day, random.randint(8, 11), random.choice([5, 20, 35, 50]), tzinfo=IST)
    if day == 26:
        start = dt.datetime(2026, 11, 26, 8, 10 + i % 40, tzinfo=IST)
    lid = build("planning" if stage == "cancel" else stage, start, bill, cancel=(stage == "cancel"))
    made.append(lid)

# Make sure nothing went past the demo's "now"; squeeze any late times to just before END.
print("late rows:", conn.execute("select count(*) from public.activity where at > %s", (END,)).fetchone()[0])
conn.execute("update public.activity set at = %s - (random() * interval '40 minutes') where at > %s", (END, END))
for tbl, c in [("loads", "updated_at"), ("load_lines", "updated_at"), ("line_prices", "updated_at"), ("load_costs", "updated_at"),
               ("load_billing", "updated_at"), ("payments", "updated_at"), ("load_reviews", "reviewed_at")]:
    conn.execute(f"update public.{tbl} set {c} = %s where {c} > %s", (END, END))

# Owner and accountant checked everything on the evening of 25 Nov; staff Ravi checked on the 24th.
for who, when in [("owner", "2026-11-25 20:30+05:30"), ("acc", "2026-11-25 19:00+05:30"), ("ravi", "2026-11-24 18:00+05:30")]:
    conn.execute("""insert into public.load_reviews (load_id, user_id, reviewed_at)
                    select id, %s, %s from public.loads where created_at < %s
                    on conflict (load_id, user_id) do update set reviewed_at = greatest(public.load_reviews.reviewed_at, excluded.reviewed_at)""", (P[who], when, when))

# ---------------------------------------------------------------- export
tables = ["profiles", "sawmills", "parties", "app_settings", "loads", "load_lines", "line_prices", "load_costs",
          "load_billing", "payments", "load_files", "activity", "load_reviews"]
data = {"generated": dt.datetime.now(IST).isoformat(), "now": END.isoformat(), "people": {k: v for k, v in P.items()}, "tables": {}}
for t in tables:
    data["tables"][t] = conn.execute(f"select coalesce(json_agg(r order by 1), '[]') from (select * from public.{t}) r").fetchone()[0]
json.dump(data, open(OUT, "w"), ensure_ascii=False, separators=(",", ":"))
summary = conn.execute("""select truck_stage, count(*) from public.loads group by 1 order by min(array_position(array['planning','truck_fixed','going_to_load','under_loading','loaded','in_transit','delivered','cancelled'], truck_stage))""").fetchall()
print("loads by stage:", summary)
# Bill stage as the owner would see it
with conn.cursor() as c:
    c.execute("set role authenticated"); c.execute("select set_config('request.jwt.claims', %s, false)", (json.dumps({"sub": P["owner"]}),))
    print("bill stages:", c.execute("select bill_stage, count(*) from public.v_loads group by 1 order by 1").fetchall())
    print("owner flags:", c.execute("select my_flag, count(*) from public.v_loads group by 1").fetchall())
    c.execute("reset role")
print("activity rows:", conn.execute("select count(*) from public.activity").fetchone()[0], " size:", round(len(json.dumps(data)) / 1024), "KB")
