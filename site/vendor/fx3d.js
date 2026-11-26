/*
 * Empire Tweaks – 3D effects (loaded lazily, only when the sections come near the screen)
 *  initCore(el)   : 24k-particle galaxy that assembles into the ET logo while scrolling
 *  initLogo3D(el) : real extruded metal/glass ET logo that follows the mouse
 */
import * as THREE from "three";
import { RoomEnvironment } from "./RoomEnvironment.js";

const RM = matchMedia("(prefers-reduced-motion:reduce)").matches;
const MOBILE = innerWidth < 820;
const SKEW = Math.tan(-14 * Math.PI / 180);
const LOGO = [
  { d: "M40 8 H118 L110 22 H86 L80 70 H66 L72 22 H40 C33 22 28 27 28 34 V58 C28 64 32 68 38 68 H62 L60 82 H36 C22 82 14 73 14 60 V32 C14 18 25 8 40 8 Z", skew: true },
  { d: "M38 38 H66 L64 50 H38 Z", skew: true },
  { d: "M10 88 C38 104 98 96 124 46 C112 62 70 92 10 88 Z", skew: false, swoosh: true }
];
const clamp = (v, a = 0, b = 1) => Math.min(b, Math.max(a, v));
const smooth = (a, b, v) => { const t = clamp((v - a) / (b - a)); return t * t * (3 - 2 * t); };

/* ───────────────────────── logo → point cloud (sampled from a 2D raster) ───────────────────────── */
function sampleLogo(n, span) {
  const K = 6, W = 138 * K, H = 104 * K;
  const cv = document.createElement("canvas"); cv.width = W; cv.height = H;
  const ctx = cv.getContext("2d");
  ctx.fillStyle = "#fff";
  for (const p of LOGO) {
    ctx.setTransform(K, 0, p.skew ? SKEW * K : 0, K, p.skew ? 14 * K : 0, 0);
    ctx.fill(new Path2D(p.d));
  }
  const data = ctx.getImageData(0, 0, W, H).data, pts = [];
  for (let y = 0; y < H; y += 2) for (let x = 0; x < W; x += 2) if (data[(y * W + x) * 4 + 3] > 128) pts.push(x, y);
  const out = new Float32Array(n * 3), cnt = pts.length / 2;
  for (let i = 0; i < n; i++) {
    const k = (Math.random() * cnt) | 0;
    out[i * 3] = (pts[k * 2] / W - 0.5) * span + (Math.random() - 0.5) * 0.02;
    out[i * 3 + 1] = -(pts[k * 2 + 1] / H - 0.5) * span * (H / W);
    out[i * 3 + 2] = (Math.random() - 0.5) * 0.55;
  }
  return out;
}

function galaxy(n) {
  const out = new Float32Array(n * 3), arms = 3;
  for (let i = 0; i < n; i++) {
    const r = Math.pow(Math.random(), 0.75) * 7.5 + 0.3;
    const a = (i % arms) / arms * Math.PI * 2 + r * 0.75 + (Math.random() - 0.5) * (0.9 / (r * 0.25 + 0.6));
    const spread = (Math.random() - 0.5) * (1.3 - r / 12);
    out[i * 3] = Math.cos(a) * r + spread;
    out[i * 3 + 1] = (Math.random() - 0.5) * (1.2 - r / 14) * Math.random();
    out[i * 3 + 2] = Math.sin(a) * r + spread;
  }
  return out;
}

