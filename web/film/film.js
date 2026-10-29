// From Sand to Chip (docs/CHIP-FILM.md): the film's renderer and its thirteen scenes, in Three.js.
// Semi-real: physically based materials, a studio environment for reflections, soft shadows, bloom and depth of
// field, with explainer marks drawn on a 2D layer above. Every scene is a pure function of its time, so a still or a
// video frame renders the same on every run. The fab's part runs on the SMT2020 model; the rest is general knowledge.
//
//   ?scene=quarry&t=8   one frame          ?stills=1   every scene's still, saved by film/serve.py
//   ?frames=0-4919&fps=30   video frames, saved by film/serve.py

import * as THREE from "three";
import { RoomEnvironment } from "three/addons/environments/RoomEnvironment.js";
import { RoundedBoxGeometry } from "three/addons/geometries/RoundedBoxGeometry.js";
import { EffectComposer } from "three/addons/postprocessing/EffectComposer.js";
import { RenderPass } from "three/addons/postprocessing/RenderPass.js";
import { UnrealBloomPass } from "three/addons/postprocessing/UnrealBloomPass.js";
import { BokehPass } from "three/addons/postprocessing/BokehPass.js";
import { OutputPass } from "three/addons/postprocessing/OutputPass.js";

const FS = window.FilmScript;
const W = 1920, H = 1080;
const glCanvas = document.getElementById("gl"), uiCanvas = document.getElementById("ui");
uiCanvas.width = W; uiCanvas.height = H;
const ui = uiCanvas.getContext("2d");
const renderer = new THREE.WebGLRenderer({ canvas: glCanvas, antialias: true, preserveDrawingBuffer: true });
renderer.setPixelRatio(1);
renderer.setSize(W, H, false);
renderer.toneMapping = THREE.ACESFilmicToneMapping;
renderer.toneMappingExposure = 1.0;
renderer.outputColorSpace = THREE.SRGBColorSpace;
renderer.shadowMap.enabled = true;
renderer.shadowMap.type = THREE.PCFSoftShadowMap;
const ENV = new THREE.PMREMGenerator(renderer).fromScene(new RoomEnvironment(), 0.04).texture;

// ------------------------------------------------------------------ small helpers
const ease = (x) => (x <= 0 ? 0 : x >= 1 ? 1 : x * x * (3 - 2 * x));
const lerp = (a, b, x) => a + (b - a) * x;
const span = (t, a, b) => ease((t - a) / (b - a));
function rng(seed) { let s = seed >>> 0; return () => ((s = (s * 1664525 + 1013904223) >>> 0) / 4294967296); }
function hash3(x, y, z) { const s = Math.sin(x * 127.1 + y * 311.7 + z * 74.7) * 43758.5453; return s - Math.floor(s); }
function noise3(x, y, z) {
  const xi = Math.floor(x), yi = Math.floor(y), zi = Math.floor(z), xf = x - xi, yf = y - yi, zf = z - zi;
  const u = xf * xf * (3 - 2 * xf), v = yf * yf * (3 - 2 * yf), w = zf * zf * (3 - 2 * zf);
  const c = (a, b, d) => hash3(xi + a, yi + b, zi + d);
  const x00 = lerp(c(0, 0, 0), c(1, 0, 0), u), x10 = lerp(c(0, 1, 0), c(1, 1, 0), u);
  const x01 = lerp(c(0, 0, 1), c(1, 0, 1), u), x11 = lerp(c(0, 1, 1), c(1, 1, 1), u);
  return lerp(lerp(x00, x10, v), lerp(x01, x11, v), w);
}
const std = (color, roughness = 0.6, metalness = 0, extra = {}) => new THREE.MeshStandardMaterial({ color, roughness, metalness, ...extra });
const glow = (color, intensity = 2) => new THREE.MeshStandardMaterial({ color: 0x000000, emissive: color, emissiveIntensity: intensity, roughness: 1 });
function mesh(geo, mat, x = 0, y = 0, z = 0, cast = true) { const m = new THREE.Mesh(geo, mat); m.position.set(x, y, z); m.castShadow = cast; m.receiveShadow = true; return m; }
function displace(geo, amount, freq, seed = 0) {
  const p = geo.attributes.position, v = new THREE.Vector3();
  for (let i = 0; i < p.count; i++) {
    v.fromBufferAttribute(p, i);
    const n = noise3(v.x * freq + seed, v.y * freq, v.z * freq) * 0.65 + noise3(v.x * freq * 2.7, v.y * freq * 2.7 + seed, v.z * freq * 2.7) * 0.35;
    v.multiplyScalar(1 + (n - 0.5) * amount);
    p.setXYZ(i, v.x, v.y, v.z);
  }
  geo.computeVertexNormals();
  return geo;
}
function baseScene(bg, fog) {
  const scene = new THREE.Scene();
  scene.background = new THREE.Color(bg);
  scene.environment = ENV;
  scene.environmentIntensity = 0.5;
  if (fog) scene.fog = new THREE.Fog(bg, fog[0], fog[1]);
  return scene;
}
// a sky dome: a gradient from the zenith to the horizon (drawn behind everything)
function sky(scene, top, horizon, bottom = 0x2a2420) {
  const mat = new THREE.ShaderMaterial({ side: THREE.BackSide, depthWrite: false, fog: false,
    uniforms: { top: { value: new THREE.Color(top) }, horizon: { value: new THREE.Color(horizon) }, bottom: { value: new THREE.Color(bottom) } },
    vertexShader: "varying vec3 vP; void main(){ vP = normalize(position); gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); }",
    fragmentShader: "uniform vec3 top; uniform vec3 horizon; uniform vec3 bottom; varying vec3 vP; void main(){ float h = vP.y; vec3 c = h > 0.0 ? mix(horizon, top, pow(h, 0.6)) : mix(horizon, bottom, pow(-h, 0.4)); gl_FragColor = vec4(c, 1.0); }" });
  const dome = new THREE.Mesh(new THREE.SphereGeometry(400, 32, 16), mat);
  scene.add(dome);
  return dome;
}
// a rocky surface texture (noise), tiled
function rockTexture(base, seed, repeat = 8) {
  const c = document.createElement("canvas"); c.width = c.height = 256;
  const g = c.getContext("2d"), r = rng(seed), b = new THREE.Color(base);
  const img = g.createImageData(256, 256);
  for (let y = 0; y < 256; y++) for (let x = 0; x < 256; x++) {
    const n = noise3(x / 18, y / 18, seed) * 0.6 + noise3(x / 5, y / 5, seed + 3) * 0.4, k = 0.72 + n * 0.5 + (r() - 0.5) * 0.08, i = (y * 256 + x) * 4;
    img.data[i] = Math.min(255, b.r * 255 * k); img.data[i + 1] = Math.min(255, b.g * 255 * k); img.data[i + 2] = Math.min(255, b.b * 255 * k); img.data[i + 3] = 255;
  }
  g.putImageData(img, 0, 0);
  const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace; t.wrapS = t.wrapT = THREE.RepeatWrapping; t.repeat.set(repeat, repeat);
  return t;
}
function sun(scene, color, intensity, x, y, z, size = 30) {
  const l = new THREE.DirectionalLight(color, intensity);
  l.position.set(x, y, z);
  l.castShadow = true;
  l.shadow.mapSize.set(2048, 2048);
  Object.assign(l.shadow.camera, { left: -size, right: size, top: size, bottom: -size, near: 0.5, far: 200 });
  l.shadow.bias = -0.0005;
  scene.add(l);
  return l;
}
function camera(fov, x, y, z, tx, ty, tz) { const c = new THREE.PerspectiveCamera(fov, W / H, 0.05, 500); c.position.set(x, y, z); c.lookAt(tx, ty, tz); return c; }
function waferTexture(seed, good = true) {
  const c = document.createElement("canvas"); c.width = c.height = 1024;
  const g = c.getContext("2d");
  const grad = g.createLinearGradient(0, 0, 1024, 1024);
  grad.addColorStop(0, "#4a3f7a"); grad.addColorStop(0.35, "#2e6f8a"); grad.addColorStop(0.65, "#7a4f86"); grad.addColorStop(1, "#2f5a7a");
  g.fillStyle = "#1b2230"; g.fillRect(0, 0, 1024, 1024);
  g.save(); g.beginPath(); g.arc(512, 512, 506, 0, Math.PI * 2); g.clip();
  g.fillStyle = grad; g.fillRect(0, 0, 1024, 1024);
  const r = rng(seed), n = 22, s = 1024 / n;
  for (let i = 0; i < n; i++) for (let j = 0; j < n; j++) {
    const x = i * s, y = j * s;
    if (Math.hypot(x + s / 2 - 512, y + s / 2 - 512) > 490) continue;
    g.fillStyle = `rgba(${150 + r() * 60},${170 + r() * 50},${200 + r() * 40},0.22)`;
    g.fillRect(x + 3, y + 3, s - 6, s - 6);
    g.strokeStyle = "rgba(230,240,255,0.18)"; g.strokeRect(x + 3.5, y + 3.5, s - 7, s - 7);
    g.fillStyle = "rgba(255,255,255,0.10)"; g.fillRect(x + 8, y + 8, s * 0.35, s * 0.2);
  }
  g.restore();
  const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace; t.anisotropy = 8;
  return t;
}
function wafer(seed = 3, radius = 1.5) {
  const m = new THREE.MeshPhysicalMaterial({ map: waferTexture(seed), metalness: 0.55, roughness: 0.18, clearcoat: 1, clearcoatRoughness: 0.05, iridescence: 0.6, iridescenceIOR: 1.6 });
  const geo = new THREE.CylinderGeometry(radius, radius, 0.03, 128);
  const side = std(0x9aa3ad, 0.3, 0.9);
  const w = new THREE.Mesh(geo, [side, m, side]);
  w.castShadow = true; w.receiveShadow = true;
  return w;
}

