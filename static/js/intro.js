/* Cinematic intro for the opening screen.

   Five satin ribbons, one per role and in that role's colour, sweep in from
   the dark, weave toward the centre and tie off on the KS monogram. The camera
   flies through the monogram, a flash fills the screen, and the five role
   tiles rise into place.

   Three.js draws the ribbons (real 3D: lit, twisting strips of geometry).
   GSAP runs the timeline, so every beat is one line below.

   It only runs when index.html marked the page "intro-pending", which never
   happens for people who asked their device to reduce motion, or for a second
   visit in the same browser session. If anything fails (no WebGL, a blocked
   script), finish() hands the page straight back: the picker is always there. */

const html = document.documentElement;
let finished = false;
let revealed = false;
let cleanup = () => {};

if (html.classList.contains("intro-pending")) {
  start().catch((err) => {
    console.warn("Intro skipped:", err);
    finish();
  });
}

async function start() {
  html.classList.add("intro-running");
  try { sessionStorage.setItem("ks-intro", "1"); } catch (e) { /* private mode: fine */ }

  const gsap = window.gsap;
  if (!gsap) throw new Error("GSAP did not load");
  const THREE = await import("../vendor/three-lite.module.js");

  const root = document.querySelector("[data-intro]");
  const canvas = root.querySelector("[data-intro-canvas]");
  const mark = root.querySelector("[data-intro-mark]");
  const flash = root.querySelector("[data-intro-flash]");
  const skip = document.querySelector("[data-intro-skip]");
  const tiles = [...document.querySelectorAll("[data-picker-tile]")];
  const colors = tiles.map((t) => getComputedStyle(t).getPropertyValue("--role").trim() || "#C6F36B");

  const stage = createStage(THREE, canvas, colors);
  const onResize = () => stage.resize(window.innerWidth, window.innerHeight);
  onResize();
  window.addEventListener("resize", onResize);
  await stage.warmUp();

  // ---------------------------------------------------------------- motion
  const state = { t: 0, cam: 18, spin: 0.38 };
  const tick = () => {
    state.t += gsap.ticker.deltaRatio(60) / 60;
    stage.draw(state);
  };
  gsap.ticker.add(tick);

  const tl = gsap.timeline({ onComplete: finish });
  tl.to(state, { cam: 12.5, spin: -0.12, duration: 2.6, ease: "power2.out" }, 0)             // dolly in
    .to(stage.ribbons, { reveal: 1, duration: 1.7, ease: "power2.inOut", stagger: 0.09 }, 0.1) // ribbons sweep in
    .fromTo(mark, { opacity: 0, scale: 0.72, letterSpacing: "0.4em" },                        // monogram rises
      { opacity: 1, scale: 1, letterSpacing: "0.02em", duration: 0.9, ease: "power3.out" }, 1.35)
    .to(state, { cam: 2.2, duration: 0.75, ease: "power3.in" }, 2.45)                          // fly through
    .to(mark, { scale: 7, opacity: 0, duration: 0.7, ease: "power3.in" }, 2.45)
    .to(flash, { opacity: 0.9, duration: 0.18, ease: "power1.in" }, 2.95)                      // flash
    .add(reveal, 3.05)                                                                         // picker rises
    .to(flash, { opacity: 0, duration: 0.5 }, 3.05)
    .to(root, { opacity: 0, duration: 0.5, ease: "power1.out" }, 3.05);

  // Skip: the button, or Esc / Enter / Space.
  const skipNow = () => {
    tl.kill();
    reveal();
    gsap.to([root, flash], { opacity: 0, duration: 0.25, onComplete: finish });
  };
  const onKey = (e) => {
    if (e.key === "Escape" || e.key === "Enter" || e.key === " ") { e.preventDefault(); skipNow(); }
  };
  skip.addEventListener("click", skipNow);
  window.addEventListener("keydown", onKey);

  cleanup = () => {
    gsap.ticker.remove(tick);
    window.removeEventListener("resize", onResize);
    window.removeEventListener("keydown", onKey);
    stage.dispose();                            // hand the GPU memory back
    root.remove();
    skip.remove();
  };
}

/* ------------------------------------------------------------------ the 3D stage
   Everything Three.js: renderer, studio lighting, the five ribbons. Exported so
   a test page can build the same stage and draw any single moment of it. */
export function createStage(THREE, canvas, colors) {
  const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, powerPreference: "high-performance" });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
  // Neutral tone mapping keeps each ribbon in its true role colour. (ACES, the
  // usual choice, drains saturation from bright surfaces and turns satin pastel.)
  renderer.toneMapping = THREE.NeutralToneMapping;
  renderer.outputColorSpace = THREE.SRGBColorSpace;

  const scene = new THREE.Scene();
  scene.background = new THREE.Color("#06070A");
  // A soft studio "room" reflected in the satin: this is what makes it read as fabric.
  const pmrem = new THREE.PMREMGenerator(renderer);
  const envMap = pmrem.fromScene(new THREE.RoomEnvironment(), 0.04).texture;
  scene.environment = envMap;

  const camera = new THREE.PerspectiveCamera(35, 1, 0.1, 100);
  camera.position.set(0, 0, 18);
  scene.add(new THREE.HemisphereLight(0xffffff, 0x0b0d12, 0.32));
  const key = new THREE.DirectionalLight(0xffffff, 1.9);
  key.position.set(-4, 6, 8);
  scene.add(key);
  const rim = new THREE.DirectionalLight(0xdfe6ff, 0.8);   // cool back light picks out the folds
  rim.position.set(6, -3, -4);
  scene.add(rim);

  const group = new THREE.Group();
  group.rotation.x = -0.18;
  scene.add(group);
  const ribbons = colors.map((hex, i) => makeRibbon(THREE, hex, i, colors.length));
  ribbons.forEach((r) => group.add(r.mesh));

  return {
    ribbons,
    resize(w, h) {
      renderer.setSize(w, h, false);
      camera.aspect = w / h;
      camera.fov = w < 700 ? 54 : 35;            // portrait phones need a wider lens
      camera.updateProjectionMatrix();
    },
    // Compile the satin shader and upload textures before the clock starts.
    // Otherwise the first frame freezes while the GPU does it, and the ribbons
    // jump instead of sweeping in.
    async warmUp() {
      try { await renderer.compileAsync(scene, camera); } catch (e) { /* older drivers compile on first draw */ }
      renderer.render(scene, camera);
    },
    draw(state) {
      ribbons.forEach((r) => shape(r, state.t));
      camera.position.z = state.cam;
      group.rotation.y = state.spin;
      renderer.render(scene, camera);
    },
    dispose() {
      ribbons.forEach((r) => { r.geo.dispose(); r.mat.dispose(); });
      envMap.dispose();
      pmrem.dispose();
      renderer.dispose();
    },
  };
}

