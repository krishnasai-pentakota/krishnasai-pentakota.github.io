"""Builds the stage-by-stage walkthrough page (out/guide.html) from the demo screenshots."""
import html, os
HERE = os.path.dirname(os.path.abspath(__file__))

# (title, count, who, steps, rules, [(image, caption)])
SECTIONS = [
 ("Home screen", None, "Everyone (money tiles only for Owner and Accountant)",
  ["Counts of loads at every truck stage. Tap a tile to see those loads.",
   "Red bar: loads changed by someone else since you last checked.",
   "Latest updates: every change, with the exact time, the person and the reason."],
  ["Staff never see the money tiles."],
  [("01_owner_home", "Owner's home: 5–6 loads at each stage, 10 to check, money tiles"), ("20_staff_home", "Staff home (Ravi): same loads, no money")]),
 ("1 · Planning", 5, "Owner or Staff",
  ["Tap + New load. Choose the buyer, destination and state, and the truck size (30 T / 35 T).",
   "Write the reason (e.g. “Goel asked for one load of Mango”).",
   "Check which mills have wood: More → Mills → Ask mills about loads (ready WhatsApp message to each mill).",
   "Post the replies as updates on the load, so nobody has to phone around."],
  ["No truck number is needed yet."],
  [("10_list_planning", "Loads in Planning"), ("11_load_planning", "A load in Planning, with the staff's update about mill stock")]),
 ("2 · Truck fixed", 5, "Staff (or Owner)",
  ["Edit the load: truck number, driver name and phone, transporter, freight.",
   "Move to Truck fixed with a reason (e.g. “Truck booked with Sri Sai Transport”)."],
  ["The app refuses to leave Planning without a truck number.",
   "Freight and costs are visible to staff (owner's decision)."],
  [("10_list_truck_fixed", "Loads with a truck fixed"), ("11_load_truck_fixed", "Truck, driver, transporter and freight; history shows who entered them")]),
 ("3 · Going to load", 5, "Staff",
  ["When the driver starts, tap Move to: Going to load and give the reason.",
   "Call or WhatsApp the driver straight from the load page."],
  [],
  [("10_list_going_to_load", "Trucks on the way to the mills"), ("11_load_going_to_load", "Load page with the stage bar")]),
 ("4 · Under loading", 6, "Staff add mills · Owner/Accountant set rates",
  ["Staff: + Add mill for each mill the truck loads at: mill, wood, unit (CFT, Tons, Pieces, CBM…), quantity, length.",
   "The size grade is set from the length: Small under 4 ft, Medium 4–6 ft, Large over 6 ft (provisional, change in Settings).",
   "Owner or accountant: Set rate on each mill line. Amount = quantity × rate ± adjustment. The mill's last rate is suggested.",
   "The fill bar shows CFT against the owner's guide (about 1,350 CFT for 35 T)."],
  ["Staff never see rates or amounts — the database does not send them to staff phones at all.",
   "Every rate change is logged as “Admin only” with the reason."],
  [("10_list_under_loading", "Six loads being loaded; the red one changed since the owner last looked"),
   ("11_load_under_loading", "Owner's view: mill lines with purchase rate and amount"),
   ("21_staff_under_loading", "Ravi's (staff) view of a load being loaded: same lines, no prices")]),
 ("5 · Loaded", 5, "Staff",
  ["At each mill: Mark done with the final quantity.",
   "Add costs (hamali, weighbridge…) and the kata slip photo.",
   "Move to Loaded: the app asks for the kata (weighbridge) net weight in tons, and the reason, e.g. “All mills loaded”.",
   "The net weight then shows on the load card and the truck details (“34.2 T of 35 T”)."],
  ["Loaded is refused while any mill line is not done.",
   "After Loaded, mills cannot be added or re-opened (move back to Under loading first)."],
  [("10_list_loaded", "Loaded trucks"), ("22_staff_after_loading", "Ravi finished both mills, marked Loaded and posted an update")]),
 ("6 · In transit", 6, "Accountant enters e-way bill · Staff move the stage",
  ["Accountant: edit the load and enter the e-way bill number.",
   "Staff: Move to In transit. Tap Ask location to send the driver a ready WhatsApp message asking for his live location.",
   "Post driver updates (“crossed Nagpur”) on the load instead of calling the office."],
  [],
  [("10_list_in_transit", "Trucks on the road"), ("11_load_in_transit", "Load in transit: e-way bill, driver updates in the history")]),
 ("7 · Delivered and billing", 20, "Owner/Staff mark delivered · Accountant bills and records payments",
  ["When the party confirms unloading: Move to Delivered → the bill status becomes Ready to bill.",
   "Accountant: + Create bill — invoice no and date, sale quantity, rate, adjustment, GST amount, credit days.",
   "Due date = invoice date + credit days. Record payments received (bank, UPI, cash, cheque) and payments to mills and transporters."],
  ["Bill status moves by itself: Ready to bill → Billed → Payment pending (part paid or overdue) → Paid.",
   "Sample GST is left at ₹0 — the rate is for the accountant to confirm."],
  [("12_list_ready_to_bill", "Ready to bill (5)"), ("12_list_billed", "Billed, not yet due (5)"), ("12_list_payment_pending", "Payment pending (5)"),
   ("12_list_paid", "Paid (5)"), ("13_load_payment_pending", "A part-paid bill: invoice, due date, received, balance in red")]),
 ("Who changed what — red flags", None, "Everyone",
  ["Each person has their own “checked” time per load. Anything changed by others after that shows in red, with how many changes.",
   "Open the load: the new entries are marked red in the history. Tap Mark checked when done.",
   "The Updates screen lists every change across all loads."],
  ["Nobody can edit or delete the history."],
  [("30_accountant_sees_staff_change", "Lakshmi (accountant) sees exactly what Ravi changed, when and why"),
   ("31_accountant_billing", "Lakshmi bills the load and records a part payment"),
   ("40_owner_updates_after", "Bharat (owner) sees both in Updates")]),
 ("Parties and balances", None, "Owner and Accountant only",
  ["Buyers: what to collect. Mills and transporters: what to pay.",
   "Open a party for its loads, payments and a WhatsApp reminder with the balance."],
  [],
  [("14_parties_buyers", "Buyers to collect from"), ("15_parties_mills", "Mills to pay")]),
]