// ------------------------------------------------------------------ explainer marks (the 2D layer)
const INK = "#f2f5fa", SOFT = "rgba(242,245,250,0.75)", TEAL = "#7EE8D8", AMBER = "#FFB347";
function roundRect(x, y, w, h, r) { ui.beginPath(); ui.moveTo(x + r, y); ui.arcTo(x + w, y, x + w, y + h, r); ui.arcTo(x + w, y + h, x, y + h, r); ui.arcTo(x, y + h, x, y, r); ui.arcTo(x, y, x + w, y, r); ui.closePath(); }
function label(x, y, text, sub, alpha = 1, color = INK) {
  ui.save(); ui.globalAlpha = alpha;
  ui.font = "700 34px -apple-system, Inter, sans-serif";
  const w1 = ui.measureText(text).width;
  ui.font = "500 24px -apple-system, Inter, sans-serif";
  const w2 = sub ? ui.measureText(sub).width : 0;
  const w = Math.max(w1, w2) + 40, h = sub ? 96 : 62;
  ui.fillStyle = "rgba(10,14,24,0.72)"; roundRect(x, y, w, h, 14); ui.fill();
  ui.strokeStyle = "rgba(126,232,216,0.55)"; ui.lineWidth = 2; ui.stroke();
  ui.fillStyle = color; ui.font = "700 34px -apple-system, Inter, sans-serif"; ui.textBaseline = "top"; ui.fillText(text, x + 20, y + 14);
  if (sub) { ui.fillStyle = SOFT; ui.font = "500 24px -apple-system, Inter, sans-serif"; ui.fillText(sub, x + 20, y + 58); }
  ui.restore();
  return { w, h };
}
function leader(ax, ay, bx, by, alpha = 1) {
  ui.save(); ui.globalAlpha = alpha; ui.strokeStyle = TEAL; ui.lineWidth = 3;
  ui.beginPath(); ui.moveTo(ax, ay); ui.lineTo(bx, by); ui.stroke();
  ui.fillStyle = TEAL; ui.beginPath(); ui.arc(ax, ay, 8, 0, Math.PI * 2); ui.fill();
  ui.restore();
}
function callout(p3, cam, text, sub, alpha, dx = 160, dy = -150) {
  const p = p3.clone().project(cam), x = (p.x * 0.5 + 0.5) * W, y = (-p.y * 0.5 + 0.5) * H;
  const lx = x + dx, ly = y + dy;
  leader(x, y, lx, ly + 30, alpha);
  label(lx, ly, text, sub, alpha);
}
function caption(text, alpha = 1) {
  if (!text || alpha <= 0) return;
  ui.save(); ui.globalAlpha = alpha;
  ui.font = "600 38px -apple-system, Inter, sans-serif"; ui.textAlign = "center"; ui.textBaseline = "middle";
  const w = ui.measureText(text).width + 60;
  ui.fillStyle = "rgba(10,14,24,0.6)"; roundRect(W / 2 - w / 2, H - 150, w, 70, 35); ui.fill();
  ui.fillStyle = INK; ui.fillText(text, W / 2, H - 115);
  ui.restore();
}
function subtitle(text) {
  if (!text) return;
  ui.save(); ui.font = "500 28px -apple-system, Inter, sans-serif"; ui.textAlign = "center"; ui.textBaseline = "bottom";
  const words = text.split(" "), lines = []; let line = "";
  for (const w of words) { const t = line ? line + " " + w : w; if (ui.measureText(t).width > 1500) { lines.push(line); line = w; } else line = t; }
  lines.push(line);
  lines.forEach((l, i) => { ui.fillStyle = "rgba(0,0,0,0.55)"; ui.fillText(l, W / 2 + 2, H - 30 - (lines.length - 1 - i) * 36 + 2); ui.fillStyle = "rgba(255,255,255,0.92)"; ui.fillText(l, W / 2, H - 30 - (lines.length - 1 - i) * 36); });
  ui.restore();
}
function scaleBar(x, y, text, frac, alpha = 1) {
  ui.save(); ui.globalAlpha = alpha; ui.strokeStyle = INK; ui.lineWidth = 4;
  const w = 260;
  ui.beginPath(); ui.moveTo(x, y); ui.lineTo(x + w, y); ui.moveTo(x, y - 12); ui.lineTo(x, y + 12); ui.moveTo(x + w, y - 12); ui.lineTo(x + w, y + 12); ui.stroke();
  ui.fillStyle = TEAL; ui.fillRect(x, y - 3, w * frac, 6);
  ui.fillStyle = INK; ui.font = "700 32px -apple-system, Inter, sans-serif"; ui.textBaseline = "bottom"; ui.fillText(text, x, y - 18);
  ui.restore();
}
function counter(x, y, head, value, alpha = 1) {
  ui.save(); ui.globalAlpha = alpha;
  ui.fillStyle = "rgba(10,14,24,0.72)"; roundRect(x, y, 420, 120, 16); ui.fill();
  ui.fillStyle = SOFT; ui.font = "600 24px -apple-system, Inter, sans-serif"; ui.textBaseline = "top"; ui.fillText(head.toUpperCase(), x + 22, y + 16);
  ui.fillStyle = TEAL; ui.font = "800 52px -apple-system, Inter, sans-serif"; ui.fillText(value, x + 22, y + 50);
  ui.restore();
}
function simFrame(alpha) {
  if (alpha <= 0) return;
  ui.save(); ui.globalAlpha = alpha; ui.strokeStyle = TEAL; ui.lineWidth = 6; ui.strokeRect(14, 14, W - 28, H - 28);
  ui.font = "700 24px -apple-system, Inter, sans-serif";
  const t = "SMT2020 MODEL · SIMULATED", w = ui.measureText(t).width + 30;
  ui.fillStyle = TEAL; roundRect(W - w - 40, 34, w, 42, 21); ui.fill();
  ui.fillStyle = "#0b1418"; ui.textBaseline = "middle"; ui.fillText(t, W - w - 25, 56);
  ui.restore();
}
function molecule(x, y, alpha) {
  ui.save(); ui.globalAlpha = alpha;
  const atom = (cx, cy, r, c, t) => { const g = ui.createRadialGradient(cx - r / 3, cy - r / 3, r / 6, cx, cy, r); g.addColorStop(0, "#fff"); g.addColorStop(0.3, c); g.addColorStop(1, "#111"); ui.fillStyle = g; ui.beginPath(); ui.arc(cx, cy, r, 0, Math.PI * 2); ui.fill(); ui.fillStyle = INK; ui.font = "700 22px -apple-system, Inter, sans-serif"; ui.textAlign = "center"; ui.textBaseline = "middle"; ui.fillText(t, cx, cy + r + 18); };
  ui.strokeStyle = SOFT; ui.lineWidth = 6; ui.beginPath(); ui.moveTo(x - 70, y + 20); ui.lineTo(x, y); ui.lineTo(x + 70, y + 20); ui.stroke();
  atom(x - 70, y + 20, 26, "#ff5a5a", "O"); atom(x + 70, y + 20, 26, "#ff5a5a", "O"); atom(x, y, 34, "#9aa3ad", "Si");
  ui.restore();
}

