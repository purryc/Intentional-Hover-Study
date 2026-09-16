const $ = id => document.getElementById(id);
const sceneName = { news: '新闻长文', notes: '图文流', video: '短视频流', ALL: '全部场景' };
const postureName = { THUMB: '拇指', CRADLE_INDEX: '托握＋食指' };
const sceneTask = {news:'A5 新闻',notes:'A6 图文流',video:'A7 短视频'};
const fmt = (v, digits=0) => v == null ? '—' : Number(v).toFixed(digits);
const shortDay = day => day.includes('09-15') ? '09-15' : '09-16';

const [homeData, thresholdData, thresholdSweep, motionData] = await Promise.all([
  fetch('./home-position.json').then(r => r.json()),
  fetch('./threshold-800.json').then(r => r.json()),
  fetch('./threshold-sweep.json').then(r => r.json()),
  fetch('./summary.json').then(r => r.json()),
]);
if (thresholdSweep.source.some((source, i) => source.sha256 !== thresholdData.source[i]?.sha256)) {
  throw new Error('Threshold sweep and 500/800 ms evidence use different source CSVs');
}

const days = [...new Set(homeData.trials.map(t => t.day))];
for (const day of days) {
  $('home-day').add(new Option(day, day));
  $('threshold-day').add(new Option(day, day));
}
$('home-day').value = days[1];

function heatColor(fraction) {
  const a = Math.max(0, Math.min(1, fraction));
  if (a < .5) return `rgba(39,${Math.round(89+a*2*71)},${Math.round(159-a*2*5)},${.36 + a*.8})`;
  return `rgba(${Math.round(110+(a-.5)*2*132)},${Math.round(165-(a-.5)*2*57)},${Math.round(152-(a-.5)*2*88)},${.65+a*.25})`;
}

function renderHomeMap(trial) {
  const canvas = $('home-map');
  const ctx = canvas.getContext('2d');
  ctx.fillStyle = '#101f31'; ctx.fillRect(0, 0, 390, 830);
  const cells = trial.cells;
  const max = Math.max(0.001, ...cells.map(c => c[2]));
  for (const [ix,iy,seconds] of cells) {
    ctx.fillStyle = heatColor(Math.log1p(seconds*10)/Math.log1p(max*10));
    ctx.fillRect(ix*20, iy*20, 19, 19);
  }
  if (trial.home) {
    ctx.strokeStyle = '#ffdb71'; ctx.lineWidth = 5;
    ctx.beginPath(); ctx.arc(trial.home.x, trial.home.y, homeData.radiusPt, 0, Math.PI*2); ctx.stroke();
    ctx.fillStyle = '#ffe18a'; ctx.beginPath(); ctx.arc(trial.home.x, trial.home.y, 5, 0, Math.PI*2); ctx.fill();
  }
  ctx.font = 'bold 20px system-ui'; ctx.fillStyle = '#e9f3fb'; ctx.fillText(`${sceneName[trial.scene]} · ${shortDay(trial.day)}`, 17, 34);
  ctx.font = '15px system-ui'; ctx.fillText(`${postureName[trial.posture]} · 390 × 830 pt`, 17, 57);
}

function setMetric(key, val, detail) {
  return `<div class="metric"><span>${key}</span><b>${val}</b><span>${detail}</span></div>`;
}
function renderHome() {
  const trial = homeData.trials.find(t => t.day === $('home-day').value && t.posture === $('home-posture').value && t.scene === $('home-scene').value);
  if (!trial) return;
  renderHomeMap(trial);
  const stable = trial.validatedStableWallS;
  $('home-meta').innerHTML = [
    setMetric('首次可估计', trial.firstEstimableWallS == null ? '未获得' : `${trial.firstEstimableWallS} s`, `此时已实测 ${fmt(trial.firstEstimableObservedS,1)} s 悬停`),
    setMetric('复现后的稳定定位', stable == null ? '未证实' : `${stable} s`, `前后中心距离 ${fmt(trial.halfCentersDistancePt,1)} pt`),
    setMetric('Home 候选 XY', trial.home ? `${fmt(trial.home.x)}, ${fmt(trial.home.y)}` : '—', '手机局部坐标 pt · 圈半径 50 pt'),
    setMetric('有效悬停覆盖', `${fmt(trial.observedS,1)} s`, `${fmt(trial.coverage*100,1)}% 的阅读记录时长`),
  ].join('');
  const status = $('home-status');
  status.classList.toggle('warn', !trial.halfReplicated);
  status.textContent = trial.halfReplicated
    ? `这段阅读前后两半的热点相距 ${fmt(trial.halfCentersDistancePt,1)} pt；空间位置通过复现检查。`
    : `这段阅读前后两半的热点相距 ${fmt(trial.halfCentersDistancePt,1)} pt；当前只能标注位置候选，不能声称稳定 Home。`;
  $('home-prefix').replaceChildren(...trial.prefixes.map(p => {
    const span = document.createElement('span');
    span.className = !p.candidate ? 'empty' : p.distanceToFullPt <= homeData.stableDistancePt ? 'good' : 'bad';
    span.textContent = `${p.wallS}s`;
    span.title = `${p.wallS}秒：${p.candidate ? `中心偏差${fmt(p.distanceToFullPt,1)}pt` : '观测不足'}；有效悬停${fmt(p.observedS,1)}秒`;
    return span;
  }));
  $('home-prefix-note').textContent = `整段热点占有效悬停 ${fmt(trial.home?.share*100,1)}%；前 60 秒与后 60 秒中心间隔 ${fmt(trial.halfCentersDistancePt,1)} pt。绿色只表示与回顾性整段中心接近，不单独证明在线定位。`;
  const group = sceneTask[trial.scene];
  if ($('day').options.length && $('group').options.length) {
    $('day').value = trial.day;
    $('posture').value = trial.posture;
    $('group').value = group;
    $('group').dispatchEvent(new Event('input'));
  }
}
for (const id of ['home-day','home-posture','home-scene']) $(id).addEventListener('change', renderHome);
document.addEventListener('atlas-ready', renderHome);

