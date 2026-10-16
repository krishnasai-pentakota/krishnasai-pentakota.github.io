# Layer 1 notes — Tailwind, the store map, and motion

## What changed

```
styles/site.css ──► Tailwind binary (via pytailwindcss) ──► dist/static/css/site.css
templates/*.html ─┘ (scanned for class names)
static/js/site.js ──► copied as-is ──► dist/static/js/site.js
```

- `styles/` is new: it holds the Tailwind *source*. It is not copied raw; `build.py`
  compiles it. The old `static/css/site.css` from Layer 0 is no longer used.
- Three new project files: sales dashboard, warehouse 3D map, store inventory system.
- A new field, `highlights` (up to 5 short bullets), for what each system actually does.

## Block 1 — Tailwind without Node (`render.py: compile_css`)

`pytailwindcss` downloads Tailwind's standalone binary the first time and runs it.
The version is pinned (`TAILWIND_VERSION = "v4.3.3"`), so the CSS is the same on your
laptop and on GitHub Actions. This is the same idea as pinning versions in `requirements.txt`.

In `styles/site.css`:

- `@import "tailwindcss" source(none);` plus `@source "../templates";` means "only look
  in templates/ for class names". The output is about 15 KB because Tailwind only
  writes the classes you actually used.
- `@theme { --color-lime: #C6F36B; ... }` defines each token once. Tailwind turns it into a CSS
  variable *and* utilities (`bg-lime`, `text-lime`, `border-lime`). Change the hex once and
  everything follows.
- `@layer components` holds named pieces (`.card`, `.panel`, `.plate`). Utilities do
  layout in the templates, and components do anything with many rules or states.

## Block 2 — the store map is a tiny 3D engine (`site.js: project`)

There's no library. Three steps turn a world point `(x, y, z)` into a screen point:

```js
X = x*cos(θ) - z*sin(θ);   Z = x*sin(θ) + z*cos(θ);      // 1. turn the world (orbit)
Y = y*cos(φ) + Z*sin(φ);   D = Z*cos(φ) - y*sin(φ) + dist // 2. tilt the camera down
screenX = W/2 + X * focal/D;  screenY = H*0.56 - Y * focal/D  // 3. perspective divide
```

Step 3 is the whole trick of 3D: divide by depth, and far things get smaller. Racks are
drawn far-to-near (sorted by `D`) so near racks paint over far ones. That's the
"painter's algorithm".

**Why not Three.js?** The scene is boxes and lines. Three.js would add roughly 150 KB of
compressed JavaScript, and it ships only as ES modules, which browsers refuse to run
from `file://`, so you couldn't double-click `dist/index.html` any more. The
hand-written version is about 200 lines you can explain line by line in an interview.
Three.js comes in when we need real meshes and lighting (a full warehouse demo in Layer 3).

## Block 3 — motion rules (`site.js: setRunning`)

- **One orchestrated moment:** racks rise once (1.6 s), then a slow orbit. No fade-up on
  every section, and no hover tilt on cards that aren't clickable. Scattered effects read as
  template noise.
- **Pause when nobody's looking:** an `IntersectionObserver` stops the animation loop when
  the map scrolls off screen, and `visibilitychange` stops it in a background tab. That
  saves battery on phones.
- **Reduced motion:** if the visitor asked their OS to reduce motion, the map draws one
  still frame and the feed doesn't tick. The CSS scan line is switched off too.
- `devicePixelRatio` is capped at 2, so a 3x phone screen doesn't triple the drawing work.

## Block 4 — the feed is safe by construction

New feed lines are built with `createElement` and `createTextNode`, never by assigning
HTML strings. Even if a message contained `<script>`, it would show as text. A test
(`test_script_is_classic_and_safe`) fails the build if anyone adds an `innerHTML =`.

## Block 5 — the mobile menu works without JavaScript too

`<script>document.documentElement.classList.add("js")</script>` runs before the CSS
applies. The CSS only collapses the menu under `.js`, so if JavaScript fails, the links
simply stay visible. That's progressive enhancement: the page works first, then gets better.

## Things the build caught this layer

- My weaving summary was 310 characters, and the 300-character rule refused it. The shorter
  version reads better.
- The JS safety test flagged the word "innerHTML" inside a *comment*. The test now looks for
  actual assignments (`.innerHTML =`). Lesson: a test that cries wolf gets ignored, so make
  it precise.

## Exercises

1. In `styles/site.css`, change `--color-lime` to another colour, run `python build.py`,
   and refresh. Count how many places changed. Then change it back.
2. In `site.js`, find `theta = -0.62 + t * 0.045`. Make the orbit twice as fast, then set it
   back. Which variable would tilt the camera more steeply?
3. Turn on "reduce motion" in Windows (Settings, Accessibility, Visual effects, Animation
   effects off) and reload the page. What changes?

## Interview questions this layer prepares you for

- *Why pin the Tailwind version?*
- *Explain perspective projection in one sentence.*
- *How do you keep an animation from draining a phone battery?*
- *What's progressive enhancement? Give an example from your own site.*

<details><summary>Short answers</summary>

1. Reproducible builds: the same commit gives the same CSS everywhere, and an upstream release
   can't silently change the site.
2. Divide x and y by the distance from the camera, so things further away are drawn smaller.
3. Stop the loop when it's off screen or the tab is hidden, cap the pixel ratio, and respect
   reduced motion.
4. Build the working version first, then add behaviour on top. The menu stays usable without
   JavaScript and only collapses when the script that opens it is present.

</details>