// ------------------------------------------------------------------ the scenes
const SCN = {};

SCN.open = () => {
  const scene = baseScene(0x030407);
  const cam = camera(30, 0, 0, 7, 0, 0, 0);
  const g = new THREE.Group(); scene.add(g);
  const grain = mesh(displace(new THREE.IcosahedronGeometry(1, 6), 0.35, 1.6, 4), std(0xb8955c, 0.9, 0.02));
  g.add(grain);
  const pts = []; const r = rng(7);
  for (let i = 0; i < 900; i++) { const v = new THREE.Vector3(r() - 0.5, r() - 0.5, r() - 0.5).normalize().multiplyScalar(1.06 + r() * 0.04); pts.push(v); }
  const lattice = new THREE.Points(new THREE.BufferGeometry().setFromPoints(pts), new THREE.PointsMaterial({ color: 0x7ee8d8, size: 0.035, transparent: true, opacity: 0, blending: THREE.AdditiveBlending, depthWrite: false }));
  g.add(lattice);
  const key = new THREE.DirectionalLight(0xffd9a8, 1.3); key.position.set(3, 2, 4); scene.add(key);
  const rim = new THREE.DirectionalLight(0x7ee8d8, 3.5); rim.position.set(-4, 1, -3); scene.add(rim);
  return { scene, camera: cam, focus: 6, bloom: 0.35, exposure: 0.85, update(t) {
    g.rotation.y = t * 0.25; g.rotation.x = 0.3 + t * 0.05;
    cam.position.z = lerp(7, 2.6, span(t, 0, 8)); cam.lookAt(0, 0, 0);
    lattice.material.opacity = span(t, 3.5, 6.5) * 0.9;
    this.focus = cam.position.z - 0.9;
  }, overlay(t) {
    const zooms = ["1 mm", "0.1 mm", "10 µm", "1 µm", "100 nm", "10 nm", "1 nm", "0.3 nm"];
    const k = Math.min(zooms.length - 1, Math.floor(span(t, 0.5, 7.5) * zooms.length));
    scaleBar(90, H - 110, zooms[k], 1, span(t, 0.3, 1.2));
    if (t > 5.6) { ui.save(); ui.globalAlpha = span(t, 5.6, 6.6); ui.fillStyle = INK; ui.font = "800 120px -apple-system, Inter, sans-serif"; ui.textAlign = "center"; ui.fillText("From Sand to Chip", W / 2, 230); ui.restore(); }
  } };
};

SCN.quarry = () => {
  const scene = baseScene(0xe7b48c, [90, 300]);
  sky(scene, 0x35507e, 0xffb98a, 0x5a4a3c);
  const cam = camera(38, 34, 22, 40, 0, -2, 0);
  const hemi = new THREE.HemisphereLight(0xffd8b0, 0x2e3440, 0.55); scene.add(hemi);
  sun(scene, 0xffb070, 4.2, 50, 18, 20, 45);
  const land = mesh(new THREE.PlaneGeometry(600, 600), std(0x8f8170, 1, 0, { map: rockTexture(0x9b8c79, 2, 60) }), 0, 1.9, 0, false); land.rotation.x = -Math.PI / 2;
  const hole = new THREE.Shape(); hole.absarc(0, 0, 300, 0, Math.PI * 2);
  const pitHole = new THREE.Path(); pitHole.absarc(0, 0, 31, 0, Math.PI * 2, true); hole.holes.push(pitHole);
  land.geometry = new THREE.ShapeGeometry(hole, 64); scene.add(land);
  // the pit: a stepped bowl turned on a lathe
  const prof = [];
  for (let i = 0; i <= 6; i++) { const r = 6 + i * 4.2, y = -12 + i * 2; prof.push(new THREE.Vector2(r, y), new THREE.Vector2(r + 0.01, y + 2)); }
  prof.unshift(new THREE.Vector2(0, -12));
  prof.push(new THREE.Vector2(80, 2));
  const pit = mesh(displace(new THREE.LatheGeometry(prof, 160), 0.035, 0.18, 2), std(0xa89884, 0.95, 0, { flatShading: true, side: THREE.DoubleSide, map: rockTexture(0xb5a690, 5, 6) }), 0, 0, 0, false);
  scene.add(pit);
  // quartz: a pile of white rock
  const rock = std(0xf2f1ec, 0.45, 0.02);
  const r = rng(11);
  for (let i = 0; i < 40; i++) { const s = 0.4 + r() * 0.9; const m = mesh(displace(new THREE.IcosahedronGeometry(s, 1), 0.4, 1.4, i), rock, 5.5 + r() * 4, -6 + s * 0.6, 13 + r() * 3.5); m.rotation.set(r() * 3, r() * 3, r() * 3); scene.add(m); }
  // an excavator
  const yel = std(0xf2b233, 0.45, 0.3), dark = std(0x2a2d33, 0.7, 0.4), glass = new THREE.MeshPhysicalMaterial({ color: 0x223040, roughness: 0.05, metalness: 0.2, transmission: 0.4 });
  const ex = new THREE.Group(); ex.position.set(11.5, -6, 10.5); ex.rotation.y = 2.3; ex.scale.setScalar(1.4); scene.add(ex);
  ex.add(mesh(new RoundedBoxGeometry(4.2, 1, 2.8, 4, 0.2), dark, 0, 0.5, 0));
  const house = new THREE.Group(); house.position.y = 1.1; ex.add(house);
  house.add(mesh(new RoundedBoxGeometry(3.4, 1.4, 2.4, 4, 0.2), yel, 0, 0.7, 0));
  house.add(mesh(new RoundedBoxGeometry(1.2, 1.2, 1.1, 4, 0.12), glass, 1.1, 1.9, 0.6));
  const boom = new THREE.Group(); boom.position.set(1.3, 1.4, -0.4); house.add(boom);
  boom.add(mesh(new THREE.BoxGeometry(4.6, 0.5, 0.5), yel, 2.2, 0, 0));
  const stick = new THREE.Group(); stick.position.set(4.4, 0, 0); boom.add(stick);
  stick.add(mesh(new THREE.BoxGeometry(0.4, 3.2, 0.4), yel, 0, -1.5, 0));
  const bucket = mesh(new THREE.BoxGeometry(1, 0.8, 1.2), dark, 0, -3.2, 0); stick.add(bucket);
  // a haul truck
  const truck = new THREE.Group(); truck.position.set(15, -6, 4); truck.rotation.y = -0.9; truck.scale.setScalar(1.3); scene.add(truck);
  truck.add(mesh(new RoundedBoxGeometry(6, 1.6, 3, 4, 0.25), yel, 0, 1.6, 0));
  truck.add(mesh(new RoundedBoxGeometry(2, 1.8, 3, 4, 0.2), yel, 3.6, 2.3, 0));
  const bed = mesh(new RoundedBoxGeometry(5.6, 1.4, 3.2, 3, 0.2), std(0xc9922a, 0.5, 0.3), -0.3, 3, 0); truck.add(bed);
  for (const [x, z] of [[-2, 1.6], [-2, -1.6], [2.4, 1.6], [2.4, -1.6]]) { const w = mesh(new THREE.CylinderGeometry(0.9, 0.9, 0.7, 24), dark, x, 0.9, z); w.rotation.x = Math.PI / 2; truck.add(w); }
  // the crusher and its conveyor up the bank
  const crusher = mesh(new RoundedBoxGeometry(4, 4, 4, 3, 0.3), std(0x5f7f88, 0.5, 0.6), 18, -3.5, -6); scene.add(crusher);
  const belt = mesh(new THREE.BoxGeometry(22, 0.3, 1.4), dark, 29, 1, -6); belt.rotation.z = 0.35; scene.add(belt);
  const gravel = new THREE.InstancedMesh(new THREE.IcosahedronGeometry(0.28, 0), rock, 40); scene.add(gravel);
  const tmp = new THREE.Object3D();
  return { scene, camera: cam, focus: 42, bloom: 0.25, aperture: 0.00012, update(t) {
    const a = Math.sin(t * 0.9);
    house.rotation.y = 0.5 + a * 0.6; boom.rotation.z = -0.25 + a * 0.15; stick.rotation.z = -0.4 - a * 0.2;
    const go = span(t, 8, 14);
    truck.position.set(lerp(15, 16.5, span(t, 0, 4)) + go * 3, -6, lerp(4, 6.5, span(t, 0, 4)) - go * 12);
    for (let i = 0; i < 40; i++) { const u = ((i / 40) + t * 0.05) % 1; tmp.position.set(19 + u * 20, -1.6 + u * 7.6, -6); tmp.rotation.set(i, i * 2, 0); tmp.updateMatrix(); gravel.setMatrixAt(i, tmp.matrix); }
    gravel.instanceMatrix.needsUpdate = true;
    cam.position.set(lerp(40, 30, span(t, 0, 14)), lerp(24, 17, span(t, 0, 14)), lerp(44, 34, span(t, 0, 14))); cam.lookAt(8, -6, 9);
    this.focus = cam.position.distanceTo(new THREE.Vector3(10, -6, 12));
  }, overlay(t) {
    const a = span(t, 3, 4.5) * (1 - span(t, 12.5, 13.5));
    const p = new THREE.Vector3(7.5, -5, 14.5).project(cam), x = (p.x * 0.5 + 0.5) * W, y = (-p.y * 0.5 + 0.5) * H;
    leader(x, y, 1260, 330, a); molecule(1440, 250, a); label(1300, 380, "quartz = SiO₂", "one silicon, two oxygen", a);
    if (t > 8) label(1180, 760, "crushed to gravel", null, span(t, 8, 9));
  } };
};

