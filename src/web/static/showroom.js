/* GEARHEAD showroom: the selected car in 3D, behind the whole app.
 *
 * - Each car is described in /static/cars/cars.json (model file, backdrop, heading).
 * - Each car has its own backdrop (sky, horizon, floor and light colours). Picking
 *   another car fades to its backdrop.
 * - The model is scaled and centred so every car uses the same camera positions.
 * - With no model file (or no WebGL) a plain stand-in is drawn, never a blank box.
 * - Frames are only drawn while something moves, to keep the GPU cool.
 */
import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";
import { DRACOLoader } from "three/addons/loaders/DRACOLoader.js";
import { MeshoptDecoder } from "three/addons/libs/meshopt_decoder.module.js";
import { RoomEnvironment } from "three/addons/environments/RoomEnvironment.js";
import { Reflector } from "three/addons/objects/Reflector.js";

const CAR_LENGTH = 5;            // every model is scaled to this length, in scene units
const IDLE_FPS = 30;             // frame cap while the car turns on its own
const MAX_PIXEL_RATIO = 1.25;
const BACKDROP_FADE_MS = 700;    // fade out, swap, fade in
const SKY_BAND_DEG = 13;         // the sky colours change within this many degrees of the horizon
const REDUCED = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

/* Light mode. Some browsers draw WebGL on the CPU (no graphics acceleration), and
   some machines are simply slow. Light mode drops the mirror floor, the smoothing and
   some of the pixels, and uses the lighter model file. Full quality is always the
   default. Light mode is only ever chosen by the person, with the switch in the top
   bar; when the page is slow it shows a hint, it does not switch by itself. */
const SLOW_FRAME_MS = 50;        // slower than 20 frames a second
const LITE_PIXEL_RATIO = 0.7;
function softwareRenderer() {
  try {
    const gl = document.createElement("canvas").getContext("webgl2") || document.createElement("canvas").getContext("webgl");
    const info = gl && gl.getExtension("WEBGL_debug_renderer_info");
    const name = info ? gl.getParameter(info.UNMASKED_RENDERER_WEBGL) : "";
    return /basic render|swiftshader|llvmpipe|software/i.test(name);
  } catch (e) { return false; }
}
function savedQuality() {
  try { return localStorage.getItem("gearhead-quality"); } catch (e) { return null; }
}
const LITE_FROM_START = savedQuality() === "lite";

/* Backdrops. sky is top to horizon; ground is the far floor colour; ridge is the
   outline on the horizon ("dunes", "peaks", "skyline" or none). */
const BACKDROPS = {
  studio: {
    sky: ["#000000", "#000000", "#0b0c0e"], ground: "#000000", ridge: null,
    key: "#ffffff", rim: "#dfe9ff", floorDim: 0.88, pool: 0.075, env: 0.5,
  },
  desert: {
    sky: ["#05060d", "#161327", "#5a2a2c", "#c8643a"], ground: "#0c0706", ridge: "dunes",
    key: "#ffe9d6", rim: "#ffb38a", floorDim: 0.94, pool: 0.06, env: 0.45,
  },
  alpine: {
    sky: ["#03060c", "#0c1a2e", "#31506e", "#9db6c8"], ground: "#05080b", ridge: "peaks",
    key: "#f1f7ff", rim: "#a9c8ff", floorDim: 0.88, pool: 0.06, env: 0.5,
  },
  city: {
    sky: ["#020207", "#0a0a1c", "#1c1838", "#3a2a5c"], ground: "#030305", ridge: "skyline",
    key: "#ffffff", rim: "#8f7bff", floorDim: 0.84, pool: 0.07, env: 0.5,
  },
};

/* Finishes by material name. Free models often ship flat and matte; these give paint,
   chrome, glass and rubber a showroom finish. First match wins. */
