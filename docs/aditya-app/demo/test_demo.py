"""Browser test of the DEMO page + screenshots for the walkthrough.
Serves demo2/out on localhost; the real supabase-js file is served locally."""
import os, re, subprocess, sys, time, json
from playwright.sync_api import sync_playwright, expect

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "out"); SHOTS = os.path.join(HERE, "shots"); os.makedirs(SHOTS, exist_ok=True)
SBJS = "/home/claude/apptest/sbjs/package/dist/umd/supabase.js"
XLSX = "/home/claude/apptest/package/dist/xlsx.full.min.js"
PORT = 8877; BASE = f"http://127.0.0.1:{PORT}/"
srv = subprocess.Popen([sys.executable, "-m", "http.server", str(PORT), "-d", OUT, "-b", "127.0.0.1"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(.8)
res = []; errs = []


def ok(name, fn):
    try:
        fn(); res.append(True); print("PASS", name, flush=True)
    except Exception as e:
        res.append(False); print("FAIL", name, " [", str(e).split("\n")[0][:250], "]", flush=True)


def truthy(v, msg=""):
    if not v: raise AssertionError(msg or v)


pw = sync_playwright().start()
br = pw.chromium.launch(executable_path="/usr/bin/google-chrome", args=["--no-sandbox"])
ctx = br.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2, accept_downloads=True)
pg = ctx.new_page()
pg.route("https://cdn.jsdelivr.net/**", lambda r: r.fulfill(path=SBJS, content_type="text/javascript"))
pg.route("https://cdnjs.cloudflare.com/**", lambda r: r.fulfill(path=XLSX, content_type="text/javascript"))
pg.on("dialog", lambda d: d.accept())
pg.on("pageerror", lambda e: errs.append(str(e)))
pg.on("console", lambda m: errs.append(m.text) if m.type == "error" and "406" not in m.text and "Failed to load resource" not in m.text else None)


def shot(name, full=False):
    pg.screenshot(path=os.path.join(SHOTS, name + ".png"), full_page=full)


def as_person(login):
    pg.select_option("#demoWho", value=login)
    pg.wait_for_selector("#nav:not(.hidden)", timeout=10000)
    pg.wait_for_timeout(400)


def open_filter(key):
    pg.goto(BASE + "#/loads"); pg.wait_for_selector(".chip")
    pg.click(f"[data-f={key}]"); pg.wait_for_timeout(250)


def sheet(values):
    sh = pg.wait_for_selector(".sheet")
    for k, v in values.items():
        el = pg.locator("#sf_" + k)
        if el.evaluate("e => e.tagName") == "SELECT": el.select_option(label=v)
        else: el.fill(str(v))
    pg.click("#sheetOk")
    try: sh.wait_for_element_state("hidden", timeout=6000)
    except Exception: print("SHEETERR", repr(pg.locator("#sf_quantity").input_value()), pg.locator("#sf_quantity").get_attribute("value"), pg.locator("#title").inner_text().replace(chr(10)," "), pg.evaluate("JSON.stringify(JSON.parse(localStorage.getItem(\"at2_demo_db_v1\")).t.load_lines.filter(x=>x.sawmill_id===1).slice(-3))")); raise


try:
    pg.goto(BASE); pg.wait_for_selector("#lUser", timeout=15000)
    ok("demo login screen shows the demo bar and one-tap logins", lambda: (expect(pg.locator("#demoBar")).to_be_visible(), expect(pg.locator("[data-l]")).to_have_count(5)))
    shot("00_login")
    pg.click("[data-l='owner@adityatraders.demo']"); pg.wait_for_selector("#nav:not(.hidden)", timeout=10000); pg.wait_for_timeout(500)
    counts = {k: pg.locator(f".tile[data-goto={k}] .n").inner_text() for k in ["planning", "truck_fixed", "going_to_load", "under_loading", "loaded", "in_transit", "delivered"]}
    ok("owner home: 5-6 loads at every stage", lambda: truthy(counts == {"planning": "5", "truck_fixed": "5", "going_to_load": "5", "under_loading": "6", "loaded": "5", "in_transit": "6", "delivered": "20"}, counts))
    ok("owner sees loads changed since he last checked", lambda: expect(pg.locator(".banner.red")).to_contain_text("to check"))
    ok("money tiles show amounts", lambda: truthy(re.search(r"₹[\d,]+", pg.locator(".tile.money").first.inner_text())))
    ok("ready to bill = 5, payment pending = 5", lambda: (expect(pg.locator(".tile[data-goto=ready_to_bill] .n")).to_have_text("5"), expect(pg.locator(".tile[data-goto=payment_pending] .n")).to_have_text("5")))
    shot("01_owner_home", True)

    # one screenshot per stage list + one load page per stage (owner view)
    for key in ["planning", "truck_fixed", "going_to_load", "under_loading", "loaded", "in_transit", "delivered"]:
        open_filter(key); shot(f"10_list_{key}")
        pg.locator(".loadc").first.click(); pg.wait_for_selector("#setStage"); pg.wait_for_timeout(300)
        shot(f"11_load_{key}", True)
    for key in ["ready_to_bill", "billed", "payment_pending", "paid"]:
        open_filter(key); shot(f"12_list_{key}")
        ok(f"{key}: 5 loads", lambda: expect(pg.locator(".loadc")).to_have_count(5))
    open_filter("payment_pending"); pg.locator(".loadc").first.click(); pg.wait_for_selector("#editBill"); pg.wait_for_timeout(300); shot("13_load_payment_pending", True)
    pg.goto(BASE + "#/parties"); pg.wait_for_selector(".loadc"); shot("14_parties_buyers")
    pg.click("[data-tab=mill]"); pg.wait_for_timeout(300); shot("15_parties_mills")
    pg.goto(BASE + "#/updates"); pg.wait_for_selector(".tl"); shot("16_updates")
    ok("updates feed shows staff, accountant and owner entries", lambda: truthy(all(n in pg.locator("main").inner_text() for n in ["Lakshmi", "Bharat"]) and re.search(r"Ravi|Suresh|Prasad|Naidu|Kiran|Srinu|Raju", pg.locator("main").inner_text())))

    # ---- STAFF Ravi: moves a truck_fixed load on; no prices
    as_person("9848000001")
    shot("20_staff_home", True)
    ok("staff sees no money tiles", lambda: expect(pg.locator(".tile.money")).to_have_count(0))
    open_filter("under_loading"); pg.locator(".loadc").first.click(); pg.wait_for_selector("#addLine"); pg.wait_for_timeout(300)
    body = pg.locator("main").inner_text()
    ok("staff load page shows no purchase rates", lambda: truthy("Purchase" not in body and not re.search(r"₹3[4-7]\d\b", body), "price visible"))
    shot("21_staff_under_loading", True)
    load_title = pg.locator("#title").inner_text()
    # staff finishes every open line, then marks Loaded
    while pg.locator("[data-done]").count():
        n = pg.locator("[data-done]").count()
        pg.locator("[data-done]").first.click(); sheet({"change_reason": "Tally finished, demo"})
        pg.wait_for_function(f"document.querySelector('#setStage') && document.querySelectorAll('[data-done]').length < {n}", timeout=8000)
    pg.click("#setStage"); sheet({"stage": "Loaded", "change_reason": "All mills loaded, kata 34.2 T (Ravi)"})
    try: pg.wait_for_selector(".sect .pill.s-loaded", timeout=8000)
    except Exception: print("STAGEFAIL", pg.locator(".toast").all_inner_texts(), pg.locator("#title").inner_text()); raise
    ok("staff marks the under-loading load as Loaded", lambda: expect(pg.locator(".sect .pill.s-loaded")).to_be_visible())
    pg.fill("#noteText", "Driver will leave by 7 pm after e-way bill"); pg.click("#noteForm button"); pg.wait_for_selector("text=Driver will leave by 7 pm")
    shot("22_staff_after_loading", True)
    leak = pg.evaluate("""async () => {
      const sb = window.supabase.createClient(window.ADITYA_CONFIG.url, 'x', {global:{fetch: window.ADITYA_CONFIG.fetch}, auth:{storageKey:'probe'}});
      await sb.auth.signInWithPassword({email:'9848000001@staff.adityatraders.in', password: window.ADITYA_DEMO.password});
      const a = await sb.from('line_prices').select('*'); const b = await sb.from('payments').select('*');
      const c = await sb.from('v_lines').select('rate'); const d = await sb.from('activity').select('visibility');
      const e = await sb.from('v_balances').select('*');
      return [ (a.data||[]).length, (b.data||[]).length, (c.data||[]).filter(x => x.rate !== null).length, (d.data||[]).filter(x => x.visibility==='admin').length, (e.data||[]).length ];
    }""")
    ok("demo keeps staff rules: no prices, payments, rates, admin history, balances", lambda: truthy(leak == [0, 0, 0, 0, 0], leak))

    # ---- ACCOUNTANT: sees Ravi's change flagged; e-way + in transit; bills a ready load
    as_person("accounts@adityatraders.demo")
    pg.goto(BASE + "#/loads"); pg.wait_for_selector(".loadc")
    pg.locator(".loadc", has_text=load_title.split(" · ")[0]).first.click(); pg.wait_for_selector("#editBill")
    ok("accountant sees Ravi's changes flagged red with the reason", lambda: (expect(pg.locator(".banner.red")).to_contain_text("since you checked"), expect(pg.locator(".tl.new").first).to_contain_text("Ravi")))
    shot("30_accountant_sees_staff_change", True)
    open_filter("ready_to_bill"); pg.locator(".loadc").first.click(); pg.wait_for_selector("#editBill")
    pg.click("#editBill"); sheet({"invoice_no": "AT/26-27/999", "sale_rate": "435", "change_reason": "Bill made (demo)"})
    pg.wait_for_selector(".sect .pill.b-billed")
    ok("accountant bills a delivered load → Billed", lambda: expect(pg.locator(".sect .pill.b-billed")).to_be_visible())
    pg.click("#addPay"); sheet({"amount": "1000", "reference": "UTR-DEMO"}); pg.wait_for_selector(".sect .pill.b-payment_pending")
    ok("part payment → Payment pending", lambda: expect(pg.locator(".sect .pill.b-payment_pending")).to_be_visible())
    shot("31_accountant_billing", True)

    # ---- OWNER sees both
    as_person("owner@adityatraders.demo")
    pg.goto(BASE + "#/updates"); pg.wait_for_selector(".tl")
    ok("owner's Updates shows the accountant's bill and Ravi's note at the top", lambda: truthy("Lakshmi" in pg.locator(".tl").nth(0).inner_text() and any("Ravi" in pg.locator(".tl").nth(i).inner_text() for i in range(6))))
    shot("40_owner_updates_after", True)
    pg.goto(BASE + "#/"); pg.wait_for_timeout(500); shot("41_owner_home_after", True)

    # ---- reset
    pg.click("#demoReset"); pg.wait_for_selector("#nav:not(.hidden)", timeout=10000); pg.wait_for_timeout(500)
    ok("Reset puts the sample back (5 under loading again)", lambda: expect(pg.locator(".tile[data-goto=under_loading] .n")).to_have_text("6"))
    ok("no JavaScript errors", lambda: truthy(not errs, errs[:3]))
finally:
    br.close(); pw.stop(); srv.terminate()
print(f"\n{sum(res)} passed, {len(res) - sum(res)} failed")