def card(img, cap):
    return f'<figure><img src="guide/{img}.jpg" alt="{html.escape(cap)}" loading="lazy"><figcaption>{html.escape(cap)}</figcaption></figure>'

parts = []
for title, n, who, steps, rules, imgs in SECTIONS:
    parts.append(f"""<section><h2>{html.escape(title)}{f' <span class="n">{n} sample loads</span>' if n else ''}</h2>
<p class="who"><b>Who:</b> {html.escape(who)}</p>
<ol>{''.join(f'<li>{html.escape(s)}</li>' for s in steps)}</ol>
{('<ul class="rules">' + ''.join(f'<li>{html.escape(r)}</li>' for r in rules) + '</ul>') if rules else ''}
<div class="shots">{''.join(card(i, c) for i, c in imgs)}</div></section>""")

page = f"""<!DOCTYPE html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex"><title>Aditya Traders · How each stage works</title>
<style>
body{{margin:0;background:#f4f1ec;color:#1f1a15;font:16px/1.5 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}}
header{{background:#4a2a12;color:#fbf3e9;padding:22px 16px}}header h1{{margin:0 0 4px;font-size:24px}}header p{{margin:0;opacity:.9}}
main{{max-width:1100px;margin:0 auto;padding:12px}}
.try{{background:#f3b733;border-radius:14px;padding:14px 16px;margin:12px 0;display:flex;gap:12px;align-items:center;flex-wrap:wrap}}
.try a{{background:#4a2a12;color:#fff;text-decoration:none;font-weight:700;padding:10px 16px;border-radius:10px}}
section{{background:#fff;border:1px solid #e6dfd5;border-radius:14px;padding:16px;margin:14px 0}}
h2{{margin:0 0 6px;font-size:20px}}.n{{font-size:13px;background:#efe9e2;border-radius:999px;padding:2px 9px;vertical-align:middle;color:#5b4a3a}}
.who{{margin:0 0 6px;color:#6d4220}}ol{{margin:6px 0;padding-left:22px}}li{{margin:3px 0}}
.rules{{background:#fdecea;border-radius:10px;padding:8px 10px 8px 28px;color:#7f1d1d;margin:8px 0}}
.shots{{display:flex;gap:14px;overflow-x:auto;padding:8px 2px 4px}}
figure{{margin:0;flex:0 0 260px}}figure img{{width:260px;border-radius:12px;border:1px solid #e6dfd5;display:block;background:#eee}}
figcaption{{font-size:13.5px;color:#6b6058;margin-top:6px}}
table{{border-collapse:collapse;width:100%;font-size:15px}}td,th{{border-bottom:1px solid #e6dfd5;padding:7px 6px;text-align:left}}
footer{{text-align:center;color:#6b6058;font-size:13px;padding:16px}}
</style></head><body>
<header><h1>How each stage works</h1><p>Aditya Traders app · sample data · who does what at every stage</p></header>
<main>
<div class="try"><span style="flex:1;min-width:200px"><b>Try it yourself.</b> The demo has the same sample loads. Switch between Owner, Accountant and Staff at the top and watch each other's changes turn red.</span><a href="./">Open the demo</a></div>
<section><h2>The people in the sample</h2><table>
<tr><th>Person</th><th>Role</th><th>Sees</th></tr>
<tr><td>Bharat</td><td>Owner</td><td>Everything, can change everything</td></tr>
<tr><td>Lakshmi</td><td>Accountant</td><td>Same as owner</td></tr>
<tr><td>Ravi, Suresh, Prasad, Naidu, Kiran, Srinu, Raju (+3 more)</td><td>Staff</td><td>Loads, mills, quantities, freight, costs, photos, updates — never rates, bills or payments</td></tr>
</table><p style="margin:8px 0 0;font-size:14px;color:#6b6058">All names, mills, buyers, rates and amounts are invented sample values. The sample was made by running every step as these people through the real database rules, from 1 to 26 Nov 2026.</p></section>
{''.join(parts)}
</main><footer>Aditya Traders · app version 2.0 · sample walkthrough</footer></body></html>"""
open(os.path.join(HERE, "out", "guide.html"), "w", encoding="utf-8").write(page)
print("guide built")
