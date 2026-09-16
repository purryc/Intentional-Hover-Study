/* Local report explorer. Recomputes retrospective rule candidates; never edits the CSV. */
(() => {
  const byId = id => document.getElementById(id);
  const source = byId("dwell-threshold-data");
  if (!source) return;
  const data = JSON.parse(source.textContent);
  const slider = byId("dwell-ms");
  const scene = byId("dwell-scene");
  const posture = byId("dwell-posture");
  const thresholdPoints = Array.from({ length: 37 }, (_, i) => 100 + i * 25);

  function selectedRows(cohort) {
    return data.trials.filter(row => row.cohort === cohort &&
      (!scene.value || row.scene === scene.value) &&
      (!posture.value || row.posture === posture.value));
  }

  function summary(rows, threshold) {
    let episodes = 0, candidates = 0, seconds = 0, hover = 0, inside = 0, visits = 0;
    for (const row of rows) {
      seconds += row.trialDurationS;
      hover += row.hoverObservedS;
      inside += row.targetInsideS || 0;
      visits += row.targetVisits || 0;
      for (const episode of row.episodes) {
        episodes++;
        if (episode.thresholdMs + 1e-7 >= threshold) candidates++;
      }
    }
    return { trials: rows.length, episodes, candidates, minutes: seconds / 60,
      perMinute: seconds ? candidates * 60 / seconds : null,
      share: episodes ? 100 * candidates / episodes : null,
      hover, inside, visits };
  }

  const fixed = (value, digits = 2) => value == null ? "—" : value.toFixed(digits);

  function chart(cohort, rows, threshold, current) {
    const svg = byId(`dwell-chart-${cohort}`);
    if (!rows.length) {
      svg.innerHTML = '<text x="24" y="83" fill="#526a79">该筛选组合没有自然阅读试次</text>';
      return;
    }
    const color = cohort === "A" ? "#0b78ac" : "#8655a3";
    const rates = thresholdPoints.map(t => summary(rows, t).perMinute || 0);
    const yMax = Math.max(.1, Math.ceil(Math.max(...rates) * 10) / 10);
    const x = t => 44 + (t - 100) / 900 * 412;
    const y = rate => 128 - rate / yMax * 98;
    const path = thresholdPoints.map((t, i) => `${i ? "L" : "M"}${x(t).toFixed(2)},${y(rates[i]).toFixed(2)}`).join(" ");
    svg.innerHTML = `<line x1="44" y1="30" x2="44" y2="128" stroke="#9bb3c3"/>` +
      `<line x1="44" y1="128" x2="456" y2="128" stroke="#9bb3c3"/>` +
      `<line x1="44" y1="30" x2="456" y2="30" stroke="#e1eaf0"/>` +
      `<text x="3" y="34" font-size="11" fill="#526a79">${fixed(yMax, 1)}</text>` +
      `<text x="21" y="132" font-size="11" fill="#526a79">0</text>` +
      `<text x="44" y="148" font-size="11" fill="#526a79">100</text>` +
      `<text x="215" y="148" font-size="11" fill="#526a79">500</text>` +
      `<text x="425" y="148" font-size="11" fill="#526a79">1000 ms</text>` +
      `<path d="${path}" fill="none" stroke="${color}" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/>` +
      `<line x1="${x(threshold)}" y1="30" x2="${x(threshold)}" y2="128" stroke="${color}" stroke-dasharray="4 4" opacity=".7"/>` +
      `<circle cx="${x(threshold)}" cy="${y(current.perMinute || 0)}" r="5" fill="${color}" stroke="white" stroke-width="2"/>`;
  }

  function updateCard(cohort, rows, threshold) {
    const result = summary(rows, threshold);
    byId(`dwell-${cohort}-count`).textContent = `${result.candidates} 次候选`;
    byId(`dwell-${cohort}-rate`).textContent = `${fixed(result.perMinute)} 次/记录分钟`;
    const share = result.share == null ? "—" : `${fixed(result.share, 1)}%`;
    byId(`dwell-${cohort}-support`).textContent = cohort === "A" ?
      `${result.candidates}/${result.episodes} 段达标（${share}） · ${fixed(result.minutes, 1)} 分钟 · 有效悬停 ${fixed(result.hover, 1)} 秒` :
      `${result.candidates}/${result.episodes} 段达标（${share}） · 进入目标 ${result.visits} 次 · 目标内实测 ${fixed(result.inside)} 秒 / 有效悬停 ${fixed(result.hover, 1)} 秒`;
    chart(cohort, rows, threshold, result);
    return result;
  }

  function render() {
    const threshold = Number(slider.value);
    byId("dwell-ms-value").textContent = `${threshold} ms`;
    const aRows = selectedRows("A"), cRows = selectedRows("C3");
    updateCard("A", aRows, threshold);
    updateCard("C3", cRows, threshold);
    for (const button of document.querySelectorAll("[data-dwell-preset]")) {
      button.setAttribute("aria-pressed", String(Number(button.dataset.dwellPreset) === threshold));
    }
    const points = Array.from(new Set([100, 250, 500, 750, 1000, threshold])).sort((a, b) => a - b);
    byId("dwell-table").innerHTML = points.map(t => {
      const a = summary(aRows, t), c = summary(cRows, t);
      return `<tr${t === threshold ? ' style="background:#e8f5fd;font-weight:700"' : ""}>` +
        `<td>${t} ms${t === threshold ? " · 当前" : ""}</td><td>${a.candidates}</td><td>${fixed(a.perMinute)}</td>` +
        `<td>${c.candidates}</td><td>${fixed(c.perMinute)}</td></tr>`;
    }).join("");
  }

  slider.addEventListener("input", render);
  scene.addEventListener("change", render);
  posture.addEventListener("change", render);
  for (const button of document.querySelectorAll("[data-dwell-preset]")) {
    button.addEventListener("click", () => { slider.value = button.dataset.dwellPreset; render(); });
  }
  render();
})();