SCN.smelt = () => {
  const scene = baseScene(0x0c0a0a, [30, 70]);
  const cam = camera(36, 9, 6, 13, 0, 1.5, 0);
  scene.add(new THREE.HemisphereLight(0x6a5a50, 0x050505, 0.5));
  const fire = new THREE.PointLight(0xff7a2a, 120, 30, 2); fire.position.set(0, 3, 0); scene.add(fire);
  const shell = mesh(new THREE.CylinderGeometry(3.4, 3.8, 3.2, 48, 1, true), std(0x3b3f45, 0.55, 0.85, { side: THREE.DoubleSide }), 0, 1.6, 0); scene.add(shell);
  const melt = mesh(new THREE.CylinderGeometry(3.3, 3.3, 0.2, 48), glow(0xff8a2a, 4), 0, 2.4, 0, false); scene.add(melt);
  const els = [];
  for (let i = 0; i < 3; i++) { const a = (i / 3) * Math.PI * 2; const e = mesh(new THREE.CylinderGeometry(0.45, 0.45, 6, 24), std(0x222222, 0.6, 0.3), Math.cos(a) * 1.4, 5.5, Math.sin(a) * 1.4); scene.add(e); els.push(e); }
  const floor = mesh(new THREE.PlaneGeometry(80, 80), std(0x221d1a, 0.95), 0, 0, 0, false); floor.rotation.x = -Math.PI / 2; scene.add(floor);
  // the atoms beside: silicon, oxygen, carbon
  const atoms = new THREE.Group(); atoms.position.set(-6.5, 3.2, 1); scene.add(atoms);
  const si = std(0x9aa3ad, 0.3, 0.6), ox = std(0xe24b4b, 0.35, 0.1), ca = std(0x1c1c1c, 0.5, 0.1);
  const S = mesh(new THREE.SphereGeometry(0.55, 32, 16), si); atoms.add(S);
  const O = [mesh(new THREE.SphereGeometry(0.4, 32, 16), ox), mesh(new THREE.SphereGeometry(0.4, 32, 16), ox)]; O.forEach((o) => atoms.add(o));
  const C = [mesh(new THREE.SphereGeometry(0.42, 32, 16), ca), mesh(new THREE.SphereGeometry(0.42, 32, 16), ca)]; C.forEach((c) => atoms.add(c));
  const sparks = new THREE.Points(new THREE.BufferGeometry(), new THREE.PointsMaterial({ color: 0xffb35a, size: 0.12, blending: THREE.AdditiveBlending, transparent: true, depthWrite: false }));
  scene.add(sparks);
  return { scene, camera: cam, focus: 14, bloom: 1.1, update(t) {
    els.forEach((e, i) => (e.position.y = 5.5 - span(t, 0, 3) * 1.2 + Math.sin(t * 3 + i) * 0.05));
    melt.material.emissiveIntensity = 3.5 + Math.sin(t * 6) * 0.5;
    fire.intensity = 110 + Math.sin(t * 7.3) * 20;
    const k = span(t, 3, 8);
    O.forEach((o, i) => { const s = i ? 1 : -1; o.position.set(s * lerp(0.9, 2.2, k), lerp(0, 1.6, k), 0); });
    C.forEach((c, i) => { const s = i ? 1 : -1; c.position.set(s * lerp(2.6, 2.9, k), lerp(-0.4, 1.6, k), 0); });
    const pts = []; const r = rng(Math.floor(t * 12));
    for (let i = 0; i < 160; i++) { const a = r() * Math.PI * 2, h = r(); pts.push(new THREE.Vector3(Math.cos(a) * (0.5 + r() * 3), 2.5 + h * 4, Math.sin(a) * (0.5 + r() * 3))); }
    sparks.geometry.setFromPoints(pts);
    cam.position.set(lerp(9, 7, span(t, 0, 12)), 6, lerp(13, 11, span(t, 0, 12))); cam.lookAt(-1, 2.2, 0);
  }, overlay(t) {
    label(1260, 150, "about 2,000 °C", "inside the arc furnace", span(t, 1, 2));
    const p = new THREE.Vector3(-6.5, 4.6, 1);
    callout(p, cam, "carbon takes the oxygen", "CO gas leaves; silicon stays", span(t, 4, 5), -140, -260);
  } };
};

SCN.purify = () => {
  const scene = baseScene(0x0b1220, [20, 60]);
  const cam = camera(34, 0, 3, 13, 0, 3, 0);
  scene.add(new THREE.HemisphereLight(0x9fc6ff, 0x101520, 0.7));
  sun(scene, 0xffffff, 1.5, 5, 10, 6, 10);
  const colGeo = new THREE.CylinderGeometry(1.6, 1.6, 7, 64, 1, true);
  const col = mesh(colGeo, new THREE.MeshPhysicalMaterial({ color: 0xcfe6ff, roughness: 0.05, metalness: 0, clearcoat: 1, transparent: true, opacity: 0.16, side: THREE.DoubleSide, depthWrite: false }), 0, 3.5, 0, false); scene.add(col);
  for (const y of [0, 7]) scene.add(mesh(new THREE.CylinderGeometry(1.8, 1.8, 0.3, 64), std(0x8a96a6, 0.3, 0.9), 0, y, 0));
  const gas = new THREE.Points(new THREE.BufferGeometry(), new THREE.PointsMaterial({ color: 0xd8f3ff, size: 0.16, transparent: true, opacity: 1, blending: THREE.AdditiveBlending, depthWrite: false })); scene.add(gas);
  const bad = new THREE.Points(new THREE.BufferGeometry(), new THREE.PointsMaterial({ color: 0xff8a4c, size: 0.16, transparent: true, depthWrite: false })); scene.add(bad);
  const rods = [];
  for (let i = 0; i < 3; i++) { const r = mesh(displace(new THREE.CylinderGeometry(0.28, 0.28, 1, 24, 8), 0.12, 3, i), std(0x8f979f, 0.75, 0.5), 3.6 + i * 0.8, 0.5, -0.5); scene.add(r); rods.push(r); }
  const floor = mesh(new THREE.PlaneGeometry(60, 60), std(0x141a24, 0.9), 0, -0.15, 0, false); floor.rotation.x = -Math.PI / 2; scene.add(floor);
  return { scene, camera: cam, focus: 13, bloom: 0.8, update(t) {
    const a = [], b = [], r = rng(5);
    for (let i = 0; i < 1600; i++) { const ph = r() * 6.28, h = (r() + t * 0.12) % 1; const rr = 0.3 + r() * 1.1; a.push(new THREE.Vector3(Math.cos(ph + t * 1.4 + h * 8) * rr, 0.3 + h * 6.4, Math.sin(ph + t * 1.4 + h * 8) * rr)); }
    const nb = Math.round(40 * (1 - span(t, 0, 10)));
    for (let i = 0; i < nb; i++) { const ph = r() * 6.28, h = r(); b.push(new THREE.Vector3(Math.cos(ph + t) * 1.3, 0.5 + h * 6, Math.sin(ph + t) * 1.3)); }
    gas.geometry.setFromPoints(a); bad.geometry.setFromPoints(b.length ? b : [new THREE.Vector3(0, -9, 0)]);
    rods.forEach((rd, i) => { const h = 0.2 + span(t, 2 + i, 11) * 4; rd.scale.y = h; rd.position.y = h / 2; });
    cam.position.set(Math.sin(t * 0.08) * 4, 3 + t * 0.12, 13); cam.lookAt(1, 3, 0);
  }, overlay(t) {
    const vals = ["99%", "99.99%", "99.9999%", "99.9999999%"];
    counter(110, 110, "purity", vals[Math.min(3, Math.floor(span(t, 0.5, 10) * 4))], span(t, 0.2, 1));
    if (t > 9) label(1300, 830, "one stray atom in a billion", null, span(t, 9, 10));
  } };
};

