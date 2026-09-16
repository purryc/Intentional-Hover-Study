import * as THREE from 'three';
import { OrbitControls } from './vendor/OrbitControls.js';

const host = document.getElementById('atlas');
const daySelect = document.getElementById('day');
const postureSelect = document.getElementById('posture');
const groupSelect = document.getElementById('group');
const threshold = document.getElementById('atlas-threshold');
const thresholdValue = document.getElementById('atlas-threshold-value');
const meta = document.getElementById('atlas-meta');

const scene = new THREE.Scene();
scene.background = new THREE.Color('#111b2d');
const camera = new THREE.PerspectiveCamera(42, 1, 1, 4000);
camera.position.set(640, 610, 1020);
const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false });
renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
host.appendChild(renderer.domElement);
const controls = new OrbitControls(camera, renderer.domElement);
controls.target.set(0, 90, 0);
controls.enableDamping = true;
controls.minDistance = 300;
controls.maxDistance = 2400;
controls.update();

scene.add(new THREE.AmbientLight(0xffffff, 2));
const sun = new THREE.DirectionalLight(0xffffff, 2.2);
sun.position.set(-300, 500, 300);
scene.add(sun);

const phone = new THREE.Mesh(
  new THREE.BoxGeometry(390, 4, 830),
  new THREE.MeshStandardMaterial({ color: '#243955', roughness: .9, metalness: .03 }),
);
phone.position.y = -4;
scene.add(phone);
const outline = new THREE.LineSegments(
  new THREE.EdgesGeometry(new THREE.BoxGeometry(390, 4, 830)),
  new THREE.LineBasicMaterial({ color: '#83a3d2' }),
);
outline.position.y = -4;
scene.add(outline);
const grid = new THREE.GridHelper(820, 41, '#415e83', '#2e425f');
grid.position.y = 0;
scene.add(grid);

function axis(from, to, color) {
  const geometry = new THREE.BufferGeometry().setFromPoints([new THREE.Vector3(...from), new THREE.Vector3(...to)]);
  scene.add(new THREE.Line(geometry, new THREE.LineBasicMaterial({ color })));
}
axis([-195, 0, 415], [195, 0, 415], '#ee917a');
axis([-195, 0, 415], [-195, 0, -415], '#61c7c3');
axis([-195, 0, 415], [-195, 220, 415], '#a296ee');

function label(text, pos, color) {
  const canvas = document.createElement('canvas');
  canvas.width = 300; canvas.height = 75;
  const ctx = canvas.getContext('2d');
  ctx.fillStyle = color;
  ctx.font = 'bold 29px system-ui';
  ctx.fillText(text, 10, 46);
  const texture = new THREE.CanvasTexture(canvas);
  const sprite = new THREE.Sprite(new THREE.SpriteMaterial({ map: texture, transparent: true, depthTest: false }));
  sprite.position.set(...pos); sprite.scale.set(190, 48, 1);
  scene.add(sprite);
}
label('X · 390 pt', [130, 6, 465], '#eea691');
label('Y · 830 pt', [-205, 6, -325], '#77d7d0');
label('Z · API 0–1', [-145, 225, 365], '#baadff');

let allData = null;
let homeData = null;
let voxelsMesh = null;
let homeMarker = null;
const dummy = new THREE.Object3D();
const color = new THREE.Color();
const stops = [
  [0, new THREE.Color('#2f60ab')],
  [.35, new THREE.Color('#28a6b0')],
  [.7, new THREE.Color('#f4cc65')],
  [1, new THREE.Color('#f06b4d')],
];
function heatColor(v) {
  const n = Math.max(0, Math.min(1, v));
  for (let i = 1; i < stops.length; i++) {
    if (n <= stops[i][0]) {
      const [a, ca] = stops[i - 1]; const [b, cb] = stops[i];
      return color.copy(ca).lerp(cb, (n - a) / (b - a));
    }
  }
  return color.copy(stops[stops.length - 1][1]);
}

function selectedData() {
  return allData.groups[[daySelect.value, postureSelect.value, groupSelect.value].join('|')];
}

