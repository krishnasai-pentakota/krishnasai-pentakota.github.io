# Layer 5 notes — the intro film and the role cubes

## What changed

```
static/media/intro.webm, intro.mp4   the film: you walk out of a computer screen (9 s, ~0.5 / 0.8 MB)
static/media/intro-poster.webp       its first frame, shown while the film loads (9 KB)
static/js/opening.js                 plays the film, hands over to the cubes
static/img/roles/*.webp              the photo on the front of each role cube
content/roles.yaml                   photo, photo_credit, photo_link per role
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

## Block 3 — a real 3D cube in plain CSS

```
.cube        transform-style: preserve-3d   (children keep their own 3D positions)
.cube-front  translateZ(edge / 2)           (each face pushed half an edge out from the centre…)
.cube-right  rotateY(90deg) translateZ(edge / 2)   (…after turning to face its direction)
.cube        translateZ(-edge / 2)          (the whole cube pushed back, so the front face isn't enlarged)
```

- **Perspective** on the parent (`.cube-stage`) is what makes near parts look bigger.
- **The tumble** is one `@keyframes` rule. Every keyframe lists the same transform functions in
  the same order, so the browser animates each angle instead of guessing between matrices.
- **`animation-fill-mode: backwards`**, not `both`: it holds the first frame during each cube's
  delay, but after the animation the cube's own resting transform applies again. With `both`, the
  last keyframe would stay locked on and the hover tilt would never work.
- **Stagger without JavaScript:** each tile carries `--i` (0–4), and the delay is
  `calc(var(--i) * 130ms + 120ms)`.

## Block 4 — using other people's photos properly

- Unsplash photos are free to use, even commercially, under the Unsplash License. **Unsplash+**
  photos look the same in search but need a paid licence; they come from `plus.unsplash.com`,
  so those were excluded.
- Each photo was downloaded, cropped square and saved as WebP on your own site (never hotlinked).
- `roles.yaml` refuses a role photo without `photo_credit` and `photo_link`, and the opening
  screen credits all five photographers. A test checks that every credit appears.

## Exercises

1. Open the site in a private window (the film plays), then press Esc halfway. Open it again in
   the same window: why doesn't the film play this time? Find the line in `index.html`.
2. In `styles/site.css`, change `130ms` in the cube delay to `400ms` and rebuild. What changes?
   Change it back.
3. Turn on "reduce motion" in your phone or computer's accessibility settings and open the site.
   What's different?

## Interview questions this layer prepares you for

- *How do you autoplay video on the web, and what can go wrong?*
- *How would you build a 3D effect without a 3D library?*
- *How do you make sure third-party images are used legally?*

<details><summary>Short answers</summary>

1. Muted, inline, and handle the `play()` promise failing. Don't download the video unless it
   plays (`preload="none"`), offer Skip, respect reduced motion and Data Saver, and always have
   a way back to the content.
2. CSS 3D transforms: `perspective` on the parent, `preserve-3d` on the object, each face
   rotated and pushed out with `translateZ`. It runs on the GPU and needs no JavaScript.
3. Check the licence of each image (and paid tiers like Unsplash+), host your own copy, credit
   the photographer, and make the build refuse an image without a credit.

</details>