/* Show the picker and let the tiles rise, staggered, with a little 3D tilt. */
function reveal() {
  if (revealed) return;
  revealed = true;
  html.classList.remove("intro-pending");
  const gsap = window.gsap;
  if (!gsap) return;
  gsap.from("[data-picker-fade]", { y: 18, opacity: 0, duration: 0.7, ease: "power3.out", stagger: 0.08 });
  gsap.from("[data-picker-tile]", {
    y: 46, opacity: 0, rotateX: 28, transformPerspective: 900, transformOrigin: "50% 100%",
    duration: 0.85, ease: "power3.out", stagger: 0.07, delay: 0.1, clearProps: "transform,opacity",
  });
}

function finish() {
  if (finished) return;
  finished = true;
  html.classList.remove("intro-pending", "intro-running");
  cleanup();
}

/* ------------------------------------------------------------------ ribbons
   A ribbon is a flat strip laid along a 3D curve. At each of SEG slices we take
   the curve's frame (tangent, normal, binormal), turn a "side" vector around
   the tangent by the twist angle, and place two vertices half a width either
   side. Twisting over time makes it ripple like fabric; growing the draw range
   makes it sweep in. */
const SEG = 240;

function makeRibbon(THREE, hex, i, n) {
  const a = (i / n) * Math.PI * 2 + 0.5;
  const P = (r, ang, y, z) => new THREE.Vector3(Math.cos(ang) * r, Math.sin(ang) * r * 0.62 + y, z);
  // From far off-screen, spiralling in, ending wrapped around the centre.
  const curve = new THREE.CatmullRomCurve3([
    P(15, a, -1, -8), P(8, a + 0.9, 0.5, -2), P(4.2, a + 1.9, 0, 1.5),
    P(2.2, a + 2.9, 0, 0.8), P(1.35, a + 3.9, 0, 0.2), P(1.25, a + 4.9, 0, 0),
  ], false, "centripetal");
  const frames = curve.computeFrenetFrames(SEG, false);
  const pts = curve.getSpacedPoints(SEG);

  const positions = new Float32Array((SEG + 1) * 2 * 3);
  const index = [];
  for (let s = 0; s < SEG; s++) {
    const a0 = s * 2, b0 = a0 + 1, a1 = a0 + 2, b1 = a0 + 3;
    index.push(a0, b0, a1, b0, b1, a1);
  }
  const geo = new THREE.BufferGeometry();
  geo.setAttribute("position", new THREE.BufferAttribute(positions, 3));
  geo.setIndex(index);

  // Satin = a saturated base colour plus a soft sheen of the SAME colour.
  // (A white-ish sheen and a bright room reflection wash every ribbon out to pastel.)
  const color = new THREE.Color(hex);
  const mat = new THREE.MeshPhysicalMaterial({
    color, roughness: 0.48, metalness: 0.0,
    sheen: 0.65, sheenRoughness: 0.4, sheenColor: color.clone(),
    side: THREE.DoubleSide, envMapIntensity: 0.3,
  });
  const mesh = new THREE.Mesh(geo, mat);
  const ribbon = { mesh, geo, mat, pts, frames, phase: i * 1.3, reveal: 0, width: 0.46 };
  shape(ribbon, 0);
  return ribbon;
}

function shape(r, t) {
  const pos = r.geo.attributes.position.array;
  const { normals, binormals } = r.frames;
  for (let s = 0; s <= SEG; s++) {
    const u = s / SEG;
    const twist = r.phase + u * Math.PI * 3 + Math.sin(t * 1.4 + r.phase) * 0.5;
    const c = Math.cos(twist), sn = Math.sin(twist);
    const n = normals[s], b = binormals[s], p = r.pts[s];
    // Taper the far tail so it doesn't end in a hard edge.
    const half = r.width * 0.5 * Math.min(1, u * 10 + 0.15);
    const sx = (n.x * c + b.x * sn) * half, sy = (n.y * c + b.y * sn) * half, sz = (n.z * c + b.z * sn) * half;
    const k = s * 6;
    pos[k] = p.x + sx; pos[k + 1] = p.y + sy; pos[k + 2] = p.z + sz;
    pos[k + 3] = p.x - sx; pos[k + 4] = p.y - sy; pos[k + 5] = p.z - sz;
  }
  r.geo.attributes.position.needsUpdate = true;
  r.geo.computeVertexNormals();
  r.geo.setDrawRange(0, Math.floor(r.reveal * SEG) * 6);   // how far it has swept in
}