const FINISHES = [
  [/paint|body/i,          { paint: true, metalness: 0.55, roughness: 0.3, clearcoat: 1, clearcoatRoughness: 0.06 }],
  [/chrome/i,              { color: "#f2f2f2", metalness: 1, roughness: 0.07 }],
  [/mirror/i,              { color: "#dfe6ea", metalness: 1, roughness: 0.02 }],
  [/\brim|wheel|^material$/i, { color: "#b9bcc0", metalness: 1, roughness: 0.24 }],
  [/brake|disc|disk/i,     { color: "#7c7f83", metalness: 0.9, roughness: 0.42 }],
  [/metal/i,               { metalness: 0.9, roughness: 0.38 }],
  [/tire|tyre|rubber/i,    { color: "#0b0b0c", metalness: 0, roughness: 0.92, env: 0.12, shine: 0.08 }],
  [/orangeglass/i,         { color: "#ff7a1a", metalness: 0, roughness: 0.15, opacity: 0.85, emissive: "#5a1c00" }],
  [/redglass/i,            { color: "#c0121a", metalness: 0, roughness: 0.15, opacity: 0.88, emissive: "#3a0306" }],
  [/clearglass/i,          { color: "#ffffff", metalness: 0.1, roughness: 0.05, opacity: 0.3 }],
  [/glass/i,               { color: "#0d1416", metalness: 0.35, roughness: 0.04, opacity: 0.55 }],
  [/interior/i,            { color: "#26272a", metalness: 0, roughness: 0.85, env: 0.2, shine: 0.15 }],
  [/black|plastic/i,       { color: "#0e0f10", metalness: 0.1, roughness: 0.58, env: 0.3, shine: 0.3 }],
];

function finishFor(source, paintColour, aliases) {
  const name = (aliases && aliases[source.name]) || source.name || "";
  const hit = FINISHES.find(([pattern]) => pattern.test(name));
  if (!hit) return source;
  const look = hit[1];
  const mat = new THREE.MeshPhysicalMaterial({
    name: source.name,
    color: look.paint ? paintColour : (look.color || source.color),
    metalness: look.metalness, roughness: look.roughness,
    clearcoat: look.clearcoat || 0, clearcoatRoughness: look.clearcoatRoughness || 0,
    emissive: look.emissive || "#000000",
    transparent: look.opacity !== undefined, opacity: look.opacity === undefined ? 1 : look.opacity,
    depthWrite: look.opacity === undefined,
    // dark matte parts pick up the room and the spotlights and go grey-brown otherwise
    envMapIntensity: look.env === undefined ? 1.25 : look.env,
    specularIntensity: look.shine === undefined ? 1 : look.shine,
    side: source.side,
  });
  mat.userData.isPaint = Boolean(look.paint);
  return mat;
}

/* Camera stops, in car space: +z is the nose, +x the left side, y is up.
   shift slides the picture right (as a share of the width), lift slides it up. */
const VIEWS = {
  hero:       { pos: [6.7, 1.5, 7.9],  look: [0, 0.8, 0],       shift: 0,    lift: 0.03, name: 1 },
  engine:     { pos: [3.3, 2.5, 5.8],   look: [0, 1.05, 1.5],    shift: 0.2,  lift: 0 },
  cooling:    { pos: [0.8, 1.3, 7.6],   look: [0, 0.95, 2.0],    shift: 0.2,  lift: 0 },
  chassis:    { pos: [5.8, 1.0, 4.9],   look: [0.7, 0.55, 1.2],  shift: 0.2,  lift: 0 },
  driveline:  { pos: [6.4, 0.9, -4.6],  look: [0, 0.6, -0.7],    shift: 0.2,  lift: 0 },
  electrical: { pos: [-5.4, 2.3, 4.6],  look: [0, 1.1, 0.4],     shift: 0.2,  lift: 0 },
  report:     { pos: [-6.2, 1.9, -5.6], look: [0, 0.9, 0],       shift: 0.26, lift: 0 },
};

const canvas = document.getElementById("showroom");
const state = {
  ready: false, cars: {}, carId: null, car: null, view: "hero",
  autoRotate: !REDUCED, dirtyUntil: 0, lastFrame: 0, loadToken: 0, tween: null,
  shift: 0, lift: VIEWS.hero.lift, nameOpacity: 0,
  backdrop: null, backdropFade: null,
  lite: false, frameTimes: [],
};

let renderer, scene, camera, controls, carHolder, nameplate, dome, mirror, cover, pool, keyLight, rimLeft, draco;

function setStatus(text, pct) {
  const box = document.getElementById("showroomStatus");
  if (!box) return;
  box.classList.toggle("on", Boolean(text));
  box.querySelector(".ss-text").textContent = text || "";
  box.querySelector(".ss-bar i").style.width = pct == null ? "0%" : `${Math.round(pct)}%`;
}

function invalidate(ms = 400) { state.dirtyUntil = Math.max(state.dirtyUntil, performance.now() + ms); }