const VS = `
attribute vec3 aStart; attribute vec3 aEnd; attribute float aR;
uniform float uP, uTime, uExplode, uSize, uPR; uniform vec3 uMouse;
varying float vR; varying float vP; varying vec3 vE;
mat2 rot(float a){ float c = cos(a), s = sin(a); return mat2(c, -s, s, c); }
void main(){
  float d = aR * 0.45;
  float p = smoothstep(d, d + 0.55, uP);
  vec3 s = aStart; s.xz = rot(uTime * (0.05 + aR * 0.05)) * s.xz;
  vec3 pos = mix(s, aEnd, p);
  float w = 0.35 + (1.0 - p) * 2.6;
  pos += 0.03 * w * vec3(sin(uTime * 1.3 + aR * 40.0), cos(uTime * 1.1 + aR * 31.0), sin(uTime * 0.9 + aR * 17.0));
  pos += normalize(aEnd + vec3(0.0001, 0.0001, 0.3)) * uExplode * (1.2 + aR * 3.5);
  vec2 dm = pos.xy - uMouse.xy; float l = length(dm);
  pos.xy += normalize(dm + 1e-4) * smoothstep(1.7, 0.0, l) * 0.6 * p;
  pos.z += smoothstep(1.7, 0.0, l) * 0.8 * p;
  vec4 mv = modelViewMatrix * vec4(pos, 1.0);
  gl_Position = projectionMatrix * mv;
  gl_PointSize = uSize * uPR * (0.5 + aR * 0.9) * (1.0 + (1.0 - p) * 0.7) / (-mv.z);
  vR = aR; vP = p; vE = aEnd;
}`;
const FS = `
precision mediump float;
varying float vR; varying float vP; varying vec3 vE;
void main(){
  vec2 c = gl_PointCoord - 0.5; float r = length(c); if (r > 0.5) discard;
  float a = smoothstep(0.5, 0.0, r); a *= a;
  vec3 blue = vec3(0.17, 0.55, 1.0), cyan = vec3(0.25, 0.9, 1.0), vio = vec3(0.5, 0.36, 1.0), lime = vec3(0.78, 1.0, 0.3);
  vec3 col = mix(vio, blue, smoothstep(-3.5, 0.5, vE.x));
  col = mix(col, cyan, smoothstep(0.6, 3.6, vE.x + vE.y * 0.4));
  col = mix(col, lime, step(0.986, vR));
  gl_FragColor = vec4(col * (1.35 + vP * 0.5), a * (0.8 + vP * 0.2));
}`;

export function initCore({ canvas, pin, onProgress }) {
  const renderer = new THREE.WebGLRenderer({ canvas, antialias: false, alpha: true, powerPreference: "high-performance" });
  const PR = Math.min(devicePixelRatio || 1, MOBILE ? 1.5 : 1.75);
  renderer.setPixelRatio(PR);
  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(42, 1, 0.1, 100);
  camera.position.set(0, 0, 12);

  const N = MOBILE ? 12000 : 24000;
  const span = MOBILE ? 5.2 : 8.4;
  const geo = new THREE.BufferGeometry();
  const end = sampleLogo(N, span), start = galaxy(N), rnd = new Float32Array(N);
  for (let i = 0; i < N; i++) rnd[i] = Math.random();
  geo.setAttribute("position", new THREE.BufferAttribute(end.slice(), 3));
  geo.setAttribute("aStart", new THREE.BufferAttribute(start, 3));
  geo.setAttribute("aEnd", new THREE.BufferAttribute(end, 3));
  geo.setAttribute("aR", new THREE.BufferAttribute(rnd, 1));
  geo.boundingSphere = new THREE.Sphere(new THREE.Vector3(), 20);
  const uni = { uP: { value: 0 }, uTime: { value: 0 }, uExplode: { value: 0 }, uSize: { value: MOBILE ? 26 : 30 }, uPR: { value: PR }, uMouse: { value: new THREE.Vector3(99, 99, 0) } };
  const mat = new THREE.ShaderMaterial({ vertexShader: VS, fragmentShader: FS, uniforms: uni, transparent: true, depthWrite: false, blending: THREE.AdditiveBlending });
  const group = new THREE.Group();
  group.add(new THREE.Points(geo, mat));
  scene.add(group);

  // mouse → world position on the z=0 plane
  const ndc = new THREE.Vector2(9, 9), ray = new THREE.Raycaster(), plane = new THREE.Plane(new THREE.Vector3(0, 0, 1), 0), hit = new THREE.Vector3();
  let mxs = 0, mys = 0;
  addEventListener("pointermove", e => {
    const r = canvas.getBoundingClientRect();
    ndc.set(((e.clientX - r.left) / r.width) * 2 - 1, -((e.clientY - r.top) / r.height) * 2 + 1);
    mxs = ndc.x; mys = ndc.y;
  }, { passive: true });

  function size() {
    const w = canvas.clientWidth, h = canvas.clientHeight;
    renderer.setSize(w, h, false); camera.aspect = w / h; camera.updateProjectionMatrix();
    camera.position.z = w / h < 0.8 ? 17 : 12;
  }
  size(); addEventListener("resize", size);

  let t = 0, last = performance.now(), rx = 0, ry = 0;
  function frame(now) {
    requestAnimationFrame(frame);
    const r = pin.getBoundingClientRect();
    if (r.bottom < -50 || r.top > innerHeight + 50 || document.hidden) { last = now; return; }
    const dt = Math.min(0.05, (now - last) / 1000); last = now;
    if (!RM) t += dt;
    const total = pin.offsetHeight - innerHeight;
    const prog = clamp(-r.top / total);
    onProgress && onProgress(prog);
    const p = smooth(0.1, 0.56, prog);
    uni.uP.value = p;
    uni.uTime.value = t;
    uni.uExplode.value = smooth(0.84, 1.0, prog) * 1.6;
    // camera + group choreography
    const tx = mxs * 0.25, ty = mys * 0.18;
    rx += (tx - rx) * 0.05; ry += (ty - ry) * 0.05;
    group.rotation.x = (1 - p) * 0.95 - ry;
    group.rotation.y = (prog - 0.56) * 1.1 + rx + (1 - p) * t * 0.08;
    group.rotation.z = (1 - p) * 0.25;
    camera.position.y = (1 - p) * 0.8;
    camera.lookAt(0, 0, 0);
    if (Math.abs(ndc.x) < 2) {
      ray.setFromCamera(ndc, camera); ray.ray.intersectPlane(plane, hit);
      if (hit) { const loc = group.worldToLocal(hit.clone()); uni.uMouse.value.lerp(loc, 0.2); }
    }
    renderer.render(scene, camera);
  }
  requestAnimationFrame(frame);
  return true;
}

