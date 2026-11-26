"""End-to-end browser tests: the real app page + real supabase-js + the local
Supabase stand-in + the real migrations on local Postgres.

Journeys (phone-sized screen, 390 x 844):
  owner     signs in, adds the accountant and 10 staff, creates a load with a
            new buyer/transporter/mills, sets purchase rates, loads, photos
  staff     signs in with a phone number, sees the red flag, sees NO prices,
            bills or payments, moves the stage with a reason, posts an update
  accountant sees exactly what staff changed (who, exact time, reason, stage),
            bills, records payments, checks balances, exports Excel
  owner     sees the accountant's changes flagged
Run:  python3 tests/e2e/test_app.py
"""
import json, os, re, subprocess, sys, time, traceback
import psycopg
from playwright.sync_api import sync_playwright, expect

ROOT = os.path.dirname(os.path.abspath(__file__))
PORT = 8765
BASE = f"http://127.0.0.1:{PORT}/app/"
DSN = "host=/tmp port=54329 user=postgres dbname=aditya"
SBJS = "/home/claude/apptest/sbjs/package/dist/umd/supabase.js"
XLSX = "/home/claude/apptest/package/dist/xlsx.full.min.js"
SHOTS = os.path.join(ROOT, "shots"); os.makedirs(SHOTS, exist_ok=True)
OWNER = ("owner@adityatraders.test", "owner-test-pass")      # local test values only
results = []


def ok(name, cond, detail=""):
    results.append(cond)
    print(("PASS " if cond else "FAIL ") + name + ("" if cond else f"  [{detail}]"), flush=True)


def check(name, fn):
    try:
        fn(); ok(name, True)
    except Exception as e:
        ok(name, False, str(e).split("\n")[0][:300])


# ---------------------------------------------------------------- database + server
subprocess.run(["/home/claude/localdb/reset.sh"], check=True, capture_output=True)
with psycopg.connect(DSN, autocommit=True) as c:
    c.execute("insert into auth.users (instance_id,id,aud,role,email) values ('00000000-0000-0000-0000-000000000000','c0000000-0000-0000-0000-000000000001','authenticated','authenticated',%s)", (OWNER[0],))
    c.execute("update public.profiles set full_name='Owner (test)' where email=%s", (OWNER[0],))
json.dump({OWNER[0]: ["c0000000-0000-0000-0000-000000000001", OWNER[1]]}, open("/tmp/e2e_users.json", "w"))
subprocess.run("pkill -f fake_supabase.py", shell=True)
srv = subprocess.Popen([sys.executable, os.path.join(ROOT, "fake_supabase.py"), str(PORT)], env={**os.environ, "FAKE_SB_USERS": "/tmp/e2e_users.json"})
time.sleep(1.2)


def db(sql, params=()):
    with psycopg.connect(DSN, autocommit=True) as c:
        r = c.execute(sql, params)
        return r.fetchall() if r.description else None


pw = sync_playwright().start()
browser = pw.chromium.launch(executable_path="/usr/bin/google-chrome", args=["--no-sandbox"])
console_errors = []


def new_phone(tag):
    ctx = browser.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2, accept_downloads=True)
    pg = ctx.new_page()
    pg.route("https://cdn.jsdelivr.net/**", lambda r: r.fulfill(path=SBJS, content_type="text/javascript"))
    pg.route("https://cdnjs.cloudflare.com/**", lambda r: r.fulfill(path=XLSX, content_type="text/javascript"))
    pg.on("dialog", lambda d: d.accept())
    pg.on("pageerror", lambda e: console_errors.append(f"{tag}: {e}"))
    pg.on("console", lambda m: console_errors.append(f"{tag}: {m.text}") if m.type == "error" and "favicon" not in m.text and "406" not in m.text else None)
    return pg


def login(pg, user, password):
    pg.goto(BASE)
    pg.fill("#lUser", user); pg.fill("#lPw", password); pg.click("#lBtn")
    pg.wait_for_selector("#nav:not(.hidden)", timeout=8000)