/* ---------- scene ---------- */
function buildScene() {
  renderer = new THREE.WebGLRenderer({ canvas, antialias: !LITE_FROM_START, powerPreference: "high-performance" });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, MAX_PIXEL_RATIO));
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.0;
  renderer.shadowMap.enabled = true;
  renderer.shadowMap.type = THREE.PCFSoftShadowMap;
  renderer.shadowMap.autoUpdate = false;   // the car does not move, so one shadow pass is enough

  scene = new THREE.Scene();
  scene.background = new THREE.Color("#000000");
  scene.fog = new THREE.Fog("#000000", 14, 40);
  const pmrem = new THREE.PMREMGenerator(renderer);
  scene.environment = pmrem.fromScene(new RoomEnvironment(), 0.03).texture;
  scene.environmentIntensity = 0.5;

  camera = new THREE.PerspectiveCamera(30, 1, 0.1, 140);
  camera.position.set(11, 3.4, 13);

  controls = new OrbitControls(camera, canvas);
  controls.enablePan = false;
  controls.enableDamping = true;
  controls.dampingFactor = 0.06;
  controls.minDistance = 3.4;
  controls.maxDistance = 12;
  controls.minPolarAngle = 0.3;
  controls.maxPolarAngle = Math.PI / 2 - 0.04;   // never below the floor
  controls.autoRotateSpeed = 0.4;
  controls.target.set(0, 0.8, 0);
  controls.addEventListener("start", () => { state.tween = null; controls.autoRotate = false; invalidate(1500); });
  controls.addEventListener("change", () => invalidate(600));
  controls.addEventListener("end", () => {
    clearTimeout(controls._resume);
    controls._resume = setTimeout(() => { controls.autoRotate = state.autoRotate; }, 4000);
  });

  // sky: a dome painted with the car's backdrop
  dome = new THREE.Mesh(
    new THREE.SphereGeometry(70, 48, 24),
    new THREE.MeshBasicMaterial({ side: THREE.BackSide, fog: false, depthWrite: false, toneMapped: false, transparent: true, opacity: 0 }),
  );
  dome.renderOrder = -1;
  scene.add(dome);

  // floor: a true mirror, mostly covered by a dark sheet, so the car has a faint reflection
  mirror = new Reflector(new THREE.CircleGeometry(60, 64), {
    textureWidth: 768, textureHeight: 768, color: 0xffffff, clipBias: 0.002,
  });
  mirror.rotation.x = -Math.PI / 2;
  scene.add(mirror);
  cover = new THREE.Mesh(
    new THREE.CircleGeometry(60, 64),
    new THREE.MeshStandardMaterial({ color: "#000000", roughness: 0.7, metalness: 0, transparent: true, opacity: 0.88 }),
  );
  cover.rotation.x = -Math.PI / 2;
  cover.position.y = 0.003;
  cover.receiveShadow = true;
  scene.add(cover);

  // a soft pool of light on the floor under the car
  pool = new THREE.Mesh(new THREE.CircleGeometry(7.5, 64), new THREE.MeshBasicMaterial({
    map: radialTexture(), color: "#ffffff", transparent: true, opacity: 0.075,
    blending: THREE.AdditiveBlending, depthWrite: false, toneMapped: false,
  }));
  pool.rotation.x = -Math.PI / 2;
  pool.position.y = 0.006;
  scene.add(pool);

  // lights: one soft key from above, two rims that draw the outline
  keyLight = new THREE.SpotLight("#ffffff", 55, 34, 0.6, 0.9, 1.5);
  keyLight.position.set(3.5, 9.5, 5);
  keyLight.castShadow = true;
  keyLight.shadow.mapSize.set(2048, 2048);
  keyLight.shadow.bias = -0.0004;
  keyLight.shadow.radius = 8;
  scene.add(keyLight, keyLight.target);

  rimLeft = new THREE.SpotLight("#dfe9ff", 75, 34, 0.7, 0.9, 1.4);
  rimLeft.position.set(-8, 3.4, -6.5);
  scene.add(rimLeft, rimLeft.target);
  const rimRight = new THREE.SpotLight("#ffffff", 40, 34, 0.7, 0.9, 1.4);
  rimRight.position.set(8, 2.6, -7);
  scene.add(rimRight, rimRight.target);

  nameplate = new THREE.Mesh(
    new THREE.PlaneGeometry(10.5, 2.625),
    new THREE.MeshBasicMaterial({ transparent: true, opacity: 0, depthWrite: false, fog: false, toneMapped: false }),
  );
  scene.add(nameplate);

  carHolder = new THREE.Group();
  scene.add(carHolder);
}

