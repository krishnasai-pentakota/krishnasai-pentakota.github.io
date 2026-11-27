"""Database tests for the piece-count tally (migration 013).
Uses the client's own workbook counts (workbook_tally_counts.json) and checks that the
database gives exactly the workbook's CFT and pieces, sheet by sheet and in total.
Runs the real migrations on a local Postgres (localdb/reset.sh)."""
import json, os, subprocess, sys
import psycopg

HERE = os.path.dirname(os.path.abspath(__file__))
DSN = "host=/tmp port=54329 user=postgres dbname=aditya"
U = {"owner": "c1000000-0000-0000-0000-000000000001", "acc": "c1000000-0000-0000-0000-000000000002",
     "staff": "c1000000-0000-0000-0000-000000000003", "stranger": "c1000000-0000-0000-0000-000000000004"}
WB = json.load(open(os.path.join(HERE, "workbook_tally_counts.json")))
results = []
subprocess.run(["/home/claude/localdb/reset.sh"], check=True, capture_output=True)
conn = psycopg.connect(DSN, autocommit=True)


def ok(name, cond, detail=""):
    results.append(bool(cond)); print(("PASS " if cond else "FAIL ") + name + ("" if cond else f"  [{detail}]"), flush=True)


def run(who, sql, params=None, fetch=True):
    with conn.cursor() as c:
        if who:
            c.execute("set role authenticated")
            c.execute("select set_config('request.jwt.claims', %s, false)", (json.dumps({"sub": U[who], "role": "authenticated"}),))
        try:
            c.execute(sql, params)
            return c.fetchall() if fetch and c.description else None
        finally:
            c.execute("reset role"); c.execute("select set_config('request.jwt.claims', '', false)")


def err(who, sql, params=None):
    try: run(who, sql, params); return None
    except Exception as e: return str(e).split("\n")[0]


def one(who, sql, params=None):
    r = run(who, sql, params); return r[0][0] if r else None


def merged(thickness):
    out = {}
    for s in WB["sheets"].values():
        if s["thickness"] == thickness:
            for k, n in s["counts"].items(): out[k] = out.get(k, 0) + n
    return out


for k, uid in U.items():
    run(None, "insert into auth.users (instance_id, id, aud, role, email) values ('00000000-0000-0000-0000-000000000000', %s, 'authenticated', 'authenticated', %s)", (uid, f"{k}@tally.test"), fetch=False)
run(None, "update public.profiles set active=true, role='accountant', full_name='Lakshmi', perm_finance=true where id=%s", (U["acc"],), fetch=False)
run(None, "update public.profiles set active=true, role='staff', full_name='Ravi' where id=%s", (U["staff"],), fetch=False)

# ---------------------------------------------------------------- settings from the workbook
S = dict(run("staff", "select key, value from public.app_settings"))
ok("size bands from the workbook: Small below 3 ft, Large from 5 ft (old key removed)", S.get("size_small_below_ft") == 3 and S.get("size_large_from_ft") == 5 and "size_large_above_ft" not in S, S)
ok("tally grid shows lengths up to 8.5 ft and widths 4–11 in (the workbook's data)", (S.get("tally_len_max_ft"), S.get("tally_width_min_in"), S.get("tally_width_max_in")) == (8.5, 4, 11), S)
ok("Mango is in the saved wood list", one("staff", "select count(*) from public.wood_types where name='Mango'") == 1)

# ---------------------------------------------------------------- the formula, sheet by sheet
for name, exp in WB["expected"].items():
    if name == "2TOTAL": continue
    s = WB["sheets"][name]
    cft, pcs = run("staff", "select round(sum(cft), 2), sum(pieces) from public.v2_tally_totals(jsonb_build_object(%s::text, %s::jsonb))", (s["thickness"], json.dumps(s["counts"])))[0]
    ok(f"sheet {name}: {exp['cft']} CFT, {exp['pieces']} pcs, same as the workbook", float(cft) == exp["cft"] and pcs == exp["pieces"], (cft, pcs))