const sceneSummary = $('scene-summary');
for (const scene of ['news','notes','video']) {
  const trials = homeData.trials.filter(t => t.scene === scene);
  const first = trials.map(t => t.firstEstimableWallS).filter(v => v != null);
  const replicated = trials.filter(t => t.halfReplicated).length;
  const card = document.createElement('article');
  card.innerHTML = `<strong>${sceneName[scene]}</strong><br>首次候选 ${Math.min(...first)}–${Math.max(...first)} s<br><span class="muted small">前后位置复现 ${replicated}/${trials.length} 段</span>`;
  sceneSummary.append(card);
}
$('home-table').innerHTML = homeData.trials.map(t => `<tr><td>${shortDay(t.day)}</td><td>${sceneName[t.scene]}</td><td>${postureName[t.posture]}</td><td>${t.firstEstimableWallS ?? '—'} s</td><td>${t.validatedStableWallS == null ? '未证实' : `${t.validatedStableWallS} s`}</td><td>${fmt(t.halfCentersDistancePt,1)} pt</td><td>${fmt(t.observedS,1)} s / ${fmt(t.coverage*100,1)}%</td></tr>`).join('');
renderHome();

const motionGroups = [
  ['B1 菜单','主动 · 菜单'], ['B2 单选','主动 · 单选'], ['B3 多选','主动 · 多选'],
  ['C 主动 Hover','主动 · C 验证'], ['自然阅读候选','A5–A7 · 自然阅读'], ['点击前悬停','A1/C1 · 落笔前'],
];
function renderMotion(day) {
  document.querySelectorAll('#motion-day button').forEach(b => b.classList.toggle('active', b.dataset.day === day));
  const rows = motionGroups.map(([group,label]) => {
    const r = motionData.table.find(row => row.day === day && row.group === group);
    if (!r || !r.paired) return `<div class="motion-row"><div class="name">${label}</div><div class="muted">无可比窗</div></div>`;
    const lo = Math.max(0, Math.min(r.speedEarly, r.speedLate)/550*100);
    const hi = Math.min(100, Math.max(r.speedEarly, r.speedLate)/550*100);
    return `<div class="motion-row"><div><div class="name">${label}</div><div class="sub">${r.paired}/${r.events} 事件可比 · ${r.trials} 次试次</div></div><div class="track" role="img" aria-label="前段${fmt(r.speedEarly,1)}，末段${fmt(r.speedLate,1)} pt每秒"><span class="span" style="left:${lo}%;width:${hi-lo}%"></span><span class="dot" style="left:${Math.min(100,r.speedEarly/550*100)}%"></span><span class="dot end" style="left:${Math.min(100,r.speedLate/550*100)}%"></span></div><div class="motion-value"><b>${fmt(r.speedEarly,0)} → ${fmt(r.speedLate,0)}</b><br>减速 ${r.speedLower}/${r.paired} · Z 变小 ${r.zLower}/${r.paired}</div></div>`;
  });
  $('motion-rows').innerHTML = rows.join('');
}
for (const day of days) {
  const button = document.createElement('button');
  button.type = 'button'; button.dataset.day = day; button.textContent = day;
  button.addEventListener('click', () => renderMotion(day));
  $('motion-day').append(button);
}
renderMotion(days[1]);
$('motion-table').innerHTML = motionData.table.map(r => `<tr><td>${shortDay(r.day)}</td><td>${r.group}</td><td>${r.events}/${r.trials}</td><td>${r.paired}</td><td>${fmt(r.speedEarly,1)}</td><td>${fmt(r.speedLate,1)}</td><td>${r.speedLower}/${r.paired}</td><td>${r.zLower}/${r.paired}</td></tr>`).join('');

