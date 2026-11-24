# Aditya Traders: lorry trips app (version 1.3)

A mobile web app for Aditya Traders. It records lorry trips and their costs, and **flags edits in red** so the accountant sees what changed without being told.

- **App:** `apps/aditya/index.html`, plain HTML/CSS/JS. The site build copies it as-is to https://krishnasai-pentakota.github.io/aditya/
- **Database:** Supabase project `aditya-traders` (Mumbai). The schema and security rules are in `docs/aditya-app/supabase/` (001 to 005).
- **Demo (no login, sample data):** https://krishnasai-pentakota.github.io/aditya/demo/ (built from the real page by `docs/aditya-app/demo/build_demo.py`; rebuild it after changing the app).
- **Login:** email and password. Only people the owner approves can see or change anything (enforced by Row-Level Security in the database).

## What version 1 does
- **Lorries:** date, vehicle number, 30/35-ton size, driver name and phone, transporter, sawmill, wood, CFT, net weight, lorry hire, party, destination, status (order taken / on the way / completed) and notes.
- **Costs:** add, change or remove cost lines (hamali, weighbridge, permit and so on) at any time. The app shows the total for each lorry.
- **Edit flags:**
  - Each person has their own "checked" mark on each lorry.
  - A lorry that someone else changed after you checked it shows **Edited** in red.
  - The lorry's page shows the old values in red.
  - "Mark as checked" clears the flag.
- **History:** every add, change and delete is recorded with who made it and when. Nobody can edit or delete the history.
- **Excel export:** for a date range, with three sheets: Lorries, Costs and Changes.
- **WhatsApp:** share a summary of any lorry.
- **Photos and files (1.2):** attach the weighbridge (kanta) slip, receipts, invoices and other photos to a lorry. Photos are shrunk before upload and kept private. Adding one shows the red flag to others.
- **Purchase and sale price (1.3), owner only:** rate, basis (per CFT / per ton / per lorry), amount and note, for both purchase and sale. The database hides these from the accountant and staff, and they are kept out of the shared history. The owner's Excel export adds a Prices sheet. Amounts are typed in, not calculated.
- **Weak signal:**
  - The last list stays viewable when there's no signal.
  - A new-lorry form is kept as a draft if saving fails.

## Not in version 1 (waiting on the client)
- **CFT calculation:** waits for the client's Excel template (spec Q-01). CFT is typed in by hand for now.
- **Payment reminders and sawmill rates:** waiting for the questionnaire answers.
- **WhatsApp location-tracking bot:** proposed, not yet agreed.

## Adding a person
1. In the Supabase dashboard, open **Authentication → Users → Add user → Create new user**. Enter their email and a password, and tick **Auto Confirm User**.
2. **The very first account becomes the owner automatically.** Everyone after that waits for approval.
3. The owner opens **Menu → Team** in the app, taps **Approve**, and sets their role (owner, accountant or staff).

## Who can do what (version 1.3)
The accountant may not change costs (owner's answer, 24 Nov). The database enforces this.

| | Owner | Accountant | Staff |
|---|---|---|---|
| See all lorries and history | ✓ | ✓ | ✓ |
| Add or edit lorries | ✓ | ✓ | ✓ |
| Add or change costs (cost lines, lorry hire) | ✓ | | ✓ |
| Add photos and files | ✓ | ✓ | ✓ |
| Remove photos and files | ✓ | | |
| See and change purchase/sale price | ✓ | | |
| Delete a lorry | ✓ | | |
| Approve people and set roles | ✓ | | |

## Updating the app
Edit `apps/aditya/index.html` and push to `main`. The site rebuilds and publishes in about 2 minutes.