two = merged("2"); one_in = merged("1")
bands = dict((g, float(c)) for g, c in run("staff", "select size_grade, round(sum(cft), 2) from public.v2_tally_totals(jsonb_build_object('2', %s::jsonb)) group by 1", (json.dumps(two),)))
e2 = WB["expected"]["2TOTAL"]["bands_cft"]
ok("2-inch total by size = the workbook's 2TOTAL bands (548.22 / 598.05 / 53.44+16.89+6.59)", bands == {"small": e2[0], "medium": e2[1], "large": round(e2[2] + e2[3] + e2[4], 2)}, bands)

# ---------------------------------------------------------------- a real tally on a load
mill = one("owner", "insert into public.sawmills (name, place, contact_name) values ('Sri Lakshmi Saw Mill','Rajanagaram','Appa Rao') returning id")
buyer = one("owner", "insert into public.parties (name, city, kind) values ('Goel Timber Store','Bornada','buyer') returning id")
for k in ("driver_photo_required", "weigh_slip_required"):
    run("owner", "update public.app_settings set value=0 where key=%s", (k,), fetch=False)
L = one("owner", "insert into public.loads (party_id, vehicle_no, capacity_t, change_reason) values (%s,'AP31TB1234',35,'Mango order') returning id", (buyer,))
run("owner", "update public.loads set truck_stage='going_to_load', change_reason='Truck on the way' where id=%s", (L,), fetch=False)
A = one("staff", "insert into public.load_allocations (load_id, sawmill_id) values (%s,%s) returning id", (L, mill))
counts = {"1": one_in, "2": two}
T = one("staff", "insert into public.load_tallies (allocation_id, wood_type, counts, change_reason) values (%s,'Mango',%s,'Tally from the paper sheets') returning id", (A, json.dumps(counts)))
items = {r[0]: r[1:] for r in run("staff", "select size_grade, quantity, pieces, unit, wood_type, dimensions from public.load_lines where tally_id=%s", (T,))}
ok("saving a tally makes three wood items: Small, Medium, Large", sorted(items) == ["large", "medium", "small"], items)
ok("items are in CFT, Mango, with pieces and thickness noted", all(v[2] == "CFT" and v[3] == "Mango" and v[4] == 'Piece tally, 1", 2" thick' for v in items.values()), items)
q = {g: float(v[0]) for g, v in items.items()}; p = {g: v[1] for g, v in items.items()}
ok("Small 621.46 CFT (1,166 + 3,868 pcs)", round(q["small"], 2) == 621.46 and p["small"] == 5034, (q, p))
ok("Medium 646.25 CFT (472 + 2,496 pcs)", round(q["medium"], 2) == 646.25 and p["medium"] == 2968, (q, p))
ok("Large 82.29 CFT (32 + 211 pcs)", round(q["large"], 2) == 82.29 and p["large"] == 243, (q, p))
ok("whole truck: 1,350.00 CFT and 8,245 pieces, same as the workbook", round(sum(q.values()), 2) == 1350.00 and sum(p.values()) == 8245, (sum(q.values()), sum(p.values())))
ok("load summary shows the CFT total", one("staff", "select round(cft_total, 2) from public.v_loads where id=%s", (L,)) == 1350)
ok("item quantities keep 3 decimals (no rounding to whole numbers)", all(str(v[0]).count(".") == 1 and len(str(v[0]).split(".")[1]) == 3 for v in items.values()), items)

# ---------------------------------------------------------------- checking the counts
for bad, why in [({"3": {"2|4": 1}}, "thickness 3 inch"), ({"2": {"1.25|4": 1}}, "length below 1 ft 6 in"), ({"2": {"2.1|4": 1}}, "length not in 3-inch steps"),
                 ({"2": {"2|20": 1}}, "width above 18 in"), ({"2": {"2|4": 1.5}}, "half a piece"), ({"2": {"2|4": -1}}, "negative count"), ({"2": {"abc": 1}}, "bad cell name")]:
    e = err("staff", "update public.load_tallies set counts=%s where id=%s", (json.dumps(bad), T))
    ok(f"refused: {why}", e is not None, e)