function radialTexture() {
  const c = document.createElement("canvas");
  c.width = c.height = 256;
  const g = c.getContext("2d");
  const grad = g.createRadialGradient(128, 128, 0, 128, 128, 128);
  grad.addColorStop(0, "rgba(255,255,255,1)");
  grad.addColorStop(0.5, "rgba(255,255,255,.3)");
  grad.addColorStop(1, "rgba(255,255,255,0)");
  g.fillStyle = grad;
  g.fillRect(0, 0, 256, 256);
  return new THREE.CanvasTexture(c);
}

/* ---------- backdrop ---------- */
/* The sky as one picture wrapped round the dome: top half sky, bottom half ground,
   with the ridge outline sitting on the horizon. */
function paintBackdrop(spec) {
  const W = 4096, H = 2048, horizon = H / 2;
  const deg = H / 180;                      // texture rows per degree of sky
  const c = document.createElement("canvas");
  c.width = W; c.height = H;
  const g = c.getContext("2d");
  const sky = g.createLinearGradient(0, horizon - SKY_BAND_DEG * deg, 0, horizon);
  spec.sky.forEach((colour, i) => sky.addColorStop(i / (spec.sky.length - 1), colour));
  g.fillStyle = spec.sky[0];
  g.fillRect(0, 0, W, horizon);
  g.fillStyle = sky;
  g.fillRect(0, horizon - SKY_BAND_DEG * deg, W, SKY_BAND_DEG * deg);
  g.fillStyle = spec.ground;
  g.fillRect(0, horizon, W, H - horizon);

  // heights repeat cleanly across the seam because every wave fits the width a whole number of times
  const wave = (x, parts) => parts.reduce((sum, [n, amp, phase]) => sum + amp * Math.sin((x / W) * Math.PI * 2 * n + phase), 0);
  const ridge = (height, colour) => {
    g.fillStyle = colour;
    g.beginPath();
    g.moveTo(0, horizon + 2);
    for (let x = 0; x <= W; x += 4) g.lineTo(x, horizon - Math.max(0, height(x)) * deg);
    g.lineTo(W, horizon + 2);
    g.closePath();
    g.fill();
  };
  if (spec.ridge === "dunes") {
    ridge((x) => 1.5 + wave(x, [[3, 0.9, 0.4], [7, 0.45, 1.9], [13, 0.2, 0.7]]), "#2a1413");
    ridge((x) => 0.6 + wave(x, [[5, 0.5, 2.2], [11, 0.25, 0.3]]), spec.ground);
  } else if (spec.ridge === "peaks") {
    ridge((x) => 2 + Math.abs(wave(x, [[9, 2.2, 0.2], [17, 1.1, 1.1]])) + wave(x, [[4, 0.7, 2]]), "#16283a");
    ridge((x) => 0.7 + Math.abs(wave(x, [[13, 1.2, 1.7], [23, 0.5, 0.4]])), spec.ground);
  } else if (spec.ridge === "skyline") {
    g.fillStyle = "#07060f";
    const blocks = 256, bw = W / blocks;
    for (let i = 0; i < blocks; i++) {
      const h = (0.8 + ((i * 7919) % 53) / 18 + (i % 9 === 0 ? 2.4 : 0)) * deg;   // fixed pattern, same every load
      g.fillRect(i * bw, horizon - h, bw - 2, h + 2);
      g.fillStyle = "rgba(255,225,170,.55)";
      for (let wy = 5; wy < h - 4; wy += 7) if ((i * 31 + wy * 17) % 5 === 0) g.fillRect(i * bw + 4, horizon - h + wy, 3, 3);
      g.fillStyle = "#07060f";
    }
  }
  const texture = new THREE.CanvasTexture(c);
  texture.colorSpace = THREE.SRGBColorSpace;
  return texture;
}

function applyBackdrop(name) {
  const spec = BACKDROPS[name] || BACKDROPS.studio;
  const old = dome.material.map;
  dome.material.map = paintBackdrop(spec);
  dome.material.needsUpdate = true;
  if (old) old.dispose();
  const horizonColour = spec.ridge ? spec.ground : spec.sky[spec.sky.length - 1];
  scene.fog.color.set(horizonColour);
  scene.background.set(spec.ground);
  cover.material.color.set(spec.ground);
  cover.material.opacity = state.lite ? 1 : spec.floorDim;
  pool.material.opacity = spec.pool;
  pool.material.color.set(spec.key);
  keyLight.color.set(spec.key);
  rimLeft.color.set(spec.rim);
  scene.environmentIntensity = spec.env;
  document.body.dataset.backdrop = BACKDROPS[name] ? name : "studio";
}

