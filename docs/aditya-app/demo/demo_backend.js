// =====================================================================
// DEMO ONLY. Stands in for Supabase so the app can be tried without a
// login. Sample data lives in this phone's browser (localStorage) and
// copies the real database's rules: history, red "Edited" flags, totals.
// Nothing here talks to the real Aditya Traders database.
// =====================================================================
(function(){
  const KEY = "aditya_demo_v1";
  const USERS = {
    "owner@demo":      {id:"d-owner", email:"owner@demo"},
    "accountant@demo": {id:"d-acc",   email:"accountant@demo"},
    "staff@demo":      {id:"d-staff", email:"staff@demo"}
  };
  const META = ["id","created_at","created_by","updated_at","updated_by","last_change_at","last_change_by"];
  const CMETA = ["id","trip_id","created_at","created_by","updated_at","updated_by"];
  let st, session = null, seeding = false;
  const cbs = [];

  // ---------- time: seeded steps go back in time, live actions use the clock
  function now(){
    if (seeding) { st.clock += 7 * 60000; return new Date(st.clock).toISOString(); }
    st.clock = Math.max(st.clock + 1000, Date.now());
    return new Date(st.clock).toISOString();
  }
  const uid = () => session ? session.user.id : null;
  const save = () => { try { localStorage.setItem(KEY, JSON.stringify(st)); } catch(e){} };
  const diff = (o, n, skip) => { const d = {}; for (const k in n) if (!skip.includes(k) && JSON.stringify(o[k]) !== JSON.stringify(n[k])) d[k] = [o[k], n[k]]; return d; };
  const strip = (r, skip) => { const c = {...r}; skip.forEach(k => delete c[k]); return c; };
  const log = (trip_id, table_name, record_id, action, changes) => st.DB.change_log.push({id:++st.seq.change_log, trip_id, table_name, record_id, action, changes, changed_by:uid(), changed_at:now()});
  const touch = t => { const DB = st.DB; if (!DB.trips.some(x => x.id === t)) return; const r = DB.trip_reviews.find(x => x.trip_id === t && x.user_id === uid()); const ts = now(); if (r) r.reviewed_at = ts; else DB.trip_reviews.push({trip_id:t, user_id:uid(), reviewed_at:ts}); };
  const bump = t => { const tr = st.DB.trips.find(x => x.id === t); if (tr) { tr.last_change_at = now(); tr.last_change_by = uid(); } touch(t); };

  function vtrips(){
    const DB = st.DB;
    return DB.trips.map(t => {
      const s = DB.sawmills.find(x => x.id === t.sawmill_id), p = DB.parties.find(x => x.id === t.party_id);
      const ch = DB.trip_charges.filter(c => c.trip_id === t.id).reduce((a, c) => a + Number(c.amount), 0);
      const r = DB.trip_reviews.find(x => x.trip_id === t.id && x.user_id === uid());
      return {...t, sawmill_name:s?.name ?? null, sawmill_place:s?.place ?? null, party_name:p?.name ?? null, party_city:p?.city ?? null,
        charges_total:ch, total_cost:Number(t.freight_amount || 0) + ch, my_reviewed_at:r ? r.reviewed_at : null,
        my_flag: !r ? "new" : (t.last_change_at > r.reviewed_at ? "edited" : "ok"),
        change_count: DB.change_log.filter(l => l.trip_id === t.id && !(l.table_name === "trips" && l.action === "insert")).length};
    });
  }

  // ---------- a tiny query builder with the same calls the app uses
  function Q(table){ this.t = table; this.f = []; this.op = "select"; this.ord = []; this.lim = null; this.one = null; }
  Q.prototype.select = function(){ return this; };
  Q.prototype.eq = function(k, v){ this.f.push(r => r[k] === v); return this; };
  Q.prototype.in = function(k, v){ this.f.push(r => v.includes(r[k])); return this; };
  Q.prototype.gte = function(k, v){ this.f.push(r => r[k] >= v); return this; };
  Q.prototype.lte = function(k, v){ this.f.push(r => r[k] <= v); return this; };
  Q.prototype.order = function(k, o){ this.ord.push([k, !o || o.ascending !== false]); return this; };
  Q.prototype.limit = function(n){ this.lim = n; return this; };
  Q.prototype.single = function(){ this.one = "single"; return this; };
  Q.prototype.maybeSingle = function(){ this.one = "maybe"; return this; };
  Q.prototype.insert = function(o){ this.op = "insert"; this.val = o; return this; };
  Q.prototype.update = function(o){ this.op = "update"; this.val = o; return this; };
  Q.prototype.delete = function(){ this.op = "delete"; return this; };
  Q.prototype.then = function(res, rej){ return Promise.resolve().then(() => { const r = this.run(); if (!seeding) save(); return r; }).then(res, rej); };
  Q.prototype.run = function(){
    const DB = st.DB, t = this.t;
    const me = DB.profiles.find(p => p.id === uid());
    const member = me && me.active;
    if (t !== "profiles" && !member) return {data: this.op === "select" ? [] : null, error: this.op === "select" ? null : {message:"row-level security"}};
    // Owner's answer E5: the accountant may not change costs (same rule as the real database).
    if (me && me.role === "accountant" && this.op !== "select" && (t === "trip_charges" || (t === "trips" && this.op === "update" && this.val && "freight_amount" in this.val)))
      return {data:null, error:{message:"The accountant cannot change costs."}};
    if (this.op === "select") {
      let rows = t === "v_trips" ? vtrips() : DB[t].slice();
      if (t === "trip_reviews") rows = rows.filter(r => r.user_id === uid());
      rows = rows.filter(r => this.f.every(f => f(r)));
      for (const [k, asc] of this.ord.slice().reverse()) rows.sort((a, b) => (a[k] > b[k] ? 1 : a[k] < b[k] ? -1 : 0) * (asc ? 1 : -1));
      if (this.lim) rows = rows.slice(0, this.lim);
      rows = JSON.parse(JSON.stringify(rows));
      if (this.one) return {data: rows[0] || null, error: (!rows[0] && this.one === "single") ? {message:"not found"} : null};
      return {data: rows, error: null};
    }
    if (this.op === "insert") {
      const ts = now();
      const r = {...this.val, id: ++st.seq[t], created_at: ts, created_by: uid()};
      if (t === "trips") { r.updated_at = ts; r.last_change_at = ts; r.last_change_by = uid(); r.status = r.status || "order_taken"; r.trip_date = r.trip_date || ts.slice(0, 10); DB.trips.push(r); log(r.id, "trips", r.id, "insert", strip(r, META)); touch(r.id); }
      else if (t === "trip_charges") { r.amount = Number(r.amount); DB.trip_charges.push(r); log(r.trip_id, "trip_charges", r.id, "insert", strip(r, CMETA)); bump(r.trip_id); }
      else DB[t].push(r);
      return {data: this.one ? {...r} : [r], error: null};
    }
    if (this.op === "update") {
      if (t === "profiles" && !(me && me.role === "owner")) return {data: null, error: null};
      for (const r of DB[t].filter(r => this.f.every(f => f(r)))) {
        const before = {...r};
        Object.assign(r, this.val);
        if (t === "trips") { const d = diff(before, r, META); if (Object.keys(d).length) { r.updated_at = r.last_change_at = now(); r.updated_by = r.last_change_by = uid(); log(r.id, "trips", r.id, "update", d); touch(r.id); } }
        if (t === "trip_charges") { const d = diff(before, r, CMETA); if (Object.keys(d).length) { r.updated_at = now(); r.updated_by = uid(); log(r.trip_id, "trip_charges", r.id, "update", d); bump(r.trip_id); } }
      }
      return {data: null, error: null};
    }
    if (this.op === "delete") {
      if ((t === "trips" || t === "sawmills" || t === "parties") && me.role !== "owner") return {data: null, error: null};
      const keep = [], gone = [];
      DB[t].forEach(r => (this.f.every(f => f(r)) ? gone : keep).push(r));
      DB[t] = keep;
      for (const r of gone) {
        if (t === "trips") { log(r.id, "trips", r.id, "delete", strip(r, META)); DB.trip_charges = DB.trip_charges.filter(c => c.trip_id !== r.id); DB.trip_reviews = DB.trip_reviews.filter(x => x.trip_id !== r.id); }
        if (t === "trip_charges") { log(r.trip_id, "trip_charges", r.id, "delete", strip(r, CMETA)); bump(r.trip_id); }
      }
      return {data: null, error: null};
    }
  };

  function markChecked(ids){ ids.forEach(touch); }

  // ---------- sample data (clearly marked "sample")
  function istDate(daysAgo){ return new Date(Date.now() - daysAgo * 864e5).toLocaleDateString("en-CA", {timeZone:"Asia/Kolkata"}); }
  function as(email){ session = {user: USERS[email]}; }
  function at(daysAgo){ st.clock = Date.now() - daysAgo * 864e5; }
  function run(q){ seeding = true; const r = q.run(); return r.data; }
  function seed(){
    st = {clock: Date.now() - 3 * 864e5, seq:{sawmills:0, parties:0, trips:0, trip_charges:0, change_log:0},
      DB:{profiles:[
          {id:"d-owner", email:"owner@demo", full_name:"Owner (sample)", role:"owner", active:true, created_at:new Date(Date.now() - 5 * 864e5).toISOString()},
          {id:"d-acc", email:"accountant@demo", full_name:"Accountant (sample)", role:"accountant", active:true, created_at:new Date(Date.now() - 5 * 864e5).toISOString()},
          {id:"d-staff", email:"staff@demo", full_name:"Field staff (sample)", role:"staff", active:true, created_at:new Date(Date.now() - 5 * 864e5).toISOString()},
          {id:"d-new", email:"new.person@demo", full_name:"", role:"staff", active:false, created_at:new Date(Date.now() - 864e5).toISOString()}],
        sawmills:[], parties:[], trips:[], trip_charges:[], change_log:[], trip_reviews:[]}};
    seeding = true;
    const q = t => new Q(t);
    as("owner@demo"); at(3.2);
    const s1 = run(q("sawmills").insert({name:"Sri Lakshmi Saw Mill (sample)", place:"Rajanagaram"}).single());
    const s2 = run(q("sawmills").insert({name:"Venkateswara Timber Depot (sample)", place:"Narsipatnam"}).single());
    const s3 = run(q("sawmills").insert({name:"Durga Saw Mill (sample)", place:"Peddapuram"}).single());
    const p1 = run(q("parties").insert({name:"Marwar Timber Co. (sample)", city:"Jodhpur"}).single());
    const p2 = run(q("parties").insert({name:"Shekhawati Wood Traders (sample)", city:"Jaipur"}).single());
    const trip = o => run(q("trips").insert(o).single());
    const cost = (id, type, amt, to) => run(q("trip_charges").insert({trip_id:id, charge_type:type, amount:amt, paid_to:to || null, paid_on:null, note:null}));
    const t1 = trip({trip_date:istDate(3), vehicle_no:"AP39TA1001", lorry_capacity_t:35, driver_name:"Ramesh (sample)", driver_phone:"90000 00001", transporter:"Sri Sai Transport (sample)", sawmill_id:s1.id, wood_type:"Mango", quantity_cft:1180, net_weight_t:34.6, freight_amount:52000, party_id:p1.id, destination:null, status:"completed", notes:null});
    cost(t1.id, "Hamali / loading", 3500); cost(t1.id, "Weighbridge", 300);
    at(2.2);
    const t2 = trip({trip_date:istDate(2), vehicle_no:"AP37TB2002", lorry_capacity_t:30, driver_name:"Suresh (sample)", driver_phone:"90000 00002", transporter:"Sri Sai Transport (sample)", sawmill_id:s2.id, wood_type:"Mango", quantity_cft:1010, net_weight_t:29.8, freight_amount:47000, party_id:p2.id, destination:null, status:"on_the_way", notes:null});
    cost(t2.id, "Hamali / loading", 3000); cost(t2.id, "Permit", 1200);
    as("staff@demo"); at(1.25);
    const t3 = trip({trip_date:istDate(1), vehicle_no:"AP31TC3003", lorry_capacity_t:35, driver_name:"Naresh (sample)", driver_phone:"90000 00003", transporter:null, sawmill_id:s1.id, wood_type:"Mango", quantity_cft:1205, net_weight_t:34.9, freight_amount:52500, party_id:p1.id, destination:null, status:"on_the_way", notes:"Tally paper photo sent on WhatsApp"});
    cost(t3.id, "Hamali / loading", 3500);
    // accountant checks the first three lorries in the evening
    as("accountant@demo"); at(0.9); markChecked([t1.id, t2.id, t3.id]);
    // next morning the owner corrects freight and adds a toll -> red flag for the accountant
    as("owner@demo"); at(0.45);
    run(q("trips").update({freight_amount:48500}).eq("id", t2.id));
    cost(t2.id, "Toll", 850);
    markChecked([t1.id, t2.id]);
    at(0.1);
    trip({trip_date:istDate(0), vehicle_no:"AP05TD4004", lorry_capacity_t:35, driver_name:null, driver_phone:"90000 00004", transporter:null, sawmill_id:s3.id, wood_type:"Acacia", quantity_cft:null, net_weight_t:null, freight_amount:51000, party_id:p2.id, destination:null, status:"order_taken", notes:"Loading today"});
    seeding = false; session = null;
    save();
    return st;
  }
  try { st = JSON.parse(localStorage.getItem(KEY) || "null"); } catch(e) { st = null; }
  if (!st || !st.DB) seed();

  window.supabase = { createClient: () => ({
    from: t => new Q(t),
    rpc: (fn, args) => Promise.resolve().then(() => { if (fn === "mark_checked") { markChecked(args.p_trip_ids); save(); return {data:null, error:null}; } return {data:null, error:{message:"unknown"}}; }),
    auth: {
      onAuthStateChange(cb){ cbs.push(cb); setTimeout(() => cb("INITIAL_SESSION", session), 0); return {data:{subscription:{unsubscribe(){}}}}; },
      async signInWithPassword({email}){ const u = USERS[email]; if (!u) return {error:{message:"Invalid login credentials"}}; session = {user:u}; cbs.forEach(cb => cb("SIGNED_IN", session)); return {data:{session}, error:null}; },
      async signOut(){ session = null; cbs.forEach(cb => cb("SIGNED_OUT", null)); return {error:null}; },
      async getSession(){ return {data:{session}}; }
    }
  })};
  window.__demoReset = () => { try { localStorage.removeItem(KEY); localStorage.removeItem("at_draft_new"); } catch(e){} location.replace(location.pathname); };
})();