ok("tidies the counts: zero cells dropped, 2.50 written as 2.5", one("staff", "select public.v2_tally_clean(%s::jsonb)", (json.dumps({"2": {"2.50|4": 3, "3|5": 0}, "1.5": {"2|4": 0}}),)) == {"2": {"2.5|4": 3}})
e = err("staff", "insert into public.load_tallies (allocation_id, wood_type, counts) values (%s,'Mango','{}')", (A,))
ok("one tally per wood at a sawmill (Mango twice is refused)", e and "duplicate" in e, e)

# ---------------------------------------------------------------- tally items change only through the tally
small_id = one("staff", "select id from public.load_lines where tally_id=%s and size_grade='small'", (T,))
e = err("staff", "update public.load_lines set quantity=999 where id=%s", (small_id,))
ok("a tally item's CFT cannot be typed over", e and "Change the tally instead" in e, e)
e = err("staff", "update public.load_lines set size_grade='large' where id=%s", (small_id,))
ok("a tally item's size cannot be changed by hand", e and "Change the tally instead" in e, e)
e = err("staff", "delete from public.load_lines where id=%s", (small_id,))
ok("a tally item cannot be deleted on its own", e and "Remove the tally instead" in e, e)
e = err("staff", "insert into public.load_lines (allocation_id, wood_type, unit, quantity, tally_id) values (%s,'Mango','CFT',1,%s)", (A, T))
ok("nobody can add an item that pretends to come from a tally", e and "made by the tally" in e, e)
ok("marking a tally item loading / done still works", err("staff", "update public.load_lines set line_status='loading', change_reason='Loading' where id=%s", (small_id,)) is None)

# ---------------------------------------------------------------- editing the tally
n_act = one("owner", "select count(*) from public.activity where load_id=%s", (L,))
c2 = json.loads(json.dumps(counts)); c2["2"]["1.5|4"] = c2["2"].get("1.5|4", 0) + 12          # 12 more 1'6" x 4" x 2" pieces
c2["1"] = {k: v for k, v in c2["1"].items() if float(k.split("|")[0]) < 5}                      # and no 1-inch large pieces any more
run("staff", "update public.load_tallies set counts=%s, change_reason='Recounted 2 inch, 4 inch wide' where id=%s", (json.dumps(c2), T), fetch=False)
items2 = {r[0]: (float(r[1]), r[2]) for r in run("staff", "select size_grade, quantity, pieces from public.load_lines where tally_id=%s", (T,))}
ok("small item updated: +12 pieces, +1.00 CFT (2 x 4 x 1.5 x 12 / 144)", round(items2["small"][0] - q["small"], 2) == 1.00 and items2["small"][1] == p["small"] + 12, items2)
ok("large item updated without the 1-inch pieces: 76.92 CFT, 211 pcs", round(items2["large"][0], 2) == 76.92 and items2["large"][1] == 211, items2)
ok("an unchanged size is left alone (medium not rewritten)", one("owner", "select count(*) from public.activity where entity='load_lines' and entity_id=%s and action='update'", (str(one("staff", "select id from public.load_lines where tally_id=%s and size_grade='medium'", (T,))),)) == 0)
acts = run("owner", "select entity, action, reason from public.activity where load_id=%s order by id desc limit 3", (L,))
ok("history: the tally change and the item changes carry the reason", acts[0] == ("load_tallies", "update", "Recounted 2 inch, 4 inch wide") and all(a[2] == "Recounted 2 inch, 4 inch wide" for a in acts), acts)
ok("history entries are visible to everyone (no money in a tally)", one("staff", "select count(*) from public.activity where entity='load_tallies' and load_id=%s", (L,)) == 2)
run("staff", "update public.load_tallies set counts=%s, change_reason='Only small pieces' where id=%s", (json.dumps({"2": {"2|4": 10}}), T), fetch=False)
ok("sizes that drop to zero pieces lose their item", [r[0] for r in run("staff", "select size_grade from public.load_lines where tally_id=%s", (T,))] == ["small"])
run("staff", "update public.load_tallies set wood_type='Country Wood', change_reason='Wrong wood picked' where id=%s", (T,), fetch=False)
ok("changing the tally's wood changes its items", one("staff", "select wood_type from public.load_lines where tally_id=%s", (T,)) == "Country Wood")
run("staff", "update public.load_tallies set wood_type='Mango', counts=%s, change_reason='Back to the full count' where id=%s", (json.dumps(counts), T), fetch=False)

