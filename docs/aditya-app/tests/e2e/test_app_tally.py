"""Browser tests for the piece-count tally (app 3.3, migration 013).
Real app page + real supabase-js + local Supabase stand-in + real migrations on local Postgres.
Staff type the client's own workbook counts into the tally screen; the app and the database
must give exactly the workbook's CFT and pieces."""
import json, os, re, subprocess, sys, time, traceback
import psycopg
from openpyxl import load_workbook
from pypdf import PdfReader
from playwright.sync_api import sync_playwright, expect

ROOT = os.path.dirname(os.path.abspath(__file__))
PORT = 8766; BASE = f"http://127.0.0.1:{PORT}/app/"
DSN = "host=/tmp port=54329 user=postgres dbname=aditya"
SBJS = "/home/claude/apptest/sbjs/package/dist/umd/supabase.js"
XLSX = "/home/claude/apptest/package/dist/xlsx.full.min.js"
JSPDF = "/home/claude/apptest/pdf/jspdf-2.5.1/package/dist/jspdf.umd.min.js"
AUTOT = "/home/claude/apptest/pdf/jspdf-autotable-3.8.2/package/dist/jspdf.plugin.autotable.min.js"
SHOTS = os.path.join(ROOT, "shots_tally"); os.makedirs(SHOTS, exist_ok=True)
WB = json.load(open(os.path.join(ROOT, "..", "db", "workbook_tally_counts.json")))
USERS = {"owner": ("d1000000-0000-0000-0000-000000000001", "owner@tally.test", "owner-test-pass"),     # local test values only
         "acc":   ("d1000000-0000-0000-0000-000000000002", "acc@tally.test", "acc-test-pass-1"),
         "staff": ("d1000000-0000-0000-0000-000000000003", "9848011111@staff.adityatraders.in", "staff-test-pass-1")}
results = []; console_errors = []


def ok(name, cond, detail=""):
    results.append(bool(cond)); print(("PASS " if cond else "FAIL ") + name + ("" if cond else f"  [{detail}]"), flush=True)


def check(name, fn):
    try: fn(); ok(name, True)
    except Exception as e: ok(name, False, str(e).split("\n")[0][:300])


def truthy(v, msg=""):
    if not v: raise AssertionError(msg or repr(v))


def db(sql, params=(), who=None):
    with psycopg.connect(DSN, autocommit=True) as c:
        if who:
            c.execute("set role authenticated")
            c.execute("select set_config('request.jwt.claims', %s, false)", (json.dumps({"sub": USERS[who][0], "role": "authenticated"}),))
        r = c.execute(sql, params); return r.fetchall() if r.description else None


subprocess.run(["/home/claude/localdb/reset.sh"], check=True, capture_output=True)
for k, (uid, email, _) in USERS.items():
    db("insert into auth.users (instance_id,id,aud,role,email) values ('00000000-0000-0000-0000-000000000000',%s,'authenticated','authenticated',%s)", (uid, email))
db("update public.profiles set full_name='Owner (Aditya & Bharat)' where id=%s", (USERS["owner"][0],))
db("update public.profiles set active=true, role='accountant', full_name='Lakshmi', perm_finance=true where id=%s", (USERS["acc"][0],))
db("update public.profiles set active=true, role='staff', full_name='Ravi' where id=%s", (USERS["staff"][0],))
mill = db("insert into public.sawmills (name, place, contact_name) values ('Sri Lakshmi Saw Mill','Rajanagaram','Appa Rao') returning id", who="owner")[0][0]
mill2 = db("insert into public.sawmills (name, place) values ('Durga Saw Mill','Peddapuram') returning id", who="owner")[0][0]
buyer = db("insert into public.parties (name, city, state, kind) values ('Goel Timber Store','Bornada','Rajasthan','buyer') returning id", who="owner")[0][0]
LID = db("insert into public.loads (party_id, destination, vehicle_no, capacity_t, driver_name, change_reason) values (%s,'Bornada','AP31TB1234',35,'Sankar','Mango order') returning id", (buyer,), who="owner")[0][0]
db("insert into public.load_files (load_id, kind, storage_path, mime_type) values (%s,'Driver with truck','v3/t/driver.jpg','image/jpeg')", (LID,), who="owner")
db("update public.loads set truck_stage='going_to_load', change_reason='Truck on the way' where id=%s", (LID,), who="owner")
A1 = db("insert into public.load_allocations (load_id, sawmill_id) values (%s,%s) returning id", (LID, mill), who="owner")[0][0]
A2 = db("insert into public.load_allocations (load_id, sawmill_id) values (%s,%s) returning id", (LID, mill2), who="owner")[0][0]
json.dump({e: [u, p] for u, e, p in USERS.values()}, open("/tmp/e2e_tally_users.json", "w"))
srv = subprocess.Popen([sys.executable, os.path.join(ROOT, "fake_supabase.py"), str(PORT)], env={**os.environ, "FAKE_SB_USERS": "/tmp/e2e_tally_users.json"})
time.sleep(1.2)
pw = sync_playwright().start()
browser = pw.chromium.launch(executable_path="/usr/bin/google-chrome", args=["--no-sandbox"])


