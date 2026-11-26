"""Builds the stage-by-stage walkthrough page (out/guide.html) for app 3.3 from the demo screenshots.
Run test_demo.py first (it writes shots/*.png and shots/staff_loading_details.pdf)."""
import html, os, subprocess
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
SHOTS = os.path.join(HERE, "shots"); GDIR = os.path.join(HERE, "out", "guide")
os.makedirs(GDIR, exist_ok=True)
for f in os.listdir(GDIR): os.remove(os.path.join(GDIR, f))

# First page of the staff PDF, as a picture for the guide.
subprocess.run(["pdftoppm", "-png", "-r", "110", "-f", "1", "-l", "1", "-singlefile",
                os.path.join(SHOTS, "staff_loading_details.pdf"), os.path.join(SHOTS, "50_staff_pdf_page")], check=True)

# (title, sample count, who, steps, rules, [(image, caption)])
SECTIONS = [
 ("Home screen", None, "Everyone. Money tiles only on the owner and accountant logins",
  ["Quick actions at the top. The owner gets + New load in the top bar; staff get + Truck (register a truck).",
   "Counts of loads at every stage. Tap a tile to see those loads.",
   "Red bar: loads changed by someone else since you last checked. Amber bar: trucks or sawmills still missing a document."],
  ["Staff do not see Planning, Truck fixed, freight, expenses, rates, bills or payments. The database does not send these to staff phones at all."],
  [("01_owner_home", "Owner login (Aditya and Bharat share it): quick actions, loads to check, pending documents"),
   ("02_owner_home_tiles", "Owner: loads by stage, freight and expenses this month, money to collect and pay"),
   ("20_staff_home", "Staff (Ravi): no Planning or Truck fixed, no money")]),
 ("1 · Planning", 5, "Owner login only",
  ["Tap + New load. Choose the buyer, destination and truck size, and write the reason (e.g. the buyer's order).",
   "Check which sawmills have wood: More → Mills → Ask mills about loads (ready WhatsApp message to each mill)."],
  ["Planning loads and their history are never shown to staff."],
  [("10_list_planning", "Loads in Planning"), ("11_load_planning", "A load in Planning")]),
 ("2 · Truck fixed", 5, "Owner login only",
  ["Edit the load: truck number, driver, transporter. Move to Truck fixed with a reason.",
   "Freight is entered on the owner login under Freight and expenses."],
  ["The app refuses to leave Planning without a truck number."],
  [("10_list_truck_fixed", "Loads with a truck fixed"), ("11_load_truck_fixed", "Truck and driver details")]),
 ("3 · Going to load: register the truck", 5, "Staff (or owner)",
  ["Tap + Truck. Enter the date, truck number, capacity, driver name and phone.",
   "Take the photo of the driver standing beside the truck. This is compulsory.",
   "Driving licence and C-Book are optional. When missing they show “Not Provided” in grey and do not stop you.",
   "Tap + Add sawmill for each sawmill the truck will load at, then + Add wood item: wood type, size (Small / Medium / Large), quantity and unit (CFT, CBM, RFT, SFT, Tons or Pieces), dimensions if known."],
  ["Without the driver photo the app shows a red “Driver photo with truck is mandatory.” and does not save.",
   "One truck = one trip, however many sawmills. A truck can also take its full load at a single sawmill."],
  [("21_register_missing_photo", "No photo yet: red warning, photo box highlighted, licence and C-Book “Not Provided”"),
   ("22_staff_sawmills", "Ravi's truck: two sawmills, three wood items, CFT and Pieces kept apart"),
   ("10_list_going_to_load", "Trucks going to the sawmills")]),
 ("4 · Under loading", 6, "Staff",
  ["When the truck reaches a sawmill, tap Truck reached on that sawmill. The load moves to Under loading and the time is recorded.",
   "Load at that sawmill, then go on to the next one and tap Truck reached there too.",
   "Owner login: set the purchase rate on each wood item. The sawmill's rate card for that date is suggested."],
  ["Under loading starts only when the truck has reached a sawmill.",
   "Staff never see rates or amounts."],
  [("10_list_under_loading", "Six trucks being loaded"),
   ("11b_load_under_loading_mills", "Owner's view: “Truck reached” time, wood items with purchase rate and amount")]),
 ("Piece tally: CFT from the piece count", None, "Staff at the sawmill, or in the office from the paper sheet",
  ["On a sawmill, tap + Piece tally. Mango is chosen; pick the thickness: 1\", 1.5\" or 2\".",
   "Each row is a length (1'6\" to 8'6\", with the paper style under it: 2.3 = 2'3\"), each column a width (4\" to 11\"). Type the count from the paper, or tap a box and use +1 / +5 / +10.",
   "The total updates as you type: pieces and CFT for Small, Medium and Large, and the CBM.",
   "Save: the app makes the Small, Medium and Large wood items for that sawmill, in CFT, with the piece count. To change them, open the tally again (a reason is asked)."],
  ["CFT = thickness × width × length × pieces ÷ 144, exactly as in the owner's Excel workbook. Checked against it: every sheet gives the same total, and the full truck comes to 1,350.00 CFT.",
   "Sizes for every wood: Small 1'6\" to 2'9\", Medium 3'0\" to 4'9\", Large 5'0\" and up.",
   "Counts stay on the phone if the signal drops before saving. After Loaded the tally is locked."],
  [("27_tally_screen", "New tally: wood, thickness, grid of length × width"), ("28_tally_grid", "Counts typed from the paper (the workbook's sheet 1-1)"),
   ("29_tally_summary", "Total: 477 pieces, 36.91 CFT, split by size"), ("30_load_with_tally", "Saved: the tally and its Small / Medium / Large items"),
   ("19b_sample_tally_summary", "A sample truck's tally")]),
 ("5 · Loading done and weigh slip at each sawmill", 5, "Staff",
  ["When loading finishes at a sawmill, tap Loading done here + weigh slip. Take the photo of that sawmill's weigh slip (net weight optional).",
   "Each sawmill has its own weigh-slip box. A second slip for the same sawmill can be added.",
   "When every sawmill is done, tap Move to: Loaded and enter the kata net weight for the whole truck."],
  ["Loaded is refused while any sawmill has no weigh slip or any wood item is not done.",
   "A slip is always linked to its own sawmill, so it cannot be filed under another one."],
  [("23_weigh_slips", "Weigh slips: one section per sawmill"),
   ("24_staff_after_loading", "Ravi's truck is Loaded"),
   ("10_list_loaded", "Loaded trucks")]),
 ("Loading document (PDF)", None, "Staff and owner",
  ["On the load page tap Export Staff PDF. It downloads a printable A4 document: TRUCK LOADING / DISPATCH DETAILS.",
   "Columns: Sl. No. · Saw Mill Name · Name of Product · Size · Quantity · Unit. The same sawmill appears on several rows when it has several wood items.",
   "Footer: Prepared by, driver and loading signatures, remarks."],
  ["The PDF never has rates, amounts, GST, freight, bank or payment details. It is not a tax invoice.",
   "Still to confirm with the owner: HSN, GSTIN, e-way bill number, driver photo and signature lines on this PDF."],
  [("25_staff_pdf_button", "Export Staff PDF on the load page"), ("50_staff_pdf_page", "The PDF for Ravi's truck (page 1)")]),
 ("6 · In transit", 6, "Accountant enters the e-way bill · Staff move the stage",
  ["Move to In transit. Tap Ask location to send the driver a ready WhatsApp message asking for his live location.",
   "Post driver updates (e.g. “crossed Nagpur”) on the load instead of calling the office."],
  [],
  [("10_list_in_transit", "Trucks on the road"), ("11_load_in_transit", "A truck in transit"),
   ("11b_load_in_transit_slips", "Its weigh slips, one per sawmill")]),
 ("7 · Delivered and billing", 20, "Accountant bills and records payments",
  ["When the party confirms unloading: Move to Delivered. The bill status becomes Ready to bill.",
   "Accountant: + Create bill (invoice number and date, sale quantity, rate, GST amount, credit days), then record payments."],
  ["Bill status moves by itself: Ready to bill → Billed → Payment pending (part paid or overdue) → Paid.",
   "GST in the sample is ₹0. The rate is for the accountant to confirm."],
  [("12_list_ready_to_bill", "Ready to bill (5)"), ("12_list_payment_pending", "Payment pending (5)"), ("12_list_paid", "Paid (5)"),
   ("13_load_payment_pending", "A part-paid bill"), ("31_accountant_billing", "Lakshmi bills a load and records a part payment")]),
 ("Freight and expenses", None, "Entered on the owner login only · Accountant can view",
  ["On a load: + Add expense. Choose the category (Truck Freight, Fuel, Toll, Hamali / Loading, Unloading, Weighbridge Charges, Other Travel Expenses), amount, who was paid, and the sawmill if it belongs to one. Add the receipt photo if there is one.",
   "More → Expenses shows the month by category and trip by trip."],
  ["Shared charges are not split between sawmills automatically.",
   "Receipts can only be opened on the owner and accountant logins."],
  [("14_expenses", "Expenses for the month"), ("40_owner_money_on_truck", "Freight and hamali on Ravi's truck"),
   ("11b_load_delivered_money", "Expenses on a delivered load")]),
 ("Sawmill rates", None, "Entered on the owner login only · Accountant can view",
  ["More → Sawmill rates. Choose a sawmill and tap + New rate: wood type, size, unit, rate and the date it starts.",
   "On a load, the rate in force on the load date is suggested for each wood item."],
  ["A new rate never changes rates already saved on past loads. The old rate stays in the history with who changed it and why."],
  [("15_rates", "A sawmill's current rates and its purchases and payments"), ("15b_rates_history", "Rate history"),
   ("40b_owner_rate_on_item", "Rate set on a wood item: 700 CFT × ₹350")]),
 ("Who changed what: red flags", None, "Everyone",
  ["Each person has their own “checked” point per load. A load nobody has opened yet shows blue; changes made by others after your check show red.",
   "Open the load: new entries are red in the history, with the exact time, the person and the reason. Tap Mark checked when done.",
   "The Updates screen lists every change across all loads."],
  ["Nobody can edit or delete the history. Money entries are visible only on the owner and accountant logins."],
  [("30_accountant_sees_staff_change", "Lakshmi opens Ravi's new truck"),
   ("42_accountant_red_flags", "After the owner adds freight and a rate, Lakshmi sees the load in red"),
   ("42b_accountant_red_history", "The red entries: who, when, what, why"),
   ("26_staff_history", "Staff see the same history without the money entries"),
   ("41_owner_updates_after", "Owner's Updates screen")]),
 ("Team and parties", None, "Owner login",
  ["More → Team: add staff (phone number login) and the accountant. One owner login is shared by Aditya and Bharat.",
   "Parties: what to collect from buyers and what to pay sawmills and transporters."],
  [],
  [("16_team", "Team"), ("17_parties_buyers", "Buyers to collect from")]),
]

