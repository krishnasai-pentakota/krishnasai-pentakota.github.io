/* Aditya Traders: DEMO backend (version 2).
   Runs inside the browser and answers the same requests the real app sends to
   Supabase, so the demo page is the real app page with sample data.

   It copies the live database's rules (migrations 001-009):
     * who sees what (staff never see rates, bills, payments, admin history)
     * every change is logged: who, exact time, what changed, reason, stage
     * stage rules (truck number before leaving Planning; "Loaded" only when
       every mill line is done; no new/re-opened lines after Loaded)
     * red flags per person, size grade from length, money maths in the views
   Data is kept on this phone/browser only (localStorage). "Reset demo" restores the sample.
   Sample data: sample_data.json, generated through the REAL database rules. */
(function () {
  "use strict";
  const BASE = "https://demo.adityatraders.local";
  const KEY = "at2_demo_db_v1";
  const PASSWORD = "demo1234";               // every demo login uses this (sample data only)
  const SKIP = ["id", "created_at", "created_by", "updated_at", "updated_by", "change_reason"];
  const STAGES_AFTER_PLAN = ["truck_fixed", "going_to_load", "under_loading", "loaded", "in_transit", "delivered"];
  const LOADED_PLUS = ["loaded", "in_transit", "delivered"];
  const UNITS = ["CFT", "CBM", "Pieces", "Tons", "Quintal", "Kg", "Running ft", "Sq ft"];
  const PK = {line_prices: "line_id", load_billing: "load_id", app_settings: "key"};
  let D = null, ready = null;

  /* ---------------- storage ---------------- */
  function save() { try { localStorage.setItem(KEY, JSON.stringify(D)); } catch (e) { /* demo still works this session */ } }
  async function load(fresh) {
    if (!fresh) { try { const s = JSON.parse(localStorage.getItem(KEY) || "null"); if (s && s.t) { D = s; return; } } catch (e) {} }
    const r = await window.__realFetch("sample_data.json", {cache: "no-store"});
    const j = await r.json();
    // Times from Postgres carry an offset; store them all as UTC ISO so they compare as text.
    for (const rows of Object.values(j.tables)) for (const r of rows) for (const k of Object.keys(r))
      if ((k === "at" || k.endsWith("_at")) && r[k]) r[k] = new Date(r[k]).toISOString();
    D = {t: j.tables, auth: {}, files: {}, seq: {}};
    for (const p of D.t.profiles) D.auth[p.email] = {id: p.id, pw: PASSWORD};
    for (const [t, rows] of Object.entries(D.t)) D.seq[t] = rows.reduce((m, r) => Math.max(m, typeof r.id === "number" ? r.id : 0), 0);
    D.seq.load_no = D.t.loads.length;
    save();
  }
  window.ADITYA_DEMO = {
    reset: async () => { localStorage.removeItem(KEY); await load(true); },
    password: PASSWORD,
  };

  /* ---------------- helpers ---------------- */
  const nowIso = () => new Date().toISOString();
  const todayIST = () => new Date().toLocaleDateString("en-CA", {timeZone: "Asia/Kolkata"});
  const clone = o => JSON.parse(JSON.stringify(o));
  const r2 = v => v === null || v === undefined || v === "" ? null : Math.round(Number(v) * 100) / 100;
  const r3 = v => v === null || v === undefined || v === "" ? null : Math.round(Number(v) * 1000) / 1000;
  const same = (a, b) => JSON.stringify(a ?? null) === JSON.stringify(b ?? null);
  class ApiErr extends Error { constructor(status, code, msg) { super(msg); this.status = status; this.code = code; } }
  const deny = () => new ApiErr(403, "42501", "new row violates row-level security policy");
  const ruleErr = m => new ApiErr(400, "P0001", m);

  function json(status, body, extra) {
    return new Response(body === null ? null : JSON.stringify(body), {status, headers: {"Content-Type": "application/json", ...(extra || {})}});
  }
  function b64(o) { return btoa(unescape(encodeURIComponent(JSON.stringify(o)))).replace(/=+$/, ""); }
  function claimsFrom(headers) {
    const a = headers.get("Authorization") || "";
    const p = a.replace(/^Bearer /, "").split(".");
    if (p.length !== 3) return null;
    try { const c = JSON.parse(decodeURIComponent(escape(atob(p[1])))); return c.exp > Date.now() / 1000 ? c : null; } catch (e) { return null; }
  }

  /* ---------------- who is asking ---------------- */
  function ctx(uid) {
    const me = uid ? D.t.profiles.find(p => p.id === uid) : null;
    const member = !!(me && me.active);
    return {uid, me, member, admin: member && (me.role === "owner" || me.role === "accountant")};
  }

  /* ---------------- views (same maths as the SQL views) ---------------- */
  function vLines(c) {
    if (!c.member) return [];
    return D.t.load_lines.map(l => {
      const s = D.t.sawmills.find(m => m.id === l.sawmill_id) || {};
      const lp = c.admin ? D.t.line_prices.find(p => p.line_id === l.id) : null;
      const amount = lp && lp.rate !== null ? r2((Number(l.quantity) || 0) * Number(lp.rate) + Number(lp.adjustment || 0)) : null;
      return {...l, sawmill_name: s.name, sawmill_place: s.place, sawmill_area: s.area, rate: lp ? lp.rate : null, adjustment: lp ? lp.adjustment : null, amount};
    });
  }
  const fmtQty = n => Number(n).toLocaleString("en-US", {maximumFractionDigits: 3});
  function vLoads(c) {
    if (!c.member) return [];
    const VL = vLines(c);
    return D.t.loads.map(l => {
      const b = D.t.parties.find(p => p.id === l.party_id), tr = D.t.parties.find(p => p.id === l.transporter_id);
      const lines = VL.filter(x => x.load_id === l.id);
      const byUnit = {};
      lines.forEach(x => { if (x.quantity !== null) byUnit[x.unit] = (byUnit[x.unit] || 0) + Number(x.quantity); });
      const units = Object.keys(byUnit).sort();
      const cft = lines.filter(x => x.unit === "CFT").reduce((s, x) => s + Number(x.quantity || 0), 0);
      const amounts = lines.map(x => x.amount).filter(x => x !== null);
      const costs = D.t.load_costs.filter(x => x.load_id === l.id).reduce((s, x) => s + Number(x.amount), 0);
      const bl = c.admin ? D.t.load_billing.find(x => x.load_id === l.id) : null;
      const pays = c.admin ? D.t.payments.filter(p => p.load_id === l.id && p.party_kind === "buyer") : [];
      const received = pays.length ? r2(pays.reduce((s, p) => s + Number(p.amount), 0)) : null;
      const invTotal = bl && bl.sale_rate !== null ? r2((Number(bl.sale_qty) || 0) * Number(bl.sale_rate) + Number(bl.sale_adjustment) + Number(bl.gst_amount)) : null;
      let due = null;
      if (bl && bl.invoice_date) { const d = new Date(bl.invoice_date + "T00:00:00Z"); d.setUTCDate(d.getUTCDate() + (bl.credit_days ?? (b ? b.credit_days : null) ?? 30)); due = d.toISOString().slice(0, 10); }
      let bill = null;
      if (c.admin) {
        const full = bl ? r2((Number(bl.sale_qty) || 0) * Number(bl.sale_rate || 0) + Number(bl.sale_adjustment) + Number(bl.gst_amount)) : 0;
        if (!bl || bl.invoice_no === null) bill = l.truck_stage === "delivered" ? "ready_to_bill" : "not_ready";
        else if ((received || 0) >= full && Number(bl.sale_rate || 0) > 0) bill = "paid";
        else if ((received || 0) > 0 || (due && due < todayIST())) bill = "payment_pending";
        else bill = "billed";
      }
      const rv = D.t.load_reviews.find(r => r.load_id === l.id && r.user_id === c.uid);
      const la = D.t.activity.filter(a => a.load_id === l.id).sort((x, y) => x.at < y.at ? 1 : x.at > y.at ? -1 : y.id - x.id)[0];
      return {...l,
        party_name: b ? b.name : null, party_city: b ? b.city : null, party_state: b ? b.state : null, party_phone: b ? b.phone : null,
        transporter_name: tr ? tr.name : null, transporter_phone: tr ? tr.phone : null,
        lines_total: lines.length, lines_done: lines.filter(x => x.line_status === "done").length,
        mills_count: new Set(lines.map(x => x.sawmill_id)).size,
        qty_summary: units.length ? units.map(u => fmtQty(byUnit[u]) + " " + u).join(" + ") : null,
        cft_total: lines.some(x => x.unit === "CFT") ? r3(cft) : null,
        purchase_total: amounts.length ? r2(amounts.reduce((s, x) => s + x, 0)) : null,
        costs_total: r2(costs), transport_total: r2(Number(l.freight_amount || 0) + costs),
        invoice_no: bl ? bl.invoice_no : null, invoice_date: bl ? bl.invoice_date : null, invoice_total: invTotal, due_date: due, received,
        bill_stage: bill,
        my_reviewed_at: rv ? rv.reviewed_at : null, last_at: la ? la.at : null, last_by: la ? la.actor : null, last_reason: la ? la.reason : null, last_action: la ? la.action : null,
        my_flag: !rv ? "new" : (la && la.at > rv.reviewed_at ? "edited" : "ok")};
    });
  }
  function vBalances(c) {
    if (!c.admin) return [];
    const VL = vLoads(c), LN = vLines(c), out = [];
    const paid = (k, f) => r2(D.t.payments.filter(p => p.party_kind === k && f(p)).reduce((s, p) => s + Number(p.amount), 0));
    D.t.parties.filter(p => p.kind === "buyer").forEach(p => {
      const ls = VL.filter(l => l.party_id === p.id);
      const open = ls.filter(l => l.bill_stage === "billed" || l.bill_stage === "payment_pending").map(l => l.due_date).sort();
      out.push({party_kind: "buyer", party_id: p.id, sawmill_id: null, name: p.name, place: p.city, phone: p.phone,
        total_due: r2(ls.reduce((s, l) => s + Number(l.invoice_total || 0), 0)), total_paid: paid("buyer", x => x.party_id === p.id),
        bills: ls.filter(l => l.invoice_no !== null).length, oldest_due: open[0] || null});
    });
    D.t.sawmills.forEach(s => out.push({party_kind: "mill", party_id: null, sawmill_id: s.id, name: s.name, place: s.place, phone: s.phone,
      total_due: r2(LN.filter(x => x.sawmill_id === s.id).reduce((a, x) => a + Number(x.amount || 0), 0)), total_paid: paid("mill", x => x.sawmill_id === s.id),
      bills: new Set(D.t.load_lines.filter(x => x.sawmill_id === s.id).map(x => x.load_id)).size, oldest_due: null}));
    D.t.parties.filter(p => p.kind === "transporter").forEach(p => out.push({party_kind: "transporter", party_id: p.id, sawmill_id: null, name: p.name, place: p.city, phone: p.phone,
      total_due: r2(D.t.loads.filter(l => l.transporter_id === p.id).reduce((a, l) => a + Number(l.freight_amount || 0), 0)), total_paid: paid("transporter", x => x.party_id === p.id),
      bills: D.t.loads.filter(l => l.transporter_id === p.id).length, oldest_due: null}));
    return out;
  }

  /* ---------------- row-level security ---------------- */
  const READ = {
    profiles: c => r => c.member || r.id === c.uid,
    sawmills: c => () => c.member, parties: c => () => c.member, app_settings: c => () => c.member,
    loads: c => () => c.member, load_lines: c => () => c.member, load_costs: c => () => c.member, load_files: c => () => c.member,
    line_prices: c => () => c.admin, load_billing: c => () => c.admin, payments: c => () => c.admin,
    activity: c => r => c.member && (r.visibility === "all" || c.admin),
    load_reviews: c => r => r.user_id === c.uid,
  };
  const CAN = {   // insert / update / delete
    insert: {sawmills: "m", parties: "m", loads: "m", load_lines: "m", load_costs: "m", load_files: "m", line_prices: "a", load_billing: "a", payments: "a"},
    update: {sawmills: "m", parties: "m", loads: "m", load_lines: "m", load_costs: "m", line_prices: "a", load_billing: "a", payments: "a", profiles: "a", app_settings: "a"},
    delete: {sawmills: "a", parties: "a", loads: "a", load_files: "a", load_lines: "m", load_costs: "m", line_prices: "a", load_billing: "a", payments: "a"},
  };
  const allowed = (c, op, t) => { const need = CAN[op][t]; return need === "m" ? c.member : need === "a" ? c.admin : false; };

  /* ---------------- triggers ---------------- */
  function loadIdOf(t, row) { return t === "loads" ? row.id : t === "line_prices" ? (D.t.load_lines.find(l => l.id === row.line_id) || {}).load_id : row.load_id; }
  function strip(o) { const d = {}; Object.entries(o).forEach(([k, v]) => { if (v !== null && v !== undefined && !SKIP.includes(k)) d[k] = v; }); return d; }
  function touch(c, lid) {
    if (!c.uid || !D.t.loads.some(l => l.id === lid)) return;
    const r = D.t.load_reviews.find(x => x.load_id === lid && x.user_id === c.uid);
    if (r) r.reviewed_at = nowIso(); else D.t.load_reviews.push({load_id: lid, user_id: c.uid, reviewed_at: nowIso()});
  }
  function log(c, t, op, oldR, newR) {
    const vis = ["line_prices", "load_billing", "payments"].includes(t) ? "admin" : "all";
    const rec = newR || oldR, lid = loadIdOf(t, rec);
    let d, act = op;
    if (op === "update") {
      d = {};
      Object.keys(newR).forEach(k => { if (!SKIP.includes(k) && !same(oldR[k], newR[k])) d[k] = [oldR[k] ?? null, newR[k] ?? null]; });
      if (!Object.keys(d).length) return;
      if (t === "loads" && d.truck_stage) act = "stage";
    } else d = strip(rec);
    const L = D.t.loads.find(l => l.id === lid);
    D.t.activity.push({id: ++D.seq.activity, load_id: lid ?? null, entity: t, entity_id: String(rec.id ?? rec.line_id ?? rec.load_id),
      action: act, changes: d, reason: newR && newR.change_reason && String(newR.change_reason).trim() ? String(newR.change_reason).trim() : null,
      truck_stage: L ? L.truck_stage : (t === "loads" ? rec.truck_stage : null), visibility: vis, actor: c.uid, at: nowIso()});
    touch(c, lid);
  }
  const LOGGED = ["loads", "load_lines", "load_costs", "load_files", "line_prices", "load_billing", "payments"];

  function checkRow(t, r, op, old) {
    const need = (cond, what) => { if (!cond) throw new ApiErr(400, "23514", `new row for relation "${t}" violates check constraint (${what})`); };
    if (t === "loads") {
      need(!r.capacity_t || r.capacity_t > 0, "capacity"); need(r.freight_amount === null || r.freight_amount === undefined || r.freight_amount >= 0, "freight");
      if (STAGES_AFTER_PLAN.includes(r.truck_stage) && !String(r.vehicle_no || "").trim()) throw ruleErr("Enter the truck number before moving past Planning.");
      if (LOADED_PLUS.includes(r.truck_stage) && (op === "insert" || r.truck_stage !== old.truck_stage)) {
        const ls = D.t.load_lines.filter(x => x.load_id === r.id);
        if (!ls.length) throw ruleErr("Add at least one mill line before marking the load as Loaded.");
        const open = ls.filter(x => x.line_status !== "done").length;
        if (open) throw ruleErr(`Cannot mark as Loaded: ${open} mill line(s) are not done yet.`);
      }
    }
    if (t === "load_lines") {
      need(r.load_id && D.t.loads.some(l => l.id === r.load_id), "load"); need(r.sawmill_id && D.t.sawmills.some(m => m.id === r.sawmill_id), "mill");
      need(String(r.wood_type || "").trim(), "wood"); need(UNITS.includes(r.unit), "unit"); need(r.quantity === null || r.quantity >= 0, "quantity");
    }
    if (t === "load_costs") { need(String(r.cost_type || "").trim(), "cost"); need(r.amount !== null && r.amount >= 0, "amount"); }
    if (t === "payments") {
      need(r.amount > 0, "amount");
      need((r.party_kind === "mill" && r.sawmill_id && !r.party_id) || (["buyer", "transporter"].includes(r.party_kind) && r.party_id && !r.sawmill_id), "party");
    }
    if (t === "load_files") need(String(r.storage_path || "").trim(), "file");
    if (t === "sawmills" || t === "parties") need(String(r.name || "").trim(), "name");
  }
  function lineRules(op, oldR, newR) {
    const lid = (newR || oldR).load_id, L = D.t.loads.find(l => l.id === lid);
    if (L && LOADED_PLUS.includes(L.truck_stage) && (op !== "update" || newR.line_status !== "done"))
      throw ruleErr(`This load is already ${L.truck_stage.replace("_", " ")}. Move it back to Under loading first to change its mill lines.`);
    if (newR && !newR.size_grade && newR.length_ft) {
      const lo = Number((D.t.app_settings.find(s => s.key === "size_small_below_ft") || {}).value ?? 4);
      const hi = Number((D.t.app_settings.find(s => s.key === "size_large_above_ft") || {}).value ?? 6);
      newR.size_grade = newR.length_ft < lo ? "small" : newR.length_ft > hi ? "large" : "medium";
    }
  }
  const NUM2 = ["freight_amount", "rate", "adjustment", "amount", "sale_rate", "sale_adjustment", "gst_amount", "value"];
  const NUM3 = ["quantity", "sale_qty"];
  function normalise(r) {
    for (const k of Object.keys(r)) {
      if (NUM2.includes(k)) r[k] = r2(r[k]);
      else if (NUM3.includes(k)) r[k] = r3(r[k]);
      else if (["capacity_t", "length_ft"].includes(k)) r[k] = r[k] === null || r[k] === "" || r[k] === undefined ? null : Number(r[k]);
      else if (k.endsWith("_id") && k !== "user_id" && k !== "line_id" && r[k] !== null && r[k] !== undefined && /^\d+$/.test(String(r[k]))) r[k] = Number(r[k]);
    }
    return r;
  }
  function defaults(c, t, r) {
    const n = nowIso(), base = {};
    if (!PK[t] && t !== "load_reviews") base.id = ++D.seq[t];
    if (["loads", "load_lines", "load_costs", "payments", "load_files", "sawmills", "parties"].includes(t)) { base.created_at = n; base.created_by = c.uid; }
    if (["loads", "load_lines", "load_costs", "payments", "line_prices", "load_billing"].includes(t)) { base.updated_at = n; base.updated_by = ["line_prices", "load_billing"].includes(t) ? c.uid : null; }
    if (t === "loads") Object.assign(base, {load_no: "L-" + String(++D.seq.load_no).padStart(4, "0"), load_date: todayIST(), truck_stage: "planning"});
    if (t === "load_lines") Object.assign(base, {line_status: "planned", size_grade: null});
    if (t === "line_prices") base.adjustment = 0;
    if (t === "load_billing") Object.assign(base, {sale_adjustment: 0, gst_amount: 0});
    if (t === "payments") Object.assign(base, {paid_on: todayIST(), mode: "bank"});
    if (t === "load_files") base.kind = "Other";
    if (t === "parties") Object.assign(base, {kind: "buyer", credit_days: 30});
    return {...base, ...r};
  }

  /* ---------------- REST ---------------- */
  function parseFilters(sp) {
    const f = [];
    for (const [k, v] of sp.entries()) {
      if (["select", "order", "limit", "offset", "on_conflict", "columns"].includes(k)) continue;
      const i = v.indexOf("."), op = v.slice(0, i), val = v.slice(i + 1);
      f.push(row => {
        const x = row[k];
        switch (op) {
          case "eq": return String(x) === val;
          case "neq": return String(x) !== val;
          case "gte": return x !== null && x !== undefined && (typeof x === "number" ? x >= Number(val) : String(x) >= val);
          case "lte": return x !== null && x !== undefined && (typeof x === "number" ? x <= Number(val) : String(x) <= val);
          case "gt": return x !== null && x !== undefined && (typeof x === "number" ? x > Number(val) : String(x) > val);
          case "lt": return x !== null && x !== undefined && (typeof x === "number" ? x < Number(val) : String(x) < val);
          case "in": return val.replace(/^\(|\)$/g, "").split(",").map(s => s.replace(/^"|"$/g, "")).includes(String(x));
          case "is": return val === "null" ? x === null || x === undefined : String(x) === val;
          default: throw new ApiErr(400, "PGRST100", "unsupported filter " + op);
        }
      });
    }
    return row => f.every(fn => fn(row));
  }
  function orderLimit(rows, sp) {
    const o = sp.get("order");
    if (o) {
      const terms = o.split(",").map(t => { const b = t.split("."); return {k: b[0], desc: b.includes("desc")}; });
      rows.sort((a, b) => {
        for (const {k, desc} of terms) {
          const x = a[k], y = b[k];
          if (x === y) continue;
          if (x === null || x === undefined) return 1;      // nulls last
          if (y === null || y === undefined) return -1;
          const cmp = typeof x === "number" && typeof y === "number" ? x - y : String(x) < String(y) ? -1 : 1;
          return desc ? -cmp : cmp;
        }
        return 0;
      });
    }
    const off = Number(sp.get("offset") || 0), lim = sp.get("limit");
    return rows.slice(off, lim ? off + Number(lim) : undefined);
  }
  function pick(rows, sp) {
    const s = (sp.get("select") || "*").trim();
    if (s === "*") return rows.map(clone);
    const cols = s.split(",").map(x => x.trim());
    return rows.map(r => Object.fromEntries(cols.map(k => [k, r[k] ?? null])));
  }
  function source(c, t) {
    if (t === "v_lines") return vLines(c);
    if (t === "v_loads") return vLoads(c);
    if (t === "v_balances") return vBalances(c);
    if (!D.t[t]) throw new ApiErr(404, "42P01", `relation "public.${t}" does not exist`);
    const ok = READ[t] ? READ[t](c) : () => false;
    return D.t[t].filter(ok);
  }

  function deleteRow(c, t, r) {
    if (t === "load_lines") lineRules("delete", r, null);
    D.t[t] = D.t[t].filter(x => x !== r);
    if (LOGGED.includes(t)) log(c, t, "delete", r, null);
    if (t === "loads") {                                   // cascades, like the foreign keys
      ["load_lines", "load_costs", "load_billing", "load_files"].forEach(ct => D.t[ct].filter(x => x.load_id === r.id).forEach(x => {
        if (ct === "load_lines") D.t.line_prices = D.t.line_prices.filter(p => p.line_id !== x.id);
        D.t[ct] = D.t[ct].filter(y => y !== x); log(c, ct, "delete", x, null);
      }));
      D.t.load_reviews = D.t.load_reviews.filter(x => x.load_id !== r.id);
      D.t.payments.forEach(p => { if (p.load_id === r.id) p.load_id = null; });
    }
    if (t === "load_lines") D.t.line_prices = D.t.line_prices.filter(p => p.line_id !== r.id);
  }

  function rest(c, method, t, sp, headers, bodyText) {
    const prefer = headers.get("Prefer") || "";
    const wantObj = (headers.get("Accept") || "").includes("vnd.pgrst.object");
    let rows;
    if (method === "GET" || method === "HEAD") {
      rows = orderLimit(source(c, t).filter(parseFilters(sp)), sp);
    } else {
      if (t.startsWith("v_")) throw new ApiErr(400, "55000", "cannot change a view");
      const backup = JSON.stringify(D.t), seqBackup = JSON.stringify(D.seq);
      try {
        const out = [];
        if (method === "DELETE") {
          if (!allowed(c, "delete", t)) { rows = []; }
          else { const victims = source(c, t).filter(parseFilters(sp)); victims.forEach(r => { deleteRow(c, t, r); out.push(r); }); rows = out; }
        } else {
          const payload = JSON.parse(bodyText || "null"), items = Array.isArray(payload) ? payload : [payload];
          if (method === "POST") {
            const upsert = prefer.includes("merge-duplicates"), key = sp.get("on_conflict");
            for (const it0 of items) {
              const it = normalise({...it0});
              const existing = upsert && key ? D.t[t].find(r => key.split(",").every(k => String(r[k]) === String(it[k]))) : null;
              if (existing) {
                if (!allowed(c, "update", t) || !source(c, t).includes(existing)) throw deny();
                out.push(update(c, t, existing, it));
              } else {
                if (!allowed(c, "insert", t)) throw deny();
                const row = defaults(c, t, it);
                if (PK[t] && D.t[t].some(r => String(r[PK[t]]) === String(row[PK[t]]))) throw new ApiErr(409, "23505", "duplicate key value violates unique constraint");
                if (t === "load_files" && D.t.load_files.some(r => r.storage_path === row.storage_path)) throw new ApiErr(409, "23505", "duplicate key value violates unique constraint");
                if (t === "load_lines") lineRules("insert", null, row);
                if (t === "line_prices" && !D.t.load_lines.some(l => l.id === row.line_id)) throw new ApiErr(409, "23503", "line not found");
                if (t === "load_billing" && !D.t.loads.some(l => l.id === row.load_id)) throw new ApiErr(409, "23503", "load not found");
                checkRow(t, row, "insert", null);
                D.t[t].push(row);
                if (LOGGED.includes(t)) log(c, t, "insert", null, row);
                out.push(row);
              }
            }
          } else if (method === "PATCH") {
            const it = normalise({...items[0]});
            if (allowed(c, "update", t)) source(c, t).filter(parseFilters(sp)).forEach(r => out.push(update(c, t, r, it)));
          }
          rows = out;
        }
        save();
      } catch (e) { D.t = JSON.parse(backup); D.seq = JSON.parse(seqBackup); throw e; }   // all-or-nothing, like a transaction
      if (!prefer.includes("return=representation")) return json(method === "POST" ? 201 : 204, null);
    }
    rows = pick(rows, sp);
    if (wantObj) {
      if (rows.length !== 1) return json(406, {code: "PGRST116", message: "JSON object requested, multiple (or no) rows returned", details: `The result contains ${rows.length} rows`, hint: null});
      return json(200, rows[0]);
    }
    return json(method === "GET" ? 200 : 201, rows);
  }
  function update(c, t, row, patch) {
    const old = clone(row), next = {...row, ...patch};
    if (t === "profiles" && patch.role && !["owner", "accountant", "staff"].includes(patch.role)) throw new ApiErr(400, "23514", "bad role");
    if (["loads", "load_lines", "load_costs", "payments", "line_prices", "load_billing"].includes(t)) { next.updated_at = nowIso(); next.updated_by = c.uid; }
    if (t === "load_lines") lineRules("update", old, next);
    checkRow(t, next, "update", old);
    Object.assign(row, next);
    if (LOGGED.includes(t)) log(c, t, "update", old, row);
    return row;
  }

  /* ---------------- RPC, team, auth, storage ---------------- */
  function rpc(c, fn, args) {
    if (fn === "is_admin") return c.admin;
    if (fn === "is_member") return c.member;
    if (fn === "v2_mark_checked") {
      if (!c.member) throw new ApiErr(400, "P0001", "not allowed");
      (args.p_load_ids || []).forEach(id => { const lid = Number(id); if (D.t.loads.some(l => l.id === lid)) touch(c, lid); });
      save(); return null;
    }
    if (fn === "v2_post_note") {
      if (!c.member) throw new ApiErr(400, "P0001", "not allowed");
      const msg = String(args.p_message || "").trim();
      if (!msg) throw ruleErr("Write the update first.");
      if (args.p_admin_only && !c.admin) throw new ApiErr(400, "P0001", "not allowed");
      const L = D.t.loads.find(l => l.id === Number(args.p_load));
      if (!L) throw ruleErr("Load not found.");
      D.t.activity.push({id: ++D.seq.activity, load_id: L.id, entity: "note", entity_id: null, action: "note", changes: null, reason: msg.slice(0, 2000),
        truck_stage: L.truck_stage, visibility: args.p_admin_only ? "admin" : "all", actor: c.uid, at: nowIso()});
      touch(c, L.id); save(); return null;
    }
    throw new ApiErr(404, "42883", "function not found");
  }
  function teamAdmin(c, b) {
    if (!c.uid) return json(401, {error: "Sign in first."});
    if (!c.admin) return json(403, {error: "Only the owner or accountant can manage logins."});
    if (String(b.password || "").length < 8) return json(400, {error: "Password must be at least 8 characters."});
    if (b.action === "create") {
      const email = String(b.email || "").trim().toLowerCase();
      if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email)) return json(400, {error: "Enter a valid phone number or email."});
      if (!["owner", "accountant", "staff"].includes(b.role)) return json(400, {error: "Bad role."});
      if (D.auth[email]) return json(400, {error: "A login with this phone/email already exists."});
      const id = "d1000000-0000-0000-0000-" + String(Date.now()).slice(-12).padStart(12, "0");
      D.auth[email] = {id, pw: b.password};
      D.t.profiles.push({id, email, full_name: b.full_name || "", role: b.role, active: true, phone: b.phone || null, created_at: nowIso()});
      save(); return json(200, {ok: true, user_id: id});
    }
    if (b.action === "set_password") {
      const e = Object.entries(D.auth).find(([, v]) => v.id === b.user_id);
      if (!e) return json(404, {error: "Person not found."});
      e[1].pw = b.password; save(); return json(200, {ok: true});
    }
    return json(400, {error: "Unknown action."});
  }
  function session(id, email) {
    const exp = Math.floor(Date.now() / 1000) + 8 * 3600;
    return {access_token: "demo." + b64({sub: id, email, role: "authenticated", exp}) + ".x", token_type: "bearer", expires_in: 8 * 3600, expires_at: exp,
      refresh_token: id + "|" + email, user: {id, email, aud: "authenticated", role: "authenticated", app_metadata: {}, user_metadata: {}, created_at: "2026-11-01T00:00:00Z"}};
  }
  function kataSvg(name) {
    const n = (name.match(/kata-(\d+)/) || [, "0"])[1];
    return `<svg xmlns="http://www.w3.org/2000/svg" width="600" height="800" viewBox="0 0 600 800"><rect width="600" height="800" fill="#fbf8f1"/><rect x="30" y="30" width="540" height="740" fill="none" stroke="#999" stroke-dasharray="6 6"/><text x="300" y="110" font-family="Arial" font-size="34" text-anchor="middle" font-weight="700">SAMPLE WEIGHBRIDGE SLIP</text><text x="300" y="160" font-family="Arial" font-size="24" text-anchor="middle" fill="#666">Demo image for load ${n}</text><text x="80" y="300" font-family="monospace" font-size="28">GROSS   ......  48,620 kg</text><text x="80" y="360" font-family="monospace" font-size="28">TARE    ......  14,150 kg</text><text x="80" y="420" font-family="monospace" font-size="28">NET     ......  34,470 kg</text><text x="300" y="700" font-family="Arial" font-size="22" text-anchor="middle" fill="#a00">Not a real document</text></svg>`;
  }

  async function handle(url, init) {
    await ready;
    const u = new URL(url), method = (init.method || "GET").toUpperCase(), headers = new Headers(init.headers || {});
    let bodyText = init.body;
    if (bodyText && typeof bodyText !== "string" && !(bodyText instanceof FormData) && !(bodyText instanceof Blob)) bodyText = String(bodyText);
    const claims = claimsFrom(headers), c = ctx(claims ? claims.sub : null), p = u.pathname;
    try {
      if (p === "/auth/v1/token") {
        const b = JSON.parse(bodyText || "{}"), g = u.searchParams.get("grant_type");
        if (g === "password") {
          const a = D.auth[String(b.email || "").toLowerCase()];
          if (!a || a.pw !== b.password) return json(400, {error: "invalid_grant", error_description: "Invalid login credentials", msg: "Invalid login credentials", code: 400});
          return json(200, session(a.id, String(b.email).toLowerCase()));
        }
        const [id, email] = String(b.refresh_token || "").split("|");
        return id ? json(200, session(id, email)) : json(400, {error: "invalid_grant", error_description: "Invalid Refresh Token"});
      }
      if (p === "/auth/v1/user") return claims ? json(200, {id: claims.sub, email: claims.email, aud: "authenticated", role: "authenticated", app_metadata: {}, user_metadata: {}}) : json(401, {msg: "invalid JWT"});
      if (p === "/auth/v1/logout") return new Response(null, {status: 204});
      if (p.startsWith("/rest/v1/rpc/")) {
        const r = rpc(c, p.slice(13), JSON.parse(bodyText || "{}"));
        return json(200, r);
      }
      if (p.startsWith("/rest/v1/")) return rest(c, method, p.slice(9), u.searchParams, headers, bodyText);
      if (p.startsWith("/functions/v1/team-admin")) return teamAdmin(c, JSON.parse(bodyText || "{}"));
      if (p.startsWith("/storage/v1/")) return storage(c, method, p.slice(12), u, bodyText);
      return json(404, {message: "not found"});
    } catch (e) {
      if (e instanceof ApiErr) return json(e.status, {code: e.code, message: e.message, details: null, hint: null});
      console.error(e); return json(500, {message: String(e && e.message || e)});
    }
  }
  async function storage(c, method, sub, u, body) {
    let m;
    if ((m = sub.match(/^object\/sign\/([^/]+)\/(.+)$/)) && method === "GET") {
      const key = decodeURIComponent(m[2]), f = D.files[key];
      if (f) { const blob = await (await window.__realFetch(f)).blob(); return new Response(blob, {status: 200}); }
      if (/^demo\/kata-/.test(key)) return new Response(kataSvg(key), {status: 200, headers: {"Content-Type": "image/svg+xml"}});
      return json(400, {message: "not found"});
    }
    if (!c.member) return json(403, {statusCode: "403", error: "Unauthorized", message: "new row violates row-level security policy"});
    if ((m = sub.match(/^object\/sign\/([^/]+)$/)) && method === "POST") {
      const b = JSON.parse(body || "{}");
      // Signed links point at a data: URL (uploaded) or the sample slip, so <img> works offline.
      return json(200, (b.paths || []).map(pth => ({path: pth, error: null,
        signedURL: D.files[pth] ? null : `/object/sign/lorry-files/${pth}?token=demo`,
        signedUrl: D.files[pth] || ("data:image/svg+xml;charset=utf-8," + encodeURIComponent(kataSvg(pth)))})));
    }
    if ((m = sub.match(/^object\/([^/]+)$/)) && method === "DELETE") {
      const b = JSON.parse(body || "{}"); (b.prefixes || []).forEach(x => delete D.files[x]); save(); return json(200, []);
    }
    if ((m = sub.match(/^object\/([^/]+)\/(.+)$/)) && (method === "POST" || method === "PUT")) {
      const key = decodeURIComponent(m[2]);
      let file = body;
      if (body instanceof FormData) for (const [, v] of body.entries()) if (v instanceof Blob) file = v;
      const dataUrl = await new Promise((ok, bad) => { const fr = new FileReader(); fr.onload = () => ok(fr.result); fr.onerror = bad; fr.readAsDataURL(file); });
      D.files[key] = dataUrl; save();
      return json(200, {Key: "lorry-files/" + key, Id: key});
    }
    return json(404, {message: "not found"});
  }

  /* ---------------- install ---------------- */
  window.__realFetch = window.fetch.bind(window);
  ready = load(false);
  window.ADITYA_DEMO.ready = ready;
  window.ADITYA_CONFIG = {url: BASE, key: "demo-anon-key",
    fileUrl: async path => { await ready; return D.files[path] || ("data:image/svg+xml;charset=utf-8," + encodeURIComponent(kataSvg(path))); },
    fetch: (url, init) => String(url).startsWith(BASE) ? handle(String(url), init || {}) : window.__realFetch(url, init)};
})();