def cdn(route):
    u = route.request.url
    route.fulfill(path=SBJS if "jsdelivr" in u else JSPDF if "jspdf.umd" in u else AUTOT if "autotable" in u else XLSX, content_type="text/javascript")


def phone(tag):
    ctx = browser.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2, accept_downloads=True)
    pg = ctx.new_page()
    pg.route("https://cdn.jsdelivr.net/**", cdn); pg.route("https://cdnjs.cloudflare.com/**", cdn)
    pg.route("https://fonts.googleapis.com/**", lambda r: r.fulfill(body="", content_type="text/css"))
    pg.on("dialog", lambda d: d.accept())
    pg.on("pageerror", lambda e: console_errors.append(f"{tag}: {e}"))
    pg.on("console", lambda m: console_errors.append(f"{tag}: {m.text}") if m.type == "error" and "406" not in m.text and "Failed to load resource" not in m.text else None)
    return pg


def login(pg, who):
    pg.goto(BASE); pg.fill("#lUser", USERS[who][1].split("@staff")[0] if who == "staff" else USERS[who][1]); pg.fill("#lPw", USERS[who][2]); pg.click("#lBtn")
    pg.wait_for_selector("#nav:not(.hidden)", timeout=10000); pg.wait_for_timeout(300)


def sheet(pg, values):
    sh = pg.wait_for_selector(".sheet")
    for k, v in values.items(): pg.locator("#sf_" + k).fill(str(v))
    pg.click("#sheetOk"); sh.wait_for_element_state("hidden", timeout=8000)


def shot(pg, name, at=None):
    if at: pg.locator(at).first.evaluate("e => { e.scrollIntoView({block:'start'}); window.scrollBy(0, -70); }")
    pg.wait_for_timeout(150); pg.screenshot(path=os.path.join(SHOTS, name + ".png"))


def type_counts(pg, counts):
    for k, n in counts.items():
        pg.locator(f'#tGrid input[data-k="{k}"]').fill(str(n))


def total_txt(pg): return pg.locator("#tTotal").inner_text()


