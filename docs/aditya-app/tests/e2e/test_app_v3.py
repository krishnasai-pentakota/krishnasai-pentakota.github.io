"""Browser acceptance tests for the master product requirements (app 3.0).
Real app page + real supabase-js + local Supabase stand-in + real migrations on local Postgres.
Phone-sized screens (390 x 844), one browser per person (= separate devices).
Covers acceptance tests 1-10 of the master prompt."""
import json, os, re, subprocess, sys, time, traceback, io
import psycopg
from pypdf import PdfReader
from playwright.sync_api import sync_playwright, expect

ROOT = os.path.dirname(os.path.abspath(__file__))
PORT = 8765; BASE = f"http://127.0.0.1:{PORT}/app/"
DSN = "host=/tmp port=54329 user=postgres dbname=aditya"
SBJS = "/home/claude/apptest/sbjs/package/dist/umd/supabase.js"
XLSX = "/home/claude/apptest/package/dist/xlsx.full.min.js"
JSPDF = "/home/claude/apptest/pdf/jspdf-2.5.1/package/dist/jspdf.umd.min.js"
AUTOT = "/home/claude/apptest/pdf/jspdf-autotable-3.8.2/package/dist/jspdf.plugin.autotable.min.js"
IMG = "/home/claude/apptest/kanta_slip.png"
SHOTS = os.path.join(ROOT, "shots_v3"); os.makedirs(SHOTS, exist_ok=True)
OWNER = ("owner@adityatraders.test", "owner-test-pass")       # local test values only
results = []; console_errors = []


def ok(name, cond, detail=""):
    results.append(bool(cond)); print(("PASS " if cond else "FAIL ") + name + ("" if cond else f"  [{detail}]"), flush=True)


def check(name, fn):
    try: fn(); ok(name, True)
    except Exception as e: ok(name, False, str(e).split("\n")[0][:300])


def truthy(v, msg=""):
    if not v: raise AssertionError(msg or repr(v))


def db(sql, params=()):
    with psycopg.connect(DSN, autocommit=True) as c:
        r = c.execute(sql, params); return r.fetchall() if r.description else None


subprocess.run(["/home/claude/localdb/reset.sh"], check=True, capture_output=True)
db("insert into auth.users (instance_id,id,aud,role,email) values ('00000000-0000-0000-0000-000000000000','c0000000-0000-0000-0000-000000000001','authenticated','authenticated',%s)", (OWNER[0],))
db("update public.profiles set full_name='Owner (Aditya & Bharat)' where email=%s", (OWNER[0],))
json.dump({OWNER[0]: ["c0000000-0000-0000-0000-000000000001", OWNER[1]]}, open("/tmp/e2e_users.json", "w"))
subprocess.run("pkill -f fake_supabase.py", shell=True)
srv = subprocess.Popen([sys.executable, os.path.join(ROOT, "fake_supabase.py"), str(PORT)], env={**os.environ, "FAKE_SB_USERS": "/tmp/e2e_users.json"})
time.sleep(1.2)
pw = sync_playwright().start()
browser = pw.chromium.launch(executable_path="/usr/bin/google-chrome", args=["--no-sandbox"])


def cdn(route):
    u = route.request.url
    path = SBJS if "jsdelivr" in u else JSPDF if "jspdf.umd" in u else AUTOT if "autotable" in u else XLSX
    route.fulfill(path=path, content_type="text/javascript")


def phone(tag):
    ctx = browser.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2, accept_downloads=True)
    pg = ctx.new_page()
    pg.route("https://cdn.jsdelivr.net/**", cdn); pg.route("https://cdnjs.cloudflare.com/**", cdn)
    pg.route("https://fonts.googleapis.com/**", lambda r: r.fulfill(body="", content_type="text/css"))
    pg.on("dialog", lambda d: d.accept())
    pg.on("pageerror", lambda e: console_errors.append(f"{tag}: {e}"))
    pg.on("console", lambda m: console_errors.append(f"{tag}: {m.text}") if m.type == "error" and "406" not in m.text and "Failed to load resource" not in m.text else None)
    return pg