/* ───────────────────────── extruded 3D logo ───────────────────────── */
function svgToShape(d) {
  const shape = new THREE.Shape(), tk = d.match(/[MHLVCZ]|-?\d*\.?\d+/g);
  let i = 0, cx = 0, cy = 0, cmd = "";
  const num = () => parseFloat(tk[i++]);
  while (i < tk.length) {
    if (/[MHLVCZ]/.test(tk[i])) cmd = tk[i++];
    if (cmd === "M") { cx = num(); cy = num(); shape.moveTo(cx, -cy); cmd = "L"; }
    else if (cmd === "H") { cx = num(); shape.lineTo(cx, -cy); }
    else if (cmd === "V") { cy = num(); shape.lineTo(cx, -cy); }
    else if (cmd === "L") { cx = num(); cy = num(); shape.lineTo(cx, -cy); }
    else if (cmd === "C") { const a = num(), b = num(), c = num(), e = num(); cx = num(); cy = num(); shape.bezierCurveTo(a, -b, c, -e, cx, -cy); }
    else if (cmd === "Z") { shape.closePath(); }
  }
  return shape;
}

export function initLogo3D({ canvas }) {
  const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true });
  renderer.setPixelRatio(Math.min(devicePixelRatio || 1, 2));
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.15;
  const scene = new THREE.Scene();
  const pmrem = new THREE.PMREMGenerator(renderer);
  scene.environment = pmrem.fromScene(new RoomEnvironment(), 0.04).texture;
  const camera = new THREE.PerspectiveCamera(32, 1, 1, 2000);
  camera.position.set(0, 0, 330);

  const body = new THREE.MeshPhysicalMaterial({ color: 0x2a7dff, metalness: 0.65, roughness: 0.16, clearcoat: 1, clearcoatRoughness: 0.08, iridescence: 0.9, iridescenceIOR: 1.35, envMapIntensity: 1.5 });
  const sw = new THREE.MeshPhysicalMaterial({ color: 0x3ee6ff, metalness: 0.4, roughness: 0.12, clearcoat: 1, emissive: 0x0a5a8a, emissiveIntensity: 0.35, envMapIntensity: 1.6 });
  const logo = new THREE.Group();
  const skew = new THREE.Matrix4().set(1, -SKEW, 0, 14, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1); // y is flipped, so the skew sign flips too
  for (const p of LOGO) {
    const g = new THREE.ExtrudeGeometry(svgToShape(p.d), { depth: p.swoosh ? 10 : 16, bevelEnabled: true, bevelThickness: 2.4, bevelSize: 1.6, bevelSegments: 4, curveSegments: 24 });
    if (p.skew) g.applyMatrix4(skew);
    if (p.swoosh) g.translate(0, 0, 3);
    logo.add(new THREE.Mesh(g, p.swoosh ? sw : body));
  }
  const box = new THREE.Box3().setFromObject(logo), c = box.getCenter(new THREE.Vector3());
  logo.children.forEach(m => m.geometry.translate(-c.x, -c.y, -c.z));
  const pivot = new THREE.Group(); pivot.add(logo); scene.add(pivot);
  const l1 = new THREE.PointLight(0x3ee6ff, 60000, 0, 2); l1.position.set(-160, 120, 160); scene.add(l1);
  const l2 = new THREE.PointLight(0x7a5cff, 50000, 0, 2); l2.position.set(180, -100, 120); scene.add(l2);

  function size() { const w = canvas.clientWidth, h = canvas.clientHeight; renderer.setSize(w, h, false); camera.aspect = w / h; camera.updateProjectionMatrix(); }
  size(); addEventListener("resize", size);

  let mx = 0, my = 0, cx2 = 0, cy2 = 0, t = 0, last = performance.now();
  addEventListener("pointermove", e => { mx = e.clientX / innerWidth - 0.5; my = e.clientY / innerHeight - 0.5; }, { passive: true });
  function frame(now) {
    requestAnimationFrame(frame);
    const r = canvas.getBoundingClientRect();
    if (r.bottom < 0 || r.top > innerHeight || document.hidden) { last = now; return; }
    const dt = Math.min(0.05, (now - last) / 1000); last = now; if (!RM) t += dt;
    cx2 += (mx - cx2) * 0.06; cy2 += (my - cy2) * 0.06;
    pivot.rotation.y = Math.sin(t * 0.6) * 0.45 + cx2 * 1.1;
    pivot.rotation.x = Math.sin(t * 0.4) * 0.12 + cy2 * 0.7;
    pivot.position.y = Math.sin(t * 1.1) * 4;
    renderer.render(scene, camera);
  }
  requestAnimationFrame(frame);
  return true;
}