/* Fade the scene down, swap the backdrop, fade back up. */
function setBackdrop(name) {
  if (name === state.backdrop) return;
  const first = state.backdrop === null;
  state.backdrop = name;
  if (first || REDUCED) { applyBackdrop(name); dome.material.opacity = 1; renderer.toneMappingExposure = 1; invalidate(); return; }
  if (state.backdropFade && !state.backdropFade.swapped) state.backdropFade.name = name;
  else state.backdropFade = { start: performance.now(), name, swapped: false };
  invalidate(BACKDROP_FADE_MS * 2 + 200);
}

function stepBackdrop(now) {
  const fade = state.backdropFade;
  if (!fade) return;
  const t = (now - fade.start) / BACKDROP_FADE_MS;        // 0..1 out, 1..2 in
  if (t >= 1 && !fade.swapped) { applyBackdrop(fade.name); fade.swapped = true; }
  const level = t < 1 ? 1 - ease(Math.min(1, t)) : ease(Math.min(1, t - 1));
  dome.material.opacity = level;
  renderer.toneMappingExposure = 0.15 + 0.85 * level;
  if (t >= 2) { state.backdropFade = null; dome.material.opacity = 1; renderer.toneMappingExposure = 1; }
}

/* ---------- nameplate: the model name, very large, standing behind the car ---------- */
async function writeNameplate(text) {
  const token = state.loadToken;
  try { await document.fonts.load('200 300px "Outfit"'); } catch (e) { /* system font */ }
  if (token !== state.loadToken) return;
  const c = document.createElement("canvas");
  c.width = 2048; c.height = 512;
  const g = c.getContext("2d");
  g.textAlign = "center";
  g.textBaseline = "middle";
  const spaced = (text || "").toUpperCase().split("").join(" ");
  let size = 440;
  do { size -= 10; g.font = `200 ${size}px "Outfit", "Segoe UI", sans-serif`; }
  while (g.measureText(spaced).width > c.width * 0.96 && size > 80);
  const grad = g.createLinearGradient(0, 60, 0, 460);
  grad.addColorStop(0, "rgba(255,255,255,.3)");
  grad.addColorStop(1, "rgba(255,255,255,.05)");
  g.fillStyle = grad;
  g.fillText(spaced, c.width / 2, c.height / 2 + 12);
  const old = nameplate.material.map;
  nameplate.material.map = new THREE.CanvasTexture(c);
  nameplate.material.map.colorSpace = THREE.SRGBColorSpace;
  nameplate.material.needsUpdate = true;
  if (old) old.dispose();
  invalidate(800);
}

/* Keep the name behind the car from wherever the camera is. */
const _dir = new THREE.Vector3();
function placeNameplate() {
  _dir.subVectors(controls.target, camera.position).setY(0).normalize();
  nameplate.position.copy(controls.target).addScaledVector(_dir, 7).setY(2.35);
  nameplate.lookAt(camera.position.x, nameplate.position.y, camera.position.z);
  nameplate.material.opacity = state.nameOpacity;
  nameplate.visible = state.nameOpacity > 0.005;
}

/* ---------- the car ---------- */
function disposeTree(root) {
  root.traverse((o) => {
    if (o.geometry) o.geometry.dispose();
    for (const m of [].concat(o.material || [])) {
      for (const key in m) if (m[key] && m[key].isTexture) m[key].dispose();
      m.dispose();
    }
  });
}

/* Scale to CAR_LENGTH, sit the wheels on the floor, centre it, and turn the nose to +z.
   upright is [x, y, z] degrees for a file whose up direction is not y. */
function fitToStage(source, headingDeg, upright) {
  const fitted = new THREE.Group();
  const model = new THREE.Group();
  if (upright) source.rotation.set(...upright.map(THREE.MathUtils.degToRad));
  model.add(source);
  fitted.add(model);
  let box = new THREE.Box3().setFromObject(model);
  const size = box.getSize(new THREE.Vector3());
  if (size.x > size.z) model.rotation.y += Math.PI / 2;      // long axis onto z
  model.rotation.y += THREE.MathUtils.degToRad(headingDeg || 0);
  box = new THREE.Box3().setFromObject(model);
  const length = box.getSize(new THREE.Vector3()).z || 1;
  model.scale.multiplyScalar(CAR_LENGTH / length);
  box = new THREE.Box3().setFromObject(model);
  const centre = box.getCenter(new THREE.Vector3());
  model.position.x -= centre.x;
  model.position.z -= centre.z;
  model.position.y -= box.min.y;
  return fitted;
}