function thresholdCount(row, index) {
  return row.candidateSeries[index];
}
function thresholdChange(base, selected) {
  if (!base) return selected ? `基准为 0，增加 ${selected} 次` : '基准为 0，均无候选';
  const percent = Math.abs(selected - base) / base * 100;
  if (selected < base) return `候选减少 ${fmt(percent,1)}%`;
  if (selected > base) return `候选增加 ${fmt(percent,1)}%`;
  return '与 500 ms 相同';
}
function thresholdBars(id, base, selected, ms) {
  const maximum = Math.max(1, base, selected);
  $(id).innerHTML = `<div class="bar-row"><span>500 ms</span><div class="bar"><div class="base" style="width:${base/maximum*100}%"></div></div><b>${base}</b></div><div class="bar-row"><span>${ms} ms</span><div class="bar"><div class="new" style="width:${selected/maximum*100}%"></div></div><b>${selected}</b></div>`;
}
function renderThreshold() {
  const day = $('threshold-day').value;
  const scene = $('threshold-scene').value;
  const ms = Number($('threshold-ms').value);
  const index = thresholdSweep.thresholdMs.indexOf(ms);
  if (index < 0) throw new Error(`Unsupported dwell threshold: ${ms} ms`);
  $('threshold-ms-value').value = `${ms} ms`;
  for (const [cohort,prefix] of [['A','a'],['C3','c']]) {
    const r = thresholdSweep.summary.find(t => t.day === day && t.scene === scene && t.cohort === cohort);
    if (!r) continue;
    const selected = thresholdCount(r, index);
    const perMinute = ms === 500 ? r.perMinute500 : ms === 800 ? r.perMinute800 :
      r.recordedMinutes ? selected / r.recordedMinutes : null;
    $(`${prefix}-threshold`).textContent = `${r.candidate500} → ${selected} 次`;
    $(`${prefix}-threshold-sub`).textContent = `${r.trials} 段、${fmt(r.recordedMinutes,1)} 分钟；每分钟 ${fmt(r.perMinute500,2)} → ${fmt(perMinute,2)}。${thresholdChange(r.candidate500, selected)}。`;
    thresholdBars(`${prefix}-threshold-bars`, r.candidate500, selected, ms);
  }
  const dayRows = days.filter(value => day === 'BOTH' || value === day).map(value => {
    const row = thresholdSweep.summary.find(t => t.day === value && t.scene === scene && t.cohort === 'A');
    if (!row) return null;
    return `${shortDay(value)}：${row.candidate500} → ${thresholdCount(row,index)} 次（${thresholdChange(row.candidate500,thresholdCount(row,index))}）`;
  }).filter(Boolean);
  const dayCaveat = day === 'BOTH' ? '两天合计仅用于描述，不是同一协议下的重复实验。' : '';
  $('threshold-day-note').textContent = `分日看 A 自然阅读${scene === 'ALL' ? '' : ` · ${sceneName[scene]}`}：${dayRows.join('；')}。${dayCaveat}`;
  $('threshold-accuracy-title').textContent = `${ms} ms 的真实准确率：无法从现有数据估计。`;
  const wait = ms > 500 ? `比现行规则至少多等 ${ms-500} ms 才达到触发条件` :
               ms < 500 ? `比现行规则提前 ${500-ms} ms 达到触发条件` : '与现行 500 ms 触发条件相同';
  $('threshold-accuracy-detail').textContent = `滑杆只回算自然阅读时的规则候选，没有实际误触标签。${wait}。B1 在 500 ms 已弹出菜单，系统与参与者行为随即改变；其他阈值的主动成功率、召回率和净准确率需要另外实测。`;
  $('threshold-table-ms').textContent = `${ms} ms`;
  $('threshold-table').innerHTML = thresholdSweep.summary.filter(r => r.day !== 'BOTH' && r.scene !== 'ALL' &&
    (day === 'BOTH' || r.day === day) && (scene === 'ALL' || r.scene === scene)).map(r => {
    const selected = thresholdCount(r,index);
    return `<tr><td>${shortDay(r.day)}</td><td>${r.cohort === 'A' ? 'A 自然阅读' : 'C3 指定对象'}</td><td>${sceneName[r.scene]}</td><td>${r.trials}</td><td>${fmt(r.recordedMinutes,2)}</td><td>${r.candidate500}</td><td>${selected}</td><td>${thresholdChange(r.candidate500,selected)}</td></tr>`;
  }).join('');
}
for (const id of ['threshold-day','threshold-scene']) $(id).addEventListener('change',renderThreshold);
$('threshold-ms').addEventListener('input',renderThreshold);
renderThreshold();
