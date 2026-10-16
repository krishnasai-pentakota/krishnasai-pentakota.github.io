# Portfolio — Krishna Sai Pentakota

**Live:** <https://krishnasai-pentakota.github.io/>

A cinematic, streaming-style portfolio. The opening screen asks *Who's here?* and offers
five roles. Each role has its own page: a banner with the lead project, then rows of
project tiles with dashboards, KPIs and links.

| Role | What's inside |
|---|---|
| **Factory** | Systems built inside a ribbon manufacturer: weaving intelligence, sales analytics, warehouse 3D map, store inventory, meeting builder, ERP bridge |
| **Hire me** | Resume (prints to A4), a cover letter that fills in for your role, email and GitHub |
| **Client work** | Freelance builds: TimberTrack, the clinic website, the cable/DTH WhatsApp bot |
| **FDE Lab** | Public case-study repos and the Forward Deployed Engineer program projects |
| **Studio** | Films, animated HTML slideshows and posters (demos use sample names) |

## How it's built

```
content/*.yaml    → validate (Pydantic) → render (Jinja) → dist/*.html
styles/site.css   → Tailwind (standalone binary, no Node) → dist/static/css/site.css
static/           → copied as-is (JS, images, demos, vendor libraries) → dist/static/
push to main      → GitHub Actions: tests → build → publish to GitHub Pages
```

Python only runs at build time. Visitors get plain HTML, CSS and a little JavaScript, with
no frameworks or libraries to download. The opening screen goes straight to the five roles.
Coming next: a short intro video of Krishna walking out of a computer screen with a suitcase.

## Updating it

See **[docs/daily-updates.md](docs/daily-updates.md)**: edit a project's `.yaml` file
(on github.com or locally), push, and the site rebuilds in about 2 minutes. A failed
check never reaches the live site.

## Running it locally (Windows, PowerShell)

Needs Python 3.11 or newer (`py --version`).

```powershell
git clone https://github.com/krishnasai-pentakota/krishnasai-pentakota.github.io portfolio
cd portfolio
py -3.12 -m venv .venv
.venv\Scripts\Activate.ps1          # if blocked: Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
pip install -r requirements.txt
python build.py                     # first run downloads Tailwind once
python -m http.server 8000 --directory dist    # then open http://localhost:8000
python -m pytest -q                 # the 58 checks
python tools/check_layout.py        # optional: real-browser check, every page at 3 widths
                                    # (needs: pip install playwright; playwright install chromium)
```

You can also double-click `dist/index.html`: every page works straight from disk.

## Folder map

| Path | What it is | Edit it? |
|---|---|---|
| `content/profile.yaml` | Name, headline, email, GitHub, LinkedIn | Yes |
| `content/roles.yaml` | The five roles: names, taglines, icons, colours | Rarely |
| `content/projects/*.yaml` | One file per project; file name = project id | Yes, often |
| `content/resume.yaml` | Resume: summary, jobs, skills, education | Yes |
| `content/testimonials/*.yaml` | Client quotes (only `verified: true` with a source show) | Yes |
| `static/img/` | Screenshots and covers (WebP) | Yes |
| `static/demos/` | Playable Studio demos | Yes |
| `static/js/site.js` | Rows, quick look, menu, cover letter | Rarely |
| `styles/site.css` | Design tokens and components (Tailwind source) | When the look changes |
| `templates/` | Page layouts (Jinja) | When the structure changes |
| `portfolio/` | The content rules (`models.py`), loader and renderer | When a rule changes |
| `tests/` | The checks that gate every deploy | With every rule change |
| `docs/` | Learning notes per layer, the tracker, the daily-update guide | — |

## What the build refuses, and why

| Rule | Why it exists |
|---|---|
| Unknown field (e.g. `sumary:`) | Typos would otherwise vanish silently |
| A link that isn't a real `https://` URL | No dead buttons |
| `metrics` on a `concept` or `in_progress` project | Results only exist for work that exists; use `goal` for targets |
| A metric without `evidence` | Every number has a source you can open in an interview |
| `implemented`/`delivered` with no link and no `proof_note` | Shipped work is either checkable or says where it runs |
| Delivered client or studio work without `my_role` | People want to know what *you* did |
| A screenshot without `alt` text, or a path outside `static/` | Accessibility, and paths that work on GitHub Pages |
| More than one featured project per role | One banner per role page |
| `[placeholder]`, `TODO` or `TBD` in the resume or a case study | Half-finished lines never reach a recruiter |
| The employer's name on a Factory page | Factory pages say "a ribbon manufacturer"; the name stays on the resume |
| Real names in a Studio demo | Demos use sample names and amounts |
| A template typo like `{{ profile.nmae }}` | StrictUndefined fails the build instead of shipping a blank |

Statuses: `implemented` · `delivered` · `in_progress` · `prototype` · `concept`.

## Layers

- [x] **L0 Skeleton:** content models, loader, page template, build script, tests
- [x] **L1 Shell:** Tailwind (pinned standalone binary), mobile menu, reduced-motion fallbacks
- [x] **L2 Interactions:** sideways rows, quick-look dialog, project pages, printable resume
- [x] **L3 Five roles:** role picker, Netflix-style role pages, real dashboard screenshots, Hire me, cover letter, Studio demo
- [x] **L4 Ship:** GitHub repo, Actions (test → build → publish), privacy guards, phone layout check
- [ ] **Next:** intro video (walking out of a screen with a suitcase), more case studies (clinic, sales, store system), Sri Veda film on YouTube, warehouse 3D demo on generated data

Tracker with hours and done-criteria: `docs/tracker.csv`. Learning notes: `docs/layer-0-notes.md` to `docs/layer-3-notes.md`.