def sheet_fill(pg, values, ok_text=None):
    """Fill the open bottom sheet. values: {field_id: value}; selects get select_option."""
    sh = pg.wait_for_selector(".sheet")
    for k, v in values.items():
        el = pg.locator("#sf_" + k)
        tag = el.evaluate("e => e.tagName")
        if tag == "SELECT":
            el.select_option(label=v) if not str(v).startswith("=") else el.select_option(value=str(v)[1:])
        elif el.get_attribute("type") == "checkbox":
            el.set_checked(bool(v))
        else:
            el.fill(str(v))
    pg.click("#sheetOk")
    sh.wait_for_element_state("hidden", timeout=6000)


def toast(pg):
    pg.wait_for_selector(".toast", timeout=6000)
    return pg.locator(".toast").inner_text()


def shot(pg, name):
    pg.screenshot(path=os.path.join(SHOTS, name + ".png"), full_page=True)


try:
    # ============================================================ OWNER
    o = new_phone("owner")
    check("login page shows phone/email sign-in", lambda: (o.goto(BASE), expect(o.locator("#lUser")).to_be_visible()))
    o.fill("#lUser", OWNER[0]); o.fill("#lPw", "wrong-password"); o.click("#lBtn")
    check("wrong password is refused with a clear message", lambda: expect(o.locator("#lMsg")).to_have_text("Wrong phone/email or password."))
    o.fill("#lPw", OWNER[1]); o.click("#lBtn")
    check("owner signs in and sees the home screen", lambda: expect(o.locator("#title")).to_contain_text("Aditya Traders", timeout=8000))
    check("owner sees money tiles", lambda: expect(o.locator("text=To collect from buyers")).to_be_visible())
    shot(o, "01_owner_home_empty")

    # ---- team: accountant + 10 staff
    o.goto(BASE + "#/team"); o.wait_for_selector("#addPerson")
    o.click("#addPerson"); sheet_fill(o, {"full_name": "Lakshmi (accountant)", "login": "accounts@adityatraders.test", "password": "acc-test-pass-1", "role": "Accountant"})
    check("owner creates the accountant login", lambda: expect(o.locator(".toast")).to_contain_text("Login created"))
    staff_phones = [f"98480{i:05d}" for i in range(1, 11)]
    for i, ph in enumerate(staff_phones, 1):
        o.wait_for_selector("#addPerson"); o.click("#addPerson")
        sheet_fill(o, {"full_name": f"Staff {i}", "login": ("+91 " + ph) if i == 1 else ph, "password": f"staff-test-pass-{i}", "role": "Staff"})
        o.wait_for_selector(f"text=Staff {i}", timeout=6000)
    n_staff = db("select count(*) from public.profiles where role='staff' and active")[0][0]
    check("10 staff logins created and approved", lambda: (n_staff == 10) or (_ for _ in ()).throw(AssertionError(n_staff)))
    check("phone '+91 98480 00001' is stored as a 10-digit login", lambda: (db("select email, phone from public.profiles where full_name='Staff 1'")[0] == ("9848000001@staff.adityatraders.in", "9848000001")) or (_ for _ in ()).throw(AssertionError(db("select email, phone from public.profiles where full_name='Staff 1'"))))
    o.click("#addPerson"); o.wait_for_selector(".sheet")
    o.fill("#sf_full_name", "Dup"); o.fill("#sf_login", staff_phones[1]); o.fill("#sf_password", "another-pass-9"); o.click("#sheetOk")
    check("duplicate phone login is refused", lambda: expect(o.locator(".toast")).to_contain_text("already exists"))
    o.click("#addPerson"); o.wait_for_selector(".sheet")
    o.fill("#sf_full_name", "Short"); o.fill("#sf_login", "9000000000"); o.fill("#sf_password", "short"); o.click("#sheetOk")
    check("short password is refused", lambda: expect(o.locator(".toast")).to_contain_text("at least 8"))
    shot(o, "02_owner_team")

    # ---- new load with new buyer + transporter
    o.goto(BASE + "#/new"); o.wait_for_selector("#lf")
    o.select_option("select[name=party_id]", value="__new")
    sheet_fill(o, {"name": "Goel Timber Store", "city": "Yamunanagar", "state": "Haryana", "phone": "9812345678", "credit_days": "15"})
    o.select_option("select[name=transporter_id]", value="__new")
    sheet_fill(o, {"name": "Sri Sai Transport", "city": "Rajahmundry"})
    o.click("[data-seg=capacity_t] button[data-v='35']")
    o.fill("input[name=destination]", "Yamunanagar"); o.fill("input[name=destination_state]", "Haryana")
    o.fill("input[name=freight_amount]", "95000")
    o.fill("input[name=change_reason]", "Goel asked for one load of Mango")
    o.click("#fSave")
    check("owner saves a new load and lands on its page", lambda: expect(o.locator("#title")).to_contain_text("L-0001", timeout=6000))
    load_id = db("select id from public.loads where load_no='L-0001'")[0][0]

    # ---- stage rule: no truck number
    o.click("#nextStage"); sheet_fill(o, {"change_reason": "Truck booked"})
    check("moving past Planning without a truck number is blocked", lambda: expect(o.locator(".toast")).to_contain_text("truck number"))
    o.goto(BASE + f"#/edit/{load_id}"); o.wait_for_selector("#lf")
    o.fill("input[name=vehicle_no]", "ap 39 ta 1234"); o.fill("input[name=driver_name]", "Ramesh"); o.fill("input[name=driver_phone]", "9876543210")
    o.click("#fSave")
    check("editing a load without a reason is refused", lambda: expect(o.locator(".toast")).to_contain_text("reason"))
    o.fill("input[name=change_reason]", "Sri Sai gave truck details")
    o.click("#fSave"); o.wait_for_selector("#nextStage")
    check("truck number saved in standard form", lambda: expect(o.locator("#title")).to_contain_text("AP39TA1234"))
    o.click("#nextStage"); sheet_fill(o, {"change_reason": "Truck booked with Sri Sai"})
    o.wait_for_selector(".pill.s-truck_fixed")
    check("stage moves to Truck fixed", lambda: expect(o.locator(".sect .pill.s-truck_fixed")).to_be_visible())

    # ---- mill lines (new mills), rates
    o.click("#addLine"); sheet_fill(o, {"sawmill_id": "=__new", "wood_type": "Mango", "unit": "CFT", "quantity": "700", "length_ft": "3.5"})
    sheet_fill(o, {"name": "Sri Lakshmi Saw Mill", "place": "Rajanagaram", "area": "Rajanagaram", "phone": "9440011111"})
    o.wait_for_selector("text=Sri Lakshmi Saw Mill")
    check("size grade set automatically from length (3.5 ft → Small)", lambda: expect(o.locator(".line").first).to_contain_text("Small"))
    o.click("#addLine"); sheet_fill(o, {"sawmill_id": "=__new", "wood_type": "Mango", "unit": "CFT", "quantity": "640", "length_ft": "6"})
    sheet_fill(o, {"name": "Durga Saw Mill", "place": "Peddapuram", "area": "Peddapuram", "phone": "9440022222"})
    o.wait_for_selector("text=Durga Saw Mill")
    check("6 ft is Medium (boundary)", lambda: expect(o.locator(".line").nth(1)).to_contain_text("Medium"))
    rate_btns = o.locator("[data-rate]")
    rate_btns.nth(0).click(); sheet_fill(o, {"rate": "350", "adjustment": "-500"})
    o.wait_for_selector("text=Rate saved"); o.wait_for_selector("[data-rate] >> nth=1")
    o.locator("[data-rate]").nth(1).click(); sheet_fill(o, {"rate": "360", "adjustment": "0"})
    o.wait_for_selector("text=Purchase total")
    check("purchase amount = qty × rate ± adj (700×350−500 = ₹2,44,500)", lambda: expect(o.locator(".line").first).to_contain_text("₹2,44,500"))
    check("purchase total = ₹4,74,900", lambda: expect(o.locator(".tot.big").first).to_contain_text("₹4,74,900"))
    check("fill bar shows CFT against the 35 T guide", lambda: expect(o.locator("text=1,340 CFT of about 1,350 CFT")).to_be_visible())

    # ---- costs, stage to under loading, loaded rule
    o.click("#addCost"); sheet_fill(o, {"cost_type": "Hamali / loading", "amount": "6000", "paid_to": "Loading gang"})
    o.wait_for_selector("text=Hamali / loading")
    check("transport total = freight + costs (₹1,01,000)", lambda: expect(o.locator(".card:has-text('Freight and costs') .tot.big")).to_contain_text("₹1,01,000"))
    o.click("#setStage"); sheet_fill(o, {"stage": "Loaded", "change_reason": "Done?"}); sheet_fill(o, {})
    check("cannot mark Loaded while mill lines are not done", lambda: expect(o.locator(".toast")).to_contain_text("not done"))
    for _ in range(2):
        o.wait_for_selector("[data-done]"); o.locator("[data-done]").first.click()
        sheet_fill(o, {})
        o.wait_for_selector("text=Line done"); o.wait_for_timeout(300)
    o.click("#setStage"); sheet_fill(o, {"stage": "Loaded", "change_reason": "Both mills loaded, kata 34.6 T"})
    check("moving to Loaded asks for the kata net weight", lambda: expect(o.locator("#sf_net_weight_t")).to_be_visible())
    sheet_fill(o, {"net_weight_t": "34.6"})
    o.wait_for_selector(".sect .pill.s-loaded")
    check("kata net weight shows on the truck card (34.6 T of 35 T)", lambda: expect(o.locator("dd:has-text('34.6 T')")).to_contain_text("of 35 T"))
    href = o.locator("a:has-text('Ask location')").get_attribute("href")
    check("Ask location opens WhatsApp to the driver asking for live location", lambda: ("wa.me/919876543210?text=" in href and "live%20location" in href) or (_ for _ in ()).throw(AssertionError(href)))
    check("kata net weight is saved in the database", lambda: (float(db("select net_weight_t from public.loads where id=%s", (load_id,))[0][0]) == 34.6) or (_ for _ in ()).throw(AssertionError()))
    check("after both lines are done the load moves to Loaded", lambda: expect(o.locator(".sect .pill.s-loaded")).to_be_visible())
    o.click("#addLine"); sheet_fill(o, {"sawmill_id": "Durga Saw Mill, Peddapuram", "wood_type": "Teak", "unit": "Tons", "quantity": "2"})
    check("adding a mill after Loaded is blocked", lambda: expect(o.locator(".toast")).to_contain_text("loaded"))

    # ---- photo
    o.select_option("#fKind", label="Weighbridge (kata) slip")
    o.set_input_files("#fPick", "/home/claude/apptest/kanta_slip.png")
    o.wait_for_selector(".file img", timeout=8000)
    check("kata slip photo uploads and shows", lambda: expect(o.locator(".file .cap")).to_contain_text("Weighbridge"))
    o.wait_for_function("() => { const i = document.querySelector('.file img'); return i && i.complete && i.naturalWidth > 0; }", timeout=6000)
    check("photo loads through a signed link", lambda: None)
    o.fill("#noteText", "Truck left Peddapuram at 6 pm"); o.click("#noteForm button")
    o.wait_for_selector(".tl.note")
    check("owner posts an update on the load", lambda: expect(o.locator(".tl.note").first).to_contain_text("Truck left Peddapuram"))
    check("history shows exact time to the second", lambda: (re.search(r"\d{1,2}:\d{2}:\d{2}\s?(am|pm)", o.locator(".tl .when").first.inner_text(), re.I)) or (_ for _ in ()).throw(AssertionError(o.locator(".tl .when").first.inner_text())))
    shot(o, "03_owner_load")

    # ============================================================ STAFF (phone login)
    s = new_phone("staff")
    login(s, "98480 00003", "staff-test-pass-3")
    check("staff signs in with a phone number", lambda: expect(s.locator("#title")).to_contain_text("staff"))
    check("staff sees no money tiles", lambda: expect(s.locator("text=To collect from buyers")).to_have_count(0))
    check("staff sees the red 'to check' banner", lambda: expect(s.locator(".banner.red")).to_contain_text("1 load to check"))
    check("staff nav shows Mills, not Parties", lambda: expect(s.locator("#navPartiesLabel")).to_have_text("Mills"))
    s.goto(BASE + "#/loads"); s.wait_for_selector(".loadc")
    check("load card flagged New for staff", lambda: expect(s.locator(".loadc .flag.new")).to_be_visible())
    s.click(".loadc"); s.wait_for_selector("#addLine")
    body = s.locator("main").inner_text()
    check("staff page shows NO purchase rates", lambda: ("₹350" not in body and "₹360" not in body and "Purchase" not in body and "₹4,74,900" not in body) or (_ for _ in ()).throw(AssertionError("price text visible")))
    check("staff page has no Billing or Payments section", lambda: expect(s.locator("text=Payments on this load")).to_have_count(0))
    check("staff can see freight and costs (owner allowed)", lambda: expect(s.locator("text=₹95,000")).to_be_visible())
    check("staff cannot delete loads", lambda: expect(s.locator("#delLoad")).to_have_count(0))
    shot(s, "04_staff_load")
    s.click("#chk"); s.wait_for_selector("text=Marked as checked")
    s.click("#nextStage"); s.wait_for_selector(".sheet"); s.click("#sheetOk")
    check("staff must give a reason to move the stage", lambda: expect(s.locator("#sheetErr")).to_contain_text("Reason"))
    s.fill("#sf_change_reason", "Driver called: crossed Nagpur"); s.click("#sheetOk"); s.wait_for_selector(".sect .pill.s-in_transit")
    check("staff moves the load to In transit", lambda: expect(s.locator(".sect .pill.s-in_transit")).to_be_visible())
    s.fill("#noteText", "Expected in Yamunanagar on 29 Nov"); s.click("#noteForm button"); s.wait_for_selector("text=Expected in Yamunanagar")
    # direct API attempts as staff (what a curious staff member could try from the browser)
    leak = s.evaluate("""async () => {
      const sb = window.supabase.createClient(location.origin, 'local-anon-key');
      const a = await sb.from('line_prices').select('*'); const b = await sb.from('load_billing').select('*');
      const c = await sb.from('v_lines').select('rate,amount'); const d = await sb.from('activity').select('visibility');
      const e = await sb.from('line_prices').update({rate: 1}).eq('line_id', 1).select();
      const f = await sb.from('profiles').update({role: 'owner'}).eq('full_name', 'Staff 3').select();
      return {prices: (a.data||[]).length, bills: (b.data||[]).length, rates: (c.data||[]).filter(x => x.rate !== null || x.amount !== null).length,
              admin_acts: (d.data||[]).filter(x => x.visibility === 'admin').length, upd: (e.data||[]).length, promote: (f.data||[]).length};
    }""")
    check("staff API: purchase prices, bills and admin history all hidden; no self-promotion",
          lambda: (leak == {"prices": 0, "bills": 0, "rates": 0, "admin_acts": 0, "upd": 0, "promote": 0}) or (_ for _ in ()).throw(AssertionError(leak)))
    s.goto(BASE + "#/parties"); s.wait_for_timeout(500)
    check("staff opening Parties is sent to Mills", lambda: expect(s.locator("#title")).to_have_text("Mills"))
    s.goto(BASE + "#/team"); s.wait_for_timeout(400)
    check("staff cannot open Team", lambda: (s.url.endswith("#/")) or (_ for _ in ()).throw(AssertionError(s.url)))
    shot(s, "05_staff_after")

    # ============================================================ ACCOUNTANT
    a = new_phone("accountant")
    login(a, "accounts@adityatraders.test", "acc-test-pass-1")
    check("accountant has the same money view as the owner", lambda: expect(a.locator("text=To pay mills")).to_be_visible())
    a.goto(BASE + "#/loads"); a.wait_for_selector(".loadc")
    check("load card shows the latest change: who and why", lambda: expect(a.locator(".loadc .t4")).to_contain_text("Staff 3"))
    a.click(".loadc"); a.wait_for_selector("#editBill")
    check("accountant sees purchase rates", lambda: expect(a.locator(".line").first).to_contain_text("₹350"))
    check("history shows the staff stage change with its reason", lambda: expect(a.locator(".tl:has-text('Loaded → In transit')").first).to_contain_text("crossed Nagpur"))
    check("history shows the owner's rate change as admin-only", lambda: expect(a.locator(".tl.adm").first).to_be_visible())
    # deliver → ready to bill → bill → part paid → paid
    a.click("#nextStage"); sheet_fill(a, {"change_reason": "Goel confirmed unloading"})
    a.wait_for_selector(".pill.b-ready_to_bill")
    check("delivered load is Ready to bill", lambda: expect(a.locator(".pill.b-ready_to_bill")).to_be_visible())
    a.click("#editBill"); sheet_fill(a, {"invoice_no": "AT/339", "invoice_date": "2026-11-20", "sale_qty": "1340", "sale_rate": "420", "sale_adjustment": "-800", "gst_amount": "28100"})
    a.wait_for_selector("text=AT/339")
    check("invoice total = 1340×420 − 800 + 28,100 = ₹5,90,100", lambda: expect(a.locator("text=₹5,90,100").first).to_be_visible())
    check("due date uses buyer credit days (20 Nov + 15)", lambda: expect(a.locator("dd:has-text('5 Dec 2026')")).to_be_visible())
    check("unpaid bill not yet due shows Billed", lambda: expect(a.locator(".sect .pill.b-billed")).to_be_visible())
    a.click("#addPay"); sheet_fill(a, {"amount": "300000", "mode": "Bank", "reference": "UTR123"})
    a.wait_for_selector("text=UTR123")
    a.click("#addPay"); sheet_fill(a, {"who": "Paid to mill: Sri Lakshmi Saw Mill, Rajanagaram", "amount": "244500", "mode": "UPI"})
    a.wait_for_selector("text=−₹2,44,500")
    check("part-paid bill shows Payment pending", lambda: expect(a.locator(".sect .pill.b-payment_pending")).to_be_visible())
    check("balance after part payment = ₹2,90,100", lambda: expect(a.locator("dd:has-text('₹2,90,100')")).to_be_visible())
    a.goto(BASE + "#/parties"); a.wait_for_selector(".loadc")
    check("buyer balance on Parties = ₹2,90,100", lambda: expect(a.locator(".loadc:has-text('Goel')")).to_contain_text("₹2,90,100"))
    a.click("[data-tab=mill]"); a.wait_for_selector(".loadc:has-text('Durga')")
    check("mill balances: Sri Lakshmi paid in full, Durga ₹2,30,400 to pay", lambda: (expect(a.locator(".loadc:has-text('Lakshmi')")).to_contain_text("₹0"), expect(a.locator(".loadc:has-text('Durga')")).to_contain_text("₹2,30,400")))
    a.click("[data-tab=buyer]"); a.wait_for_selector(".loadc:has-text('Goel')"); a.click(".loadc:has-text('Goel')")
    a.wait_for_selector("text=Send reminder")
    href = a.locator("a:has-text('Send reminder')").get_attribute("href")
    check("WhatsApp reminder link carries the buyer's number and balance", lambda: ("wa.me/919812345678" in href and "2%2C90%2C100" in href) or (_ for _ in ()).throw(AssertionError(href)))
    shot(a, "06_accountant_party")
    # Excel
    a.goto(BASE + "#/export"); a.wait_for_selector("#xGo")
    a.fill("#xFrom", "2026-11-01")
    with a.expect_download(timeout=15000) as dl:
        a.click("#xGo")
    path = os.path.join(SHOTS, "export.xlsx"); dl.value.save_as(path)
    import zipfile
    names = zipfile.ZipFile(path).read("xl/workbook.xml").decode()
    check("Excel has Loads, Mill lines, Costs, History, Payments, Balances sheets", lambda: all(n in names for n in ["Loads", "Mill lines", "Costs", "History", "Payments", "Balances"]) or (_ for _ in ()).throw(AssertionError(names)))

    # ============================================================ OWNER sees what changed
    o.goto(BASE + "#/loads"); o.click("#refreshBtn"); o.wait_for_selector(".loadc.edited", timeout=6000)
    check("owner's load card turns red after others changed it", lambda: expect(o.locator(".loadc.edited .flag.edited")).to_be_visible())
    o.click(".loadc"); o.wait_for_selector(".banner.red")
    check("owner sees how many changes since he checked", lambda: expect(o.locator(".banner.red")).to_contain_text("since you checked"))
    check("changes since last check are marked red in history", lambda: (o.locator(".tl.new").count() >= 3) or (_ for _ in ()).throw(AssertionError(o.locator(".tl.new").count())))
    o.click("#chk"); o.wait_for_selector("text=Marked as checked"); o.wait_for_timeout(400)
    check("after Mark checked the red banner goes", lambda: expect(o.locator(".banner.red")).to_have_count(0))
    o.goto(BASE + "#/updates"); o.wait_for_selector(".tl")
    check("Updates feed lists all changes with load, time, person", lambda: expect(o.locator(".tl").first).to_contain_text("L-0001"))
    shot(o, "07_owner_updates")
    # settings: grade limits
    o.goto(BASE + "#/settings"); o.wait_for_selector("#sSave")
    o.fill("#sLo", "3"); o.click("#sSave"); o.wait_for_selector("text=Saved.")
    check("owner changes the size-grade limit", lambda: (float(db("select value from public.app_settings where key='size_small_below_ft'")[0][0]) == 3.0) or (_ for _ in ()).throw(AssertionError()))
    # block a staff login
    o.goto(BASE + "#/team"); o.wait_for_selector("text=Staff 10")
    o.locator(".card:has-text('Staff 10') [data-act]").click(); o.wait_for_selector("text=Blocked.")
    b10 = new_phone("staff10"); b10.goto(BASE); b10.fill("#lUser", staff_phones[9]); b10.fill("#lPw", "staff-test-pass-10"); b10.click("#lBtn")
    check("a blocked staff login sees 'Waiting for approval' and no data", lambda: expect(b10.locator("text=Waiting for approval")).to_be_visible(timeout=6000))
    # sign out
    o.goto(BASE + "#/more"); o.click("#signOut")
    check("sign out returns to the login page", lambda: expect(o.locator("#lUser")).to_be_visible(timeout=6000))

    # ============================================================ offline
    s.goto(BASE + "#/loads"); s.wait_for_selector(".loadc")
    s.context.set_offline(True); s.click("#refreshBtn"); s.wait_for_timeout(1500)
    check("offline: staff still sees the last saved loads", lambda: expect(s.locator(".loadc")).to_have_count(1, timeout=6000))
    check("offline banner is shown", lambda: expect(s.locator("#net")).to_be_visible())
    s.context.set_offline(False)

    bad = [e for e in console_errors if "Failed to load resource" not in e and "ERR_INTERNET_DISCONNECTED" not in e and "Failed to fetch" not in e]
    check("no JavaScript errors in any session", lambda: (not bad) or (_ for _ in ()).throw(AssertionError(bad[:3])))
except Exception:
    traceback.print_exc(); ok("test run crashed", False)
finally:
    browser.close(); pw.stop(); srv.terminate()

passed = sum(results)
print(f"\n{passed} passed, {len(results) - passed} failed")
sys.exit(0 if passed == len(results) else 1)