function drawHeat() {
  if (!allData) return;
  if (voxelsMesh) {
    scene.remove(voxelsMesh);
    voxelsMesh.geometry.dispose(); voxelsMesh.material.dispose(); voxelsMesh = null;
  }
  if (homeMarker) {
    scene.remove(homeMarker);
    homeMarker.traverse(obj => { if (obj.geometry) obj.geometry.dispose(); if (obj.material) obj.material.dispose(); });
    homeMarker = null;
  }
  const data = selectedData();
  const cut = Number(threshold.value) / 100;
  thresholdValue.textContent = `${threshold.value}%`;
  if (!data || !data.voxels.length) {
    meta.textContent = '这个筛选没有可用的连续 Pencil 悬停段。';
    return;
  }
  const max = Math.max(...data.voxels.map(v => v[3]));
  const visible = data.voxels.filter(v => v[3] / max >= cut);
  const geometry = new THREE.BoxGeometry(allData.xyCellPt * .91, allData.zCellRaw * 220 * .86, allData.xyCellPt * .91);
  const material = new THREE.MeshStandardMaterial({ color: 0xffffff, transparent: true, opacity: .84, roughness: .6, metalness: .04, depthWrite: false });
  voxelsMesh = new THREE.InstancedMesh(geometry, material, visible.length);
  voxelsMesh.instanceMatrix.setUsage(THREE.StaticDrawUsage);
  visible.forEach(([ix, iy, iz, seconds], i) => {
    dummy.position.set(-195 + (ix + .5) * allData.xyCellPt, (iz + .5) * allData.zCellRaw * 220, 415 - (iy + .5) * allData.xyCellPt);
    dummy.updateMatrix();
    voxelsMesh.setMatrixAt(i, dummy.matrix);
    const normalized = Math.log1p(seconds * 100) / Math.log1p(max * 100);
    voxelsMesh.setColorAt(i, heatColor(normalized));
  });
  voxelsMesh.instanceMatrix.needsUpdate = true;
  if (voxelsMesh.instanceColor) voxelsMesh.instanceColor.needsUpdate = true;
  voxelsMesh.frustumCulled = false;
  scene.add(voxelsMesh);
  const task = groupSelect.value.split(' ')[0];
  const home = homeData?.trials.find(t => t.day === daySelect.value && t.posture === postureSelect.value && t.home &&
    ({ news: 'A5', notes: 'A6', video: 'A7' })[t.scene] === task);
  let homeText = '';
  if (home) {
    const x = -195 + home.home.x;
    const z = 415 - home.home.y;
    homeMarker = new THREE.Group();
    const ring = new THREE.Mesh(new THREE.RingGeometry(48, 52, 64),
      new THREE.MeshBasicMaterial({ color: '#ffe17a', side: THREE.DoubleSide, depthTest: false }));
    ring.renderOrder = 10;
    ring.rotation.x = -Math.PI / 2;
    ring.position.set(x, 3, z);
    const dot = new THREE.Mesh(new THREE.SphereGeometry(5, 12, 12),
      new THREE.MeshBasicMaterial({ color: '#fff0b0', depthTest: false }));
    dot.renderOrder = 11;
    dot.position.set(x, 5, z);
    homeMarker.add(ring, dot);
    scene.add(homeMarker);
    homeText = ` Home XY = (${home.home.x}, ${home.home.y}) pt；黄圈半径 50 pt，只表示空间候选。`;
  }
  meta.textContent = `${daySelect.value} · ${postureSelect.selectedOptions[0].textContent} · ${groupSelect.value}。连续悬停 ${data.seconds.toFixed(2)} 秒；显示 ${visible.length} / ${data.voxelCount} 个体素；最热体素 ${max.toFixed(3)} 秒（占本组 ${(max / data.seconds * 100).toFixed(1)}%）。${homeText}`;
}

function resize() {
  const w = host.clientWidth; const h = host.clientHeight;
  renderer.setSize(w, h);
  camera.aspect = w / h;
  camera.updateProjectionMatrix();
}
new ResizeObserver(resize).observe(host);
for (const control of [daySelect, postureSelect, groupSelect, threshold]) control.addEventListener('input', drawHeat);

try {
  const [original, reading, home] = await Promise.all([
    fetch('./heat.json').then(r => { if (!r.ok) throw new Error(`heat HTTP ${r.status}`); return r.json(); }),
    fetch('./home-heat.json').then(r => { if (!r.ok) throw new Error(`reading HTTP ${r.status}`); return r.json(); }),
    fetch('./home-position.json').then(r => { if (!r.ok) throw new Error(`home HTTP ${r.status}`); return r.json(); }),
  ]);
  allData = { ...original, groups: { ...original.groups, ...reading.groups } };
  homeData = home;
  const keys = Object.keys(allData.groups);
  const days = [...new Set(keys.map(k => k.split('|')[0]))];
  const groups = [...new Set(keys.map(k => k.split('|')[2]))];
  for (const day of days) daySelect.add(new Option(day, day));
  for (const group of ['A5 新闻', 'A6 图文流', 'A7 短视频', 'B1 菜单', 'B2 单选', 'B3 多选', 'C 主动 Hover', '自然阅读候选', '点击前悬停', 'B4 圈选']) {
    if (groups.includes(group)) groupSelect.add(new Option(group, group));
  }
  daySelect.value = document.getElementById('home-day')?.value || days[0];
  postureSelect.value = document.getElementById('home-posture')?.value || 'THUMB';
  groupSelect.value = ({ news: 'A5 新闻', notes: 'A6 图文流', video: 'A7 短视频' })[document.getElementById('home-scene')?.value] || 'A5 新闻';
  drawHeat();
  document.dispatchEvent(new Event('atlas-ready'));
} catch (error) {
  meta.textContent = `热区数据加载失败：${error.message}`;
}

function animate() { requestAnimationFrame(animate); controls.update(); renderer.render(scene, camera); }
resize(); animate();
