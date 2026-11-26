/* Aditya Traders: DEMO backend (app 3.3).
   Runs inside the browser and answers the same requests the real app sends to
   Supabase, so the demo page is the real app page with sample data.

   It copies the live database's rules (migrations 001-012):
     * permissions per person (owner = everything; plan, finance, rates, expenses, people)
     * Planning / Truck fixed loads and their history never reach other phones
     * staff never receive freight, charges, rates, bills or payments
     * sawmill allocations -> wood items; weigh slips per sawmill
     * Under loading only after the truck reached a sawmill; driver photo and
       weigh-slip rules from the owner's settings; Loaded needs every item done
     * every change logged (who, exact time, what, reason, stage); red flags per person
     * rate cards are insert-only (history kept)
     * piece tally: CFT = thickness x width x length x pieces / 144 (the owner's workbook);
       Small / Medium / Large items made from it and changed only through it
   Data is kept on this phone/browser only (localStorage). "Reset" restores the sample.
   Sample data: sample_data.json, generated through the REAL database rules. */
(function () {
  "use strict";
  const BASE = "https://demo.adityatraders.local";
  const KEY = "at3_demo_db_v2";
  const PASSWORD = "demo1234";               // every demo login uses this (sample data only)
  const SKIP = ["id", "created_at", "created_by", "updated_at", "updated_by", "change_reason"];
  const OWNER_STAGES = ["planning", "truck_fixed"];
  const AFTER_PLAN = ["truck_fixed", "going_to_load", "under_loading", "loaded", "in_transit", "delivered"];
  const LOADED_PLUS = ["loaded", "in_transit", "delivered"];
  const UNITS = ["CFT", "CBM", "RFT", "SFT", "Tons", "Pieces", "Quintal", "Kg"];
  const PK = {line_prices: "line_id", load_billing: "load_id", app_settings: "key", wood_types: "name", expense_categories: "name"};
  const LOG_VIS = {load_tallies: "all", loads: "all", load_allocations: "all", load_lines: "all", load_files: "all", load_costs: "expenses", line_prices: "finance", load_billing: "finance", payments: "finance", sawmill_rates: "finance"};
  let D = null, ready = null, tallyWrite = false; const blobs = {};

  /* ---------------- storage ---------------- */
  function save() { try { localStorage.setItem(KEY, JSON.stringify(D)); } catch (e) { /* demo still works this session */ } }
  async function load(fresh) {
    if (!fresh) { try { const s = JSON.parse(localStorage.getItem(KEY) || "null"); if (s && s.t) { D = s; return; } } catch (e) {} }
    const j = await (await window.__realFetch("sample_data.json", {cache: "no-store"})).json();
    for (const rows of Object.values(j.tables)) for (const r of rows) for (const k of Object.keys(r))
      if ((k === "at" || k.endsWith("_at")) && r[k]) r[k] = new Date(r[k]).toISOString();   // compare as text
    D = {t: j.tables, auth: {}, files: {}, seq: {}};
    D.t.load_tallies = D.t.load_tallies || [];
    for (const p of D.t.profiles) D.auth[p.email] = {id: p.id, pw: PASSWORD};
    for (const [t, rows] of Object.entries(D.t)) D.seq[t] = rows.reduce((m, r) => Math.max(m, typeof r.id === "number" ? r.id : 0), 0);
    D.seq.load_no = D.t.loads.length;
    save();
  }
  window.ADITYA_DEMO = {reset: async () => { localStorage.removeItem(KEY); await load(true); }, password: PASSWORD};

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
  const json = (status, body) => new Response(body === null ? null : JSON.stringify(body), {status, headers: {"Content-Type": "application/json"}});
  const b64 = o => btoa(unescape(encodeURIComponent(JSON.stringify(o)))).replace(/=+$/, "");
  function claimsFrom(headers) {
    const p = (headers.get("Authorization") || "").replace(/^Bearer /, "").split(".");
    if (p.length !== 3) return null;
    try { const c = JSON.parse(decodeURIComponent(escape(atob(p[1])))); return c.exp > Date.now() / 1000 ? c : null; } catch (e) { return null; }
  }
  const setting = k => Number((D.t.app_settings.find(s => s.key === k) || {}).value ?? 0);

  /* ---------------- who is asking ---------------- */
  function ctx(uid) {
    const me = uid ? D.t.profiles.find(p => p.id === uid) : null;
    const member = !!(me && me.active), owner = member && me.role === "owner";
    const has = p => owner || (member && !!me["perm_" + p]);
    return {uid, me, member, owner, has, money: has("expenses") || has("finance"), seeRates: has("finance") || has("rates")};
  }
  const loadVisible = (c, l) => !!l && c.member && (!OWNER_STAGES.includes(l.truck_stage) || c.has("plan"));
  const visLoad = (c, id) => loadVisible(c, D.t.loads.find(l => l.id === id));

  /* ---------------- views (same maths as the SQL views) ---------------- */
  function vLines(c) {
    if (!c.member) return [];
    return D.t.load_lines.filter(l => visLoad(c, l.load_id)).map(l => {
      const s = D.t.sawmills.find(m => m.id === l.sawmill_id) || {}, a = D.t.load_allocations.find(x => x.id === l.allocation_id) || {};
      const lp = c.seeRates ? D.t.line_prices.find(p => p.line_id === l.id) : null;
      const amount = lp && lp.rate !== null ? r2((Number(l.quantity) || 0) * Number(lp.rate) + Number(lp.adjustment || 0)) : null;
      return {...l, sawmill_name: s.name, sawmill_place: s.place, sawmill_area: s.area, owner_name: a.owner_name ?? null, party_name: a.party_name ?? null,
        rate: lp ? lp.rate : null, adjustment: lp ? lp.adjustment : null, amount};
    });
  }
  function vAllocations(c) {
    return D.t.load_allocations.filter(a => c.member && visLoad(c, a.load_id)).map(a => {
      const s = D.t.sawmills.find(m => m.id === a.sawmill_id) || {}, its = D.t.load_lines.filter(x => x.allocation_id === a.id);
      return {...a, sawmill_name: s.name, sawmill_place: s.place, sawmill_area: s.area, sawmill_phone: s.phone, items_total: its.length,
        items_done: its.filter(x => x.line_status === "done").length, weigh_slips: D.t.load_files.filter(f => f.allocation_id === a.id && f.kind === "Weigh slip").length};
    });
  }
  const fmtQty = n => Number(n).toLocaleString("en-US", {maximumFractionDigits: 3});
  function vLoads(c) {
    if (!c.member) return [];
    const VL = vLines(c);
    return D.t.loads.filter(l => loadVisible(c, l)).map(l => {
      const b = D.t.parties.find(p => p.id === l.party_id), tr = D.t.parties.find(p => p.id === l.transporter_id);
      const lines = VL.filter(x => x.load_id === l.id), byUnit = {};
      lines.forEach(x => { if (x.quantity !== null) byUnit[x.unit] = (byUnit[x.unit] || 0) + Number(x.quantity); });
      const units = Object.keys(byUnit).sort(), amounts = lines.map(x => x.amount).filter(x => x !== null);
      const costs = D.t.load_costs.filter(x => x.load_id === l.id);
      const costsTotal = r2(costs.reduce((s, x) => s + Number(x.amount), 0)), fr = costs.filter(x => x.cost_type === "Truck Freight");
      const files = D.t.load_files.filter(f => f.load_id === l.id), allocs = D.t.load_allocations.filter(a => a.load_id === l.id);
      const fin = c.has("finance");
      const bl = fin ? D.t.load_billing.find(x => x.load_id === l.id) : null;
      const pays = fin ? D.t.payments.filter(p => p.load_id === l.id && p.party_kind === "buyer") : [];
      const received = pays.length ? r2(pays.reduce((s, p) => s + Number(p.amount), 0)) : null;
      const invTotal = bl && bl.sale_rate !== null ? r2((Number(bl.sale_qty) || 0) * Number(bl.sale_rate) + Number(bl.sale_adjustment) + Number(bl.gst_amount)) : null;
      let due = null;
      if (bl && bl.invoice_date) { const d = new Date(bl.invoice_date + "T00:00:00Z"); d.setUTCDate(d.getUTCDate() + (bl.credit_days ?? (b ? b.credit_days : null) ?? 30)); due = d.toISOString().slice(0, 10); }
      let bill = null;
      if (fin) {
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
        lines_total: lines.length, lines_done: lines.filter(x => x.line_status === "done").length, mills_count: new Set(lines.map(x => x.sawmill_id)).size,
        qty_summary: units.length ? units.map(u => fmtQty(byUnit[u]) + " " + u).join(" + ") : null,
        cft_total: lines.some(x => x.unit === "CFT") ? r3(lines.filter(x => x.unit === "CFT").reduce((s, x) => s + Number(x.quantity || 0), 0)) : null,
        purchase_total: amounts.length ? r2(amounts.reduce((s, x) => s + x, 0)) : null,
        costs_total: c.money ? costsTotal : null, freight_total: c.money ? (fr.length ? r2(fr.reduce((s, x) => s + Number(x.amount), 0)) : null) : null, transport_total: c.money ? costsTotal : null,
        driver_photo: files.some(f => f.kind === "Driver with truck") || null, licence_doc: files.some(f => f.kind === "Driving licence") || null,
        cbook_doc: files.some(f => f.kind === "C-Book / RC") || null, weigh_slips: files.filter(f => f.kind === "Weigh slip").length,
        allocs_without_slip: allocs.filter(a => !files.some(f => f.allocation_id === a.id && f.kind === "Weigh slip")).length,
        invoice_no: bl ? bl.invoice_no : null, invoice_date: bl ? bl.invoice_date : null, invoice_total: invTotal, due_date: due, received, bill_stage: bill,
        my_reviewed_at: rv ? rv.reviewed_at : null, last_at: la ? la.at : null, last_by: la ? la.actor : null, last_reason: la ? la.reason : null, last_action: la ? la.action : null,
        my_flag: !rv ? "new" : (la && la.at > rv.reviewed_at ? "edited" : "ok")};
    });
  }
  function vBalances(c) {
    if (!c.has("finance")) return [];
    const VL = vLoads(c), LN = vLines(c), out = [];
    const paid = (k, f) => r2(D.t.payments.filter(p => p.party_kind === k && f(p)).reduce((s, p) => s + Number(p.amount), 0));
    D.t.parties.filter(p => p.kind === "buyer").forEach(p => {
      const ls = VL.filter(l => l.party_id === p.id), open = ls.filter(l => l.bill_stage === "billed" || l.bill_stage === "payment_pending").map(l => l.due_date).sort();
      out.push({party_kind: "buyer", party_id: p.id, sawmill_id: null, name: p.name, place: p.city, phone: p.phone, total_due: r2(ls.reduce((s, l) => s + Number(l.invoice_total || 0), 0)),
        total_paid: paid("buyer", x => x.party_id === p.id), bills: ls.filter(l => l.invoice_no !== null).length, oldest_due: open[0] || null});
    });
    D.t.sawmills.forEach(s => out.push({party_kind: "mill", party_id: null, sawmill_id: s.id, name: s.name, place: s.place, phone: s.phone,
      total_due: r2(LN.filter(x => x.sawmill_id === s.id).reduce((a, x) => a + Number(x.amount || 0), 0)), total_paid: paid("mill", x => x.sawmill_id === s.id),
      bills: new Set(D.t.load_lines.filter(x => x.sawmill_id === s.id).map(x => x.load_id)).size, oldest_due: null}));
    D.t.parties.filter(p => p.kind === "transporter").forEach(p => {
      const ids = new Set(D.t.loads.filter(l => l.transporter_id === p.id).map(l => l.id));
      out.push({party_kind: "transporter", party_id: p.id, sawmill_id: null, name: p.name, place: p.city, phone: p.phone,
        total_due: r2(D.t.load_costs.filter(x => ids.has(x.load_id) && x.cost_type === "Truck Freight").reduce((a, x) => a + Number(x.amount), 0)),
        total_paid: paid("transporter", x => x.party_id === p.id), bills: ids.size, oldest_due: null});
    });
    return out;
  }

  /* ---------------- row-level security ---------------- */
  const READ = {
    profiles: c => r => c.member || r.id === c.uid,
    sawmills: c => () => c.member, parties: c => () => c.member, app_settings: c => () => c.member, wood_types: c => () => c.member,
    expense_categories: c => () => c.money,
    loads: c => r => loadVisible(c, r),
    load_allocations: c => r => c.member && visLoad(c, r.load_id), load_lines: c => r => c.member && visLoad(c, r.load_id), load_files: c => r => c.member && visLoad(c, r.load_id),
    load_tallies: c => r => c.member && visLoad(c, r.load_id),
    load_costs: c => () => c.money, line_prices: c => () => c.seeRates, sawmill_rates: c => () => c.seeRates,
    load_billing: c => () => c.has("finance"), payments: c => () => c.has("finance"),
    activity: c => r => c.member && (!OWNER_STAGES.includes(r.truck_stage || "") || c.has("plan")) &&
      (r.visibility === "all" || (r.visibility === "finance" && c.has("finance")) || (r.visibility === "expenses" && c.money)),
    load_reviews: c => r => r.user_id === c.uid,
  };
  const CAN = {
    insert: {load_tallies: c => c.member, sawmills: c => c.member, parties: c => c.member, loads: c => c.member, load_allocations: c => c.member, load_lines: c => c.member, load_files: c => c.member,
      load_costs: c => c.has("expenses"), line_prices: c => c.has("rates"), sawmill_rates: c => c.has("rates"), load_billing: c => c.has("finance"), payments: c => c.has("finance"),
      wood_types: c => c.has("plan"), expense_categories: c => c.has("expenses"), app_settings: c => c.has("people")},
    update: {load_tallies: c => c.member, sawmills: c => c.member, parties: c => c.member, loads: c => c.member, load_allocations: c => c.member, load_lines: c => c.member, load_costs: c => c.has("expenses"),
      line_prices: c => c.has("rates"), load_billing: c => c.has("finance"), payments: c => c.has("finance"), profiles: c => c.has("people"), app_settings: c => c.has("people"), wood_types: c => c.has("plan")},
    delete: {load_tallies: c => c.member, sawmills: c => c.owner, parties: c => c.owner, loads: c => c.owner, load_files: c => c.member, load_allocations: c => c.member, load_lines: c => c.member,
      load_costs: c => c.has("expenses"), line_prices: c => c.has("rates"), load_billing: c => c.has("finance"), payments: c => c.has("finance")},
  };
  const allowed = (c, op, t, row) => {
    const f = CAN[op][t]; if (!f || !f(c)) return false;
    if (op !== "insert" && t === "load_files" && op === "delete") return c.owner || row.created_by === c.uid;
    if (["load_allocations", "load_lines", "load_files", "load_tallies"].includes(t) && row && row.load_id && !visLoad(c, row.load_id)) return false;
    return true;
  };

  /* ---------------- triggers ---------------- */
  function loadIdOf(t, row) { return t === "loads" ? row.id : t === "line_prices" ? (D.t.load_lines.find(l => l.id === row.line_id) || {}).load_id : row.load_id ?? null; }
  function strip(o) { const d = {}; Object.entries(o).forEach(([k, v]) => { if (v !== null && v !== undefined && !SKIP.includes(k)) d[k] = v; }); return d; }
  function touch(c, lid) {
    if (!c.uid || !lid || !D.t.loads.some(l => l.id === lid)) return;
    const r = D.t.load_reviews.find(x => x.load_id === lid && x.user_id === c.uid);
    if (r) r.reviewed_at = nowIso(); else D.t.load_reviews.push({load_id: lid, user_id: c.uid, reviewed_at: nowIso()});
  }
  function log(c, t, op, oldR, newR) {
    if (!LOG_VIS[t]) return;
    const rec = newR || oldR, lid = loadIdOf(t, rec);
    let d, act = op;
    if (op === "update") {
      d = {}; Object.keys(newR).forEach(k => { if (!SKIP.includes(k) && !same(oldR[k], newR[k])) d[k] = [oldR[k] ?? null, newR[k] ?? null]; });
      if (!Object.keys(d).length) return;
      if (t === "loads" && d.truck_stage) act = "stage";
    } else d = strip(rec);
    const L = D.t.loads.find(l => l.id === lid);
    D.t.activity.push({id: ++D.seq.activity, load_id: lid ?? null, entity: t, entity_id: String(rec.id ?? rec.line_id ?? rec.load_id), action: act, changes: d,
      reason: newR && newR.change_reason && String(newR.change_reason).trim() ? String(newR.change_reason).trim() : null,
      truck_stage: L ? L.truck_stage : (t === "loads" ? rec.truck_stage : null), visibility: LOG_VIS[t], actor: c.uid, at: nowIso()});
    touch(c, lid);
  }
  const hasPhoto = lid => D.t.load_files.some(f => f.load_id === lid && f.kind === "Driver with truck");
  function stageRules(c, r, old) {
    const moved = !old || r.truck_stage !== old.truck_stage;
    if (AFTER_PLAN.includes(r.truck_stage) && !String(r.vehicle_no || "").trim()) throw ruleErr("Enter the truck number before moving past Planning.");
    if (moved && [...OWNER_STAGES, "cancelled"].includes(r.truck_stage) && !c.has("plan")) throw ruleErr("Only the owner can use Planning, Truck fixed or Cancel.");
    if (moved && ["under_loading", ...LOADED_PLUS].includes(r.truck_stage) && setting("driver_photo_required") === 1 && !hasPhoto(r.id)) throw ruleErr("Driver photo with truck is mandatory.");
    if (moved && r.truck_stage === "under_loading" && !D.t.load_allocations.some(a => a.load_id === r.id && a.reached_at)) throw ruleErr("Mark the sawmill the truck has reached first. Under loading starts only at the sawmill.");
    if (moved && LOADED_PLUS.includes(r.truck_stage)) {
      const ls = D.t.load_lines.filter(x => x.load_id === r.id);
      if (!ls.length) throw ruleErr("Add at least one sawmill item before marking the load as Loaded.");
      const open = ls.filter(x => x.line_status !== "done").length;
      if (open) throw ruleErr(`Cannot mark as Loaded: ${open} item(s) are not done yet.`);
      if (setting("weigh_slip_required") === 1) {
        const n = D.t.load_allocations.filter(a => a.load_id === r.id && !D.t.load_files.some(f => f.allocation_id === a.id && f.kind === "Weigh slip")).length;
        if (n) throw ruleErr(`Cannot mark as Loaded: ${n} sawmill(s) have no weigh slip yet.`);
      }
    }
  }
  function allocRules(op, oldR, newR) {
    const lid = (newR || oldR).load_id, L = D.t.loads.find(l => l.id === lid), st = L ? L.truck_stage : null;
    if (LOADED_PLUS.includes(st) && op !== "update") throw ruleErr(`This load is already ${st.replace("_", " ")}. Move it back to Under loading first to change its sawmills.`);
    if (op === "insert" && !OWNER_STAGES.includes(st) && setting("driver_photo_required") === 1 && !hasPhoto(lid)) throw ruleErr("Driver photo with truck is mandatory.");
    if (op === "update" && newR.load_id !== oldR.load_id) throw ruleErr("An allocation cannot move to another load.");
    if (op === "insert" && D.t.load_allocations.some(a => a.load_id === newR.load_id && a.sawmill_id === newR.sawmill_id)) throw new ApiErr(409, "23505", "duplicate key value violates unique constraint");
    if (op === "insert" && newR.owner_name == null) newR.owner_name = (D.t.sawmills.find(s => s.id === newR.sawmill_id) || {}).contact_name ?? null;
  }
  function lineRules(op, oldR, newR) {
    if (newR && newR.allocation_id) {   // item takes its load and sawmill from the allocation
      const a = D.t.load_allocations.find(x => x.id === newR.allocation_id);
      if (!a) throw ruleErr("Sawmill allocation not found.");
      newR.load_id = a.load_id; newR.sawmill_id = a.sawmill_id;
    }
    const L = D.t.loads.find(l => l.id === (newR || oldR).load_id);
    if (L && LOADED_PLUS.includes(L.truck_stage) && (op !== "update" || newR.line_status !== "done"))
      throw ruleErr(`This load is already ${L.truck_stage.replace("_", " ")}. Move it back to Under loading first to change its mill lines.`);
    if (!tallyWrite) {   // items made by a piece tally change only through the tally
      if (op === "insert" && newR.tally_id) throw ruleErr("Items from a piece tally are made by the tally.");
      if (op === "update" && (oldR.tally_id || newR.tally_id) && ["quantity", "pieces", "size_grade", "wood_type", "unit", "tally_id", "allocation_id", "dimensions", "length_ft"].some(k => !same(oldR[k], newR[k])))
        throw ruleErr("This item comes from the piece tally. Change the tally instead.");
      if (op === "delete" && oldR.tally_id && D.t.load_tallies.some(x => x.id === oldR.tally_id) && D.t.load_allocations.some(x => x.id === oldR.allocation_id))
        throw ruleErr("This item comes from the piece tally. Remove the tally instead.");
    }
    if (newR && !newR.size_grade && newR.length_ft && setting("size_auto") === 1) newR.size_grade = gradeFor(newR.length_ft);
  }
  const gradeFor = len => len < (setting("size_small_below_ft") || 3) ? "small" : len >= (setting("size_large_from_ft") || 5) ? "large" : "medium";
  /* ---------- piece tally (same checks and formula as migration 013) ---------- */
  function tallyClean(p) {
    const res = {};
    if (p === null || p === undefined) return res;
    if (typeof p !== "object" || Array.isArray(p)) throw ruleErr("The tally is not in the right form.");
    for (const [t, cells] of Object.entries(p)) {
      if (!/^[0-9]+(\.[0-9]+)?$/.test(t) || ![1, 1.5, 2].includes(Number(t))) throw ruleErr(`Thickness ${t} inch is not on the tally (1, 1.5 or 2 inch).`);
      if (!cells || typeof cells !== "object" || Array.isArray(cells)) throw ruleErr("The tally is not in the right form.");
      const tk = String(Number(t)), o = res[tk] || {};
      for (const [k, v] of Object.entries(cells)) {
        const m = /^([0-9]+(?:\.[0-9]+)?)\|([0-9]+)$/.exec(k);
        if (!m) throw ruleErr(`Tally cell "${k}" is not a length|width.`);
        const len = Number(m[1]), w = Number(m[2]);
        if (len < 1.5 || len > 11 || len * 4 !== Math.trunc(len * 4)) throw ruleErr(`Length ${len} ft is not on the tally (1 ft 6 in to 11 ft, in 3-inch steps).`);
        if (w < 3 || w > 18) throw ruleErr(`Width ${w} inch is not on the tally (3 to 18 inches).`);
        if (typeof v !== "number") throw ruleErr("Piece counts must be numbers.");
        if (v < 0 || v > 100000 || v !== Math.trunc(v)) throw ruleErr("Piece counts must be whole numbers (0 to 100000).");
        const ck = String(len) + "|" + w;
        if (v > 0) o[ck] = v; else delete o[ck];
      }
      if (Object.keys(o).length) res[tk] = o; else delete res[tk];
    }
    return res;
  }
  function tallyTotals(p) {
    const out = {};
    for (const [t, cells] of Object.entries(p || {})) for (const [k, n] of Object.entries(cells)) {
      const [len, w] = k.split("|").map(Number), g = gradeFor(len), key = g + "|" + t;
      out[key] = out[key] || {g, t: Number(t), pcs: 0, cft: 0}; out[key].pcs += n; out[key].cft += Number(t) * w * len * n / 144;
    }
    return Object.values(out);
  }
  function tallyRules(op, oldR, newR) {
    if (op !== "delete") {
      if (op === "update" && newR.allocation_id !== oldR.allocation_id) throw ruleErr("A tally cannot move to another sawmill.");
      const a = D.t.load_allocations.find(x => x.id === newR.allocation_id);
      if (!a) throw ruleErr("Sawmill allocation not found.");
      newR.load_id = a.load_id; newR.sawmill_id = a.sawmill_id; newR.wood_type = String(newR.wood_type || "").trim();
      newR.counts = tallyClean(newR.counts);
    }
    const L = D.t.loads.find(l => l.id === (newR || oldR).load_id);
    if (L && LOADED_PLUS.includes(L.truck_stage)) throw ruleErr(`This load is already ${L.truck_stage.replace("_", " ")}. Move it back to Under loading first to change its tally.`);
    if (op === "insert" && D.t.load_tallies.some(x => x.allocation_id === newR.allocation_id && x.wood_type === newR.wood_type)) throw new ApiErr(409, "23505", "duplicate key value violates unique constraint");
    if (op === "update" && D.t.load_tallies.some(x => x !== oldR && x.id !== newR.id && x.allocation_id === newR.allocation_id && x.wood_type === newR.wood_type)) throw new ApiErr(409, "23505", "duplicate key value violates unique constraint");
  }
  function tallyItems(c, T) {   // Small / Medium / Large items in CFT, like the trigger
    tallyWrite = true;
    try {
      const tot = tallyTotals(T.counts);
      for (const g of ["small", "medium", "large"]) {
        const parts = tot.filter(x => x.g === g).sort((x, y) => x.t - y.t);
        const pcs = parts.reduce((a, x) => a + x.pcs, 0), cf = r3(parts.reduce((a, x) => a + x.cft, 0));
        const dims = "Piece tally, " + parts.map(x => x.t + '"').join(", ") + " thick";
        const ln = D.t.load_lines.find(x => x.tally_id === T.id && x.size_grade === g);
        if (pcs > 0) {
          if (!ln) insert(c, "load_lines", {allocation_id: T.allocation_id, wood_type: T.wood_type, unit: "CFT", quantity: cf, pieces: pcs, size_grade: g, dimensions: dims, tally_id: T.id, change_reason: T.change_reason ?? null});
          else if (!same([ln.wood_type, ln.quantity, ln.pieces, ln.dimensions], [T.wood_type, cf, pcs, dims])) update(c, "load_lines", ln, {wood_type: T.wood_type, quantity: cf, pieces: pcs, dimensions: dims, change_reason: T.change_reason ?? null});
        } else if (ln) deleteRow(c, "load_lines", ln);
      }
    } finally { tallyWrite = false; }
  }
  function checkRow(c, t, r, op, old) {
    const need = (cond, what) => { if (!cond) throw new ApiErr(400, "23514", `new row for relation "${t}" violates check constraint (${what})`); };
    if (t === "loads") {
      need(!r.capacity_t || r.capacity_t > 0, "capacity"); need(r.net_weight_t == null || (r.net_weight_t > 0 && r.net_weight_t < 100), "net_weight_t");
      stageRules(c, r, old);                                   // BEFORE trigger runs first, as in Postgres
      if (OWNER_STAGES.includes(r.truck_stage) && !c.has("plan")) throw deny();
    }
    if (t === "load_lines") { need(String(r.wood_type || "").trim(), "wood"); need(UNITS.includes(r.unit), "unit"); need(r.quantity == null || r.quantity >= 0, "quantity"); }
    if (t === "load_costs") { need(String(r.cost_type || "").trim(), "category"); need(r.amount !== null && r.amount >= 0, "amount");
      if (r.allocation_id && !D.t.load_allocations.some(a => a.id === r.allocation_id && a.load_id === r.load_id)) throw ruleErr("This sawmill is not on this load."); }
    if (t === "payments") { need(r.amount > 0, "amount");
      need((r.party_kind === "mill" && r.sawmill_id && !r.party_id) || (["buyer", "transporter"].includes(r.party_kind) && r.party_id && !r.sawmill_id), "party"); }
    if (t === "load_files") {
      need(String(r.storage_path || "").trim(), "file");
      if (r.kind === "Weigh slip" && !r.allocation_id) throw ruleErr("Choose the sawmill this weigh slip belongs to.");
      if (r.allocation_id && !D.t.load_allocations.some(a => a.id === r.allocation_id && a.load_id === r.load_id)) throw ruleErr("This sawmill is not on this load.");
    }
    if (t === "sawmill_rates") { need(r.rate >= 0, "rate"); need(UNITS.includes(r.unit), "unit"); }
    if (t === "profiles" && old && !c.owner && (r.role === "owner" || old.role === "owner" || r.perm_people !== old.perm_people)) throw ruleErr("Only the owner can change owner accounts or the people permission.");
    if (["sawmills", "parties", "wood_types", "expense_categories"].includes(t)) need(String(r.name || "").trim(), "name");
    if (t === "load_tallies") need(String(r.wood_type || "").trim(), "wood");
    if (t === "load_allocations") need(r.slip_net_weight_t == null || (r.slip_net_weight_t > 0 && r.slip_net_weight_t < 100), "slip weight");
  }
  const NUM2 = ["rate", "adjustment", "amount", "sale_rate", "sale_adjustment", "gst_amount", "value"], NUM3 = ["quantity", "sale_qty", "net_weight_t", "slip_net_weight_t"];
  function normalise(r) {
    for (const k of Object.keys(r)) {
      if (NUM2.includes(k)) r[k] = r2(r[k]);
      else if (NUM3.includes(k)) r[k] = r3(r[k]);
      else if (["capacity_t", "capacity_cft", "length_ft", "pieces", "credit_days"].includes(k)) r[k] = r[k] === null || r[k] === "" || r[k] === undefined ? null : Number(r[k]);
      else if (k.endsWith("_id") && k !== "user_id" && r[k] !== null && r[k] !== undefined && /^\d+$/.test(String(r[k]))) r[k] = Number(r[k]);
    }
    return r;
  }
  function defaults(c, t, r) {
    const n = nowIso(), base = {};
    if (!PK[t] && t !== "load_reviews") base.id = ++D.seq[t];
    if (["loads", "load_allocations", "load_lines", "load_costs", "payments", "load_files", "sawmills", "parties", "sawmill_rates", "load_tallies"].includes(t)) { base.created_at = n; base.created_by = c.uid; }
    if (t === "load_tallies") Object.assign(base, {counts: {}, notes: null});
    if (["loads", "load_allocations", "load_lines", "load_costs", "payments", "line_prices", "load_billing", "load_tallies"].includes(t)) { base.updated_at = n; base.updated_by = ["line_prices", "load_billing"].includes(t) ? c.uid : null; }
    if (t === "loads") Object.assign(base, {load_no: "L-" + String(++D.seq.load_no).padStart(4, "0"), load_date: todayIST(), truck_stage: "planning"});
    if (t === "load_lines") Object.assign(base, {line_status: "planned", size_grade: null});
    if (t === "line_prices") base.adjustment = 0;
    if (t === "load_billing") Object.assign(base, {sale_adjustment: 0, gst_amount: 0});
    if (t === "payments") Object.assign(base, {paid_on: todayIST(), mode: "bank"});
    if (t === "load_files") base.kind = "Other";
    if (t === "parties") Object.assign(base, {kind: "buyer", credit_days: 30});
    if (t === "sawmill_rates") base.effective_from = todayIST();
    if (["wood_types", "expense_categories"].includes(t)) Object.assign(base, {sort: 100, active: true});
    return {...base, ...r};
  }

  /* ---------------- REST ---------------- */
  function parseFilters(sp) {
    const f = [];
    for (const [k, v] of sp.entries()) {
      if (["select", "order", "limit", "offset", "on_conflict", "columns"].includes(k)) continue;
      const i = v.indexOf("."), op = v.slice(0, i), val = v.slice(i + 1);
      f.push(row => {
        const x = row[k], num = typeof x === "number";
        switch (op) {
          case "eq": return String(x) === val;
          case "neq": return String(x) !== val;
          case "gte": return x != null && (num ? x >= Number(val) : String(x) >= val);
          case "lte": return x != null && (num ? x <= Number(val) : String(x) <= val);
          case "gt": return x != null && (num ? x > Number(val) : String(x) > val);
          case "lt": return x != null && (num ? x < Number(val) : String(x) < val);
          case "in": return val.replace(/^\(|\)$/g, "").split(",").map(s => s.replace(/^"|"$/g, "")).includes(String(x));
          case "is": return val === "null" ? x == null : String(x) === val;
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
          if (x == null) return 1;
          if (y == null) return -1;
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
    if (t === "v_allocations") return vAllocations(c);
    if (!D.t[t]) throw new ApiErr(404, "42P01", `relation "public.${t}" does not exist`);
    const ok = READ[t] ? READ[t](c) : () => false;
    return D.t[t].filter(ok);
  }
  function deleteRow(c, t, r) {
    if (t === "load_lines") lineRules("delete", r, null);
    if (t === "load_allocations") allocRules("delete", r, null);
    if (t === "load_tallies") tallyRules("delete", r, null);
    D.t[t] = D.t[t].filter(x => x !== r);
    if (t === "load_tallies") D.t.load_lines.filter(x => x.tally_id === r.id).forEach(x => deleteRow(c, "load_lines", x));
    log(c, t, "delete", r, null);
    if (t === "loads") {
      ["load_allocations", "load_tallies", "load_lines", "load_costs", "load_billing", "load_files"].forEach(ct => D.t[ct].filter(x => x.load_id === r.id).forEach(x => {
        if (ct === "load_lines") D.t.line_prices = D.t.line_prices.filter(p => p.line_id !== x.id);
        D.t[ct] = D.t[ct].filter(y => y !== x); log(c, ct, "delete", x, null);
      }));
      D.t.load_reviews = D.t.load_reviews.filter(x => x.load_id !== r.id);
      D.t.payments.forEach(p => { if (p.load_id === r.id) p.load_id = null; });
    }
    if (t === "load_allocations") {
      D.t.load_lines.filter(x => x.allocation_id === r.id).forEach(x => { D.t.load_lines = D.t.load_lines.filter(y => y !== x); D.t.line_prices = D.t.line_prices.filter(p => p.line_id !== x.id); log(c, "load_lines", "delete", x, null); });
      D.t.load_files = D.t.load_files.filter(f => f.allocation_id !== r.id);
      D.t.load_tallies.filter(x => x.allocation_id === r.id).forEach(x => { D.t.load_tallies = D.t.load_tallies.filter(y => y !== x); log(c, "load_tallies", "delete", x, null); });
      D.t.load_costs.forEach(x => { if (x.allocation_id === r.id) x.allocation_id = null; });
    }
    if (t === "load_lines") D.t.line_prices = D.t.line_prices.filter(p => p.line_id !== r.id);
  }
  function update(c, t, row, patch) {
    const old = clone(row), next = {...row, ...patch};
    if (["loads", "load_allocations", "load_lines", "load_costs", "payments", "line_prices", "load_billing", "load_tallies"].includes(t)) { next.updated_at = nowIso(); next.updated_by = c.uid; }
    if (t === "load_lines") lineRules("update", old, next);
    if (t === "load_allocations") allocRules("update", old, next);
    if (t === "load_tallies") tallyRules("update", old, next);
    checkRow(c, t, next, "update", old);
    Object.assign(row, next);
    if (t === "load_tallies") tallyItems(c, row);
    log(c, t, "update", old, row);
    return row;
  }
  function insert(c, t, it) {
    const row = defaults(c, t, it);
    if (PK[t] && D.t[t].some(r => String(r[PK[t]]) === String(row[PK[t]]))) throw new ApiErr(409, "23505", "duplicate key value violates unique constraint");
    if (t === "load_files" && D.t.load_files.some(r => r.storage_path === row.storage_path)) throw new ApiErr(409, "23505", "duplicate key value violates unique constraint");
    if (["load_allocations", "load_lines", "load_files", "load_costs"].includes(t) && !visLoad(c, t === "load_lines" && row.allocation_id ? (D.t.load_allocations.find(a => a.id === row.allocation_id) || {}).load_id : row.load_id)) throw deny();
    if (t === "load_tallies" && !visLoad(c, (D.t.load_allocations.find(a => a.id === row.allocation_id) || {}).load_id)) throw deny();
    if (t === "load_lines") lineRules("insert", null, row);
    if (t === "load_allocations") allocRules("insert", null, row);
    if (t === "load_tallies") tallyRules("insert", null, row);
    if (t === "line_prices" && !D.t.load_lines.some(l => l.id === row.line_id)) throw new ApiErr(409, "23503", "item not found");
    checkRow(c, t, row, "insert", null);
    D.t[t].push(row);
    if (t === "load_tallies") tallyItems(c, row);
    log(c, t, "insert", null, row);
    return row;
  }
  function rest(c, method, t, sp, headers, bodyText) {
    const prefer = headers.get("Prefer") || "", wantObj = (headers.get("Accept") || "").includes("vnd.pgrst.object");
    let rows;
    if (method === "GET" || method === "HEAD") rows = orderLimit(source(c, t).filter(parseFilters(sp)), sp);
    else {
      if (t.startsWith("v_")) throw new ApiErr(400, "55000", "cannot change a view");
      const backup = JSON.stringify(D.t), seqBackup = JSON.stringify(D.seq);
      try {
        const out = [];
        if (method === "DELETE") {
          source(c, t).filter(parseFilters(sp)).forEach(r => { if (allowed(c, "delete", t, r)) { deleteRow(c, t, r); out.push(r); } });
        } else {
          const payload = JSON.parse(bodyText || "null"), items = Array.isArray(payload) ? payload : [payload];
          if (method === "POST") {
            const upsert = prefer.includes("merge-duplicates"), key = sp.get("on_conflict");
            for (const it0 of items) {
              const it = normalise({...it0});
              const existing = upsert && key ? D.t[t].find(r => key.split(",").every(k => String(r[k]) === String(it[k]))) : null;
              if (existing) { if (!allowed(c, "update", t, existing) || !source(c, t).includes(existing)) throw deny(); out.push(update(c, t, existing, it)); }
              else { if (!allowed(c, "insert", t, it)) throw deny(); out.push(insert(c, t, it)); }
            }
          } else if (method === "PATCH") {
            const it = normalise({...items[0]});
            source(c, t).filter(parseFilters(sp)).forEach(r => {
              if (!allowed(c, "update", t, r)) return;
              if (t === "loads" && it.truck_stage && OWNER_STAGES.includes(it.truck_stage) && !c.has("plan")) throw deny();
              out.push(update(c, t, r, it));
            });
          }
        }
        rows = out; save();
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

  /* ---------------- RPC, team, auth, storage ---------------- */
  function rpc(c, fn, args) {
    if (fn === "is_admin") return c.has("finance");
    if (fn === "is_member") return c.member;
    if (fn === "is_owner") return c.owner;
    if (fn === "has_perm") return c.has(args.p);
    if (fn === "v2_setting") return setting(args.p_key);
    if (fn === "v2_mark_checked") {
      if (!c.member) throw ruleErr("not allowed");
      (args.p_load_ids || []).forEach(id => { if (visLoad(c, Number(id))) touch(c, Number(id)); }); save(); return null;
    }
    if (fn === "v2_post_note") {
      if (!c.member) throw ruleErr("not allowed");
      const msg = String(args.p_message || "").trim(); if (!msg) throw ruleErr("Write the update first.");
      if (args.p_admin_only && !c.has("finance")) throw ruleErr("not allowed");
      const L = D.t.loads.find(l => l.id === Number(args.p_load)); if (!L) throw ruleErr("Load not found.");
      if (OWNER_STAGES.includes(L.truck_stage) && !c.has("plan")) throw ruleErr("not allowed");
      D.t.activity.push({id: ++D.seq.activity, load_id: L.id, entity: "note", entity_id: null, action: "note", changes: null, reason: msg.slice(0, 2000),
        truck_stage: L.truck_stage, visibility: args.p_admin_only ? "finance" : "all", actor: c.uid, at: nowIso()});
      touch(c, L.id); save(); return null;
    }
    throw new ApiErr(404, "42883", "function not found");
  }
  function teamAdmin(c, b) {
    if (!c.uid) return json(401, {error: "Sign in first."});
    if (!c.has("people")) return json(403, {error: "You do not have permission to manage logins."});
    if (String(b.password || "").length < 8) return json(400, {error: "Password must be at least 8 characters."});
    if (b.action === "create") {
      const email = String(b.email || "").trim().toLowerCase();
      if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email)) return json(400, {error: "Enter a valid phone number or email."});
      if (!["owner", "accountant", "freight", "staff"].includes(b.role)) return json(400, {error: "Bad role."});
      const p = b.perms || {}, flags = {perm_plan: !!p.perm_plan, perm_finance: !!p.perm_finance, perm_expenses: !!p.perm_expenses, perm_rates: !!p.perm_rates, perm_people: !!p.perm_people};
      if ((b.role === "owner" || flags.perm_people) && !c.owner) return json(403, {error: "Only the owner can create an owner or give the people permission."});
      if (D.auth[email]) return json(400, {error: "A login with this phone/email already exists."});
      const id = "d1000000-0000-0000-0000-" + String(Date.now()).slice(-12).padStart(12, "0");
      D.auth[email] = {id, pw: b.password};
      D.t.profiles.push({id, email, full_name: b.full_name || "", role: b.role, active: true, phone: b.phone || null, created_at: nowIso(), ...flags});
      save(); return json(200, {ok: true, user_id: id});
    }
    if (b.action === "set_password") {
      const e = Object.entries(D.auth).find(([, v]) => v.id === b.user_id); if (!e) return json(404, {error: "Person not found."});
      const target = D.t.profiles.find(p => p.id === b.user_id);
      if (target && target.role === "owner" && !c.owner) return json(403, {error: "Only the owner can reset an owner's password."});
      e[1].pw = b.password; save(); return json(200, {ok: true});
    }
    return json(400, {error: "Unknown action."});
  }
  function session(id, email) {
    const exp = Math.floor(Date.now() / 1000) + 8 * 3600;
    return {access_token: "demo." + b64({sub: id, email, role: "authenticated", exp}) + ".x", token_type: "bearer", expires_in: 8 * 3600, expires_at: exp,
      refresh_token: id + "|" + email, user: {id, email, aud: "authenticated", role: "authenticated", app_metadata: {}, user_metadata: {}, created_at: "2026-11-01T00:00:00Z"}};
  }
  /* Placeholder pictures for the sample documents (clearly marked as samples). */
  function sampleSvg(name) {
    const n = (name.match(/-(\d+)/) || [, "0"])[1];
    if (/driver-/.test(name)) return `<svg xmlns="http://www.w3.org/2000/svg" width="600" height="450" viewBox="0 0 600 450"><rect width="600" height="450" fill="#e8eef3"/><rect x="250" y="150" width="300" height="170" rx="10" fill="#4b6584"/><rect x="460" y="190" width="80" height="80" fill="#a5b1c2"/><circle cx="320" cy="335" r="28" fill="#2d3436"/><circle cx="490" cy="335" r="28" fill="#2d3436"/><circle cx="150" cy="170" r="38" fill="#7f8c8d"/><rect x="118" y="212" width="64" height="120" rx="20" fill="#7f8c8d"/><text x="300" y="60" font-family="Arial" font-size="30" text-anchor="middle" font-weight="700">SAMPLE: driver beside truck</text><text x="300" y="420" font-family="Arial" font-size="20" text-anchor="middle" fill="#a00">Demo picture for load ${n}, not a real photo</text></svg>`;
    if (/doc-/.test(name)) return `<svg xmlns="http://www.w3.org/2000/svg" width="600" height="380" viewBox="0 0 600 380"><rect width="600" height="380" rx="20" fill="#f1f2f6"/><rect x="40" y="60" width="140" height="170" fill="#ced6e0"/><text x="210" y="100" font-family="Arial" font-size="28" font-weight="700">SAMPLE LICENCE</text><text x="210" y="150" font-family="monospace" font-size="20">DL No: XXXXXXXXXXXX</text><text x="300" y="340" font-family="Arial" font-size="20" text-anchor="middle" fill="#a00">Demo picture, not a real document</text></svg>`;
    return `<svg xmlns="http://www.w3.org/2000/svg" width="600" height="800" viewBox="0 0 600 800"><rect width="600" height="800" fill="#fbf8f1"/><rect x="30" y="30" width="540" height="740" fill="none" stroke="#999" stroke-dasharray="6 6"/><text x="300" y="110" font-family="Arial" font-size="34" text-anchor="middle" font-weight="700">SAMPLE WEIGH SLIP</text><text x="300" y="160" font-family="Arial" font-size="24" text-anchor="middle" fill="#666">Demo image for load ${n}</text><text x="80" y="300" font-family="monospace" font-size="28">GROSS   ......  28,620 kg</text><text x="80" y="360" font-family="monospace" font-size="28">TARE    ......  14,150 kg</text><text x="80" y="420" font-family="monospace" font-size="28">NET     ......  14,470 kg</text><text x="300" y="700" font-family="Arial" font-size="22" text-anchor="middle" fill="#a00">Not a real document</text></svg>`;
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
      if (p.startsWith("/rest/v1/rpc/")) return json(200, rpc(c, p.slice(13), JSON.parse(bodyText || "{}")));
      if (p.startsWith("/rest/v1/")) return rest(c, method, p.slice(9), u.searchParams, headers, bodyText);
      if (p.startsWith("/functions/v1/team-admin")) return teamAdmin(c, JSON.parse(bodyText || "{}"));
      if (p.startsWith("/storage/v1/")) return storage(c, method, p.slice(12), bodyText);
      return json(404, {message: "not found"});
    } catch (e) {
      if (e instanceof ApiErr) return json(e.status, {code: e.code, message: e.message, details: null, hint: null});
      console.error(e); return json(500, {message: String(e && e.message || e)});
    }
  }
  async function storage(c, method, sub, body) {
    if (!c.member) return json(403, {statusCode: "403", error: "Unauthorized", message: "new row violates row-level security policy"});
    let m;
    if ((m = sub.match(/^object\/([^/]+)$/)) && method === "DELETE") {
      const b = JSON.parse(body || "{}"); (b.prefixes || []).forEach(x => delete D.files[x]); save(); return json(200, []);
    }
    if ((m = sub.match(/^object\/([^/]+)\/(.+)$/)) && (method === "POST" || method === "PUT") && !sub.startsWith("object/sign/")) {
      const key = decodeURIComponent(m[2]); let file = body;
      if (body instanceof FormData) for (const [, v] of body.entries()) if (v instanceof Blob) file = v;
      D.files[key] = await new Promise((ok, bad) => { const fr = new FileReader(); fr.onload = () => ok(fr.result); fr.onerror = bad; fr.readAsDataURL(file); });
      save(); return json(200, {Key: "lorry-files/" + key, Id: key});
    }
    return json(404, {message: "not found"});
  }

  /* ---------------- install ---------------- */
  window.__realFetch = window.fetch.bind(window);
  ready = load(false);
  window.ADITYA_DEMO.ready = ready;
  window.ADITYA_CONFIG = {url: BASE, key: "demo-anon-key",
    // Photos in the demo live in this browser; expense receipts only for money people (same rule as the storage policy).
    // Returned as blob: links so they open in a new tab as well as inside <img>.
    fileUrl: async path => {
      await ready;
      let uid = null;
      try { const k = Object.keys(localStorage).find(x => x.startsWith("sb-") && x.endsWith("-auth-token")); uid = (claimsFrom(new Headers({Authorization: "Bearer " + JSON.parse(localStorage.getItem(k)).access_token})) || {}).sub || null; } catch (e) {}
      const me = ctx(uid);
      if (!me.member) throw new Error("Sign in first.");
      if (path.startsWith("expenses/") && !me.money) throw new Error("Not allowed.");
      if (blobs[path]) return blobs[path];
      const blob = D.files[path] ? await (await window.__realFetch(D.files[path])).blob() : new Blob([sampleSvg(path)], {type: "image/svg+xml"});
      return (blobs[path] = URL.createObjectURL(blob));
    },
    fetch: (url, init) => String(url).startsWith(BASE) ? handle(String(url), init || {}) : window.__realFetch(url, init)};
})();