# ---------------------------------------------------------------- money stays apart
for sid in [r[0] for r in run("owner", "select id from public.load_lines where tally_id=%s", (T,))]:
    run("owner", "insert into public.line_prices (line_id, rate, change_reason) values (%s, 400, 'Rate card')", (sid,), fetch=False)
ok("owner's rate works on tally items: 1,350.00 CFT x 400 = 5,40,000", float(one("owner", "select sum(amount) from public.v_lines where tally_id=%s", (T,))) == 540000.0)
ok("staff get no rate or amount on tally items", one("staff", "select count(*) from public.v_lines where tally_id=%s and (rate is not null or amount is not null)", (T,)) == 0)
ok("accountant sees the amount", float(one("acc", "select sum(amount) from public.v_lines where tally_id=%s", (T,))) == 540000.0)

# ---------------------------------------------------------------- after Loaded
run("staff", "update public.load_lines set line_status='done' where load_id=%s", (L,), fetch=False)
run("staff", "update public.load_allocations set reached_at=now() where id=%s", (A,), fetch=False)
run("staff", "update public.loads set truck_stage='under_loading', change_reason='At the mill' where id=%s", (L,), fetch=False)
run("staff", "update public.loads set truck_stage='loaded', change_reason='Loaded' where id=%s", (L,), fetch=False)
e = err("staff", "update public.load_tallies set counts='{\"2\": {\"2|4\": 1}}', change_reason='late change' where id=%s", (T,))
ok("after Loaded the tally is locked", e and "Move it back to Under loading" in e, e)
e = err("staff", "delete from public.load_tallies where id=%s", (T,))
ok("after Loaded the tally cannot be removed", e and "Move it back to Under loading" in e, e)
run("staff", "update public.loads set truck_stage='under_loading', change_reason='Recount needed' where id=%s", (L,), fetch=False)
ok("back at Under loading the tally can change again", err("staff", "update public.load_tallies set notes='recounted', change_reason='Recount' where id=%s", (T,)) is None)

# ---------------------------------------------------------------- removing
run("staff", "delete from public.load_tallies where id=%s", (T,), fetch=False)
ok("removing a tally removes its items", one("staff", "select count(*) from public.load_lines where allocation_id=%s", (A,)) == 0)
T2 = one("staff", "insert into public.load_tallies (allocation_id, wood_type, counts) values (%s,'Mango',%s) returning id", (A, json.dumps({"2": {"2|4": 5}})))
run("staff", "delete from public.load_allocations where id=%s", (A,), fetch=False)
ok("removing the sawmill removes its tally and items", one("owner", "select count(*) from public.load_tallies where id=%s", (T2,)) == 0 and one("owner", "select count(*) from public.load_lines where tally_id=%s", (T2,)) == 0)

# ---------------------------------------------------------------- who can see tallies
P = one("owner", "insert into public.loads (party_id, change_reason) values (%s,'Plan') returning id", (buyer,))
PA = one("owner", "insert into public.load_allocations (load_id, sawmill_id) values (%s,%s) returning id", (P, mill))
one("owner", "insert into public.load_tallies (allocation_id, wood_type, counts) values (%s,'Mango',%s) returning id", (PA, json.dumps({"2": {"2|4": 5}})))
ok("staff do not receive tallies of Planning loads", one("staff", "select count(*) from public.load_tallies where load_id=%s", (P,)) == 0)
ok("an unapproved login sees no tallies", one("stranger", "select count(*) from public.load_tallies") == 0)
ok("anonymous has no access to tallies", one(None, "select has_table_privilege('anon', 'public.load_tallies', 'select')") is False)

print(f"\n{sum(results)} passed, {len(results) - sum(results)} failed")
sys.exit(0 if all(results) else 1)
