const picker = document.getElementById('touch-picker');
const context = document.getElementById('touch-context');
const metrics = document.getElementById('touch-metrics');
const plots = {
  preSpeed: document.getElementById('touch-pre-xy'),
  preZSpeed: document.getElementById('touch-pre-z'),
  contactSpeed: document.getElementById('touch-contact-xy'),
};
const svgNS = 'http://www.w3.org/2000/svg';
const fmt = (number, digits = 0) => number == null ? '—' : Number(number).toFixed(digits);

function svg(tag, attrs = {}) {
  const node = document.createElementNS(svgNS, tag);
  Object.entries(attrs).forEach(([key, value]) => node.setAttribute(key, String(value)));
  return node;
}

function pathSegments(values, x, y, key) {
  const segments = [];
  let current = [];
  values.forEach((item, i) => {
    if (item[key] == null) {
      if (current.length) segments.push(current);
      current = [];
    } else current.push([x(i), y(item[key])]);
  });
  if (current.length) segments.push(current);
  return segments;
}

function drawChart(host, values, color, preTouch, unit) {
  host.replaceChildren();
  const width = 340, height = 190;
  const left = 43, right = 12, top = 16, bottom = 31;
  const plotW = width - left - right, plotH = height - top - bottom;
  const rawMax = Math.max(0, ...values.map(v => v.q75 ?? v.median ?? 0));
  const step = rawMax > 1000 ? 500 : rawMax > 100 ? 100 : 1;
  const maxY = Math.max(step, Math.ceil(rawMax / step) * step);
  const x = i => left + (i + .5) * plotW / values.length;
  const y = value => top + plotH * (1 - Math.min(maxY, value) / maxY);
  const chart = svg('svg', { viewBox: `0 0 ${width} ${height}`, role: 'img',
    'aria-label': `${preTouch ? '落笔前一秒' : '接触过程'}${unit}中位和四分位曲线` });
  for (let j = 0; j <= 2; j++) {
    const val = maxY * j / 2, yy = y(val);
    chart.append(svg('line', { x1: left, x2: width - right, y1: yy, y2: yy,
      stroke: '#dfebed', 'stroke-width': 1 }));
    const label = svg('text', { x: left - 7, y: yy + 4, 'text-anchor': 'end',
      fill: '#5b6d77', 'font-size': 11 });
    label.textContent = fmt(val);
    chart.append(label);
  }
  const bands = [];
  let band = [];
  values.forEach((v, i) => {
    if (v.q25 == null || v.q75 == null) {
      if (band.length) bands.push(band);
      band = [];
    } else band.push([x(i), y(v.q25), y(v.q75)]);
  });
  if (band.length) bands.push(band);
  bands.forEach(points => {
    const polygon = points.map(p => `${p[0]},${p[2]}`)
      .concat([...points].reverse().map(p => `${p[0]},${p[1]}`)).join(' ');
    chart.append(svg('polygon', { points: polygon, fill: color, opacity: .16 }));
  });
  pathSegments(values, x, y, 'median').forEach(points => {
    chart.append(svg('polyline', { points: points.map(p => p.join(',')).join(' '),
      fill: 'none', stroke: color, 'stroke-width': 2.7,
      'stroke-linecap': 'round', 'stroke-linejoin': 'round' }));
  });
  chart.append(svg('line', { x1: left, x2: width - right, y1: top + plotH, y2: top + plotH,
    stroke: '#839da4', 'stroke-width': 1 }));
  const ticks = preTouch ? [['−1000 ms', left], ['−500', left + plotW / 2], ['落笔 0', left + plotW]]
    : [['落笔 0%', left], ['50%', left + plotW / 2], ['抬笔 100%', left + plotW]];
  ticks.forEach(([name, position]) => {
    const label = svg('text', { x: position, y: height - 8,
      'text-anchor': position === left ? 'start' : position === left + plotW ? 'end' : 'middle',
      fill: '#526974', 'font-size': 11 });
    label.textContent = name;
    chart.append(label);
  });
  host.append(chart);
  const valid = values.filter(v => v.n > 0).length;
  const footer = document.createElement('div');
  footer.className = 'axisnote';
  footer.textContent = `纵轴 0–${fmt(maxY)} ${unit} · 有效时间箱 ${valid}/${values.length}`;
  host.append(footer);
}

function metric(label, value, note) {
  const card = document.createElement('article');
  const title = document.createElement('b');
  title.textContent = value;
  const detail = document.createElement('span');
  detail.textContent = `${label} · ${note}`;
  card.append(title, detail);
  return card;
}

function renderTask(tasks, task) {
  const row = tasks[task];
  picker.querySelectorAll('button').forEach(button => {
    const selected = button.dataset.task === task;
    button.classList.toggle('active', selected);
    button.setAttribute('aria-pressed', selected ? 'true' : 'false');
  });
  context.textContent = `${task} · ${row.context}。${row.kind === 'reading' ? '这是阅读情境中的混合接触，不能逐次推断原始手势类别。' : '每个成功试次取最后一次完整触屏操作。'}`;
  metrics.replaceChildren(
    metric('完整接触', `${row.contacts} 次`, `${row.trials} 个试次`),
    metric('接触时长中位', `${fmt(row.contactDurationMs.median)} ms`,
      `四分位 ${fmt(row.contactDurationMs.q25)}–${fmt(row.contactDurationMs.q75)} ms`),
    metric('实测路径中位', `${fmt(row.observedPathPt.median)} pt`,
      `覆盖≥70% 的 ${row.observedPathPt.n} 次；可能漏掉边缘采样`),
    metric('接触采样覆盖中位', `${fmt((row.contactCoverage.median ?? 0) * 100)}%`,
      '有效相邻接触样本时长 / 事件时长')
  );
  drawChart(plots.preSpeed, row.preSpeed, '#197d75', true, 'pt/s');
  drawChart(plots.preZSpeed, row.preZSpeed, '#be7445', true, 'API 原值/s');
  drawChart(plots.contactSpeed, row.contactSpeed, '#395faa', false, 'pt/s');
}

try {
  const response = await fetch('./touch-motion.json');
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  const data = await response.json();
  const tasks = data.tasks;
  Object.entries(tasks).forEach(([task, row]) => {
    const button = document.createElement('button');
    button.type = 'button';
    button.dataset.task = task;
    const name = document.createElement('span');
    name.className = 'touch-name';
    name.textContent = `${task} ${row.label}`;
    const stats = document.createElement('span');
    stats.className = 'touch-stats';
    stats.textContent = `${fmt(row.contactDurationMs.median)} ms · ${fmt(row.observedPathPt.median)} pt`;
    const count = document.createElement('span');
    count.className = 'touch-count';
    count.textContent = `${row.contacts} 次接触 / ${row.trials} 试次`;
    button.append(name, stats, count);
    button.addEventListener('click', () => renderTask(tasks, task));
    picker.append(button);
  });
  renderTask(tasks, 'A1');
} catch (error) {
  context.textContent = `触屏动作数据暂未加载：${error.message}。请从本地报告目录启动网页服务后重试。`;
}