used = set()
def card(img, cap):
    used.add(img)
    return f'<figure><img src="guide/{img}.jpg" alt="{html.escape(cap)}" loading="lazy"><figcaption>{html.escape(cap)}</figcaption></figure>'

parts = []
for title, n, who, steps, rules, imgs in SECTIONS:
    parts.append(f"""<section><h2>{html.escape(title)}{f' <span class="n">{n} sample loads</span>' if n else ''}</h2>
<p class="who"><b>Who:</b> {html.escape(who)}</p>
<ol>{''.join(f'<li>{html.escape(s)}</li>' for s in steps)}</ol>
{('<ul class="rules">' + ''.join(f'<li>{html.escape(r)}</li>' for r in rules) + '</ul>') if rules else ''}
<div class="shots">{''.join(card(i, c) for i, c in imgs)}</div></section>""")

for img in sorted(used):   # 2x phone screens → 520 px wide JPEGs (shown at 260 px)
    im = Image.open(os.path.join(SHOTS, img + ".png")).convert("RGB")
    if img.startswith("50_"):   # PDF page: keep the printed part (ignore the empty lower half and the page footer)
        from PIL import ImageOps
        top = im.crop((0, 0, im.width, int(im.height * .8)))
        box = ImageOps.invert(top.convert("L")).point(lambda v: 255 if v > 20 else 0).getbbox()
        im = im.crop((max(0, box[0] - 30), max(0, box[1] - 30), min(im.width, box[2] + 30), min(im.height, box[3] + 40)))
    w = 520 if not img.startswith("50_") else 700
    im.resize((w, round(im.height * w / im.width)), Image.LANCZOS).save(os.path.join(GDIR, img + ".jpg"), quality=82, optimize=True)