def login(pg, user, password):
    pg.goto(BASE); pg.fill("#lUser", user); pg.fill("#lPw", password); pg.click("#lBtn")
    pg.wait_for_selector("#nav:not(.hidden)", timeout=10000); pg.wait_for_timeout(300)


def sheet(pg, values, ok_btn=True):
    sh = pg.wait_for_selector(".sheet")
    for k, v in values.items():
        el = pg.locator("#sf_" + k)
        t = el.evaluate("e => e.tagName + ':' + (e.type || '')")
        if t.startswith("SELECT"):
            el.select_option(value=str(v)[1:]) if str(v).startswith("=") else el.select_option(label=v)
        elif t.endswith("checkbox"): el.set_checked(bool(v))
        elif t.endswith("file"): el.set_input_files(v)
        else: el.fill(str(v))
    if ok_btn:
        pg.click("#sheetOk")
        try: sh.wait_for_element_state("hidden", timeout=8000)
        except Exception:
            print("SHEET STUCK:", pg.locator(".sheet h2").all_inner_texts(), pg.locator("#sheetErr").all_inner_texts(), pg.locator(".toast").all_inner_texts(), pg.locator(".sheet").count(), repr(pg.locator("#sf_quantity").evaluate("e=>e.outerHTML + ' VALUE=' + e.value + ' valid=' + e.validity.valid")), db("select id, wood_type, quantity, line_status from public.load_lines order by id")); raise


def shot(pg, name, full=True):
    pg.screenshot(path=os.path.join(SHOTS, name + ".png"), full_page=full)


def wait_load_page(pg):
    pg.wait_for_selector("#pdfBtn", timeout=10000); pg.wait_for_timeout(250)


