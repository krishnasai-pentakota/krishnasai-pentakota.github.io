"""Builds the DEMO page from the real app page (v2/index.html).
Adds: the in-browser demo backend, and a top bar to switch person
(owner / accountant / staff) and reset the sample data.
Output folder: demo2/out/  (index.html, demo_backend.js, sample_data.json)."""
import json, os, shutil, sys

HERE = os.path.dirname(os.path.abspath(__file__))
APP = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "..", "v2", "index.html")
OUT = os.path.join(HERE, "out"); os.makedirs(OUT, exist_ok=True)

PEOPLE = [  # (label, login) — sample accounts, all with the demo password
    ("Bharat · Owner", "owner@adityatraders.demo"),
    ("Lakshmi · Accountant", "accounts@adityatraders.demo"),
    ("Ravi · Staff", "9848000001"),
    ("Suresh · Staff", "9848000002"),
    ("Prasad · Staff", "9848000003"),
]
opts = "".join(f'<option value="{l}">{n}</option>' for n, l in PEOPLE)

BAR = f"""<div id="demoBar" style="background:#f3b733;color:#2a1b0b;font:600 14px/1.3 system-ui,sans-serif;padding:6px 10px;display:flex;gap:8px;align-items:center;flex-wrap:wrap">
  <span style="background:#2a1b0b;color:#f3b733;border-radius:6px;padding:2px 7px;font-weight:800">DEMO</span>
  <span style="flex:1;min-width:120px">Sample data · changes stay on this phone</span>
  <label style="display:flex;gap:6px;align-items:center">You are
    <select id="demoWho" aria-label="Switch person" style="min-height:36px;border-radius:8px;border:1px solid #8a5a00;background:#fff;font:inherit;padding:2px 6px">
      <option value="">— choose —</option>{opts}</select></label>
  <a href="guide.html" style="min-height:36px;display:inline-flex;align-items:center;border-radius:8px;border:1px solid #8a5a00;background:#fff;color:#2a1b0b;padding:2px 10px;text-decoration:none">Guide</a>
  <button id="demoReset" style="min-height:36px;border-radius:8px;border:1px solid #8a5a00;background:#fff;font:inherit;padding:2px 10px;cursor:pointer">Reset</button>
</div>
<script>
(function () {{
  /* Switch person: forget the current login, then sign in as the chosen sample person. */
  const who = document.getElementById("demoWho");
  const cur = sessionStorage.getItem("demo_as") || "";
  who.value = cur;
  function clearLogin() {{ Object.keys(localStorage).filter(k => k.startsWith("sb-")).forEach(k => localStorage.removeItem(k)); }}
  who.onchange = () => {{
    if (!who.value) return;
    sessionStorage.setItem("demo_as", who.value); sessionStorage.setItem("demo_autologin", "1");
    clearLogin(); location.hash = "#/"; location.reload();
  }};
  document.getElementById("demoReset").onclick = async () => {{
    if (!confirm("Put the sample data back as it was? Your demo changes on this phone will be removed.")) return;
    await window.ADITYA_DEMO.reset(); clearLogin(); sessionStorage.setItem("demo_autologin", cur ? "1" : ""); location.hash = "#/"; location.reload();
  }};
  /* Fill and submit the login form automatically after a switch; otherwise show the demo logins. */
  const iv = setInterval(() => {{
    const u = document.getElementById("lUser");
    if (!u) return;
    clearInterval(iv);
    const box = document.createElement("div");
    box.className = "card"; box.style.marginTop = "12px";
    box.innerHTML = '<b>Demo logins</b><p class="small mut" style="margin:4px 0 8px">Tap a person to sign in. Password for all: <b></b></p>' +
      {json.dumps(PEOPLE, ensure_ascii=False)}.map(p => '<button type="button" class="btn sm" style="margin:0 6px 6px 0" data-l="' + p[1] + '">' + p[0] + '</button>').join("");
    box.querySelector("b + p b").textContent = window.ADITYA_DEMO.password;
    u.closest("form").after(box);
    box.querySelectorAll("[data-l]").forEach(b => b.onclick = () => {{ sessionStorage.setItem("demo_as", b.dataset.l); who.value = b.dataset.l; go(b.dataset.l); }});
    function go(login) {{ u.value = login; document.getElementById("lPw").value = window.ADITYA_DEMO.password; document.getElementById("lBtn").click(); }}
    if (sessionStorage.getItem("demo_autologin") === "1" && cur) {{ sessionStorage.removeItem("demo_autologin"); go(cur); }}
  }}, 100);
}})();
</script>
"""

html = open(APP, encoding="utf-8").read()
html = html.replace("<title>Aditya Traders</title>", "<title>Aditya Traders · Demo</title>", 1)
html = html.replace('<meta name="viewport"', '<meta name="robots" content="noindex">\n<meta name="viewport"', 1)
assert '<div class="top" id="top">' in html
html = html.replace('<div class="top" id="top">', BAR + '<div class="top" id="top">', 1)
tag = '<script src="https://cdn.jsdelivr.net/npm/@supabase/supabase-js'
assert tag in html
html = html.replace(tag, '<script src="demo_backend.js"></script>\n' + tag, 1)
open(os.path.join(OUT, "index.html"), "w", encoding="utf-8").write(html)
for f in ("demo_backend.js", "sample_data.json"):
    shutil.copy(os.path.join(HERE, f), os.path.join(OUT, f))
print("demo built:", OUT)