try:
    s = phone("staff"); login(s, "staff")
    s.goto(BASE + f"#/load/{LID}"); s.wait_for_selector("#pdfBtn")
    check("each sawmill has '+ Piece tally'", lambda: expect(s.locator("[data-newtally]")).to_have_count(2))
    s.locator(f'[data-newtally="{A1}"]').click(); s.wait_for_selector("#tGrid")
    check("tally screen: Mango chosen, thickness 1\" / 1.5\" / 2\"", lambda: (expect(s.locator("#tWood")).to_have_value("Mango"), truthy([t.split('"')[0] for t in s.locator("#tTh .chip").all_inner_texts()] == ["1", "1.5", "2"], s.locator("#tTh .chip").all_inner_texts())))
    heads = s.locator("#tGrid thead th").all_inner_texts()
    check("grid widths 4\" to 11\" (the workbook's data)", lambda: truthy(heads[1:-1] == [f'{w}"' for w in range(4, 12)], heads))
    rows = [r.split("\n")[0] for r in s.locator("#tGrid tbody th").all_inner_texts()]
    check("grid lengths 1'6\" to 8'6\" in 3-inch steps, with the paper style (2.3 = 2'3\")", lambda: (truthy(rows[0] == "1'6\"" and rows[-1] == "8'6\"" and len(rows) == 29, rows), expect(s.locator("#tGrid tbody tr").nth(3).locator("th small")).to_have_text("2.3")))

    # ---- sheet 1-1 of the workbook, typed in (1 inch)
    sh11 = WB["sheets"]["1-1"]["counts"]
    type_counts(s, sh11)
    check("sheet 1-1 typed: 36.91 CFT, 477 pieces, same as the workbook", lambda: (expect(s.locator("#tTotal")).to_have_text("36.91"), expect(s.locator('#tTh [data-th="1"] .c')).to_have_text("477")))
    sm = s.locator(".tsum tr").nth(1).inner_text(); md = s.locator(".tsum tr").nth(2).inner_text(); lg = s.locator(".tsum tr").nth(3).inner_text()
    check("by size like the workbook: Small 20.36, Medium 13.11, Large 3.44 (2.02 + 0.69 + 0.73)", lambda: truthy("20.36" in sm and "13.11" in md and "3.44" in lg, (sm, md, lg)))
    check("CBM shown as CFT ÷ 35.3147 (1.05 CBM)", lambda: expect(s.locator("#tSum")).to_contain_text("= 1.05 CBM"))
    shot(s, "01_tally_typed")
    # quick add on one box
    s.locator('#tGrid input[data-k="2|4"]').click()
    check("tapping a box names it in the add bar", lambda: expect(s.locator("#tCell")).to_contain_text("2'0\" long × 4\" wide · 1\" thick"))
    for d in ("10", "5", "-1"): s.click(f'[data-add="{d}"]')
    check("+10 +5 −1 adds 14 pieces to that box", lambda: (expect(s.locator('#tGrid input[data-k="2|4"]')).to_have_value(str(sh11["2|4"] + 14)), expect(s.locator('#tTh [data-th="1"] .c')).to_have_text("491")))
    shot(s, "02_tally_quick_add", ".tqa")
    s.locator('#tGrid input[data-k="2|4"]').fill(str(sh11["2|4"]))
    # signal drop: the counts stay on the phone
    s.reload(); s.wait_for_selector("#tGrid")
    check("after a reload the unsaved counts come back (draft on the phone)", lambda: (expect(s.locator(".banner.amber")).to_contain_text("Unsaved counts"), expect(s.locator("#tTotal")).to_have_text("36.91")))
    s.click("#tSave"); s.wait_for_selector("#pdfBtn", timeout=10000); s.wait_for_timeout(300)
    items = {r[0]: (float(r[1]), r[2]) for r in db("select size_grade, quantity, pieces from public.load_lines where allocation_id=%s", (A1,))}
    check("saved: three wood items in CFT, 20.36 / 13.11 / 3.44", lambda: truthy({g: round(v[0], 2) for g, v in items.items()} == {"small": 20.36, "medium": 13.11, "large": 3.44}, items))
    check("load page shows the tally: 36.91 CFT · 477 pcs · 1\" thick", lambda: expect(s.locator(".tally").first).to_contain_text("36.91 CFT · 477 pcs · 1\" thick"))
    check("its items say 'From tally' and open the tally instead of a form", lambda: (expect(s.locator(".item .na-pill", has_text="From tally")).to_have_count(3), expect(s.locator(".item [data-item]")).to_have_count(0)))
    check("the draft is cleared after saving", lambda: truthy(s.evaluate(f"localStorage.getItem('at3_tally_{A1}_new')") is None))
    shot(s, "03_load_with_tally", ".tally")

    # ---- add the 2-inch sheet 2.0 and save with a reason
    s.locator(".tally [data-opentally]").first.click(); s.wait_for_selector("#tGrid")
    s.click('#tTh [data-th="2"]'); type_counts(s, WB["sheets"]["2.0"]["counts"])
    check("1\" + 2\" sheets: 335.05 CFT (36.91 + 298.14), 2,190 pieces", lambda: (expect(s.locator("#tTotal")).to_have_text("335.05"), expect(s.locator(".tsum tr").last).to_contain_text("2,190")))
    s.click("#tSave"); s.wait_for_timeout(500)
    check("changing a saved tally needs a reason", lambda: (expect(s.locator(".toast")).to_contain_text("reason"), truthy("#/tally/" in s.url)))
    s.fill("#tReason", "Added 2 inch pieces from sheet 2"); s.click("#tSave"); s.wait_for_selector("#pdfBtn", timeout=10000); s.wait_for_timeout(300)
    check("history: 'Piece tally changed: 36.91 CFT · 477 pcs → 335.05 CFT · 2,190 pcs' with the reason", lambda: expect(s.locator(".tl", has_text="Piece tally changed").first).to_contain_text("36.91 CFT · 477 pcs → 335.05 CFT · 2,190 pcs"))
    check("history keeps the reason", lambda: expect(s.locator(".tl", has_text="Piece tally changed").first).to_contain_text("Added 2 inch pieces from sheet 2"))
    # mark one tally item done: status only
    s.locator(".item", has_text="Small").locator("[data-done]").click(); sheet(s, {"change_reason": "Small pieces loaded"}); s.wait_for_timeout(400)
    check("marking a tally item done keeps its CFT", lambda: truthy(db("select line_status, round(quantity,2)::text from public.load_lines where allocation_id=%s and size_grade='small'", (A1,))[0] == ("done", "161.27"), db("select line_status, quantity from public.load_lines where allocation_id=%s and size_grade='small'", (A1,))))
    body = s.locator("main").inner_text()
    check("staff see no ₹ or rates on the tally items", lambda: truthy("₹" not in body and "Purchase" not in body))

    # ---- whole workbook on the second sawmill (as the app would save it)
    full = {"1": {}, "2": {}}
    for v in WB["sheets"].values():
        for k, n in v["counts"].items(): full[v["thickness"]][k] = full[v["thickness"]].get(k, 0) + n
    db("insert into public.load_tallies (allocation_id, wood_type, counts, change_reason) values (%s,'Mango',%s,'Whole vehicle from the workbook')", (A2, json.dumps(full)), who="staff")
    s.reload(); s.wait_for_selector("#pdfBtn"); s.wait_for_timeout(300)
    check("the whole workbook vehicle shows 1,350.00 CFT · 8,245 pcs", lambda: expect(s.locator(".tally", has_text="1,350.00")).to_contain_text("1,350.00 CFT · 8,245 pcs · 1\", 2\" thick"))
    s.locator(f'.tally:has-text("1,350.00") [data-opentally]').click(); s.wait_for_selector("#tGrid")
    sz = [s.locator(".tsum tr").nth(i).inner_text() for i in (1, 2, 3)]
    check("its tally screen: Small 621.46, Medium 646.25, Large 82.29 (the workbook's S/M/L table)", lambda: truthy("621.46" in sz[0] and "646.25" in sz[1] and "82.29" in sz[2], sz))
    check("= 38.23 CBM", lambda: expect(s.locator("#tSum")).to_contain_text("= 38.23 CBM"))
    shot(s, "04_tally_whole_vehicle", "#tSum")

    # ---- staff PDF: tally summary, still no money
    s.goto(BASE + f"#/load/{LID}"); s.wait_for_selector("#pdfBtn")
    with s.expect_download(timeout=20000) as dl:
        s.click("#pdfBtn")
    pdf = os.path.join(SHOTS, "tally_loading_details.pdf"); dl.value.save_as(pdf)
    text = "\n".join(p.extract_text() for p in PdfReader(pdf).pages)
    check("PDF has the piece tally table with the size bands", lambda: truthy("Piece tally - Small 1'6\" to 2'9\", Medium 3'0\" to 4'9\", Large 5'0\" and up" in text, text[:500]))
    check("PDF tally rows: 1,350 CFT / 8,245 pcs for the whole vehicle", lambda: truthy("1,350 CFT" in text and "8,245 pcs" in text, text[-800:]))
    bad = [w for w in ["Rate", "Amount", "GST", "Taxable", "Total", "Balance", "Freight", "Bank", "Payment", "₹", "Rs."] if w in text]
    check("PDF still has no money words or values", lambda: truthy(not bad, bad))
    # ---- Excel: Piece tally sheet
    s.goto(BASE + "#/export"); s.wait_for_selector("#xGo")
    with s.expect_download(timeout=20000) as dl2:
        s.click("#xGo")
    xp = os.path.join(SHOTS, "export.xlsx"); dl2.value.save_as(xp)
    wb = load_workbook(xp); ws = wb["Piece tally"]
    hdr = [c.value for c in ws[1]]; rows = list(ws.iter_rows(min_row=2, values_only=True))
    ci = {h: i for i, h in enumerate(hdr)}
    check("Excel has a Piece tally sheet: thickness, length, width, pieces, size, CFT", lambda: truthy(hdr == ["Load", "Saw Mill Name", "Wood", "Thickness (in)", "Length (ft)", "Length", "Width (in)", "Pieces", "Size", "CFT"], hdr))
    check("Excel tally adds up to 335.05 + 1,350.00 CFT and 2,190 + 8,245 pieces", lambda: truthy(round(sum(r[ci["CFT"]] for r in rows), 2) == 1685.05 and sum(r[ci["Pieces"]] for r in rows) == 2190 + 8245, (sum(r[ci["CFT"]] for r in rows), sum(r[ci["Pieces"]] for r in rows))))

    # ---- owner: rate on a tally item; accountant sees the change
    o = phone("owner"); login(o, "owner")
    o.goto(BASE + f"#/load/{LID}"); o.wait_for_selector("#pdfBtn")
    o.locator(f'.alloc:has-text("Durga Saw Mill") .item:has-text("Large") [data-rate]').click(); sheet(o, {"rate": "400"}); o.wait_for_timeout(500)
    check("owner sets a rate on a tally item: 82.29 CFT × ₹400 = ₹32,916", lambda: expect(o.locator('.alloc:has-text("Durga Saw Mill") .item:has-text("Large") .price')).to_contain_text("₹32,916"))
    a = phone("acc"); login(a, "acc")
    a.goto(BASE + f"#/load/{LID}"); a.wait_for_selector("#pdfBtn")
    check("accountant sees the tally and its history (Ravi, reason)", lambda: (expect(a.locator(".tally")).to_have_count(2), expect(a.locator(".tl", has_text="Piece tally changed").first).to_contain_text("Ravi")))

    # ---- locked after Loaded
    db("update public.app_settings set value=0 where key='weigh_slip_required'")
    db("update public.load_lines set line_status='done' where load_id=%s", (LID,), who="owner")
    db("update public.load_allocations set reached_at=now() where load_id=%s", (LID,), who="owner")
    db("update public.loads set truck_stage='under_loading', change_reason='At mill' where id=%s", (LID,), who="owner")
    db("update public.loads set truck_stage='loaded', change_reason='Loaded' where id=%s", (LID,), who="owner")
    s.goto(BASE + f"#/load/{LID}"); s.wait_for_selector("#pdfBtn")
    check("after Loaded there is no '+ Piece tally'", lambda: expect(s.locator("[data-newtally]")).to_have_count(0))
    s.locator(".tally [data-opentally]").first.click(); s.wait_for_selector("#tGrid")
    check("after Loaded the tally opens read-only", lambda: (expect(s.locator(".banner.amber")).to_contain_text("moving it back to Under loading"), expect(s.locator("#tSave")).to_have_count(0), truthy(s.locator("#tGrid input").first.is_disabled())))

    bad = [e for e in console_errors if "ERR_INTERNET_DISCONNECTED" not in e and "Failed to fetch" not in e]
    check("no JavaScript errors", lambda: truthy(not bad, bad[:3]))
except Exception:
    traceback.print_exc(); ok("test run crashed", False)
finally:
    browser.close(); pw.stop(); srv.terminate()
print(f"\n{sum(results)} passed, {len(results) - sum(results)} failed")
sys.exit(0 if all(results) else 1)