/* Stand-in when there is no model file: a plain 4WD shape in dark gloss paint. */
function buildStandIn() {
  const group = new THREE.Group();
  const paint = new THREE.MeshPhysicalMaterial({ color: "#1b1d21", roughness: 0.26, metalness: 0.85, clearcoat: 1, clearcoatRoughness: 0.12 });
  const rubber = new THREE.MeshStandardMaterial({ color: "#050505", roughness: 0.85 });
  const part = (geo, mat, x, y, z) => {
    const mesh = new THREE.Mesh(geo, mat);
    mesh.position.set(x, y, z);
    mesh.castShadow = true;
    group.add(mesh);
    return mesh;
  };
  part(new THREE.BoxGeometry(1.9, 0.75, 4.9), paint, 0, 0.95, 0);        // body
  part(new THREE.BoxGeometry(1.8, 0.7, 2.9), paint, 0, 1.65, -0.55);     // cabin
  part(new THREE.BoxGeometry(1.95, 0.2, 0.22), paint, 0, 0.62, 2.5);     // front bar
  part(new THREE.BoxGeometry(1.95, 0.2, 0.2), paint, 0, 0.62, -2.5);     // rear bar
  for (const x of [-0.98, 0.98]) for (const z of [1.55, -1.5]) {
    part(new THREE.CylinderGeometry(0.42, 0.42, 0.32, 40), rubber, x, 0.42, z).rotation.z = Math.PI / 2;
  }
  return group;
}

/* Number plates. The model's own lettering is hidden and new text is laid over the
   plate. One mesh can hold both plates, so its points are split into front (z > 0)
   and rear (z < 0), and each half gets its own text. */
function plateTexture(text) {
  const c = document.createElement("canvas");
  c.width = 1024; c.height = 256;
  const g = c.getContext("2d");
  g.fillStyle = "#f4f4f1";
  g.fillRect(0, 0, c.width, c.height);
  g.fillStyle = "#111111";
  g.textAlign = "center";
  g.textBaseline = "middle";
  const spaced = text.toUpperCase().split("").join("\u2009");
  let size = 210;
  do { size -= 6; g.font = `600 ${size}px "Outfit", "Arial Narrow", sans-serif`; }
  while (g.measureText(spaced).width > c.width * 0.8 && size > 40);
  g.fillText(spaced, c.width / 2, c.height / 2 + 8);
  const texture = new THREE.CanvasTexture(c);
  texture.colorSpace = THREE.SRGBColorSpace;
  texture.anisotropy = 8;
  return texture;
}

function fitPlates(fitted, plate) {
  if (!plate || !plate.text) return;
  fitted.updateMatrixWorld(true);
  const point = new THREE.Vector3();
  const boxes = { front: new THREE.Box3(), rear: new THREE.Box3() };
  fitted.traverse((o) => {
    if (!o.isMesh) return;
    const name = [].concat(o.material)[0].name;
    if (name === plate.lettering) o.visible = false;
    if (name !== plate.base) return;
    const pos = o.geometry.attributes.position;
    for (let i = 0; i < pos.count; i++) {
      point.fromBufferAttribute(pos, i).applyMatrix4(o.matrixWorld);
      (point.z > 0 ? boxes.front : boxes.rear).expandByPoint(point);
    }
  });
  const material = new THREE.MeshStandardMaterial({ map: plateTexture(plate.text), roughness: 0.5, metalness: 0 });
  for (const [side, box] of Object.entries(boxes)) {
    if (box.isEmpty()) continue;
    const size = box.getSize(new THREE.Vector3()), mid = box.getCenter(new THREE.Vector3());
    const facing = side === "front" ? 1 : -1;
    const label = new THREE.Mesh(new THREE.PlaneGeometry(size.x, size.y), material);
    label.position.set(mid.x, mid.y, (facing > 0 ? box.max.z : box.min.z) + facing * 0.004);
    if (facing < 0) label.rotation.y = Math.PI;
    fitted.add(label);
  }
}

function showCar(object) {
  for (const old of [...carHolder.children]) { carHolder.remove(old); disposeTree(old); }
  carHolder.add(object);
  renderer.shadowMap.needsUpdate = true;
  invalidate(1200);
}

