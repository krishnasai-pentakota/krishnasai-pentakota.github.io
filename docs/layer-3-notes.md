# Layer 3 notes — five roles, the cinematic intro, and going live

## What changed

```
content/roles.yaml ──► index.html        the "Who's here?" picker (+ the intro)
                   └─► <role>.html       factory, hire, client, lab, studio: a banner + rows of tiles
content/projects/  ──► work/<id>.html    one page per project that has something to show
.github/workflows/deploy.yml             test → build → publish on every push
```

- Every project has a `kind` (its home role) and optional `also_in` (other rows it appears in,
  like one show listed under two Netflix genres). The weaving and sales projects live in
  Factory and also appear in FDE Lab, because their repos are public case studies.
- New project fields: `why` (one breath on why it matters), `screenshots`, `cover`, `demo`,
  `updated` (drives "New this week"), and link `type` (live / code / video / doc).

## Block 1 — colour comes from the role, not the project

Each role has one colour in `roles.yaml`. The templates set it once, as the CSS variable
`--role` on `<body>`, and every accent in `styles/site.css` reads `var(--role)`: status rings,
the line under a tile, the banner glow, the timeline dots. Change one hex code and a whole
section of the site follows.

**The bug this caught:** the Hire page set `--role` only on its banner, so everything below
it fell back to lime. CSS variables inherit *down* the tree, never sideways. Setting it on
`<body>` fixed every element at once.

## Block 2 — the intro: Three.js draws, GSAP directs

> **Removed on 16 Oct 2026.** You didn't like the ribbons, so the intro, Three.js and GSAP
> were taken out and the site now opens straight on the five roles. The next intro is a
> short video of you walking out of a computer screen with a suitcase. The notes below stay
> as a record of how a real-time 3D intro works; the code is in the git history
> (commit `6543897`) if you ever want to look at it.

- **Three.js** builds real 3D geometry. Each ribbon is a strip laid along a curve. At 240 points
  along the curve we take its "frame" (which way is forward, up and sideways), rotate the
  sideways direction by a twist angle, and put a vertex half a ribbon-width each side.
  Changing the twist over time makes it ripple. Growing the draw range makes it sweep in.
- **GSAP** owns the clock: one timeline, one line per beat (dolly in, ribbons sweep, monogram
  rises, fly through, flash, tiles rise). Reordering the film means editing those lines, not
  timers scattered around the code.
- **Only the parts used ship.** `three-lite.module.js` is Three.js tree-shaken by esbuild down
  to the classes the intro imports: 135 KB gzipped instead of about 700 KB. See
  `tools/build-three-lite.md`.

**Every way out is tested:** reduced motion skips it; it plays once per browser session; a
2.5-second timer gives the page back if the script never starts; Skip / Esc / Enter / Space
skip it; any error hands the page straight back; GPU memory is released when it ends.

## Block 3 — three rendering lessons from this layer

1. **Tone mapping decides your colours.** The ribbons first rendered pastel. ACES Filmic, the
   usual "cinematic" tone mapper, desaturates bright surfaces. Three variants were rendered
   side by side and Neutral tone mapping kept each ribbon in its true role colour. Lesson:
   when colour carries meaning, pick the tone mapper by comparing, not by habit.
2. **Warm up before the clock starts.** The first frame stalled while the GPU compiled the
   satin shader. `renderer.compileAsync()` plus one silent `render()` now happen *before* the
   GSAP timeline starts, so the first visible frame is already smooth.

3. **A scroll box only clips what it positions.** After going live, the Factory and FDE Lab
   pages were 80 px too wide on phones. The cause was a hidden screen-reader label
   (`.sr-only`, which is `position: absolute`) inside the second tile. An absolutely positioned
   element is placed against its nearest *positioned* ancestor, and that was the whole rows
   area, not the shelf. A scroll container (`overflow-x: auto`) only clips descendants it
   contains in that sense, so the label poked out past the screen edge. One line fixed it:
   `position: relative` on `.shelf-track`. Found by hiding elements one at a time until the
   overflow disappeared. `tools/check_layout.py` now checks every page at three widths.

**Why `createStage()` is exported:** the sandbox has no GPU, so the timeline couldn't be
filmed in real time. Exporting the stage let a tiny test page draw any single moment of the
intro and screenshot it. *Code that's easy to test in isolation is usually better
structured code too.*

## Block 4 — CI/CD: GitHub Actions publishes the site

`.github/workflows/deploy.yml` runs on every push to `main`:

```
checkout → Python 3.12 → pip install → pytest (58 checks) → build.py → upload dist/ → deploy to Pages
```

- **A failed check blocks the deploy.** The live site never shows a broken build. That's a
  quality gate, the same idea as a database refusing a bad transaction.
- `concurrency: pages` stops two deploys from racing each other.
- The Monday schedule rebuilds the site so "New this week" badges expire even in a week with
  no edits. The build date is an input, so the output changes.
- `permissions` grants only what's needed: read the code, write Pages, and the OIDC token
  Pages uses to verify the deploy came from this workflow.

## Block 5 — tests that guard decisions, not just code

Two tests encode choices you made, so they can't be undone by accident:

- `test_factory_pages_dont_name_the_employer`: proven by putting "MISO" into a Factory
  project. The build failed with `factory.html names the employer ('MISO')`.
- `test_studio_demo_is_anonymised`: the slideshow demo must carry its "sample names" badge
  and no company names.

## Exercises

1. In `content/roles.yaml`, change Studio's colour to `"#4FD1C5"`, run `python build.py`, and
   open `studio.html` and a Studio project page. Count everything that changed. Change it back.
2. In `weaving-audit.yaml`, set `updated:` to today's date and rebuild. Where does
   "New this week" appear? When will it disappear without you touching anything?
3. On github.com, open the **Actions** tab and click the latest run. Find the step that ran
   the tests and read its output.

## Interview questions this layer prepares you for

- *What is CI/CD? What does your pipeline do, and what stops a bad deploy?*
- *Why would you tree-shake a library, and how much did it save you?*
- *How do you make an animation accessible?*
- *How would you test something that's hard to observe, like a WebGL animation?*

<details><summary>Short answers</summary>

1. Continuous integration means every change is tested automatically. Continuous delivery
   means every change that passes is shipped automatically. Mine runs 58 checks and only
   deploys if all of them pass.
2. To ship only the code you use. Three.js went from about 700 KB to 135 KB gzipped, which
   matters most on phones on mobile data.
3. Respect `prefers-reduced-motion`, always offer a skip (button and keyboard), never block
   the content behind it, and make sure failure falls back to the normal page.
4. Separate the part you want to observe from the clock. I exported the 3D stage, drew single
   moments deterministically, and compared screenshots instead of trying to film real time.

</details>
