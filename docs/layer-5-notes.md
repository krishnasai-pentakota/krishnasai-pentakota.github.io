# Layer 5 notes — the intro film, the role tiles and the star pointer

## What changed

```
static/media/intro.webm, intro.mp4   the film: you walk out of a computer screen (9 s, ~0.5 / 0.8 MB)
static/media/intro-poster.webp       its first frame, shown while the film loads (9 KB)
static/js/opening.js                 plays the film, hands over to the role tiles
static/img/roles/*.webp              the photos on the role tiles
static/img/cursor-star*.png          the 3D star pointer (normal, and over links)
content/roles.yaml                   photos: src, credit, link per role (two = cross-fade)
```

## Block 1 — getting an AI video ready for the web

1. **Find the watermark precisely.** One frame was read as numbers (NumPy) to find the bright
   pixels in the corner: the Gemini mark sits at x 1136–1184, y 576–624 in every frame, over
   near-black background.
2. **Blend it away, don't crop.** Cropping would have cut off your head or feet in the last
   shot. ffmpeg's `delogo` filter repaints a small box from the pixels around it, which is
   invisible on a dark background. Google's invisible SynthID watermark stays in the file, and
   the page itself says the film was made with AI.
3. **Two formats.** WebM (VP9) is smaller and plays in Chrome, Edge and Firefox. MP4 (H.264)
   is there for Safari. The browser takes the first `<source>` it can play.
4. **Trim and compress.** The last second (you standing still) was cut; CRF quality settings
   took 2.4 MB down to 0.5 MB (WebM) and 0.8 MB (MP4).

```
ffmpeg -i in.mp4 -t 9 -vf "delogo=x=1128:y=568:w=64:h=64" -c:v libvpx-vp9 -crf 35 -b:v 0 -c:a libopus intro.webm
ffmpeg -i in.mp4 -t 9 -vf "delogo=x=1128:y=568:w=64:h=64" -c:v libx264 -crf 25 -preset slow -movflags +faststart intro.mp4
```

## Block 2 — rules browsers have for video that plays by itself

- It must be **muted** (`muted` attribute and `video.muted = true`), and `playsinline` on iPhone.
- `video.play()` returns a promise that **fails** when autoplay is blocked (battery saver, some
  settings). The script catches that and goes straight to the roles.
- `preload="none"` means nothing downloads until the film actually plays. A second visit, or
  someone with reduced motion, downloads only the 9 KB poster. (Checked by recording the network.)

**Every way out ends on the roles:** the film ending, Skip / Esc / Enter / Space, autoplay
blocked, no playable format, no start within 4 s (slow connection), a 14 s hard limit, and
a 3 s rescue in the page head if the script never loads at all.

## Block 3 — the bug you saw: new page, old stylesheet

The first version had 3D cubes, and on your screen each icon showed three times. The live
site was fine; your browser had kept **yesterday's `site.css`** (GitHub Pages lets browsers
reuse it for up to 10 minutes) and paired it with **today's page**. The old stylesheet knew
nothing about cube faces, so the hidden sides just stacked up as plain icons.

The fix is called **cache busting**: every page now asks for `site.css?v=28d2564…`, where the
`v` is a fingerprint of the CSS, templates, scripts and film (`asset_version()` in
`portfolio/render.py`). Change any of them and the address changes, so no browser can reuse
an old copy. Two tests guard it: every page uses the same stamp, and the stamp changes when
the CSS changes.

Then, on your call, the cubes went: the tiles are now flat photos with the icon shown once
(a test counts exactly one icon per tile). Client work has two photos, a hospital and a
restaurant, and the second fades in and out over the first with one CSS animation.

## Block 3b — the star pointer

- The pointer is a **real cursor image**: `cursor: url(cursor-star.png) 16 16, auto`. The
  `16 16` is the hotspot, the exact pixel that clicks: the star's centre. Over links and
  buttons a tilted, glowing star (`cursor-star-link.png`) takes over.
- Why not a star element that chases the mouse? It lags a frame behind, can drift from where
  the click lands, and disappears behind pop-ups like Quick look (they sit on a layer above
  the page). A cursor image has none of those problems.
- The star is drawn in Python: ten triangles around a raised centre, each shaded by how much
  it faces a light from the top left (the same maths 3D games use for flat shading), plus a
  thin dark rim so it shows on white pages too. Drawn 8x bigger, then shrunk to 32 px for
  smooth edges.
- The sparkle trail is a few lines in `site.js`: one sparkle per ~16 px of movement, at most
  14 alive, each removed when its fade ends. Mouse only; none for reduced motion.

## Block 4 — using other people's photos properly

- Unsplash photos are free to use, even commercially, under the Unsplash License. **Unsplash+**
  photos look the same in search but need a paid licence; they come from `plus.unsplash.com`,
  so those were excluded.
- Each photo was downloaded, cropped square and saved as WebP on your own site (never hotlinked).
- `roles.yaml` refuses a role photo without `credit` and `link`, and the opening screen
  credits every photographer. A test checks that every credit appears.

## Exercises

1. Open the site in a private window (the film plays), then press Esc halfway. Open it again in
   the same window: why doesn't the film play this time? Find the line in `index.html`.
2. Open the site, then press Ctrl+U (view source) and find `site.css?v=`. Change one colour in
   `styles/site.css`, rebuild, and look again. What changed, and why does that matter?
3. Turn on "reduce motion" in your phone or computer's accessibility settings and open the site.
   What's different?

## Interview questions this layer prepares you for

- *How do you autoplay video on the web, and what can go wrong?*
- *A user sees a broken layout you can't reproduce. What do you check first?*
- *How do you make sure third-party images are used legally?*

<details><summary>Short answers</summary>

1. Muted, inline, and handle the `play()` promise failing. Don't download the video unless it
   plays (`preload="none"`), offer Skip, respect reduced motion and Data Saver, and always have
   a way back to the content.
2. Caching: their browser may be mixing new HTML with an old cached stylesheet or script.
   Fix it for good with fingerprinted asset URLs (cache busting), not by asking users to refresh.
3. Check the licence of each image (and paid tiers like Unsplash+), host your own copy, credit
   the photographer, and make the build refuse an image without a credit.

</details>