async function loadCar(carId) {
  const token = ++state.loadToken;
  const car = state.cars[carId] || {};
  state.carId = carId;
  state.car = car;
  state.paint = null;
  document.documentElement.style.setProperty("--accent", car.accent || "#d92b1e");
  document.body.dataset.car = carId;
  setBackdrop(car.backdrop || "studio");
  writeNameplate(car.model_name || carId.split("-")[1] || "");
  const credit = document.getElementById("modelCredit");
  if (credit) { credit.textContent = ""; credit.removeAttribute("href"); }

  if (!car.model) { showCar(buildStandIn()); setStatus(""); return; }

  const label = `Loading ${car.short || carId}`;
  setStatus(label, 0);
  if (!carHolder.children.length) showCar(buildStandIn());
  const loader = new GLTFLoader();
  if (!draco) draco = new DRACOLoader().setDecoderPath("/static/vendor/three/addons/libs/draco/gltf/");
  loader.setDRACOLoader(draco);
  loader.setMeshoptDecoder(MeshoptDecoder);
  try {
    const file = (state.lite && car.model_lite) || car.model;
    const gltf = await loader.loadAsync(`/static/cars/${file}`, (e) => {
      if (token === state.loadToken && e.total) setStatus(label, (e.loaded / e.total) * 100);
    });
    if (token !== state.loadToken) { disposeTree(gltf.scene); return; }   // another car was picked meanwhile
    const paint = state.paint || car.paint || "#b9b2a8";
    const finished = new Map();          // one new material per original, shared across meshes
    const finish = (m) => {
      if (!finished.has(m)) finished.set(m, finishFor(m, paint, car.materials));
      return finished.get(m);
    };
    gltf.scene.traverse((o) => {
      if (!o.isMesh) return;
      o.material = Array.isArray(o.material) ? o.material.map(finish) : finish(o.material);
      const seeThrough = [].concat(o.material).some((m) => m.transparent);
      o.castShadow = !seeThrough;
      o.receiveShadow = !seeThrough;
    });
    for (const original of finished.keys()) if (finished.get(original) !== original) original.dispose();
    const fitted = fitToStage(gltf.scene, car.heading, car.upright);
    fitPlates(fitted, car.plate);
    showCar(fitted);
    if (credit && car.credit) {
      credit.textContent = car.credit;
      if (car.credit_url) credit.href = car.credit_url;
    }
    setStatus("");
    flyTo(state.view, 2.6);
  } catch (err) {
    if (token !== state.loadToken) return;
    console.warn("[showroom] no 3D model for", carId, err);
    showCar(buildStandIn());
    setStatus("");
  }
}

function setPaint(colour) {
  state.paint = colour;
  carHolder.traverse((o) => {
    for (const m of [].concat(o.material || [])) if (m.userData && m.userData.isPaint) m.color.set(colour);
  });
  invalidate(600);
}

/* ---------- camera ---------- */
const ease = (t) => (t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2);
const narrow = () => window.innerWidth < 900;

function flyTo(name, seconds = 1.8) {
  state.view = VIEWS[name] ? name : "hero";
  const view = VIEWS[state.view];
  const to = {
    pos: new THREE.Vector3(...view.pos), look: new THREE.Vector3(...view.look),
    shift: narrow() ? 0 : view.shift, lift: view.lift, name: view.name ? 1 : 0,
  };
  if (REDUCED || seconds <= 0) {
    camera.position.copy(to.pos); controls.target.copy(to.look);
    state.shift = to.shift; state.lift = to.lift; state.nameOpacity = to.name;
    state.tween = null; invalidate(); return;
  }
  state.tween = {
    from: { pos: camera.position.clone(), look: controls.target.clone(), shift: state.shift, lift: state.lift, name: state.nameOpacity },
    to, start: performance.now(), ms: seconds * 1000,
  };
  controls.autoRotate = false;
  invalidate(seconds * 1000 + 300);
}

function stepTween(now) {
  const tw = state.tween;
  if (!tw) return;
  const t = Math.min(1, (now - tw.start) / tw.ms), k = ease(t);
  camera.position.lerpVectors(tw.from.pos, tw.to.pos, k);
  controls.target.lerpVectors(tw.from.look, tw.to.look, k);
  state.shift = tw.from.shift + (tw.to.shift - tw.from.shift) * k;
  state.lift = tw.from.lift + (tw.to.lift - tw.from.lift) * k;
  state.nameOpacity = tw.from.name + (tw.to.name - tw.from.name) * k;
  if (t >= 1) { state.tween = null; controls.autoRotate = state.autoRotate; }
}