try:
    # ============================================================ owner: people
    o = phone("owner"); login(o, *OWNER)
    check("owner home shows GimBooks-style quick actions incl. New load, Expenses, Rates, Team",
          lambda: [expect(o.locator(".qa a", has_text=t)).to_be_visible() for t in ["New load", "Register truck", "Expenses", "Sawmill rates", "Team"]])
    check("owner top bar has '+ New load' for quick access", lambda: (expect(o.locator("#topNew")).to_be_visible(), expect(o.locator("#topNew")).to_have_text("+ New load")))
    o.goto(BASE + "#/team"); o.wait_for_selector("#addPerson")

    def add_person(role_label, name, login_id, pwd, extra=None):
        o.click("#addPerson"); sheet(o, {"role": role_label})
        sheet(o, {"full_name": name, "login": login_id, "password": pwd, **(extra or {})})
        o.wait_for_selector(f"text={name}", timeout=8000)
    add_person("Accountant", "Lakshmi", "accounts@adityatraders.test", "acc-test-pass-1")
    for i in range(1, 11):
        add_person("Staff", f"Staff {i}", f"98480{i:05d}", f"staff-test-pass-{i}")
    perms = {r[0]: r[1:] for r in db("select full_name, role, perm_plan, perm_finance, perm_expenses, perm_rates, perm_people from public.profiles where active")}
    check("accountant: bills/payments (views rates and charges); no planning, no rate or charge entry, no people", lambda: truthy(perms["Lakshmi"] == ("accountant", False, True, False, False, False), perms["Lakshmi"]))
    check("10 staff with no money permissions", lambda: truthy(sum(1 for k, v in perms.items() if v == ("staff", False, False, False, False, False)) == 10))
    check("only one owner login (shared by Aditya and Bharat)", lambda: truthy(db("select count(*) from public.profiles where role='owner'")[0][0] == 1))
    o.click("#addPerson"); o.wait_for_selector("#sf_role")
    check("Team offers Staff / Accountant / Owner roles only (no separate freight role)", lambda: truthy(o.locator("#sf_role option").all_inner_texts() == ["Staff", "Accountant", "Owner"], o.locator("#sf_role option").all_inner_texts()))
    o.click("#sheetCancel")
    shot(o, "01_team")

    # owner plans a load (Planning)
    o.goto(BASE + "#/new"); o.wait_for_selector("#lf")
    o.select_option("select[name=party_id]", value="__new"); sheet(o, {"name": "Annapurna Traders", "city": "Koraput", "state": "Odisha"})
    o.fill("input[name=destination]", "Koraput"); o.fill("input[name=change_reason]", "Order from Annapurna")
    o.click("#fSave"); o.wait_for_selector("#pdfBtn", timeout=8000)
    plan_id = db("select id from public.loads where truck_stage='planning'")[0][0]
    check("owner's new load starts in Planning", lambda: expect(o.locator(".sect .pill.s-planning")).to_be_visible())

    # ============================================================ staff: Test 6 (no planning, no money anywhere)
    s = phone("staff"); login(s, "98480 00001", "staff-test-pass-1")
    shot(s, "10_staff_home")
    check("staff top bar has '+ Truck' (register) instead of New load", lambda: (expect(s.locator("#topNew")).to_have_text("+ Truck"), truthy(s.locator("#topNew").get_attribute("href") == "#/register")))
    check("T6 staff home: no Planning or Truck fixed tiles", lambda: (expect(s.locator(".tile[data-goto=planning]")).to_have_count(0), expect(s.locator(".tile[data-goto=truck_fixed]")).to_have_count(0)))
    check("T6 staff home: no New load / Expenses / Rates / Parties actions, no money tiles", lambda: (expect(s.locator(".qa a", has_text="New load")).to_have_count(0), expect(s.locator(".qa a", has_text="Expenses")).to_have_count(0), expect(s.locator(".qa a", has_text="Sawmill rates")).to_have_count(0), expect(s.locator(".tile.money")).to_have_count(0)))
    s.goto(BASE + "#/loads"); s.wait_for_selector(".chip")
    check("T6 staff load filters have no Planning / Truck fixed", lambda: (expect(s.locator("[data-f=planning]")).to_have_count(0), expect(s.locator("[data-f=truck_fixed]")).to_have_count(0)))
    check("T6 the owner's Planning load is not on staff phones", lambda: expect(s.locator(".loadc")).to_have_count(0))
    for path, name in [("#/new", "Register truck"), ("#/expenses", None), ("#/rates", None), ("#/team", None), ("#/parties", "Mills")]:
        s.goto(BASE + path); s.wait_for_timeout(500)
        check(f"T6 staff opening {path} is sent away", lambda: truthy(("#/register" in s.url if name == "Register truck" else ("#/mills" in s.url if name == "Mills" else s.url.endswith("#/"))), s.url))
    s.goto(BASE + f"#/load/{plan_id}"); s.wait_for_timeout(700)
    check("T6 staff cannot open the Planning load by its address", lambda: expect(s.locator("text=not available to you")).to_be_visible())

    # ============================================================ staff: Test 1 / 2 (driver photo compulsory; licence and C-Book optional)
    s.goto(BASE + "#/register"); s.wait_for_selector("#lf")
    s.fill("input[name=vehicle_no]", "ap 39 tb 5678"); s.click("[data-seg=capacity_t] button[data-v='35']"); s.fill("input[name=capacity_cft]", "1300")
    s.fill("input[name=driver_name]", "Sankar"); s.fill("input[name=driver_phone]", "9876543210")
    s.click("#fSave"); s.wait_for_timeout(700)
    check("T1 without the photo: red 'Driver photo with truck is mandatory.'", lambda: (expect(s.locator("#regMust")).to_be_visible(), expect(s.locator("#regMust")).to_contain_text("Driver photo with truck is mandatory."), truthy(s.locator("#regMust").evaluate("e => getComputedStyle(e).borderColor") == "rgb(198, 40, 40)")))
    check("T1 photo section highlighted red; nothing saved", lambda: (truthy("req" in s.locator("#reg-driver").get_attribute("class")), truthy(db("select count(*) from public.loads where vehicle_no='AP39TB5678'")[0][0] == 0)))
    check("T2 licence and C-Book show 'Not Provided'", lambda: (expect(s.locator("#reg-licence-st")).to_have_text("Not Provided"), expect(s.locator("#reg-cbook-st")).to_have_text("Not Provided")))
    shot(s, "11_register_missing_photo")
    s.set_input_files("#reg-driver-in", IMG); s.wait_for_timeout(200)
    check("T1 after choosing the photo the warning goes", lambda: expect(s.locator("#regMust")).to_be_hidden())
    s.click("#fSave"); wait_load_page(s)
    L = db("select id, truck_stage from public.loads where vehicle_no='AP39TB5678'")[0]; LID = L[0]
    check("T2 staff proceeds without licence or C-Book; truck saved at Going to load", lambda: truthy(L[1] == "going_to_load", L))
    check("T1 driver photo stored with the truck", lambda: truthy(db("select count(*) from public.load_files where load_id=%s and kind='Driver with truck'", (LID,))[0][0] == 1))
    check("T2 load page: licence and C-Book 'Not Provided' in grey", lambda: (expect(s.locator("#doc-licence .st")).to_have_text("Not Provided"), expect(s.locator("#doc-cbook .st")).to_have_text("Not Provided"), truthy("na" in s.locator("#doc-licence").get_attribute("class"))))

    # accountant opens the new truck once (her "last checked" point), on her own phone
    a = phone("accountant"); login(a, "accounts@adityatraders.test", "acc-test-pass-1")
    a.goto(BASE + f"#/load/{LID}"); wait_load_page(a); a.click("#chk"); a.wait_for_selector("text=Marked as checked")

    # ============================================================ Test 3 (3 sawmills, several items)
    def add_alloc(name, place, owner_name, party=""):
        s.click("#addAlloc"); sheet(s, {"sawmill_id": "=__new", "party_name": party})
        sheet(s, {"name": name, "place": place, "contact_name": owner_name})
        s.wait_for_selector(f".alloc:has-text('{name}')", timeout=8000); s.wait_for_timeout(300)

    def add_item(mill, vals):
        s.locator(f".alloc:has-text('{mill}') [data-additem]").click(); sheet(s, vals); s.wait_for_timeout(500); wait_load_page(s)
    add_alloc("Sawmill A", "Rajanagaram", "Appa Rao", "Sri Lakshmi Timbers")
    add_alloc("Sawmill B", "Peddapuram", "Ramana")
    add_alloc("Sawmill C", "Rajam", "Krishna")
    add_item("Sawmill A", {"wood_type": "Country Wood", "size_grade": "Large", "quantity": "700", "unit": "CFT", "dimensions": '3" x 3" x 6\'', "change_reason": "Tally sheet 1"})
    add_item("Sawmill A", {"wood_type": "Country Wood", "size_grade": "Medium", "quantity": "200", "unit": "CFT", "change_reason": "Tally sheet 2"})
    add_item("Sawmill B", {"wood_type": "Acacia", "size_grade": "Medium", "quantity": "200", "unit": "CFT", "change_reason": "Tally"})
    add_item("Sawmill C", {"wood_type": "Teak", "size_grade": "Small", "quantity": "100", "unit": "Pieces", "pieces": "100", "dimensions": '4" x 4" x 7\'', "change_reason": "Counted"})
    s.locator(".alloc:has-text('Sawmill C') [data-additem]").click(); sheet(s, {"wood_type": "Sandalwood", "size_grade": "Small", "quantity": "1", "unit": "CFT"}, ok_btn=False)
    s.click("#sheetOk"); s.wait_for_timeout(500)
    check("staff must pick a saved wood type (cannot invent one)", lambda: expect(s.locator(".toast")).to_contain_text("Choose a wood type from the list"))
    s.click("#sheetCancel") if s.locator("#sheetCancel").count() else None
    counts = db("select (select count(*) from public.loads where vehicle_no='AP39TB5678'), (select count(*) from public.load_allocations where load_id=%s), (select count(*) from public.load_lines where load_id=%s)", (LID, LID))[0]
    check("T3 one truck trip, 3 sawmills, 4 wood items (no duplicate trucks)", lambda: truthy(counts == (1, 3, 4), counts))
    check("T3 sawmill owner and party name kept separately", lambda: truthy(db("select owner_name, party_name from public.load_allocations a join public.sawmills s on s.id=a.sawmill_id where s.name='Sawmill A'")[0] == ("Appa Rao", "Sri Lakshmi Timbers")))
    check("T3 load summary keeps CFT and Pieces apart", lambda: truthy(db("select qty_summary from public.v_loads where id=%s", (LID,))[0][0] == "1,100 CFT + 100 Pieces"))
    shot(s, "12_staff_sawmills")

    # ============================================================ Under loading only after the truck reached a sawmill
    check("before arrival every sawmill shows 'Truck not here yet'", lambda: expect(s.locator(".alloc .na-pill", has_text="Truck not here yet")).to_have_count(3))
    s.click("#nextStage"); sheet(s, {"a": "Sawmill A"})            # 'Move to Under loading' asks which sawmill was reached
    sheet(s, {})                                                       # confirm "Truck reached Sawmill A"
    s.wait_for_selector(".sect .pill.s-under_loading", timeout=8000); wait_load_page(s)
    check("Under loading starts when the truck reaches Sawmill A (time recorded)", lambda: truthy(db("select l.truck_stage, a.reached_at is not null from public.loads l join public.load_allocations a on a.load_id=l.id join public.sawmills m on m.id=a.sawmill_id where l.id=%s and m.name='Sawmill A'", (LID,))[0] == ("under_loading", True)))
    allocs = {r[1]: r[0] for r in db("select a.id, s.name from public.load_allocations a join public.sawmills s on s.id=a.sawmill_id where a.load_id=%s", (LID,))}

    # ============================================================ Test 5 (weigh slip at the end of loading at each sawmill)
    check("T5 three sawmills → three weigh-slip sections, each 'Not Uploaded'", lambda: (expect(s.locator(".slip")).to_have_count(3), expect(s.locator(".slip .na-pill")).to_have_count(3)))

    def loading_done(mill, net=None, slip=True):
        s.locator(f".alloc:has-text('{mill}') [data-ldone]").click()
        vals = {"change_reason": f"Loading done at {mill}"}
        if slip: vals["slip"] = IMG
        if net: vals["slip_net_weight_t"] = net
        sheet(s, vals); s.wait_for_selector(f".alloc:has-text('{mill}') .ok-pill:has-text('Loading done')", timeout=10000); wait_load_page(s)
    s.locator(".alloc:has-text('Sawmill A') [data-ldone]").click(); s.click("#sheetOk"); s.wait_for_timeout(300)
    check("T5 'Loading done' asks for that sawmill's weigh slip", lambda: expect(s.locator("#sheetErr")).to_contain_text("Weigh slip photo"))
    s.click("#sheetCancel"); s.wait_for_timeout(300)
    loading_done("Sawmill A", "21.3")
    s.set_input_files(f"#slip-{allocs['Sawmill A']}", IMG); s.wait_for_selector(f".slip[data-slipfor='{allocs['Sawmill A']}'] .ok-pill:has-text('2 uploaded')", timeout=10000); wait_load_page(s)
    s.locator(".alloc:has-text('Sawmill B') [data-reached]").click(); sheet(s, {}); wait_load_page(s)
    loading_done("Sawmill B", "6.9")
    s.locator(".alloc:has-text('Sawmill C') [data-reached]").click(); sheet(s, {}); wait_load_page(s)
    check("T5 Sawmill C still shows 'Not Uploaded'", lambda: expect(s.locator(f".slip[data-slipfor='{allocs['Sawmill C']}'] .na-pill")).to_have_text("Not Uploaded"))
    s.click("#nextStage"); s.wait_for_timeout(400)
    check("Loaded is refused while Sawmill C has no weigh slip", lambda: expect(s.locator(".toast")).to_contain_text("Upload the weigh slip for: Sawmill C"))
    loading_done("Sawmill C", "6.1")
    slips = dict(db("select s.name, count(f.id) from public.load_allocations a join public.sawmills s on s.id=a.sawmill_id left join public.load_files f on f.allocation_id=a.id and f.kind='Weigh slip' where a.load_id=%s group by s.name", (LID,)))
    check("T5 each slip is linked to its own sawmill (A: 2, B: 1, C: 1)", lambda: truthy(slips == {"Sawmill A": 2, "Sawmill B": 1, "Sawmill C": 1}, slips))
    check("loading done marks every item of that sawmill done; slip net weights kept", lambda: truthy(db("select count(*) filter (where line_status='done'), (select string_agg(slip_net_weight_t::text, ',' order by id) from public.load_allocations where load_id=%s) from public.load_lines where load_id=%s", (LID, LID))[0] == (4, "21.300,6.900,6.100")))
    shot(s, "13_weigh_slips")
    s.click("#nextStage"); sheet(s, {"net_weight_t": "34.4", "change_reason": "All sawmills loaded"}); s.wait_for_selector(".sect .pill.s-loaded", timeout=8000)
    check("staff loads the truck (Loaded, kata 34.4 T)", lambda: truthy(db("select truck_stage, net_weight_t::text from public.loads where id=%s", (LID,))[0] == ("loaded", "34.400")))

    # ============================================================ owner enters freight and other charges (Test 7)
    o.goto(BASE + f"#/load/{LID}"); wait_load_page(o)
    o.click("#addExp"); sheet(o, {"cost_type": "Truck Freight", "amount": "95000", "paid_to": "Sri Sai Transport", "change_reason": "Freight agreed"}); wait_load_page(o)
    o.click("#addExp"); sheet(o, {"cost_type": "Hamali / Loading", "amount": "6000", "allocation_id": "Sawmill A", "receipt": IMG, "change_reason": "Paid loading gang"})
    o.wait_for_selector(".tot:has-text('Hamali / Loading')", timeout=10000); wait_load_page(o)
    check("T7 owner records freight and a sawmill-linked charge with receipt", lambda: truthy(db("select count(*), sum(amount), count(receipt_path), count(allocation_id) from public.load_costs where load_id=%s", (LID,))[0] == (2, 101000, 1, 1)))
    shot(o, "20_owner_expenses")

    # ============================================================ owner: rates (Test 9)
    o.goto(BASE + "#/rates"); o.wait_for_selector("#rMill")
    o.select_option("#rMill", label="Sawmill A, Rajanagaram"); o.wait_for_timeout(500)
    o.click("#rAdd"); sheet(o, {"wood_type": "Country Wood", "size_grade": "Large", "unit": "CFT", "rate": "350", "effective_from": "2026-11-01", "change_reason": "Agreed on visit"}); o.wait_for_timeout(500)
    o.goto(BASE + f"#/load/{LID}"); wait_load_page(o)
    o.locator(".alloc:has-text('Sawmill A') .item:has-text('Large') [data-rate]").click()
    check("T9 rate is suggested from the sawmill's rate card", lambda: (expect(o.locator("#sf_rate")).to_have_value("350")))
    sheet(o, {"adjustment": "-500"}); wait_load_page(o)
    check("item amount 700 × 350 − 500 = ₹2,44,500", lambda: expect(o.locator(".item:has-text('Large') .price")).to_contain_text("₹2,44,500"))
    o.goto(BASE + "#/rates"); o.wait_for_selector("#rAdd"); o.click("#rAdd")
    sheet(o, {"wood_type": "Country Wood", "size_grade": "Large", "unit": "CFT", "rate": "365", "effective_from": "2026-11-20", "change_reason": "Mill raised rate"}); o.wait_for_timeout(600)
    check("T9 new current rate shown, previous rate kept in history", lambda: (expect(o.locator("table.t")).to_contain_text("₹365"), expect(o.locator(".tl", has_text="₹350")).to_be_visible()))
    check("T9 the recorded transaction is unchanged (rate 350, amount 2,44,500)", lambda: truthy(db("select rate::text, (select amount::text from public.v_lines where id=lp.line_id) from public.line_prices lp")[0] == ("350.00", "244500.00")))
    shot(o, "30_owner_rates")

    # ============================================================ Test 4: staff PDF has no money anywhere
    s.goto(BASE + f"#/load/{LID}"); wait_load_page(s)
    with s.expect_download(timeout=20000) as dl:
        s.click("#pdfBtn")
    pdf_path = os.path.join(SHOTS, "staff_loading_details.pdf"); dl.value.save_as(pdf_path)
    text = "\n".join(p.extract_text() for p in PdfReader(pdf_path).pages)
    open(os.path.join(SHOTS, "staff_pdf.txt"), "w").write(text)
    heads = ["Sl. No.", "Saw Mill Name", "Name of Product", "Size", "Quantity", "Unit"]
    pos = [text.find(h) for h in heads]
    check("T4 PDF title is an operational document, not a tax invoice", lambda: truthy("TRUCK LOADING / DISPATCH DETAILS" in text and "not a tax invoice" in text))
    check("T4 PDF columns: Sl. No. first, Saw Mill Name second, then Product, Size, Quantity, Unit", lambda: truthy(all(p >= 0 for p in pos) and pos == sorted(pos), pos))
    check("T4 PDF rows carry sawmill, wood details, size, quantity and unit", lambda: truthy(all(t in text for t in ["Sawmill A", "Sawmill B", "Sawmill C", "Country Wood", 'x 6\'', "Acacia", "Teak", "Large", "Medium", "Small", "700", "Pieces", "100 pcs", "AP39TB5678", "Sankar", "net 21.3 T"]), text[:400]))
    check("T4 Sawmill A appears on two rows (two wood items)", lambda: truthy(len(re.findall(r"\n\d+ Sawmill A", "\n" + text)) == 2 or text.count("Sawmill A") >= 3, text.count("Sawmill A")))
    bad = [w for w in ["Rate", "Amount", "GST", "CGST", "SGST", "IGST", "Taxable", "Total", "Balance", "Freight", "Bank", "IFSC", "Payment", "₹", "Rs.", "95,000", "95000", "350", "2,44,500", "6,000"] if w in text]
    check("T4 PDF contains no financial values or financial fields", lambda: truthy(not bad, bad))
    o.goto(BASE + f"#/load/{LID}"); wait_load_page(o)
    with o.expect_download(timeout=20000) as dl2:
        o.click("#pdfBtn")
    otext = "\n".join(p.extract_text() for p in PdfReader(dl2.value.path()).pages)
    check("T4 even the owner's loading PDF has no money (same staff layout)", lambda: truthy(not [w for w in ["Rate", "Amount", "GST", "Freight", "95,000", "350"] if w in otext]))

    # staff screens: no money anywhere
    body = s.locator("main").inner_text()
    check("T6 staff load page shows no ₹, rates, freight or expenses", lambda: truthy(not [w for w in ["₹", "Purchase", "Freight", "expense", "Billing", "Payments"] if w in body], [w for w in ["₹", "Purchase", "Freight", "expense", "Billing", "Payments"] if w in body]))
    pr = phone("probe"); pr.goto(BASE); pr.wait_for_selector("#lUser")
    leak = pr.evaluate("""async () => {
      const sb = window.supabase.createClient(location.origin, 'local-anon-key', {auth:{storageKey:'probe'}});
      await sb.auth.signInWithPassword({email:'9848000001@staff.adityatraders.in', password:'staff-test-pass-1'});
      const out = {};
      for (const t of ['load_costs','line_prices','load_billing','payments','sawmill_rates','v_balances','expense_categories']) { const r = await sb.from(t).select('*'); out[t] = (r.data||[]).length; }
      const v = await sb.from('v_loads').select('freight_total,costs_total,purchase_total,invoice_total,bill_stage'); out.v_loads_money = (v.data||[]).filter(x => Object.values(x).some(y => y !== null)).length;
      const a = await sb.from('activity').select('visibility,truck_stage'); out.money_or_planning_history = (a.data||[]).filter(x => x.visibility !== 'all' || ['planning','truck_fixed'].includes(x.truck_stage)).length;
      const pl = await sb.from('loads').select('id').eq('truck_stage','planning'); out.planning_loads = (pl.data||[]).length;
      const rc = await sb.storage.from('lorry-files').createSignedUrl('expenses/x.jpg', 60); out.receipt_link = rc.data ? 1 : 0;
      return out; }""")
    check("T6 through the API staff receive no expenses, rates, bills, payments, balances, money history or planning loads", lambda: truthy(all(v == 0 for v in leak.values()), leak))

    # ============================================================ accountant: Test 7 / 8
    a.goto(BASE + "#/loads"); a.wait_for_selector(".loadc")
    a.locator(".loadc", has_text="AP39TB5678").click(); wait_load_page(a)
    check("T8 accountant sees staff's changes in red with who and reason", lambda: (expect(a.locator(".tl.new").first).to_be_visible(), expect(a.locator(".tl", has_text="All sawmills loaded").first).to_contain_text("Staff 1")))
    check("T8 quantity / weigh slip / sawmill additions are in the history", lambda: (expect(a.locator(".tl", has_text="Uploaded document").first).to_be_visible(), expect(a.locator(".tl", has_text="Added sawmill").first).to_be_visible()))
    check("T7 accountant sees billing and expenses", lambda: (expect(a.locator("#editBill")).to_be_visible(), expect(a.locator(".tot", has_text="Truck Freight").first).to_be_visible()))
    check("accountant views rates and charges but cannot enter them (owner login only)", lambda: (expect(a.locator(".price").first).to_contain_text("₹350"), expect(a.locator("[data-rate]")).to_have_count(0), expect(a.locator("#addExp")).to_have_count(0), expect(a.locator("[data-cost]")).to_have_count(0)))
    a.goto(BASE + "#/team"); a.wait_for_timeout(500)
    check("T7 accountant without the people permission cannot open Team", lambda: truthy(a.url.endswith("#/"), a.url))
    shot(a, "40_accountant_home")

    # ============================================================ Test 10: two devices, one database
    s.goto(BASE + f"#/load/{LID}"); wait_load_page(s)
    s.fill("#noteText", "Tarpaulin tied, leaving at 6 pm"); s.click("#noteForm button")
    try: s.wait_for_selector(".tl.note:has-text('Tarpaulin tied')", timeout=10000)
    except Exception: print("NOTE FAIL", s.locator(".toast").all_inner_texts(), s.url, db("select actor, reason from public.activity where action='note'"), s.locator("#noteText").input_value(), s.locator("#noteForm button").count()); shot(s, "zz_note_fail"); raise
    o.goto(BASE + "#/updates"); o.wait_for_selector(".tl")
    check("T10 a staff update on one phone appears on the owner's phone", lambda: expect(o.locator(".tl").first).to_contain_text("Tarpaulin tied"))
    o.goto(BASE + "#/loads"); o.click("#refreshBtn"); o.wait_for_timeout(600)
    check("T10 owner's list shows the truck flagged as changed", lambda: expect(o.locator(".loadc.edited", has_text="AP39TB5678")).to_be_visible())
    shot(o, "50_owner_home", True)

    bad = [e for e in console_errors if "ERR_INTERNET_DISCONNECTED" not in e and "Failed to fetch" not in e]
    check("no JavaScript errors in any session", lambda: truthy(not bad, bad[:3]))
except Exception:
    traceback.print_exc(); ok("test run crashed", False)
finally:
    browser.close(); pw.stop(); srv.terminate()
print(f"\n{sum(results)} passed, {len(results) - sum(results)} failed")
sys.exit(0 if all(results) else 1)