SCN.crystal = () => {
  const scene = baseScene(0x0a0c12, [25, 70]);
  const cam = camera(32, 7, 3, 12, 0, 2.5, 0);
  scene.add(new THREE.HemisphereLight(0x8090a0, 0x080808, 0.6));
  const heat = new THREE.PointLight(0xffa04a, 30, 25, 2); heat.position.set(0, 1.4, 1.5); scene.add(heat);
  sun(scene, 0xcfe0ff, 1.2, -6, 12, 6, 10);
  const cru = mesh(new THREE.LatheGeometry([new THREE.Vector2(0, 0), new THREE.Vector2(2.2, 0), new THREE.Vector2(2.4, 0.3), new THREE.Vector2(2.4, 1.4), new THREE.Vector2(2.25, 1.4), new THREE.Vector2(2.1, 0.25), new THREE.Vector2(0, 0.25)], 64), std(0xe9e4da, 0.4, 0.05)); scene.add(cru);
  const melt = mesh(new THREE.CylinderGeometry(2.1, 2.1, 0.1, 64), glow(0xff9a4a, 1.4), 0, 1.15, 0, false); scene.add(melt);
  const prof = [new THREE.Vector2(0.04, 0), new THREE.Vector2(1.5, 0), new THREE.Vector2(1.5, 5.4), new THREE.Vector2(1.2, 5.9), new THREE.Vector2(0.4, 6.3), new THREE.Vector2(0.08, 6.5)];
  const ingot = mesh(new THREE.LatheGeometry(prof, 96), std(0xb9c2cc, 0.22, 0.95)); scene.add(ingot);
  const rod = mesh(new THREE.CylinderGeometry(0.06, 0.06, 12, 12), std(0xcccccc, 0.3, 0.9), 0, 0, 0); scene.add(rod);
  // a person for scale
  const person = new THREE.Group(); person.position.set(-3.6, 0, 1); scene.add(person);
  const skin = std(0x5f6b78, 0.8);
  person.add(mesh(new THREE.CapsuleGeometry(0.28, 1.0, 6, 16), skin, 0, 0.95, 0));
  person.add(mesh(new THREE.SphereGeometry(0.22, 24, 16), skin, 0, 1.85, 0));
  const floor = mesh(new THREE.PlaneGeometry(60, 60), std(0x15181f, 0.9), 0, 0, 0, false); floor.rotation.x = -Math.PI / 2; scene.add(floor);
  return { scene, camera: cam, focus: 12, bloom: 0.45, exposure: 0.9, update(t) {
    const lift = span(t, 1, 14) * 4.6;
    ingot.position.y = 1.15 + lift - 5.4 * span(t, 1, 14) ; ingot.scale.y = Math.max(0.02, span(t, 1, 14));
    ingot.position.y = 1.15 + lift * 0.15; ingot.rotation.y = t * 0.5;
    rod.position.y = ingot.position.y + 6.5 * ingot.scale.y + 6;
    heat.intensity = 28 + Math.sin(t * 5) * 3;
    const k = span(t, 8, 15);
    cam.position.set(lerp(3.5, 9, k), lerp(1.8, 4, k), lerp(4.5, 14, k)); cam.lookAt(0, lerp(1.4, 3.2, k), 0);
    this.focus = cam.position.distanceTo(new THREE.Vector3(0, 2, 0));
  }, overlay(t) {
    label(110, 110, "silicon melts at about 1,414 °C", null, span(t, 1, 2));
    if (t > 9) callout(new THREE.Vector3(-3.6, 2.1, 1), cam, "a person, for scale", "the ingot is about as tall", span(t, 9.5, 10.5), -60, -230);
  } };
};

SCN.slice = () => {
  const scene = baseScene(0x10141c, [20, 60]);
  const cam = camera(30, 6, 3.4, 10, 0, 1.4, 0);
  scene.add(new THREE.HemisphereLight(0xdde7ff, 0x202028, 0.8));
  sun(scene, 0xffffff, 2.2, 6, 10, 8, 10);
  const metal = std(0xb9c2cc, 0.25, 0.95), mirror = std(0xe8eef5, 0.03, 1.0);
  const ingot = mesh(new THREE.CylinderGeometry(1.2, 1.2, 6, 96), metal, -2, 1.4, 0); ingot.rotation.z = Math.PI / 2; scene.add(ingot);
  const wire = mesh(new THREE.BoxGeometry(0.02, 4, 0.02), glow(0xbfe9ff, 6), 0, 1.4, 0, false); scene.add(wire);
  const discs = [];
  for (let i = 0; i < 6; i++) { const d = mesh(new THREE.CylinderGeometry(1.2, 1.2, 0.05, 96), mirror, 1.2 + i * 0.4, 1.4, 0); d.rotation.z = Math.PI / 2; scene.add(d); discs.push(d); }
  const box = mesh(new RoundedBoxGeometry(2.8, 3, 3.2, 4, 0.25), new THREE.MeshPhysicalMaterial({ color: 0xcfe9f2, transmission: 0.7, roughness: 0.15, thickness: 0.3, transparent: true }), 5.6, 1.5, -1.5); scene.add(box);
  const floor = mesh(new THREE.PlaneGeometry(60, 60), std(0x1b202a, 0.5, 0.2), 0, 0, 0, false); floor.rotation.x = -Math.PI / 2; scene.add(floor);
  return { scene, camera: cam, focus: 9, bloom: 0.6, update(t) {
    wire.position.y = 1.4 + Math.sin(t * 8) * 0.05;
    discs.forEach((d, i) => { const k = span(t, 1 + i * 0.8, 2 + i * 0.8); d.position.x = lerp(1.2 + i * 0.4, 2.4 + i * 0.5, k); });
    const hero = discs[5], k = span(t, 6, 9);
    hero.rotation.z = lerp(Math.PI / 2, 0.15, k); hero.rotation.x = lerp(0, -1.2, k); hero.position.y = lerp(1.4, 2.2, k);
    const s = span(t, 9.5, 12); hero.position.x = lerp(hero.position.x, 5.6, s); hero.position.y = lerp(hero.position.y, 1.5, s); hero.position.z = lerp(0, -1.5, s);
    cam.position.set(lerp(6, 4.5, span(t, 0, 12)), 3.4, lerp(10, 8, span(t, 0, 12))); cam.lookAt(2, 1.6, 0);
  }, overlay(t) {
    callout(new THREE.Vector3(3.4, 2.4, 0), cam, "about 0.78 mm thick", "thinner than a coin", span(t, 3, 4), 120, -240);
    if (t > 8) label(1240, 820, "a speck of dust is a boulder", "at this scale", span(t, 8, 9));
  } };
};

