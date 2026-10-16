# Layer 2 notes — pages, quick look, shelves, resume

## What changed

```
content/projects/*.yaml ──► index.html               (cards, shelves, quick-look templates)
                        └─► work/<id>.html           (only for projects that earn a page)
content/resume.yaml     ──► resume.html              (prints to A4 / saves as PDF)
```

- New content fields: `case_study` (problem, steps, decisions, outcome, next) and `flow`
  (the pipeline drawn on the page). The weaving audit has the first full case study.
- New file `content/resume.yaml`. Name, headline and contact details come from `profile.yaml`.
- New project: TimberTrack. Name order is now "Krishna Sai Pentakota" (one-line change in profile.yaml).
- 41 tests, up from 29.

## Block 1 — one build, many pages (`render.py: write`)

Every page is written by one small function. It works out two values from where the page sits:

| Page | `root` (for assets) | `home` (for section links) |
|---|---|---|
| `index.html` | `""` | `""` → `#featured` |
| `resume.html` | `""` | `index.html` → `index.html#featured` |
| `work/weaving-audit.html` | `../` | `../index.html` → `../index.html#featured` |

**Why not `/#featured`?** A leading slash means "the domain root". On
`username.github.io/portfolio/`, `/` is the wrong folder, and on your disk it's the drive
root. And why `../index.html` instead of `../`? On disk, `../` opens a folder listing; GitHub
Pages would serve `index.html`, but your laptop wouldn't.

## Block 2 — pages are earned, not automatic (`models.py: has_page`)

```python
return bool(self.case_study or self.highlights or self.metrics)
```

A project with only a summary gets no page, because the card already says everything.
A thin page looks worse than no page. When a lab project ships and you add highlights,
its page appears by itself on the next build. No template change needed.

## Block 3 — one rule, inherited everywhere (`models.py: Prose`)

`CaseStudy`, `Job`, `Resume` and friends all inherit from `Prose`. Its single validator
walks every string in the model and refuses `[one line on ...]`, `TODO` or `TBD`. Your resume
doc still has those placeholders for TCS and Oliveboard. They can't reach a recruiter now.

Database parallel: this is like a `CHECK` on a *domain type*. Define it once, and every column
of that type gets the rule.

## Block 4 — quick look is a native `<dialog>` (`site.js: initQuickLook`)

`dialog.showModal()` gives you, free from the browser:

- **Focus moves inside**, and Tab can't escape to the page behind.
- **The page behind becomes inert**: you can't click or tab to it.
- **Escape closes it.**

What we add ourselves:

- **Focus goes back to the button that opened it** (`opener.focus()` in the `close` handler).
- **A backdrop click closes it.** A click on the dim area lands on the `<dialog>` element itself.
- **`aria-labelledby` points at the project title,** so a screen reader announces the
  project's name.
- **No page scroll behind it:** `html:has(.quick-look[open]) { overflow: hidden }`, pure CSS.

**Why `<template>` + `cloneNode` and not JSON + `innerHTML`?** The detail markup is
rendered by Jinja at build time, escaped like everything else. `<template>` content is inert
(not shown, not focusable, not read aloud) until cloned. So the browser never parses an HTML
string built in JavaScript, which is the classic cross-site-scripting hole.

## Block 5 — shelves (`site.js: initShelves`)

- **Plain CSS does the scrolling:** `overflow-x: auto` + `scroll-snap-type: x mandatory`.
  Touch, trackpad and keyboard all work natively, and the mouse wheel is never hijacked.
- **One press moves as many whole cards as fit,** measured from the real card width and
  gap, so it's right on a phone and on a 1440px screen.
- **Buttons only appear when something overflows.** At 1440px three cards fit, so the
  buttons stay hidden.
- **`aria-disabled` instead of `disabled`:** a `disabled` button drops focus when you reach
  the end, throwing keyboard users back to the top of the page. `aria-disabled` keeps focus
  where it is and just ignores the press.

## Block 6 — progressive enhancement, enforced by a test

Quick look, print and shelf buttons ship with `hidden` and only appear when `site.js` runs.
Without JavaScript, the visitor gets cards and page links: less fancy, never broken.
`test_quick_look_has_a_template_for_every_button` fails the build if a JS-only button ever
ships visible.

## Block 7 — print CSS

- `@media print` flips the colour tokens to ink-on-paper for **every** page. Browsers drop
  dark backgrounds when printing, so without this you'd print white text on white paper.
- The resume sheet looks the same on screen and on paper, plus
  `@page { size: A4; margin: 12mm 14mm }`, plus `break-inside: avoid` so a job never splits
  across pages.

## Block 8 — the link crawler test

`test_no_dead_links_on_any_page` parses every built page, resolves each relative link from
*that page's* folder, and checks that the file exists and the `#anchor` id exists in it.

**Proving a test works:** I broke one link on purpose (`#weaving-audit-typo`). The test
failed and named the page and the anchor. Then I restored it. A test you've never seen fail
might not be testing anything.

## Things the build and browser checks caught this layer

1. `org: Tata Consultancy Services (client: Microsoft)` → **not valid YAML**. Same `: ` trap
   as Layer 0. The fix is quotes. That's the third time, so it's worth remembering.
2. Six numbers on the case page wrapped five-plus-one. The fix is "at most three across",
   using `minmax(max(150px, calc((100% - 20px) / 3)), 1fr)`.
3. The resume's bullet points had no bullets. Tailwind's reset sets `list-style: none` on
   every list, so they had to be turned back on for the resume.
4. The ribbon tab in the quick look was invisible: the panel had no `data-kind`, so the
   `--ribbon` colour variable was undefined, and an undefined variable silently draws nothing.

## Exercises

1. In `weaving-audit.yaml`, add `TODO` to the end of any decision's `why`. Run
   `python build.py --check` and read the message. Remove it.
2. Write a `case_study:` for the sales dashboard: problem, 3–4 steps, 2 decisions. Rebuild.
   The card's link changes from "See project details" to "Read the case study" by itself.
   Why? (Look at `page_link_label` in `_macros.html`.)
3. Open `resume.html`, press Ctrl+P, and look at the preview. Then fill in one real TCS
   bullet in `resume.yaml` and print again.

## Interview questions this layer prepares you for

- *Why use a native `<dialog>` instead of a styled `<div>` for a modal?*
- *When would you use `aria-disabled` instead of `disabled`?*
- *How do you make sure a test actually tests something?*
- *How do you keep a static site working at a subpath like `/portfolio/`?*

<details><summary>Short answers</summary>

1. The browser handles focus trapping, making the background inert, and Escape. Those are
   the three things hand-built modals most often get wrong.
2. When the control should stay focusable and announced, just inactive. For example, a
   carousel "next" button at the end of the row.
3. Break the code it guards on purpose and watch it fail, with a useful message. That's
   mutation testing in its simplest form.
4. Write every link relative to the page (`../static/...`, `../index.html#x`), never
   root-absolute (`/static/...`). Then test it with a crawler.

</details>
