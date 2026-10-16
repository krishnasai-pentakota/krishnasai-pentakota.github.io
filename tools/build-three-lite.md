# How static/vendor/three-lite.module.js was made

Three.js no longer ships a minified build, and the full library is ~2 MB. The intro
only needs a handful of classes, so they're bundled once with esbuild (tree-shaking
drops the rest). This needs Node.js, but only when you want to change the bundle;
the site build itself never needs Node.

```bash
mkdir three-lite && cd three-lite
npm init -y && npm install three@0.186.1 esbuild@0.25.10
cat > entry.js <<'JS'
export {
  WebGLRenderer, Scene, PerspectiveCamera, Color, Vector3, CatmullRomCurve3,
  BufferGeometry, BufferAttribute, Mesh, MeshPhysicalMaterial, DoubleSide,
  PMREMGenerator, NeutralToneMapping, SRGBColorSpace, DirectionalLight,
  HemisphereLight, MathUtils, Group,
} from "three";
export { RoomEnvironment } from "three/addons/environments/RoomEnvironment.js";
JS
npx esbuild entry.js --bundle --minify --format=esm --legal-comments=eof --outfile=three-lite.module.js
```

Result: 539 KB, about 135 KB gzipped (GitHub Pages serves it gzipped).
Need another Three.js class in intro.js? Add it to `entry.js`, rebuild, and copy the file
to `static/vendor/`.

`static/vendor/gsap.min.js` is GSAP 3.15.0 from npm (`gsap/dist/gsap.min.js`), free for
commercial use under GSAP's standard license.