/* ───────────────────────── site-wide background: one particle field that morphs with scroll ───────────────────────── */
function sphere(n, R) {
  const o = new Float32Array(n * 3), g = Math.PI * (3 - Math.sqrt(5));
  for (let i = 0; i < n; i++) {
    const y = 1 - (i / (n - 1)) * 2, r = Math.sqrt(1 - y * y), th = g * i, j = 1 + (Math.random() - 0.5) * 0.06;
    o[i * 3] = Math.cos(th) * r * R * j; o[i * 3 + 1] = y * R * j; o[i * 3 + 2] = Math.sin(th) * r * R * j;
  }
  return o;
}
function wave(n, W, D) {
  const o = new Float32Array(n * 3), cols = Math.ceil(Math.sqrt(n * W / D)), rows = Math.ceil(n / cols);
  for (let i = 0; i < n; i++) {
    const c = i % cols, r = (i / cols) | 0;
    o[i * 3] = (c / (cols - 1) - 0.5) * W; o[i * 3 + 1] = -1.6; o[i * 3 + 2] = (r / (rows - 1) - 0.5) * D;
  }
  return o;
}
function torus(n, R, t) {
  const o = new Float32Array(n * 3);
  for (let i = 0; i < n; i++) {
    const u = Math.random() * Math.PI * 2, v = Math.random() * Math.PI * 2, rr = t * Math.sqrt(Math.random());
    o[i * 3] = (R + rr * Math.cos(v)) * Math.cos(u); o[i * 3 + 1] = (R + rr * Math.cos(v)) * Math.sin(u); o[i * 3 + 2] = rr * Math.sin(v);
  }
  return o;
}

