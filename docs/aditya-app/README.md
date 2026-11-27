# Aditya Traders: loads app (version 3.3, 26 Nov 2026)

One place for every truck load. Phone calls and WhatsApp messages between the owner, staff and accountant are replaced by one record per load. **Each change records what changed, who made it, the exact time (to the second), why, and the load's stage at that moment.** Anything changed since you last checked shows in red.

## Where things are

- **App:** `apps/aditya/index.html`. Plain HTML/CSS/JS, phone-first. Published at https://krishnasai-pentakota.github.io/aditya/
- **Database:** Supabase project `aditya-traders` (Mumbai).
  - Schema and security rules are in `docs/aditya-app/supabase/`.
  - Version 3 adds `011_master_prompt.sql`, `012_reached_and_slips.sql` and `013_tally.sql` (piece tally).
  - The database enforces every rule below, not just the screens. Money is never sent to staff phones.
- **Login service:** the Supabase function `team-admin` (`docs/aditya-app/supabase/functions/team-admin/index.ts`). The owner creates logins and sets permissions from inside the app.
- **Demo with sample data:** https://krishnasai-pentakota.github.io/aditya/demo/
  - Walkthrough: https://krishnasai-pentakota.github.io/aditya/demo/guide.html
  - The demo is the real app page plus a small in-browser backend (`docs/aditya-app/demo/demo_backend.js`) that copies the database rules. Changes stay on that phone; **Reset** restores the sample.
  - The sample has 53 loads, 5–6 at every stage and 20 delivered. `make_sample.py` builds it by running every step as the owner, the accountant and 10 staff through the real migrations.
  - Rebuild: `make_sample.py` → `build_demo.py` → `test_demo.py` → `build_guide.py`.
