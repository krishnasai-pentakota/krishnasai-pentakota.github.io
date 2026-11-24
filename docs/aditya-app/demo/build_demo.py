"""Make the no-login demo page from the real app page.
   Real app:  apps/aditya/index.html       (talks to Supabase)
   Demo:      apps/aditya/demo/index.html  (sample data in the browser)
   Only three things change: the backend script, the login screen, and a demo bar."""
import sys
from pathlib import Path
app = Path(sys.argv[1]).read_text(encoding="utf-8")
backend = Path(sys.argv[2]).read_text(encoding="utf-8")
out = Path(sys.argv[3])

def swap(s, old, new):
    assert s.count(old) == 1, ("not found once", old[:60]); return s.replace(old, new)

# 1. backend: Supabase library -> in-browser demo backend
s = swap(app, '<script src="https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2.45.4/dist/umd/supabase.js"></script>',
         "<script>\n" + backend + "\n</script>")
# 2. title and version label
s = swap(s, "<title>Aditya Traders</title>", "<title>Aditya Traders (Demo)</title>")
s = swap(s, 'const APP_VERSION = "1.0 (25 Nov 2026)";', 'const APP_VERSION = "1.0 DEMO (sample data)";')
# 3. login screen -> pick a person, no password
a = s.index("function showLogin(msg){"); b = s.index("async function afterLogin(){")
s = s[:a] + '''function showLogin(msg){
  chrome("Aditya Traders", {menu:false});
  $("app").innerHTML = `
  <div class="login">
    <div class="brand"><b>Aditya Traders</b>Lorry trips, costs and checks</div>
    <div class="card"><h2>Try the app</h2>
      <p class="mut">This demo has sample lorries. No password needed. Open it as:</p>
      <div style="display:grid;gap:10px">
        <button class="btn pri" data-demo="owner@demo">Owner</button>
        <button class="btn" data-demo="accountant@demo">Accountant</button>
        <button class="btn" data-demo="staff@demo">Field staff</button>
      </div>
      <p class="small mut" style="margin-top:14px">Try this: open as <b>Accountant</b> to see a lorry the owner changed (red <b>Edited</b>). Then switch to <b>Owner</b>, change a lorry's freight, and switch back.</p>
    </div>
  </div>`;
  document.querySelectorAll("[data-demo]").forEach(b => b.onclick = () => sb.auth.signInWithPassword({email:b.dataset.demo, password:"demo"}));
}

''' + s[b:]
# 4. demo bar under the top bar
s = swap(s, '<div class="net hidden" id="net"></div>',
 '<div class="net hidden" id="net"></div>\n'
 '<div id="demoBar" style="background:#f3b733;color:#2a1b0b;font-size:14px;padding:6px 12px;display:flex;gap:8px;align-items:center;flex-wrap:wrap">'
 '<span style="flex:1;min-width:160px"><b>Demo</b> with sample data. Changes stay on this phone only.</span>'
 '<button id="demoSwitch" style="min-height:36px;border:1px solid #2a1b0b;background:#fff;border-radius:8px;padding:4px 10px;font-weight:700">Switch person</button>'
 '<button id="demoReset" style="min-height:36px;border:1px solid #2a1b0b;background:transparent;border-radius:8px;padding:4px 10px;font-weight:700">Reset</button></div>')
s = swap(s, "</body>",
 '<script>\n'
 'document.getElementById("demoSwitch").onclick = () => { history.replaceState(null, "", "#/"); window.supabase.createClient().auth.signOut(); };\n'
 'document.getElementById("demoReset").onclick = () => { if (confirm("Reset the demo to the original sample lorries?")) window.__demoReset(); };\n'
 '</script>\n</body>')
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(s, encoding="utf-8")
print("demo written:", out, len(s), "bytes")