const BG_VS = `
attribute vec3 p0; attribute vec3 p1; attribute vec3 p2; attribute vec3 p3; attribute vec3 p4; attribute float aR;
uniform float uA, uB, uT, uTime, uSize, uPR, uSpin; uniform vec3 uMouse;
varying float vR; varying float vLogo; varying vec3 vP;
float eq(float x, float y){ return 1.0 - step(0.5, abs(x - y)); }
vec3 pick(float k){ return p0 * eq(k, 0.0) + p1 * eq(k, 1.0) + p2 * eq(k, 2.0) + p3 * eq(k, 3.0) + p4 * eq(k, 4.0); }
mat2 rot(float a){ float c = cos(a), s = sin(a); return mat2(c, -s, s, c); }
void main(){
  float d = aR * 0.35;
  float t = smoothstep(d, d + 0.65, uT);
  vec3 a = pick(uA), b = pick(uB);
  // galaxy spins on its own
  if (uA < 0.5) a.xz = rot(uTime * (0.04 + aR * 0.04)) * a.xz;
  if (uB < 0.5) b.xz = rot(uTime * (0.04 + aR * 0.04)) * b.xz;
  // the wave moves
  float wA = eq(uA, 3.0) * (1.0 - t) + eq(uB, 3.0) * t;
  vec3 pos = mix(a, b, t);
  pos.y += wA * (sin(pos.x * 0.8 + uTime * 1.2) * 0.45 + cos(pos.z * 1.1 + uTime * 0.9) * 0.35);
  // travelling between shapes: particles arc outward a little
  pos += normalize(pos + vec3(0.001)) * sin(t * 3.14159) * (0.6 + aR * 1.4);
  pos += 0.025 * vec3(sin(uTime * 1.3 + aR * 40.0), cos(uTime * 1.1 + aR * 31.0), sin(uTime * 0.9 + aR * 17.0));
  vec2 dm = pos.xy - uMouse.xy; float l = length(dm);
  pos.xy += normalize(dm + 1e-4) * smoothstep(1.8, 0.0, l) * 0.7;
  pos.z += smoothstep(1.8, 0.0, l) * 0.9;
  vec4 mv = modelViewMatrix * vec4(pos, 1.0);
  gl_Position = projectionMatrix * mv;
  gl_PointSize = uSize * uPR * (0.5 + aR * 0.9) / (-mv.z);
  vR = aR; vLogo = eq(uA, 1.0) * (1.0 - t) + eq(uB, 1.0) * t; vP = pos;
}`;
const BG_FS = `
precision mediump float;
uniform float uAlpha;
varying float vR; varying float vLogo; varying vec3 vP;
void main(){
  vec2 c = gl_PointCoord - 0.5; float r = length(c); if (r > 0.5) discard;
  float a = smoothstep(0.5, 0.0, r); a *= a;
  vec3 blue = vec3(0.17, 0.55, 1.0), cyan = vec3(0.25, 0.9, 1.0), vio = vec3(0.5, 0.36, 1.0), lime = vec3(0.78, 1.0, 0.3);
  vec3 col = mix(vio, blue, smoothstep(-4.0, 0.0, vP.x));
  col = mix(col, cyan, smoothstep(0.5, 4.0, vP.x + vP.y * 0.4));
  col = mix(col, lime, step(0.988, vR));
  gl_FragColor = vec4(col * 1.25, a * uAlpha * (0.75 + vLogo * 0.35));
}`;

/**
 * stops: [{el, shape, x}]  – shape index (0 galaxy,1 logo,2 sphere,3 wave,4 ring), x = horizontal offset
 */