SCN.arrive = () => {
  const scene = baseScene(0x060b0e, [30, 90]);
  const cam = camera(36, 14, 7, 16, 0, 3, -4);
  scene.add(new THREE.HemisphereLight(0x4a7a80, 0x050808, 0.5));
  sun(scene, 0x9fe8e0, 0.8, 10, 20, 10, 25);
  const bld = mesh(new THREE.BoxGeometry(20, 8, 14), std(0x172429, 0.7, 0.3), 0, 4, -10); scene.add(bld);
  const seam = glow(0x7ee8d8, 3);
  for (let i = 0; i < 8; i++) scene.add(mesh(new THREE.BoxGeometry(20.05, 0.06, 0.06), seam, 0, 0.5 + i, -3, false));
  const door = mesh(new THREE.BoxGeometry(3, 3.4, 0.2), glow(0x7ee8d8, 1.5), 0, 5.2, -2.95, false); scene.add(door);
  const rail = mesh(new THREE.BoxGeometry(0.4, 0.2, 30), std(0x5f7f88, 0.4, 0.8), 0, 7.2, 8); scene.add(rail);
  const box = mesh(new RoundedBoxGeometry(1.6, 1.6, 1.8, 4, 0.18), new THREE.MeshPhysicalMaterial({ color: 0xcfe9f2, transmission: 0.6, roughness: 0.2, thickness: 0.3 }), 0, 6.1, 18); scene.add(box);
  const floor = mesh(new THREE.PlaneGeometry(120, 120), std(0x0b1113, 0.85), 0, 0, 0, false); floor.rotation.x = -Math.PI / 2; scene.add(floor);
  return { scene, camera: cam, focus: 16, bloom: 0.9, update(t) {
    box.position.z = lerp(18, -2, span(t, 0, 9));
    cam.position.set(lerp(14, 6, span(t, 0, 10)), lerp(7, 6.5, span(t, 0, 10)), lerp(16, 8, span(t, 0, 10)) + box.position.z * 0.3); cam.lookAt(0, 6, box.position.z - 2);
    this.focus = cam.position.distanceTo(box.position);
  }, overlay(t) {
    simFrame(span(t, 3, 4.5));
    callout(new THREE.Vector3(0, 6.8, 0).add(new THREE.Vector3(0, 0, 0)).setZ(lerp(18, -2, span(t, 0, 9))), cam, "a lot: 25 wafers", "in a sealed box", span(t, 1.5, 2.5), 140, -200);
  } };
};

SCN.loop = () => {
  const scene = baseScene(0x07090f, [15, 40]);
  const cam = camera(30, 0, 3.2, 5.2, 0, 0.1, 0);
  scene.add(new THREE.HemisphereLight(0x8fb0d0, 0x050505, 0.6));
  sun(scene, 0xffffff, 1.6, 3, 8, 4, 5);
  const w = wafer(9, 1.5); scene.add(w);
  const layers = new THREE.Group(); scene.add(layers);
  const COLORS = [0x7cc576, 0xd9a95a, 0x5fb0d9, 0xa98be8, 0xe07b4f, 0x9aa7b5];
  for (let i = 0; i < 24; i++) { const l = mesh(new THREE.CylinderGeometry(1.5, 1.5, 0.013, 128, 1, true), std(COLORS[i % 6], 0.35, 0.3), 0, 0.02 + i * 0.013, 0, false); l.visible = false; layers.add(l); }
  const beam = mesh(new THREE.ConeGeometry(1.4, 3, 64, 1, true), new THREE.MeshBasicMaterial({ color: 0xa98be8, transparent: true, opacity: 0.25, blending: THREE.AdditiveBlending, side: THREE.DoubleSide, depthWrite: false }), 0, 1.6, 0, false); beam.rotation.x = Math.PI; scene.add(beam);
  const mask = mesh(new THREE.BoxGeometry(3.2, 0.04, 3.2), std(0x222a33, 0.3, 0.8, { transparent: true, opacity: 0.8 }), 0, 3.1, 0); scene.add(mask);
  const plasma = new THREE.Points(new THREE.BufferGeometry(), new THREE.PointsMaterial({ color: 0xd46ab0, size: 0.04, blending: THREE.AdditiveBlending, transparent: true, depthWrite: false })); scene.add(plasma);
  const water = mesh(new THREE.PlaneGeometry(3.2, 3.2), new THREE.MeshPhysicalMaterial({ color: 0x9fd6ff, transmission: 1, roughness: 0.02, thickness: 0.05, transparent: true, opacity: 0.6 }), 0, 0.5, 0, false); water.rotation.x = -Math.PI / 2; scene.add(water);
  const scan = mesh(new THREE.BoxGeometry(3.2, 0.01, 0.03), glow(0x4fe3a3, 6), 0, 0.4, 0, false); scene.add(scan);
  const tower = new THREE.Group(); scene.add(tower);
  for (let i = 0; i < 60; i++) { const f = mesh(new THREE.BoxGeometry(0.9, 0.04, 0.9), std(COLORS[i % 6], 0.3, 0.5), 0, i * 0.045, 0); f.visible = false; tower.add(f); }
  const stageOf = (t) => (t < 12 ? [Math.floor(t / 2) % 6, (t % 2) / 2, 1] : t < 18 ? [Math.floor((t - 12) / 1) % 6, (t - 12) % 1, 2] : [-1, 0, 3]);
  return { scene, camera: cam, focus: 5.5, bloom: 1.0, update(t) {
    const [st, u, lap] = stageOf(t);
    w.rotation.y = t * 0.2;
    beam.visible = st === 1; mask.visible = st === 1;
    plasma.visible = st === 2;
    if (st === 2) { const r = rng(Math.floor(t * 20)), p = []; for (let i = 0; i < 900; i++) { const a = r() * 6.28, rr = Math.sqrt(r()) * 1.4; p.push(new THREE.Vector3(Math.cos(a) * rr, 0.08 + r() * 1.6, Math.sin(a) * rr)); } plasma.geometry.setFromPoints(p); }
    water.visible = st === 4; water.position.x = lerp(-3, 3, u);
    scan.visible = st === 5; scan.position.z = lerp(-1.5, 1.5, u);
    const done = Math.min(24, Math.floor(t / 2) + (t > 12 ? Math.floor(t - 12) : 0));
    layers.children.forEach((l, i) => (l.visible = i < done && lap < 3));
    w.position.y = done * 0.013;
    w.visible = lap < 3;
    tower.children.forEach((f, i) => (f.visible = lap === 3 && i < Math.floor(span(t, 18, 34) * 60)));
    if (lap < 3) { cam.position.set(Math.sin(t * 0.3) * 4.8, 3.2, Math.cos(t * 0.3) * 4.8); cam.lookAt(0, 0.1, 0); }
    else { const k = span(t, 18, 36); cam.position.set(4 * Math.cos(k * 3), lerp(1.2, 3.6, k), 4 * Math.sin(k * 3)); cam.lookAt(0, lerp(0.4, 1.6, k), 0); }
    this.focus = cam.position.length();
  }, overlay(t) {
    const names = ["thin film", "print with light", "etch", "implant", "wash", "check"];
    const [st, , lap] = stageOf(t);
    simFrame(1);
    if (st >= 0) label(110, 110, names[st], lap === 1 ? "lap one" : "lap two, faster", 1);
    else label(110, 110, "a city of layers", "one floor at a time", span(t, 18, 19));
    const step = Math.min(583, Math.round(t < 18 ? t * 2 : 36 + span(t, 18, 34) * 547));
    counter(W - 520, H - 300, "step", `${step} of 583`, 1);
  } };
};

