"""Browser test of the DEMO page (app 3.2) + screenshots for the walkthrough guide.
Serves demo2/out on localhost; supabase-js, SheetJS and jsPDF are served from local copies.
Phone-sized screens (390 x 844)."""
import json, os, re, subprocess, sys, time
from pypdf import PdfReader
from playwright.sync_api import sync_playwright, expect

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "out"); SHOTS = os.path.join(HERE, "shots"); os.makedirs(SHOTS, exist_ok=True)
SBJS = "/home/claude/apptest/sbjs/package/dist/umd/supabase.js"
XLSX = "/home/claude/apptest/package/dist/xlsx.full.min.js"
JSPDF = "/home/claude/apptest/pdf/jspdf-2.5.1/package/dist/jspdf.umd.min.js"
AUTOT = "/home/claude/apptest/pdf/jspdf-autotable-3.8.2/package/dist/jspdf.plugin.autotable.min.js"
IMG = os.path.join(HERE, "test_assets", "sample_slip.png")       # drawn test pictures marked SAMPLE
DRIVER = os.path.join(HERE, "test_assets", "sample_driver.png")
PORT = 8877; BASE = f"http://127.0.0.1:{PORT}/"
WB = json.load(open("/home/claude/aditya-app/tests/db/workbook_tally_counts.json"))
srv = subprocess.Popen([sys.executable, "-m", "http.server", str(PORT), "-d", OUT, "-b", "127.0.0.1"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(.8)
res = []; errs = []
STAGES = {"planning": "5", "truck_fixed": "5", "going_to_load": "5", "under_loading": "6", "loaded": "5", "in_transit": "6", "delivered": "20"}


def ok(name, fn):
    try:
        fn(); res.append(True); print("PASS", name, flush=True)
    except Exception as e:
        res.append(False); print("FAIL", name, " [", str(e).split("\n")[0][:250], "]", flush=True)


def truthy(v, msg=""):
    if not v: raise AssertionError(msg or repr(v))


def cdn(route):
    u = route.request.url
    route.fulfill(path=SBJS if "jsdelivr" in u else JSPDF if "jspdf.umd" in u else AUTOT if "autotable" in u else XLSX, content_type="text/javascript")


pw = sync_playwright().start()
br = pw.chromium.launch(executable_path="/usr/bin/google-chrome", args=["--no-sandbox"])
ctx = br.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2, accept_downloads=True)
pg = ctx.new_page()
pg.route("https://cdn.jsdelivr.net/**", cdn); pg.route("https://cdnjs.cloudflare.com/**", cdn)
pg.route("https://fonts.googleapis.com/**", lambda r: r.fulfill(body="", content_type="text/css"))
pg.on("dialog", lambda d: d.accept())
pg.on("pageerror", lambda e: errs.append(str(e)))
pg.on("console", lambda m: errs.append(m.text) if m.type == "error" and "406" not in m.text and "Failed to load resource" not in m.text else None)


def shot(name, at=None, full=False):
    """Phone-screen picture. at = section to scroll to (its top goes just under the app bar)."""
    if at:
        loc = pg.locator(at).first
        loc.scroll_into_view_if_needed(); loc.evaluate("e => { e.scrollIntoView({block:'start'}); window.scrollBy(0, -(document.getElementById('top').offsetHeight + 8)); }")
    else: pg.evaluate("window.scrollTo(0, 0)")
    pg.evaluate("document.getElementById('toastHost').style.visibility = 'hidden'")
    pg.wait_for_timeout(150)
    pg.screenshot(path=os.path.join(SHOTS, name + ".png"), full_page=full)
    pg.evaluate("document.getElementById('toastHost').style.visibility = ''")


def as_person(login):
    pg.select_option("#demoWho", value=login)
    pg.wait_for_selector("#nav:not(.hidden)", timeout=10000)
    pg.wait_for_timeout(400)


def open_filter(key):
    for attempt in range(3):           # the list can re-render once while fresh data arrives
        pg.goto(BASE + "#/loads"); pg.wait_for_selector(".chip"); pg.wait_for_timeout(300)
        try: pg.click(f"[data-f={key}]", timeout=5000); break
        except Exception:
            print("  (filter retry)", key)
            if attempt == 2: shot("zz_filter_fail", False); print("FILTER FAIL", pg.url, pg.locator(".chip").all_inner_texts()); raise
    pg.wait_for_timeout(250)


def wait_load():
    pg.wait_for_selector("#pdfBtn", timeout=10000); pg.wait_for_timeout(250)


def sheet(values, ok_btn=True):
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
            print("SHEET STUCK:", pg.locator(".sheet h2").all_inner_texts(), pg.locator("#sheetErr").all_inner_texts(), pg.locator(".toast").all_inner_texts()); raise


try:
    pg.goto(BASE); pg.wait_for_selector("#lUser", timeout=15000)
    ok("demo login screen shows the demo bar and one-tap logins", lambda: (expect(pg.locator("#demoBar")).to_be_visible(), expect(pg.locator("[data-l]")).to_have_count(5)))
    shot("00_login")

    # ================================================= OWNER (one login for Aditya and Bharat)
    pg.click("[data-l='owner@adityatraders.demo']"); pg.wait_for_selector("#nav:not(.hidden)", timeout=10000); pg.wait_for_timeout(500)
    counts = {k: pg.locator(f".tile[data-goto={k}] .n").inner_text() for k in STAGES}
    ok("owner home: 5-6 loads at every stage (20 delivered)", lambda: truthy(counts == STAGES, counts))
    ok("owner top bar has '+ New load'", lambda: expect(pg.locator("#topNew")).to_have_text("+ New load"))
    ok("owner quick actions: New load, Register truck, Expenses, Sawmill rates, Team", lambda: [expect(pg.locator(".qa a", has_text=t)).to_be_visible() for t in ["New load", "Register truck", "Expenses", "Sawmill rates", "Team"]])
    ok("owner sees loads changed since last checked", lambda: expect(pg.locator(".banner.red")).to_contain_text("to check"))
    ok("money tiles show amounts (freight, collect, pay)", lambda: truthy(re.search(r"₹[\d,]+", pg.locator(".tile.money").first.inner_text())))
    ok("ready to bill = 5, payment pending = 5", lambda: (expect(pg.locator(".tile[data-goto=ready_to_bill] .n")).to_have_text("5"), expect(pg.locator(".tile[data-goto=payment_pending] .n")).to_have_text("5")))
    shot("01_owner_home")
    shot("02_owner_home_tiles", ".sect:has(h3:has-text('Loads by stage'))")

    for key in STAGES:
        open_filter(key); shot(f"10_list_{key}")
        pg.locator(".loadc").first.click(); wait_load()
        shot(f"11_load_{key}")
        if key == "under_loading": shot("11b_load_under_loading_mills", ".card:has(h3:has-text('Sawmills'))")
        if key == "in_transit": shot("11b_load_in_transit_slips", ".card:has(h3:has-text('Weigh slips'))")
        if key == "delivered": shot("11b_load_delivered_money", ".card:has(h3:has-text('Freight and expenses'))")
    for key in ["ready_to_bill", "billed", "payment_pending", "paid"]:
        open_filter(key); shot(f"12_list_{key}")
        ok(f"{key}: 5 loads", lambda: expect(pg.locator(".loadc")).to_have_count(5))
    open_filter("payment_pending"); pg.locator(".loadc").first.click(); pg.wait_for_selector("#editBill"); pg.wait_for_timeout(300); shot("13_load_payment_pending", ".card:has(h3:has-text('Billing'))")
    pg.goto(BASE + "#/expenses"); pg.wait_for_selector("#expMonth"); pg.wait_for_timeout(400); shot("14_expenses")
    ok("Expenses screen lists freight and other charges", lambda: (expect(pg.locator("main")).to_contain_text("Truck Freight"), truthy(re.search(r"₹[\d,]+", pg.locator("main").inner_text()))))
    pg.goto(BASE + "#/rates"); pg.wait_for_selector("#rMill"); pg.wait_for_timeout(400)
    pg.select_option("#rMill", label="Sri Lakshmi Saw Mill, Rajanagaram"); pg.wait_for_timeout(500); shot("15_rates")
    shot("15b_rates_history", ".card:has(h3:has-text('Rate history'))")
    ok("rate card keeps history (the 15 Nov large-size rise and the earlier rate)", lambda: truthy(pg.locator(".tl").count() >= 2, pg.locator(".tl").count()))
    tl = pg.evaluate("JSON.parse(localStorage.getItem('at3_demo_db_v2')).t.load_tallies.map(t => [t.load_id, t.allocation_id, t.id])")
    ok("sample data has piece tallies", lambda: truthy(len(tl) >= 10, len(tl)))
    pg.goto(BASE + f"#/load/{tl[0][0]}"); wait_load()
    ok("a sample load shows its piece tally and From-tally items", lambda: (expect(pg.locator(".tally").first).to_contain_text("CFT"), expect(pg.locator(".item .na-pill", has_text="From tally").first).to_be_visible()))
    shot("19_sample_tally_items", ".tally")
    pg.goto(BASE + f"#/tally/{tl[0][1]}/{tl[0][2]}"); pg.wait_for_selector("#tGrid")
    shot("19b_sample_tally_summary", "#tSum")
    pg.goto(BASE + "#/team"); pg.wait_for_selector("#addPerson"); shot("16_team")
    ok("Team: one owner login, accountant and 10 staff", lambda: (expect(pg.locator("main")).to_contain_text("Owner (Aditya & Bharat)"), expect(pg.locator("main")).to_contain_text("Lakshmi"), expect(pg.locator("main")).to_contain_text("Gopi")))
    pg.goto(BASE + "#/parties"); pg.wait_for_selector(".loadc"); shot("17_parties_buyers")
    pg.goto(BASE + "#/updates"); pg.wait_for_selector(".tl"); shot("18_updates")
    ok("updates feed shows staff, accountant and owner entries", lambda: truthy(all(n in pg.locator("main").inner_text() for n in ["Lakshmi", "Owner"]) and re.search(r"Ravi|Suresh|Prasad|Naidu|Kiran|Srinu|Raju", pg.locator("main").inner_text())))

    # ================================================= STAFF Ravi: no planning, no money
    as_person("9848000001")
    shot("20_staff_home")
    ok("staff top bar has '+ Truck'", lambda: expect(pg.locator("#topNew")).to_have_text("+ Truck"))
    ok("staff home: no Planning / Truck fixed tiles and no money tiles", lambda: (expect(pg.locator(".tile[data-goto=planning]")).to_have_count(0), expect(pg.locator(".tile[data-goto=truck_fixed]")).to_have_count(0), expect(pg.locator(".tile.money")).to_have_count(0)))
    ok("staff quick actions: no New load, Expenses, Rates, Parties, Team", lambda: [expect(pg.locator(".qa a", has_text=t)).to_have_count(0) for t in ["New load", "Expenses", "Sawmill rates", "Parties", "Team"]])
    pg.goto(BASE + "#/loads"); pg.wait_for_selector(".chip")
    ok("staff loads list: no Planning / Truck fixed filters; 42 loads (the 10 owner-only loads never reach staff)", lambda: (expect(pg.locator("[data-f=planning]")).to_have_count(0), truthy(pg.locator(".loadc").count() == 42, pg.locator(".loadc").count())))

    # register a truck: photo is compulsory, licence/C-Book optional
    pg.goto(BASE + "#/register"); pg.wait_for_selector("#lf")
    pg.fill("input[name=vehicle_no]", "ap 39 tb 5678"); pg.click("[data-seg=capacity_t] button[data-v='35']"); pg.fill("input[name=capacity_cft]", "1300")
    pg.fill("input[name=driver_name]", "Sankar"); pg.fill("input[name=driver_phone]", "9876543210")
    pg.click("#fSave"); pg.wait_for_timeout(600)
    ok("without the photo: red 'Driver photo with truck is mandatory.' and nothing saved", lambda: (expect(pg.locator("#regMust")).to_be_visible(), expect(pg.locator("#regMust")).to_contain_text("Driver photo with truck is mandatory."), truthy("#/register" in pg.url)))
    ok("licence and C-Book show 'Not Provided'", lambda: (expect(pg.locator("#reg-licence-st")).to_have_text("Not Provided"), expect(pg.locator("#reg-cbook-st")).to_have_text("Not Provided")))
    shot("21_register_missing_photo", "#regMust")
    pg.set_input_files("#reg-driver-in", DRIVER); pg.wait_for_timeout(200)
    pg.click("#fSave"); wait_load()
    ok("truck saved at Going to load with the driver photo", lambda: (expect(pg.locator(".sect .pill.s-going_to_load")).to_be_visible(), expect(pg.locator("#doc-driver .st")).not_to_have_text("Not Provided")))
    load_no = pg.locator("#title").inner_text().split(" ")[0]

    def add_alloc(label):
        pg.click("#addAlloc"); sheet({"sawmill_id": label}); pg.wait_for_selector(f".alloc:has-text('{label.split(',')[0]}')", timeout=8000); pg.wait_for_timeout(300)

    def add_item(mill, vals):
        pg.locator(f".alloc:has-text('{mill}') [data-additem]").click(); sheet(vals); pg.wait_for_timeout(400); wait_load()
    add_alloc("Durga Saw Mill, Peddapuram"); add_alloc("Sai Ram Saw Mill, Narsipatnam")
    add_item("Durga Saw Mill", {"wood_type": "Country Wood", "size_grade": "Large", "quantity": "700", "unit": "CFT", "dimensions": '3" x 3" x 6\'', "change_reason": "Tally sheet 1"})
    add_item("Durga Saw Mill", {"wood_type": "Acacia", "size_grade": "Medium", "quantity": "200", "unit": "CFT", "change_reason": "Tally sheet 2"})
    add_item("Sai Ram Saw Mill", {"wood_type": "Teak", "size_grade": "Small", "quantity": "100", "unit": "Pieces", "pieces": "100", "change_reason": "Counted"})
    ok("one truck, two sawmills, three wood items", lambda: (expect(pg.locator(".alloc")).to_have_count(2), expect(pg.locator(".item")).to_have_count(3)))
    shot("22_staff_sawmills", ".card:has(h3:has-text('Sawmills'))")
    # piece tally at Durga: the workbook's sheet 1-1 typed in (1 inch)
    pg.locator(".alloc:has-text('Durga Saw Mill') [data-newtally]").click(); pg.wait_for_selector("#tGrid")
    shot("27_tally_screen")
    for k, n in WB["sheets"]["1-1"]["counts"].items(): pg.locator(f'#tGrid input[data-k="{k}"]').fill(str(n))
    ok("tally: the workbook's sheet 1-1 gives 36.91 CFT and 477 pieces", lambda: (expect(pg.locator("#tTotal")).to_have_text("36.91"), expect(pg.locator('#tTh [data-th="1"] .c')).to_have_text("477")))
    pg.locator('#tGrid input[data-k="2.5|5"]').click()
    shot("28_tally_grid", ".tgrid")
    shot("29_tally_summary", "#tSum")
    pg.click("#tSave"); wait_load()
    ok("tally saved: Small / Medium / Large Mango items from tally", lambda: (expect(pg.locator(".alloc:has-text('Durga Saw Mill') .tally")).to_contain_text("36.91 CFT · 477 pcs"), expect(pg.locator(".alloc:has-text('Durga Saw Mill') .item .na-pill", has_text="From tally")).to_have_count(3)))
    shot("30_load_with_tally", ".alloc:has-text('Durga Saw Mill') .tally")

    pg.click("#nextStage"); sheet({"a": "Durga Saw Mill"}); sheet({})
    pg.wait_for_selector(".sect .pill.s-under_loading", timeout=8000); wait_load()
    ok("Under loading starts when the truck reaches the first sawmill", lambda: expect(pg.locator(".alloc:has-text('Durga Saw Mill') .ok-pill", has_text="Reached")).to_be_visible())
    ok("two sawmills → two weigh-slip sections, 'Not Uploaded'", lambda: (expect(pg.locator(".slip")).to_have_count(2), expect(pg.locator(".slip .na-pill")).to_have_count(2)))

    def loading_done(mill, net):
        pg.locator(f".alloc:has-text('{mill}') [data-ldone]").click()
        sheet({"slip": IMG, "slip_net_weight_t": net, "change_reason": f"Loading done at {mill}"})
        pg.wait_for_selector(f".alloc:has-text('{mill}') .ok-pill:has-text('Loading done')", timeout=10000); wait_load()
    loading_done("Durga Saw Mill", "24.1")
    pg.locator(".alloc:has-text('Sai Ram Saw Mill') [data-reached]").click(); sheet({}); wait_load()
    pg.click("#nextStage"); pg.wait_for_timeout(400)
    ok("Loaded refused while Sai Ram has no weigh slip", lambda: expect(pg.locator(".toast")).to_contain_text("Upload the weigh slip for: Sai Ram Saw Mill"))
    loading_done("Sai Ram Saw Mill", "9.8")
    shot("23_weigh_slips", ".card:has(h3:has-text('Weigh slips'))")
    pg.click("#nextStage"); sheet({"net_weight_t": "34.1", "change_reason": "All sawmills loaded"}); pg.wait_for_selector(".sect .pill.s-loaded", timeout=8000); wait_load()
    ok("staff marks the truck Loaded (kata 34.1 T)", lambda: expect(pg.locator("dd:has-text('34.1 T')")).to_be_visible())
    pg.fill("#noteText", "Tarpaulin tied, leaving at 6 pm"); pg.click("#noteForm button"); pg.wait_for_selector(".tl.note:has-text('Tarpaulin tied')")
    shot("24_staff_after_loading")
    shot("25_staff_pdf_button", ".card:has(h3:has-text('Loading document'))")
    shot("26_staff_history", ".card:has(h3:has-text('Updates and history'))")
    body = pg.locator("main").inner_text()
    ok("staff load page shows no ₹, rates, freight or expenses", lambda: truthy(not [w for w in ["₹", "Purchase", "Freight", "expense", "Billing", "Payments"] if w in body], [w for w in ["₹", "Purchase", "Freight", "expense", "Billing", "Payments"] if w in body]))

    with pg.expect_download(timeout=20000) as dl:
        pg.click("#pdfBtn")
    pdf = os.path.join(SHOTS, "staff_loading_details.pdf"); dl.value.save_as(pdf)
    text = "\n".join(p.extract_text() for p in PdfReader(pdf).pages)
    pos = [text.find(h) for h in ["Sl. No.", "Saw Mill Name", "Name of Product", "Size", "Quantity", "Unit"]]
    ok("PDF: TRUCK LOADING / DISPATCH DETAILS, Sl. No. then Saw Mill Name", lambda: truthy("TRUCK LOADING / DISPATCH DETAILS" in text and all(p >= 0 for p in pos) and pos == sorted(pos), pos))
    ok("PDF rows carry sawmill, wood, size, quantity, unit", lambda: truthy(all(t in text for t in ["Durga Saw Mill", "Sai Ram Saw Mill", "Country Wood", "Acacia", "Teak", "Large", "700", "Pieces", "AP39TB5678", "Sankar"]), text[:300]))
    ok("PDF has the piece tally table (36.91 CFT, 477 pcs)", lambda: truthy("Piece tally - Small 1'6\" to 2'9\"" in text and "36.91 CFT" in text and "477 pcs" in text, text[-700:]))
    bad = [w for w in ["Rate", "Amount", "GST", "Taxable", "Total", "Balance", "Freight", "Bank", "Payment", "₹", "Rs."] if w in text]
    ok("PDF has no financial values or fields", lambda: truthy(not bad, bad))

    leak = pg.evaluate("""async () => {
      const sb = window.supabase.createClient(window.ADITYA_CONFIG.url, 'x', {global:{fetch: window.ADITYA_CONFIG.fetch}, auth:{storageKey:'probe'}});
      await sb.auth.signInWithPassword({email:'9848000001@staff.adityatraders.in', password: window.ADITYA_DEMO.password});
      const out = {};
      for (const t of ['load_costs','line_prices','load_billing','payments','sawmill_rates','v_balances','expense_categories']) { const r = await sb.from(t).select('*'); out[t] = (r.data||[]).length; }
      const v = await sb.from('v_loads').select('freight_total,costs_total,purchase_total,invoice_total,bill_stage'); out.v_loads_money = (v.data||[]).filter(x => Object.values(x).some(y => y !== null)).length;
      const r = await sb.from('v_lines').select('rate,amount'); out.line_money = (r.data||[]).filter(x => x.rate !== null || x.amount !== null).length;
      const a = await sb.from('activity').select('visibility,truck_stage'); out.money_or_planning_history = (a.data||[]).filter(x => x.visibility !== 'all' || ['planning','truck_fixed'].includes(x.truck_stage)).length;
      const pl = await sb.from('loads').select('id').in('truck_stage', ['planning','truck_fixed']); out.planning_loads = (pl.data||[]).length;
      const w = await sb.from('load_costs').insert({load_id: 1, cost_type: 'Fuel', amount: 1}); out.expense_insert_ok = w.error ? 0 : 1;
      try { await window.ADITYA_CONFIG.fileUrl('expenses/1/x.jpg'); out.receipt_link = 1; } catch (e) { out.receipt_link = 0; }
      return out; }""")
    ok("demo keeps the staff rules: no expenses, rates, bills, payments, balances, money history or planning loads", lambda: truthy(all(v == 0 for v in leak.values()), leak))

    # ================================================= ACCOUNTANT: sees changes, bills; views but cannot enter rates/charges
    as_person("accounts@adityatraders.demo")
    pg.goto(BASE + "#/loads"); pg.wait_for_selector(".loadc")
    pg.locator(".loadc", has_text="AP39TB5678").first.click(); wait_load()
    ok("accountant: new truck flagged 'not checked yet'; history shows Ravi, exact time and reason", lambda: (expect(pg.locator(".banner.blue")).to_contain_text("not checked this load yet"), expect(pg.locator(".tl", has_text="All sawmills loaded").first).to_contain_text("Ravi")))
    ok("accountant cannot enter charges or rates (owner login only)", lambda: (expect(pg.locator("#addExp")).to_have_count(0), expect(pg.locator("[data-rate]")).to_have_count(0)))
    shot("30_accountant_sees_staff_change")
    pg.click("#chk"); pg.wait_for_selector("text=Marked as checked"); pg.wait_for_timeout(300)
    open_filter("ready_to_bill"); pg.locator(".loadc").first.click(); pg.wait_for_selector("#editBill")
    pg.click("#editBill"); sheet({"invoice_no": "AT/26-27/999", "sale_rate": "435", "change_reason": "Bill made (demo)"})
    pg.wait_for_selector(".sect .pill.b-billed")
    ok("accountant bills a delivered load → Billed", lambda: expect(pg.locator(".sect .pill.b-billed")).to_be_visible())
    pg.click("#addPay"); sheet({"amount": "1000", "reference": "UTR-DEMO"}); pg.wait_for_selector(".sect .pill.b-payment_pending")
    ok("part payment → Payment pending", lambda: expect(pg.locator(".sect .pill.b-payment_pending")).to_be_visible())
    shot("31_accountant_billing", ".card:has(h3:has-text('Billing'))")

    # ================================================= OWNER enters freight, a charge and a rate on Ravi's truck
    as_person("owner@adityatraders.demo")
    pg.goto(BASE + "#/loads"); pg.wait_for_selector(".loadc")
    pg.locator(".loadc", has_text="AP39TB5678").first.click(); wait_load()
    pg.click("#addExp"); sheet({"cost_type": "Truck Freight", "amount": "95000", "change_reason": "Freight agreed"}); wait_load()
    pg.click("#addExp"); sheet({"cost_type": "Hamali / Loading", "amount": "6000", "allocation_id": "Durga Saw Mill", "receipt": IMG, "change_reason": "Paid loading gang"})
    pg.wait_for_selector(".tot:has-text('Hamali / Loading')", timeout=10000); wait_load()
    pg.locator(".alloc:has-text('Durga Saw Mill') .item:has-text('Country Wood'):has-text('Large') [data-rate]").click()
    sheet({"rate": "350"}); wait_load()
    ok("owner: freight + hamali recorded; 700 × ₹350 = ₹2,45,000 on the item", lambda: (expect(pg.locator(".tot", has_text="Truck Freight")).to_be_visible(), expect(pg.locator(".item:has-text('Country Wood'):has-text('Large') .price")).to_contain_text("₹2,45,000")))
    shot("40_owner_money_on_truck", ".card:has(h3:has-text('Freight and expenses'))")
    shot("40b_owner_rate_on_item", ".card:has(h3:has-text('Sawmills'))")
    as_person("accounts@adityatraders.demo")
    pg.goto(BASE + "#/loads"); pg.wait_for_selector(".loadc")
    ok("accountant's list shows Ravi's truck as Changed after the owner's entries", lambda: expect(pg.locator(".loadc.edited", has_text="AP39TB5678")).to_be_visible())
    pg.locator(".loadc", has_text="AP39TB5678").first.click(); wait_load()
    ok("accountant sees the owner's freight, charge and rate in red, with the reason", lambda: (expect(pg.locator(".banner.red")).to_contain_text("since you checked"), expect(pg.locator(".tl.new", has_text="Freight agreed").first).to_be_visible(), truthy(pg.locator(".tl.new").count() >= 3, pg.locator(".tl.new").count())))
    ok("accountant views the owner's rate and freight on the truck", lambda: (expect(pg.locator(".item:has-text('Country Wood'):has-text('Large') .price")).to_contain_text("₹2,45,000"), expect(pg.locator(".tot", has_text="Truck Freight")).to_be_visible()))
    shot("42_accountant_red_flags")
    shot("42b_accountant_red_history", ".card:has(h3:has-text('Updates and history'))")
    as_person("owner@adityatraders.demo")
    pg.goto(BASE + "#/updates"); pg.wait_for_selector(".tl")
    ok("owner's Updates shows Ravi's note and Lakshmi's bill", lambda: truthy("Tarpaulin tied" in pg.locator("main").inner_text() and "Lakshmi" in pg.locator("main").inner_text()))
    shot("41_owner_updates_after")

    # ================================================= reset
    pg.goto(BASE + "#/"); pg.wait_for_timeout(300)
    pg.click("#demoReset"); pg.wait_for_selector("#nav:not(.hidden)", timeout=10000); pg.wait_for_timeout(500)
    ok("Reset puts the sample back", lambda: (expect(pg.locator(".tile[data-goto=loaded] .n")).to_have_text("5"), expect(pg.locator(".tile[data-goto=going_to_load] .n")).to_have_text("5")))
    ok("no JavaScript errors", lambda: truthy(not errs, errs[:3]))
except Exception as e:
    import traceback; traceback.print_exc(); res.append(False)
finally:
    br.close(); pw.stop(); srv.terminate()
print(f"\n{sum(res)} passed, {len(res) - sum(res)} failed")
sys.exit(0 if all(res) else 1)