- **Tests:** `docs/aditya-app/tests/`
  - `db/test_db_v3.py` (130 checks) and `db/test_db_tally.py` (51 checks, using the piece counts from the owner's Excel workbook): run the real migrations on a local Postgres.
  - `e2e/test_app_v3.py` (59 checks) and `e2e/test_app_tally.py` (33 checks). Uses the real page and supabase-js, with the database reached through a local stand-in, on a phone-sized screen. Covers the 10 acceptance tests of the master requirements.

## Who can do what

There is one **owner** login, shared by Aditya and Bharat.

| | Owner | Accountant | Staff |
|---|---|---|---|
| Planning, Truck fixed, Cancel | ✓ | | never (not even sent to the phone) |
| Register a truck, sawmills, wood items, weigh slips, stage moves, updates | ✓ | ✓ | ✓ |
| Export the loading PDF (no money in it) | ✓ | ✓ | ✓ |
| Enter sawmill rates and item rates | ✓ | view only | never |
| Enter freight and other charges, receipts | ✓ | view only | never |
| Bills, payments, balances | ✓ | ✓ | never |
| Money entries in the history | ✓ | ✓ | never |
| Team, permissions, settings | ✓ | | |

Permissions are flags on each person: plan, finance, rates, expenses, people. The owner has all of them, and the accountant has finance by default. A flag can be given to another person later from **More → Team** without changing the database.

## How a load moves

1. **Planning** (owner): buyer, destination, truck size, reason.
2. **Truck fixed** (owner): truck number, driver, transporter.
3. **Going to load**. Staff tap **+ Truck** to register a truck:
   - Truck number, capacity (tons and CFT), driver name and phone.
   - The **photo of the driver beside the truck is compulsory**. Without it a red warning is shown and nothing is saved.
   - Licence and C-Book are optional; when missing they show "Not Provided".
4. **+ Add sawmill** for each sawmill (sawmill name, sawmill owner name and party name are kept separately). Then **+ Add wood item**:
   - Wood type from the saved list (Country Wood, Acacia, Teak, Other…).
   - Size: Small / Medium / Large, chosen by hand (Small 1'6"–2'9", Medium 3'0"–4'9", Large 5'0" and longer, for every wood).
   - Quantity and unit: CFT, CBM, RFT, SFT, Tons or Pieces, plus pieces count and dimensions.
   - Different units are never added together.
5. **Under loading** starts when staff tap **Truck reached** on a sawmill. The arrival time is recorded.
6. At the end of loading at each sawmill, staff tap **Loading done here + weigh slip** and take the slip photo; net weight is optional. A truck may take its full load at one sawmill.
7. **Loaded** asks for the kata net weight of the whole truck. It is refused while any item is open or any sawmill has no weigh slip; this weigh-slip rule can be switched off in Settings.
8. **In transit**: tap Ask location to send the driver a ready WhatsApp message. **Delivered** then opens billing.

## Piece tally (Mango and other wood counted piece by piece)

Taken from the owner's Excel workbook (`aditya_tradersmodel_sheets.xlsx`, 26 Nov 2026).

- On a sawmill, tap **+ Piece tally**. Choose the wood and the thickness (1", 1.5" or 2").
- Type or add (+1, +5, +10, −1) the piece count in the box for each length (down, 1'6" to 8'6" in 3-inch steps, written as on the paper: 2.3 = 2'3") and width (across, 4" to 11"). The grid size can be changed in Settings.
- The database works out **CFT = thickness (in) × width (in) × length (ft) × pieces ÷ 144**, exactly as the workbook (no rounding inside), and makes one wood item per size: Small, Medium, Large, in CFT with the piece count. CBM is shown as CFT ÷ 35.3147.
- Items made by a tally change only through the tally; a change needs a reason and is kept in the history. After Loaded the tally is locked.
- Unsaved counts stay on the phone if the signal drops.
- The workbook's own mistakes are not copied (1-inch rows of 9 ft and longer counted as 1.5 inch; 3-inch widths left out of the piece count).
- The loading PDF and the Excel export include the tally (pieces and CFT by thickness and size; no money).

## Money (owner and accountant)

- **Sawmill rates:** rate cards per sawmill (wood, size or any, unit, rate, effective date).
  - A new rate never changes rates saved on past loads.
  - The history keeps who changed it, when and why.
- **Item rates:** amount = quantity × rate ± adjustment. The rate card in force on the load date is suggested.
- **Freight and expenses:** categories are Truck Freight, Fuel, Toll, Hamali / Loading, Unloading, Weighbridge Charges and Other Travel Expenses.
  - Each entry can be linked to one sawmill and can have a receipt photo.
  - Shared charges are not split automatically.
- **Billing:**
  - Invoice total = qty × rate ± adjustment + GST.
  - Due date = invoice date + credit days.
  - Bill status: Ready to bill → Billed → Payment pending → Paid.
- **Payments and balances:** from buyers, to sawmills and to transporters.

## Loading PDF

**Export Staff PDF** on the load page downloads an A4 document, TRUCK LOADING / DISPATCH DETAILS.

- Columns: Sl. No. | Saw Mill Name | Name of Product / Wood Details | Size | Quantity | Unit.
- It is built from a list of permitted fields, so it never contains a rate, amount, GST, freight, bank or payment detail.
- It is not a tax invoice.

## Adding people

- Open **More → Team → Add a person**. Choose Staff, Accountant or Owner, enter the name and phone number (or email), set a password, and tick any extra permissions.
- Staff sign in with their phone number.
- **Block** removes access at once.
- **Set password** resets a forgotten password. Only the owner can reset the owner's password.

## Still to confirm with the owner

- **Loading PDF:** HSN, GSTIN, e-way bill number, driver photo, receiver signature.
- **Weigh slips:** which fields to capture (gross, tare, net, weighbridge, slip number), and whether a separate final truck slip is needed.
- **Rates:** the basis for each wood (per CFT, CBM, ton or piece).
- **Shared charges:** how freight and other shared charges are split between sawmills.
- **Staff corrections:** whether staff may change entries after Loaded.
- **Thickness:** which other thicknesses are bought, besides 1", 1.5" and 2".
- **Other open items:** a cleaned-up Excel tally template for the sawmills, automatic WhatsApp messages (needs the WhatsApp Business Platform), and opening the app with no signal at all.

## Updating

1. Edit `apps/aditya/index.html` and push to `main`. The site rebuilds in about 2 minutes.
2. For database changes, add a numbered SQL file.
3. Run both test suites before pushing either kind of change.