page = f"""<!DOCTYPE html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex"><title>Aditya Traders · How each stage works</title>
<style>
body{{margin:0;background:#f4f1ec;color:#1f1a15;font:16px/1.5 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}}
header{{background:#1b4332;color:#f4f1ec;padding:22px 16px}}header h1{{margin:0 0 4px;font-size:24px}}header p{{margin:0;opacity:.9}}
main{{max-width:1100px;margin:0 auto;padding:12px}}
.try{{background:#f3b733;border-radius:14px;padding:14px 16px;margin:12px 0;display:flex;gap:12px;align-items:center;flex-wrap:wrap}}
.try a{{background:#1b4332;color:#fff;text-decoration:none;font-weight:700;padding:10px 16px;border-radius:10px}}
section{{background:#fff;border:1px solid #e6dfd5;border-radius:14px;padding:16px;margin:14px 0}}
h2{{margin:0 0 6px;font-size:20px}}.n{{font-size:13px;background:#efe9e2;border-radius:999px;padding:2px 9px;vertical-align:middle;color:#5b4a3a}}
.who{{margin:0 0 6px;color:#6d4220}}ol{{margin:6px 0;padding-left:22px}}li{{margin:3px 0}}
.rules{{background:#fdecea;border-radius:10px;padding:8px 10px 8px 28px;color:#7f1d1d;margin:8px 0}}
.shots{{display:flex;gap:14px;overflow-x:auto;padding:8px 2px 4px}}
figure{{margin:0;flex:0 0 260px}}figure img{{width:260px;border-radius:12px;border:1px solid #e6dfd5;display:block;background:#eee}}
figure:has(img[src*="50_"]){{flex-basis:350px}}figure img[src*="50_"]{{width:350px}}
figcaption{{font-size:13.5px;color:#6b6058;margin-top:6px}}
table{{border-collapse:collapse;width:100%;font-size:15px}}td,th{{border-bottom:1px solid #e6dfd5;padding:7px 6px;text-align:left;vertical-align:top}}
footer{{text-align:center;color:#6b6058;font-size:13px;padding:16px}}
</style></head><body>
<header><h1>How each stage works</h1><p>Aditya Traders app 3.3 · sample data · who does what at every stage</p></header>
<main>
<div class="try"><span style="flex:1;min-width:200px"><b>Try it yourself.</b> The demo has the same sample loads. Switch between Owner, Accountant and Staff at the top and watch each other's changes turn red.</span><a href="./">Open the demo</a></div>
<section><h2>The people in the sample</h2><table>
<tr><th>Login</th><th>Who</th><th>Can do</th></tr>
<tr><td>Owner</td><td>Aditya and Bharat (one shared login)</td><td>Everything: Planning, Truck fixed, sawmill rates, freight and other charges, bills, payments, team and settings</td></tr>
<tr><td>Accountant</td><td>Lakshmi</td><td>Bills, payments and balances. Can view rates and expenses but not enter them</td></tr>
<tr><td>Staff</td><td>Ravi, Suresh, Prasad, Naidu, Kiran, Srinu, Raju, Venkat, Murali, Gopi</td><td>Register trucks, sawmills, wood items, piece tallies, weigh slips, loading PDF, stage moves, updates. Never Planning, Truck fixed or any money</td></tr>
</table><p style="margin:8px 0 0;font-size:14px;color:#6b6058">All names, sawmills, buyers, rates and amounts are invented sample values. The sample was made by running every step as these people through the real database rules, 1 to 26 Nov 2026. Sample photos and weigh slips are placeholder pictures marked SAMPLE.</p></section>
{''.join(parts)}
</main><footer>Aditya Traders · app version 3.3 · sample walkthrough</footer></body></html>"""
open(os.path.join(HERE, "out", "guide.html"), "w", encoding="utf-8").write(page)
print("guide built:", len(used), "pictures")