/* Slide the picture so the car sits beside the panels, not under them. */
function applyShift() {
  const w = canvas.clientWidth, h = canvas.clientHeight;
  if (Math.abs(state.shift) < 0.001 && Math.abs(state.lift) < 0.001) camera.clearViewOffset();
  else camera.setViewOffset(w, h, -w * state.shift, h * state.lift, w, h);
}

function resize() {
  const w = canvas.clientWidth, h = canvas.clientHeight;
  if (!w || !h) return;
  renderer.setSize(w, h, false);
  camera.aspect = w / h;
  camera.fov = narrow() ? 46 : 30;
  camera.updateProjectionMatrix();
  if (!state.tween) state.shift = narrow() ? 0 : VIEWS[state.view].shift;
  invalidate();
}

function goLite() {
  if (state.lite) return;
  state.lite = true;
  state.autoRotate = false;                   // a slow spin at a few frames a second looks worse than none
  controls.autoRotate = false;
  mirror.visible = false;
  cover.material.opacity = 1;
  renderer.setPixelRatio(LITE_PIXEL_RATIO);
  renderer.setSize(canvas.clientWidth, canvas.clientHeight, false);
  document.body.dataset.gfx = "lite";
  invalidate();
}

/* Time the first frames once the car is in. Too slow, and the page says why. */
function watchSpeed(ms) {
  if (state.lite || state.frameTimes === null || !carHolder.children.length) return;
  state.frameTimes.push(ms);
  if (state.frameTimes.length < 12) return;
  const typical = [...state.frameTimes].sort((a, b) => a - b)[6];
  state.frameTimes = null;                    // measured once
  if (typical > SLOW_FRAME_MS) {
    document.body.dataset.slow = softwareRenderer() ? "software" : "slow";
    window.dispatchEvent(new CustomEvent("showroom-slow"));
  }
}

/* ---------- loop: draw only while something is moving ---------- */
function frame(now) {
  requestAnimationFrame(frame);
  if (document.hidden) return;
  const turning = controls.autoRotate && state.autoRotate;
  const busy = state.tween || state.backdropFade || now < state.dirtyUntil;
  if (!busy && !turning) return;
  if (!busy && now - state.lastFrame < 1000 / IDLE_FPS) return;
  state.lastFrame = now;
  stepTween(now);
  stepBackdrop(now);
  if (!state.tween) controls.update();
  camera.lookAt(controls.target);
  applyShift();
  placeNameplate();
  const began = performance.now();
  renderer.render(scene, camera);
  watchSpeed(performance.now() - began);
}

/* ---------- public ---------- */
const api = {
  loadCar: (id) => loadCar(id),
  focus: (name, seconds) => flyTo(name, seconds),
  /* The car turns on its own only on the start screen; elsewhere it holds still. */
  setIdle: (on) => {
    state.autoRotate = Boolean(on) && !REDUCED && !state.lite;
    controls.autoRotate = state.autoRotate && !state.tween;
    controls.enabled = Boolean(on);
    invalidate();
  },
  setBackdrop: (name) => setBackdrop(name),
  setPaint: (colour) => setPaint(colour),
  /* For tuning a new model: every part with its material, colour and size. */
  parts: () => {
    const out = [];
    carHolder.traverse((o) => {
      if (!o.isMesh) return;
      const box = new THREE.Box3().setFromObject(o), size = box.getSize(new THREE.Vector3()), mid = box.getCenter(new THREE.Vector3());
      for (const m of [].concat(o.material)) out.push({ part: o.name, material: m.name, colour: "#" + m.color.getHexString(), size: size.toArray().map((n) => +n.toFixed(2)), mid: mid.toArray().map((n) => +n.toFixed(2)) });
    });
    return out;
  },
  views: Object.keys(VIEWS),
  backdrops: Object.keys(BACKDROPS),
};

async function init() {
  try {
    buildScene();
  } catch (err) {
    console.warn("[showroom] WebGL unavailable", err);
    document.body.classList.add("no-webgl");
    return;
  }
  try { state.cars = await (await fetch("/static/cars/cars.json", { cache: "no-store" })).json(); } catch (e) { state.cars = {}; }
  if (LITE_FROM_START) goLite();
  state.ready = true;
  controls.autoRotate = state.autoRotate;
  window.addEventListener("resize", resize);
  resize();
  requestAnimationFrame(frame);
  document.body.classList.add("showroom-on");
  // set only now, so calls made earlier wait in app.js's queue and are replayed
  window.Showroom = api;
  flyTo("hero", 3);
  window.dispatchEvent(new CustomEvent("showroom-ready"));
}

init();
