# Aditya Traders: loads app (version 2.1, 26 Nov 2026)

One place for every load. It replaces phone calls and WhatsApp messages between owner, staff and accountant: **each change records what changed, who made it, the exact time (to the second), why, and the load's stage at that moment.** Anything changed since you last checked shows in red.

- **App:** `apps/aditya/index.html`. Plain HTML/CSS/JS, phone-first. Published at https://krishnasai-pentakota.github.io/aditya/
- **Database:** Supabase project `aditya-traders` (Mumbai). The schema and security rules are in `docs/aditya-app/supabase/`; version 2 is `007_v2_loads.sql`, `008_lock_size_grade_fn.sql`, `009_qty_summary_format.sql` and `010_net_weight.sql`. The database enforces every rule below, not just the screens.
- **Login service:** the Supabase function `team-admin` (`docs/aditya-app/supabase/functions/team-admin/index.ts`) lets the owner or accountant create logins from inside the app.
- **Demo with sample data:** https://krishnasai-pentakota.github.io/aditya/demo/ and its walkthrough: https://krishnasai-pentakota.github.io/aditya/demo/guide.html
  - The demo is the real app page plus a small in-browser backend (`docs/aditya-app/demo/demo_backend.js`) that copies the database rules. Changes stay on that phone; **Reset** restores the sample.
  - Sample data (58 loads, 5–6 at every stage, 718 history entries by owner, accountant and 7 staff) is made by `make_sample.py`, which runs every step through the real migrations on a local Postgres. Rebuild: `make_sample.py` → `build_demo.py` → `build_guide.py`; test: `test_demo.py`.
- **Tests:** `docs/aditya-app/tests/`
  - 101 database checks: the real migrations on a local Postgres.
  - 71 browser checks: the real page, supabase-js and database through a local stand-in, on a phone-sized screen.

## What it does
- **Loads:** each truck is one load (L-0001…). It records date, truck number, 30/35 T or other, **kata (weighbridge) net weight in tons** (asked when moving to Loaded; shown as “34.6 T of 35 T”), driver and phone, transporter, freight, buyer, destination and state (any state), e-way bill and notes.
- **Truck stage:** Planning → Truck fixed → Going to load → Under loading → Loaded → In transit → Delivered (or Cancelled). Every move needs a reason.
  - The truck number is needed before the load leaves Planning.
  - **Loaded** needs every mill line marked done.
  - After Loaded, mill lines can't be added, removed or re-opened.
- **Mill lines:** one load can fill from several mills. Each line has the mill, wood, unit, quantity, length, size grade and status (planned / loading / done).
  - Units: CFT, CBM, Pieces, Tons, Quintal, Kg, Running ft, Sq ft.
  - Size grade is set from length: Small < 4 ft, Medium 4–6 ft, Large > 6 ft. These limits are **provisional** and can be changed in Settings.
  - A fill bar compares CFT with the owner's rough guide (about 1,150 CFT for 30 T, 1,350 CFT for 35 T). The guide is never used in money.
- **Purchase rate per mill line** (owner and accountant only): amount = quantity × rate ± adjustment. The app suggests the mill's last rate.
- **Freight and costs:** hamali, weighbridge, permit and others. Everyone can see these (owner's decision).
- **Billing** (owner and accountant only):
  - Each bill has invoice no and date, sale quantity, rate, adjustment and GST.
  - Invoice total = qty × rate ± adjustment + GST.
  - Due date = invoice date + credit days (the bill's own, else the buyer's, else 30).
  - Bill status: Not ready → Ready to bill (once delivered) → Billed → Payment pending (part paid or overdue) → Paid.
- **Payments:** money received from buyers, and money paid to mills and transporters (cash, UPI, bank, cheque), each with a reference.
- **Parties:**
  - Buyers to collect from; mills and transporters to pay.
  - Each one has a page with its loads, payments, balance, and a WhatsApp reminder link.
- **Mills:** the mill list grouped by area. "Ask mills about loads" opens a ready WhatsApp message for each mill.
- **Updates and history:**
  - Anyone can post an update on a load. Owner and accountant can also post admin-only ones.
  - The Updates screen shows every change across all loads.
  - Nobody can edit or delete history.
- **Red flags:** each person has their own "checked" time for each load.
  - A load that others changed since then shows **Changed** in red, with how many changes; those entries are red in the history.
  - Your own changes never flag you.
- **Ask location:** one tap sends the driver a ready WhatsApp message asking for his live location.
- **Photos:** kata slip, receipt, invoice, e-way bill, LR and loading photos. They are shrunk before upload and kept private behind signed links.
- **Excel export** for a date range:
  - Everyone gets Loads, Mill lines, Costs and History.
  - Owner and accountant also get prices, bill columns, Payments and Balances.
- **Weak signal:**
  - If the signal drops while the app is open, the last loaded list stays visible.
  - A new-load form is kept as a draft.

## Look
Paper-and-forest design (warm paper background, serif headings and numbers, forest-green money tiles, pill buttons, initial avatars), adapted from the “TimberTrack” prototype built with Grok. Only the look and two ideas (Ask location, kata net weight) were taken; its data model and PIN logins were not.
Fonts (Fraunces, Outfit) load in the background; on weak signal the phone's own fonts are used.

## Who can do what
Owner and accountant have the same full access (owner's answer, 26 Nov).

| | Owner / Accountant | Staff |
|---|---|---|
| See and edit loads, mill lines, freight, costs, photos, updates | ✓ | ✓ |
| Move the stage (with a reason) | ✓ | ✓ |
| See purchase rates, sale rates, bills, payments, balances | ✓ | never |
| Admin-only history and updates | ✓ | never |
| Delete loads, remove photos | ✓ | |
| Add people, approve or block them, set roles, reset passwords | ✓ | |
| Change size-grade limits | ✓ | |

## Adding people
- The owner's account already exists. If ever needed, the first account is created in Supabase → Authentication → Users → Add user, with **Auto Confirm User** ticked. The first account becomes owner automatically.
- Everyone else is added in the app:
  1. Open **More → Team → Add a person** and enter their name and **phone number** (or email for the accountant).
  2. Set a password and a role. They can sign in straight away.
- Staff sign in with their phone number.
- **Block** removes access at once; **Set password** resets a forgotten one.

## Not done yet
- **CFT calculation:** waiting for the client's Excel template. CFT is typed in by hand.
- **Automatic WhatsApp messages:** these need the WhatsApp Business Platform (about ₹0.15 per utility message). The app has tap-to-send links for now.
- **Opening the app with no signal at all:** reloading the page offline needs a service worker, which is not added yet.

## Updating
Edit `apps/aditya/index.html` and push to `main`. The site rebuilds in about 2 minutes. For database changes, add a numbered SQL file and run both test suites first:
- `docs/aditya-app/tests/db/test_db.py`
- `docs/aditya-app/tests/e2e/test_app.py`