SCN.done = () => {
  const scene = baseScene(0x05070c, [15, 40]);
  const cam = camera(32, 0, 1.2, 6, 0, 0.8, 0);
  scene.add(new THREE.HemisphereLight(0xa0b8ff, 0x050505, 0.6));
  const key = new THREE.SpotLight(0xffffff, 80, 20, 0.6, 0.5); key.position.set(3, 5, 5); scene.add(key);
  const w = wafer(21, 1.5); scene.add(w);
  return { scene, camera: cam, focus: 6, bloom: 0.7, update(t) {
    const k = span(t, 0, 4);
    w.position.y = lerp(0, 1, k); w.rotation.x = lerp(0, Math.PI / 2 - 0.15, k); w.rotation.z = t * 0.05;
    const d = span(t, 6, 10);
    cam.position.set(lerp(0, 0.25, d), lerp(1.2, 1.05, d), lerp(6, 1.2, d)); cam.lookAt(lerp(0, 0.25, d), 1, 0);
    this.focus = cam.position.distanceTo(new THREE.Vector3(0, 1, 0));
  }, overlay(t) {
    simFrame(1 - span(t, 8, 9.5));
    const zooms = ["30 cm", "1 cm", "1 mm", "100 µm", "10 µm"];
    scaleBar(90, H - 110, zooms[Math.min(4, Math.floor(span(t, 5, 10) * 5))], 1, span(t, 4.5, 5.5));
    label(1260, 140, "one die", "millions to billions of switches", span(t, 3, 4));
    if (t > 8.2) label(W / 2 - 200, 60, "leaving the simulator", null, span(t, 8.2, 9));
  } };
};

function dieGrid(scene, n, size, gap, y = 0.02) {
  const g = new THREE.InstancedMesh(new RoundedBoxGeometry(size, 0.04, size, 2, 0.01), std(0x2f6f8a, 0.25, 0.6), n * n);
  g.castShadow = true; scene.add(g);
  const base = [];
  for (let i = 0; i < n; i++) for (let j = 0; j < n; j++) base.push([(i - (n - 1) / 2) * (size + gap), y, (j - (n - 1) / 2) * (size + gap)]);
  return { g, base };
}

SCN.probe = () => {
  const scene = baseScene(0x07090d, [12, 30]);
  const cam = camera(32, 0, 5, 4.5, 0, 0, 0);
  scene.add(new THREE.HemisphereLight(0xc0d0e0, 0x050505, 0.7));
  sun(scene, 0xffffff, 1.8, 2, 8, 3, 4);
  const { g, base } = dieGrid(scene, 7, 0.36, 0.04);
  const tmp = new THREE.Object3D(), col = new THREE.Color();
  base.forEach((b, i) => { tmp.position.set(...b); tmp.updateMatrix(); g.setMatrixAt(i, tmp.matrix); });
  const card = new THREE.Group(); scene.add(card);
  card.add(mesh(new THREE.BoxGeometry(1.2, 0.08, 1.2), std(0x3a4450, 0.5, 0.7), 0, 0.6, 0));
  for (let i = 0; i < 9; i++) card.add(mesh(new THREE.CylinderGeometry(0.004, 0.012, 0.55, 6), std(0xd8c070, 0.2, 1), ((i % 3) - 1) * 0.12, 0.3, (Math.floor(i / 3) - 1) * 0.12));
  return { scene, camera: cam, focus: 6, bloom: 1.0, update(t) {
    const k = Math.min(48, Math.floor(span(t, 0.5, 7) * 49));
    const cur = Math.min(48, k);
    card.position.set(base[cur][0], lerp(0.6, 0.06, Math.abs(Math.sin(t * 6))), base[cur][2]);
    base.forEach((b, i) => { const passed = i < k; const bad = i === 23; col.set(!passed ? 0x2f6f8a : bad ? 0xff3b3b : 0x2fd18a); g.setColorAt(i, col); });
    g.instanceColor.needsUpdate = true;
    cam.position.set(Math.sin(t * 0.1) * 1.2, 5, 4.5); cam.lookAt(0, 0, 0);
  }, overlay(t) {
    const k = Math.min(49, Math.floor(span(t, 0.5, 7) * 49));
    counter(110, 110, "tested", `${k} dies · ${k > 23 ? 1 : 0} failed`, span(t, 0, 1));
    label(1250, 780, "yield: the share that passes", "this simulator leaves yield out", span(t, 4, 5));
  } };
};

SCN.dice = () => {
  const scene = baseScene(0x07090d, [12, 30]);
  const cam = camera(30, 3, 4, 4, 0, 0, 0);
  scene.add(new THREE.HemisphereLight(0xc0d0e0, 0x050505, 0.7));
  sun(scene, 0xffffff, 1.8, 2, 8, 3, 4);
  const { g, base } = dieGrid(scene, 7, 0.36, 0.04);
  const tmp = new THREE.Object3D();
  const laser = mesh(new THREE.BoxGeometry(3.2, 0.01, 0.01), glow(0xff6a3a, 8), 0, 0.06, 0, false); scene.add(laser);
  return { scene, camera: cam, focus: 5.5, bloom: 1.1, update(t) {
    const k = span(t, 3, 7);
    base.forEach((b, i) => { tmp.position.set(b[0] * (1 + k * 0.6), b[1], b[2] * (1 + k * 0.6)); tmp.rotation.y = (i % 5 - 2) * 0.02 * k; tmp.updateMatrix(); g.setMatrixAt(i, tmp.matrix); });
    g.instanceMatrix.needsUpdate = true;
    laser.visible = t < 3.4; laser.position.z = lerp(-1.4, 1.4, span(t, 0, 3));
    cam.position.set(lerp(3, 2.2, span(t, 0, 8)), 4, 4); cam.lookAt(0, 0, 0);
  }, overlay(t) {
    callout(new THREE.Vector3(0.2, 0.05, 0), cam, "the streets between dies", "cut by a saw or a laser", span(t, 0.8, 1.8), 160, -260);
  } };
};

SCN.package = () => {
  const scene = baseScene(0x0a0d12, [12, 30]);
  const cam = camera(30, 3.6, 2.6, 4.6, 0, 0.6, 0);
  scene.add(new THREE.HemisphereLight(0xd0dcf0, 0x080808, 0.7));
  sun(scene, 0xffffff, 2, 3, 6, 4, 4);
  const board = mesh(new RoundedBoxGeometry(2.4, 0.08, 2.4, 3, 0.03), std(0x1f5f3a, 0.5, 0.2), 0, 0, 0); scene.add(board);
  const die = mesh(new RoundedBoxGeometry(0.8, 0.06, 0.8, 2, 0.01), std(0x2f6f8a, 0.2, 0.7), 0, 0.1, 0); scene.add(die);
  const wires = new THREE.Group(); scene.add(wires);
  const gold = std(0xe2b85a, 0.2, 1);
  for (let i = 0; i < 12; i++) { const a = (i / 12) * Math.PI * 2; const p0 = new THREE.Vector3(Math.cos(a) * 0.35, 0.13, Math.sin(a) * 0.35), p2 = new THREE.Vector3(Math.cos(a) * 0.9, 0.04, Math.sin(a) * 0.9); const p1 = p0.clone().lerp(p2, 0.5).setY(0.45); wires.add(mesh(new THREE.TubeGeometry(new THREE.QuadraticBezierCurve3(p0, p1, p2), 24, 0.008, 6), gold, 0, 0, 0)); }
  const lid = mesh(new RoundedBoxGeometry(1.4, 0.18, 1.4, 3, 0.04), std(0x15171b, 0.45, 0.2), 0, 0.4, 0); scene.add(lid);
  return { scene, camera: cam, focus: 5, bloom: 0.4, update(t) {
    const ex = 1 - span(t, 4, 7);
    die.position.y = 0.1 + ex * 0.5; wires.position.y = ex * 0.9; lid.position.y = 0.32 + ex * 1.6;
    cam.position.set(lerp(3.6, 3, span(t, 0, 8)), 2.6, 4.6); cam.lookAt(0, 0.6 * ex + 0.2, 0);
  }, overlay(t) {
    const a = span(t, 0.5, 1.5) * (1 - span(t, 3.6, 4.4));
    const ex = 1 - span(t, 4, 7);
    callout(new THREE.Vector3(0, 0.32 + ex * 1.6, 0), cam, "lid", null, a, 220, -60);
    callout(new THREE.Vector3(0.6, 0.35 + ex * 0.9, 0), cam, "wires, finer than a hair", null, a, 240, -20);
    callout(new THREE.Vector3(0, 0.12 + ex * 0.5, 0.3), cam, "the die", null, a, 220, 40);
    callout(new THREE.Vector3(-1, 0, 1), cam, "the board", null, a, -360, 60);
  } };
};