export function initBackground({ canvas, stops }) {
  const renderer = new THREE.WebGLRenderer({ canvas, antialias: false, alpha: true, powerPreference: "high-performance" });
  const PR = Math.min(devicePixelRatio || 1, MOBILE ? 1.25 : 1.5);
  renderer.setPixelRatio(PR);
  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(42, 1, 0.1, 100);
  camera.position.set(0, 0, 13);
  const N = MOBILE ? 8000 : 20000;
  const span = MOBILE ? 5.2 : 8.2;
  const geo = new THREE.BufferGeometry();
  const shapes = [galaxy(N).map(v => v * 0.85), sampleLogo(N, span), sphere(N, MOBILE ? 2.4 : 3.3), wave(N, MOBILE ? 9 : 16, MOBILE ? 7 : 9), torus(N, MOBILE ? 2.4 : 3.4, 0.75)];
  const rnd = new Float32Array(N); for (let i = 0; i < N; i++) rnd[i] = Math.random();
  geo.setAttribute("position", new THREE.BufferAttribute(shapes[1].slice(), 3));
  shapes.forEach((s, i) => geo.setAttribute("p" + i, new THREE.BufferAttribute(s, 3)));
  geo.setAttribute("aR", new THREE.BufferAttribute(rnd, 1));
  geo.boundingSphere = new THREE.Sphere(new THREE.Vector3(), 30);
  const uni = { uA: { value: 0 }, uB: { value: 0 }, uT: { value: 0 }, uTime: { value: 0 }, uSize: { value: MOBILE ? 30 : 38 }, uPR: { value: PR },
    uSpin: { value: 0 }, uMouse: { value: new THREE.Vector3(99, 99, 0) }, uAlpha: { value: 0 } };
  const mat = new THREE.ShaderMaterial({ vertexShader: BG_VS, fragmentShader: BG_FS, uniforms: uni, transparent: true, depthWrite: false, blending: THREE.AdditiveBlending });
  const group = new THREE.Group(); group.add(new THREE.Points(geo, mat)); scene.add(group);

  const ndc = new THREE.Vector2(9, 9), ray = new THREE.Raycaster(), plane = new THREE.Plane(new THREE.Vector3(0, 0, 1), 0), hit = new THREE.Vector3();
  addEventListener("pointermove", e => { ndc.set((e.clientX / innerWidth) * 2 - 1, -(e.clientY / innerHeight) * 2 + 1); }, { passive: true });
  function size() { renderer.setSize(innerWidth, innerHeight, false); camera.aspect = innerWidth / innerHeight; camera.updateProjectionMatrix();
    camera.position.z = innerWidth / innerHeight < 0.8 ? 17 : 13; }
  size(); addEventListener("resize", size);

  // section positions (document coordinates), refreshed on resize / late layout
  let tops = [];
  const measure = () => { tops = stops.map(s => s.el.getBoundingClientRect().top + scrollY); };
  measure(); addEventListener("resize", measure); addEventListener("load", measure); setTimeout(measure, 1500); setTimeout(measure, 4000);

  let t = 0, last = performance.now(), lastY = scrollY, spin = 0, rx = 0, ry = 0, gx = stops[0].x || 0, fade = 0, base = 0;
  function frame(now) {
    requestAnimationFrame(frame);
    if (document.hidden) { last = now; return; }
    const dt = Math.min(0.05, (now - last) / 1000); last = now;
    if (!RM) t += dt;
    // where are we between two stops?
    const y = scrollY + innerHeight * 0.55;
    let i = 0; while (i < tops.length - 1 && y >= tops[i + 1]) i++;
    const a = stops[i], b = stops[Math.min(i + 1, stops.length - 1)];
    const segLen = Math.max(1, (tops[i + 1] ?? tops[i] + 1) - tops[i]);
    const raw = i >= tops.length - 1 ? 0 : clamp((y - tops[i]) / segLen);
    const k = smooth(0.45, 1.0, raw);                       // hold the shape, then morph near the next section
    uni.uA.value = a.shape; uni.uB.value = b.shape; uni.uT.value = k;
    gx += (((a.x || 0) * (1 - k) + (b.x || 0) * k) - gx) * 0.08;
    // scroll velocity → spin burst
    const v = scrollY - lastY; lastY = scrollY;
    spin += (clamp(v / 60, -1, 1) * 0.06 - spin) * 0.08;
    const mx = Math.abs(ndc.x) < 2 ? ndc.x : 0, my = Math.abs(ndc.y) < 2 ? ndc.y : 0;   // no pointer yet / touch → neutral
    rx += (my * 0.12 - rx) * 0.04; ry += (mx * 0.2 - ry) * 0.04;
    base += spin + (RM ? 0 : dt * 0.035);
    const logoW = (a.shape === 1 ? 1 - k : 0) + (b.shape === 1 ? k : 0);   // keep the logo facing the viewer
    const near = Math.round(base / (Math.PI * 2)) * Math.PI * 2;
    group.rotation.y = base + (near - base) * logoW + ry;
    group.rotation.x = -rx + (a.shape === 0 && k < 0.5 ? 0.9 * (1 - k * 2) : 0) * 0.6 + (b.shape === 3 ? 0.35 * k : 0) + (a.shape === 3 ? 0.35 * (1 - k) : 0);
    group.position.x = gx;
    uni.uTime.value = t;
    fade = Math.min(1, fade + dt * 0.6);
    uni.uAlpha.value = fade * (MOBILE ? 0.75 : 0.95);
    if (Math.abs(ndc.x) < 2) { ray.setFromCamera(ndc, camera); if (ray.ray.intersectPlane(plane, hit)) uni.uMouse.value.lerp(group.worldToLocal(hit.clone()), 0.2); }
    renderer.render(scene, camera);
  }
  requestAnimationFrame(frame);
  return { measure, get state() { return { tops, a: uni.uA.value, b: uni.uB.value, t: uni.uT.value, rotY: group.rotation.y, rotX: group.rotation.x }; } };
}
