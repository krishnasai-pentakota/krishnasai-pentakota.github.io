# Updating the portfolio day by day

The live site is <https://krishnasai-pentakota.github.io/>. It rebuilds itself every time
something is pushed to the `main` branch: GitHub runs the tests, builds the pages and
publishes them, usually within 2 minutes. If a check fails, nothing is published and the
old version stays live, so a typo can never break the site.

## Three ways to update

**1. Tell Claude what you finished.** For example: "Finished the store inventory return-note
screen today; 3 people use it." Claude edits the right file, runs the checks and pushes.

**2. Edit on github.com (works on your phone).**

1. Open the repo, go to `content/projects/`, open the project's `.yaml` file.
2. Click the pencil icon, change the text, then **Commit changes** (straight to `main`).
3. Watch the **Actions** tab: green tick = live in about 2 minutes; red cross = click it to
   read which file and which line the check refused. Fix and commit again.

**3. On your laptop.**

```powershell
git pull
# edit files in content/
python build.py --check      # 1 second: is the content valid?
python -m pytest -q          # optional: the full checks
git add -A
git commit -m "Store inventory: return notes in use"
git push
```

## What to change for the usual updates

| You did this | Change this in the project's `.yaml` |
|---|---|
| Worked on it today | `updated: 2026-10-17` (puts a "New this week" badge on the tile for 7 days) |
| It moved forward | `status:` concept → in_progress → prototype → implemented (client work: delivered) |
| You have a number to show | add under `metrics:`, with `evidence:` saying where you can open and show it |
| You took a screenshot | save it as `static/img/<project>/<name>.webp`, add it under `screenshots:` with `alt:` |
| There's a public link | add under `links:` with `type: live` (dashboard), `code` (repo), `video` or `doc` |
| A brand new project | copy a similar file in `content/projects/`, rename it, pick `kind:` (factory, client, lab or studio) |

Statuses that can show results (`metrics`): implemented, delivered, prototype.
Planned work (`concept`) and work in progress can only state a `goal`.

## Before anything goes public

- Factory pages say "a ribbon manufacturer". The employer's name stays on the resume and
  LinkedIn. A test fails the build if MISO, Ribest or YAMA appears on a Factory page.
- Screenshots of company dashboards: aliases for customers and staff, no real names.
- Studio work for clients: ask the client first, or use the demo version with sample names.