SCN.ship = () => {
  const scene = baseScene(0x0a0d12, [15, 40]);
  const cam = camera(32, 0, 4.4, 6, 0, 0.3, 0);
  scene.add(new THREE.HemisphereLight(0xd0dcf0, 0x080808, 0.7));
  sun(scene, 0xffffff, 2, 2, 7, 4, 6);
  const chips = new THREE.InstancedMesh(new RoundedBoxGeometry(0.3, 0.06, 0.3, 2, 0.02), std(0x15171b, 0.45, 0.2), 30); chips.castShadow = true; scene.add(chips);
  const bins = [-1.6, 0, 1.6].map((x, i) => { const b = mesh(new RoundedBoxGeometry(1.2, 0.4, 1, 3, 0.05), std([0x2fd18a, 0x7ee8d8, 0x8fa9a6][i], 0.5, 0.2, { transparent: true, opacity: 0.6 }), x, 0.2, -1.4); scene.add(b); return b; });
  const phone = mesh(new RoundedBoxGeometry(0.9, 1.8, 0.08, 4, 0.08), std(0x1a1c20, 0.3, 0.6), 2.0, 1.0, 0.4); phone.rotation.y = -0.5; scene.add(phone);
  const screen = mesh(new THREE.PlaneGeometry(0.8, 1.66), glow(0x7ee8d8, 0), 2.0, 1.0, 0.45, false); screen.rotation.y = -0.5; scene.add(screen);
  const tmp = new THREE.Object3D();
  return { scene, camera: cam, focus: 6.5, bloom: 0.9, update(t) {
    for (let i = 0; i < 30; i++) {
      const sx = ((i % 10) - 4.5) * 0.36, sz = Math.floor(i / 10) * 0.36 + 0.4, bin = (i * 7) % 3;
      const k = span(t, 1 + i * 0.08, 2.5 + i * 0.08);
      tmp.position.set(lerp(sx, [-1.6, 0, 1.6][bin] + ((i % 4) - 1.5) * 0.2, k), 0.05 + Math.sin(k * Math.PI) * 0.6 + k * 0.35, lerp(sz, -1.4, k));
      tmp.updateMatrix(); chips.setMatrixAt(i, tmp.matrix);
    }
    chips.instanceMatrix.needsUpdate = true;
    screen.material.emissiveIntensity = span(t, 7, 8) * 2.5;
    cam.position.set(lerp(0.3, 1.2, span(t, 6, 10)), lerp(3.6, 2.4, span(t, 6, 10)), lerp(5.2, 4.2, span(t, 6, 10))); cam.lookAt(lerp(0.2, 1.4, span(t, 6, 10)), 0.4, -0.2);
  }, overlay(t) {
    const names = ["fastest", "fast", "standard"];
    names.forEach((n, i) => { const p = new THREE.Vector3([-1.6, 0, 1.6][i], 0.6, -1.4).project(cam); label((p.x * 0.5 + 0.5) * W - 70, (-p.y * 0.5 + 0.5) * H - 150, n, null, span(t, 2.5, 3.5) * (1 - span(t, 8, 9))); });
    if (t > 8.5) { ui.save(); ui.globalAlpha = span(t, 8.5, 9.5); ui.fillStyle = INK; ui.font = "800 64px -apple-system, Inter, sans-serif"; ui.textAlign = "center"; ui.fillText("Fab Gym", W / 2, 180); ui.font = "500 26px -apple-system, Inter, sans-serif"; ui.fillStyle = SOFT; ui.fillText("The fab's part runs on the SMT2020 model, a published research model of a wafer fab. The rest is general knowledge.", W / 2, 230); ui.restore(); }
  } };
};

// ------------------------------------------------------------------ rendering
const built = {};
let composer = null, renderPass, bokeh, bloom;
function get(key) { if (!built[key]) built[key] = SCN[key](); return built[key]; }
function ensureComposer(sc) {
  if (!composer) {
    composer = new EffectComposer(renderer);
    composer.setPixelRatio(1); composer.setSize(W, H);
    renderPass = new RenderPass(sc.scene, sc.camera); composer.addPass(renderPass);
    bokeh = new BokehPass(sc.scene, sc.camera, { focus: sc.focus, aperture: 0.00025, maxblur: 0.008 }); composer.addPass(bokeh);
    bloom = new UnrealBloomPass(new THREE.Vector2(W, H), 0.6, 0.5, 0.82); composer.addPass(bloom);
    composer.addPass(new OutputPass());
  }
  renderPass.scene = sc.scene; renderPass.camera = sc.camera;
  bokeh.scene = sc.scene; bokeh.camera = sc.camera;
}
function frame(key, t, opts = {}) {
  const sc = get(key);
  sc.update(t);
  ensureComposer(sc);
  bokeh.uniforms.focus.value = sc.focus;
  bokeh.uniforms.aperture.value = sc.aperture ?? 0.00025;
  bokeh.uniforms.aspect.value = W / H;
  bloom.strength = sc.bloom ?? 0.6;
  renderer.toneMappingExposure = sc.exposure ?? 1.0;
  composer.render();
  ui.clearRect(0, 0, W, H);
  sc.overlay?.(t);
  const s = FS.SCENES.find((x) => x.key === key);
  if (opts.subs !== false) subtitle(s.say);
  if (opts.fades) { const a = FS.fade(s, t); if (a > 0) { ui.fillStyle = `rgba(0,0,0,${a.toFixed(3)})`; ui.fillRect(0, 0, W, H); } }
}
// one composited frame (the 3D picture and the explainer layer) as a JPEG
async function jpeg(width) {
  const c = document.createElement("canvas"); c.width = width; c.height = Math.round((width * H) / W);
  const g = c.getContext("2d"); g.drawImage(glCanvas, 0, 0, c.width, c.height); g.drawImage(uiCanvas, 0, 0, c.width, c.height);
  return new Promise((r) => c.toBlob(r, "image/jpeg", 0.92));
}
async function save(folder, name, width = 1280) {
  const c = document.createElement("canvas"); c.width = width; c.height = Math.round((width * H) / W);
  const g = c.getContext("2d"); g.drawImage(glCanvas, 0, 0, c.width, c.height); g.drawImage(uiCanvas, 0, 0, c.width, c.height);
  const blob = await new Promise((r) => c.toBlob(r, name.endsWith(".png") ? "image/png" : "image/jpeg", 0.9));
  const res = await fetch(`/save/${folder}/${name}`, { method: "POST", body: blob });
  if (!res.ok) throw new Error(`save ${name}: ${res.status}`);
}
const q = new URLSearchParams(location.search), status = document.getElementById("status");
(async () => {
  try {
    if (q.get("stills")) {
      for (const [i, s] of FS.SCENES.entries()) {
        frame(s.key, s.still);
        await save("stills", `${String(i).padStart(2, "0")}-${s.key}.jpg`);
        status.textContent = `saved ${i + 1} of ${FS.SCENES.length}`;
      }
      status.textContent = "stills done"; document.title = "stills done";
    } else if (q.get("frames")) {
      // the cut: every frame streamed to ffmpeg through film/serve.py (?pipe=name), or saved as files
      const fps = +(q.get("fps") || 30), last = Math.round(FS.total() * fps) - 1;
      const [a, b] = q.get("frames") === "all" ? [0, last] : q.get("frames").split("-").map(Number);
      const pipe = q.get("pipe"), subs = q.get("subs") !== "0";
      for (let f = a; f <= b; f++) {
        const { scene, t } = FS.at(f / fps);
        frame(scene.key, t, { subs, fades: true });
        if (pipe) { const r = await fetch(`/pipe/${pipe}/frame`, { method: "POST", body: await jpeg(1920) }); if (!r.ok) throw new Error(`frame ${f}: ${r.status}`); }
        else await save("frames", `f${String(f).padStart(5, "0")}.jpg`, 1920);
        if (f % 30 === 0) { status.textContent = `frame ${f} of ${b}`; document.title = `${Math.round((100 * (f - a)) / (b - a + 1))}%`; }
      }
      if (pipe) await fetch(`/pipe/${pipe}/end`, { method: "POST" });
      status.textContent = "frames done"; document.title = "frames done";
    } else {
      const key = q.get("scene") || "open", t = +(q.get("t") ?? FS.SCENES.find((s) => s.key === key).still);
      frame(key, t);
      status.textContent = `${key} at ${t} s`;
    }
  } catch (e) { status.textContent = "error: " + e.message; document.title = "error"; console.error(e); }
})();
