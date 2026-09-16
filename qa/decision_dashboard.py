"""Question-led local report, keeping the dense original figures as evidence."""
from __future__ import annotations

import json
import shutil
from pathlib import Path

from home_threshold_analysis import build as build_evidence
from sequence_comparison import build as build_sequences
from touch_motion_analysis import build as build_touch_motion


ROOT = Path(__file__).resolve().parents[1]


def render(output: Path):
    home, threshold, le = build_evidence(ROOT, output)
    sequence = build_sequences(output, home)
    touch = build_touch_motion(output)
    summary = json.loads((output / "summary.json").read_text())
    source = summary["inputs"]
    a_all = next(r for r in threshold["summary"] if r["day"] == "BOTH" and r["cohort"] == "A" and r["scene"] == "ALL")
    replicated = sum(r["halfReplicated"] for r in home["trials"])
    first_times = [r["firstEstimableWallS"] for r in home["trials"] if r["firstEstimableWallS"] is not None]
    b3 = [r for r in summary["table"] if r["group"] == "B3 多选"]
    html = f'''<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Intentional Hover · Touch、阅读 Home 与主动 Hover</title>
<style>
:root{{--ink:#1b2940;--muted:#53647a;--line:#dce6ee;--bg:#f4f7fa;--blue:#2468bc;--teal:#087f85;--orange:#bd6744;--gold:#eabf5a}}
*{{box-sizing:border-box}}html{{scroll-behavior:smooth}}body{{margin:0;background:var(--bg);color:var(--ink);font:16px/1.58 system-ui,-apple-system,"PingFang SC",sans-serif}}a{{color:#205ba6}}button,select,input{{font:inherit}}button,select{{cursor:pointer}}button:focus-visible,select:focus-visible,a:focus-visible,summary:focus-visible{{outline:3px solid #f2b650;outline-offset:3px}}
header{{padding:44px max(24px,calc((100vw - 1200px)/2)) 34px;color:white;background:radial-gradient(circle at 85% -30%,#4968a2,transparent 42%),linear-gradient(135deg,#10223d,#274b75)}}header h1{{font-size:clamp(30px,4vw,52px);line-height:1.13;letter-spacing:-.035em;margin:12px 0}}header p{{max-width:800px;margin:0;color:#d6e4f5;font-size:17px}}.eyebrow{{color:#a5d7ea;text-transform:uppercase;letter-spacing:.16em;font-size:12px;font-weight:800}}main{{max-width:1200px;margin:auto;padding:0 20px 80px}}nav{{display:flex;gap:8px;flex-wrap:wrap;margin:20px 0 24px}}nav a{{text-decoration:none;border:1px solid #cddbe7;background:#fff;padding:8px 13px;border-radius:999px;font-size:14px;font-weight:700}}section{{background:#fff;border:1px solid var(--line);border-radius:18px;padding:28px;margin:20px 0;box-shadow:0 12px 36px #15335b0a}}h2{{font-size:clamp(24px,2.8vw,32px);line-height:1.25;margin:0 0 8px}}h3{{font-size:19px;margin:0 0 8px}}p{{margin:8px 0 14px}}.muted{{color:var(--muted)}}.small{{font-size:13px}}.kicker{{color:var(--teal);text-transform:uppercase;font-size:12px;font-weight:850;letter-spacing:.11em}}.summary{{display:grid;grid-template-columns:repeat(3,1fr);gap:14px}}.fact{{background:#f0f5f8;border:1px solid #e3edf2;border-radius:14px;padding:19px}}.fact strong{{display:block;font-size:32px;letter-spacing:-.03em;line-height:1.18}}.fact span{{display:block;color:var(--muted);font-size:14px;margin-top:6px}}.fact .term{{color:#264c72;font-weight:750;font-size:13px;margin-bottom:7px}}.callout{{border-left:4px solid #d3973d;background:#fff8ea;padding:12px 16px;border-radius:0 10px 10px 0}}.controls{{display:flex;flex-wrap:wrap;gap:12px;align-items:end;margin:18px 0}}.controls label{{display:grid;gap:5px;font-size:13px;color:#425b70;font-weight:750}}select{{border:1px solid #aebfcf;border-radius:10px;background:#fff;padding:8px 12px;min-width:135px;color:var(--ink)}}.home-layout{{display:grid;grid-template-columns:minmax(300px,.83fr) minmax(350px,1.17fr);gap:22px;align-items:start}}.phone-wrap{{display:flex;justify-content:center;background:#0f2238;padding:18px;border-radius:18px}}#home-map{{width:min(100%,260px);height:auto;aspect-ratio:390/830;border:5px solid #617b92;border-radius:27px;background:#101f31}}.map-legend{{font-size:13px;color:#526b7f;margin:8px 0}}.gradient{{display:inline-block;vertical-align:middle;width:140px;height:10px;border-radius:8px;background:linear-gradient(90deg,#315c9c,#2ba5a6,#f5b960)}}.home-meta{{display:grid;grid-template-columns:repeat(2,1fr);gap:10px}}.metric{{background:#f3f7fa;border:1px solid #e1e9f0;padding:14px;border-radius:12px}}.metric b{{display:block;font-size:23px;line-height:1.2;margin:3px 0}}.metric span{{font-size:13px;color:var(--muted)}}.status{{padding:12px 15px;border-radius:10px;background:#e9f5f3;color:#135e61;font-weight:700;margin-top:12px}}.status.warn{{background:#fff2e8;color:#8d4d2a}}.mini-strip{{display:flex;gap:4px;flex-wrap:wrap;margin:14px 0 5px}}.mini-strip span{{display:grid;place-items:center;min-width:43px;padding:5px;border-radius:6px;background:#e1e8ed;color:#516676;font-size:12px}}.mini-strip span.good{{background:#d2eee9;color:#07585e}}.mini-strip span.bad{{background:#ffe1d4;color:#8c4128}}.mini-strip span.empty{{background:#edf0f2;color:#8a98a4}}.scene-summary{{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin:20px 0}}.scene-summary article{{border:1px solid #dae6ef;padding:12px;border-radius:10px;background:#f8fbfd}}.scene-summary strong{{font-size:18px}}details{{border:1px solid #d7e3eb;border-radius:12px;padding:12px 15px;margin:14px 0}}summary{{cursor:pointer;font-weight:750}}.table-wrap{{overflow:auto}}table{{border-collapse:collapse;width:100%;font-size:13px}}th,td{{text-align:left;padding:9px 10px;border-bottom:1px solid #e3ebf1;white-space:nowrap}}th{{background:#f1f6fa}}.tabs{{display:flex;gap:8px;flex-wrap:wrap}}.tabs button{{border:1px solid #bbcfe0;background:#fff;border-radius:999px;color:#29516e;padding:8px 15px;font-weight:750}}.tabs button.active{{background:#245f97;color:white;border-color:#245f97}}.motion-row{{display:grid;grid-template-columns:170px 1fr 145px;gap:12px;align-items:center;border-bottom:1px solid #e5edf2;padding:15px 0}}.motion-row .name{{font-weight:800}}.motion-row .sub{{font-size:12px;color:var(--muted)}}.track{{height:36px;position:relative;border-radius:7px;background:repeating-linear-gradient(to right,#e8eff4 0,#e8eff4 1px,transparent 1px,transparent 20%);border-bottom:1px solid #c9d8e4}}.track .span{{position:absolute;top:16px;height:3px;background:#7197b9}}.track .dot{{position:absolute;top:10px;height:15px;width:15px;transform:translateX(-50%);border-radius:50%;background:#426c96;border:2px solid white;box-shadow:0 0 0 1px #426c96}}.track .dot.end{{background:#e68a53;box-shadow:0 0 0 1px #e68a53}}.motion-value{{text-align:right;font-size:13px}}.motion-value b{{font-size:17px}}.axis{{display:flex;justify-content:space-between;margin-left:182px;margin-right:157px;font-size:11px;color:#7b8b99}}.phase-grid{{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin:20px 0}}.phase{{border-radius:13px;padding:18px;background:#eff6fa;border:1px solid #dbe7ed}}.phase b{{font-size:18px}}.phase p{{font-size:14px;color:#476174}}.bar-row{{display:grid;grid-template-columns:120px 1fr 55px;gap:10px;align-items:center;margin:12px 0}}.bar{{height:16px;border-radius:6px;background:#eaf0f4;position:relative;overflow:hidden}}.bar .base{{height:100%;background:#91b6cd}}.bar .new{{height:100%;background:#177f89;position:absolute;top:0;left:0}}.threshold-grid{{display:grid;grid-template-columns:1fr 1fr;gap:18px}}.threshold-card{{padding:18px;background:#f6fafb;border:1px solid #e2ecee;border-radius:13px}}.threshold-card .big{{font-size:31px;font-weight:850;line-height:1.15}}.threshold-card .accent{{color:#087f85}}.compare-table{{display:grid;grid-template-columns:1fr 1fr;gap:14px}}.compare-table article{{padding:18px;border:1px solid #dce7ee;border-radius:12px;background:#f7fafc}}.evidence-fig{{width:100%;border-radius:10px;border:1px solid #e1e9ef;margin:8px 0 18px}}#atlas{{height:min(67vh,630px);min-height:440px;border-radius:14px;background:#111b2d;overflow:hidden}}.legend{{display:inline-block;width:170px;height:10px;border-radius:20px;background:linear-gradient(90deg,#294c9e,#2da9af,#f6d36a,#f47450)}}.footlinks{{display:flex;gap:12px;flex-wrap:wrap;font-size:13px;margin-top:15px;overflow-wrap:anywhere}}
@media(max-width:740px){{.home-layout,.threshold-grid,.compare-table,.phase-grid{{grid-template-columns:1fr}}.summary{{grid-template-columns:1fr}}.motion-row{{grid-template-columns:125px 1fr;gap:8px}}.motion-value{{grid-column:2;text-align:left}}.axis{{margin-left:133px;margin-right:0}}.scene-summary{{grid-template-columns:1fr}}section{{padding:21px}}}}
</style><style>
.threshold-picker{{border:1px solid #d8e7ed;background:#f4fafb;border-radius:14px;padding:16px 19px;margin:18px 0 8px}}
.threshold-picker label{{display:flex;justify-content:space-between;align-items:baseline;gap:12px;font-weight:800}}
.threshold-picker output{{color:#087f85;font-size:25px;font-weight:850;white-space:nowrap}}
.threshold-picker input[type=range]{{width:100%;margin:15px 0 3px;accent-color:#087f85;cursor:pointer}}
.threshold-picker input[type=range]:focus-visible{{outline:3px solid #f2b650;outline-offset:5px}}
.threshold-scale{{display:flex;justify-content:space-between;color:#53647a;font-size:12px}}
.threshold-card .bar-row{{grid-template-columns:95px 1fr 55px}}
.touch-picker{{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px;margin:20px 0}}
.touch-picker button{{text-align:left;border:1px solid #cbdde7;background:#f8fbfc;color:var(--ink);border-radius:13px;padding:12px 14px;min-height:118px;transition:background .15s,border-color .15s,transform .15s}}
.touch-picker button:hover{{transform:translateY(-2px);border-color:#6aa59b}}
.touch-picker button.active{{border-color:#1c766c;background:#e8f5f0;box-shadow:inset 0 0 0 1px #1c766c}}
.touch-picker .touch-name{{display:block;font-weight:850;font-size:16px}}
.touch-picker .touch-stats{{display:block;color:#4f6673;font-size:12px;margin-top:6px}}
.touch-picker .touch-count{{display:block;color:#567b72;font-size:12px;margin-top:2px}}
.touch-metrics{{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin:18px 0}}
.touch-metrics article{{border:1px solid #dce7e9;background:#f5faf9;border-radius:12px;padding:13px}}
.touch-metrics b{{display:block;font-size:22px;line-height:1.2}}
.touch-metrics span{{font-size:12px;color:#536875}}
.touch-charts{{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px;margin-top:14px}}
.touch-chart{{border:1px solid #dce7e9;border-radius:13px;padding:14px;background:#fff}}
.touch-chart h3{{font-size:16px;margin:0 0 2px}}
.touch-chart p{{font-size:12px;color:#536875;min-height:38px;margin:0 0 7px}}
.touch-chart svg{{display:block;width:100%;height:auto}}
.touch-chart .axisnote{{font-size:11px;color:#5b6d77}}
@media(max-width:740px){{.threshold-picker{{padding:14px}}.threshold-picker label{{align-items:center}}}}
@media(max-width:850px){{.touch-charts{{grid-template-columns:1fr}}.touch-metrics{{grid-template-columns:repeat(2,1fr)}}}}
@media(max-width:720px){{.touch-picker{{grid-template-columns:repeat(2,minmax(0,1fr))}}}}
@media(max-width:420px){{.touch-picker{{grid-template-columns:1fr}}}}
</style><script type="importmap">{{"imports":{{"three":"./vendor/three.module.js"}}}}</script></head><body>
<header><div class="eyebrow">Two-day evidence · one participant</div><h1>Touch、阅读 Home 与主动 Hover</h1><p>按“接近 → 到达或确认 → 后续移动”读轨迹，再看空间 Home 和阈值。三类行为来自 9 月 15/16 日同一人的手机区域 Pencil 数据。</p></header>
<main><nav><a href="#motion">01 三类轨迹</a><a href="#touch-motion">触屏动作</a><a href="#home">02 阅读 Home</a><a href="#gaze">03 视觉热区</a><a href="#threshold">04 菜单阈值</a><a href="#le">Le 2019</a><a href="#atlas-section">3D 热区</a><a href="#evidence">原始证据</a></nav>
<section aria-labelledby="findings"><div class="kicker">研究判断</div><h2 id="findings">三个先看结果</h2><div class="summary">
<div class="fact"><div class="term">空间 Home</div><strong>{replicated}/12 段复现</strong><span>全部阅读段在 {min(first_times)}–{max(first_times)} 秒内出现可估计热点；只有前后半段中心≤50 pt 的段落算位置复现。</span></div>
<div class="fact"><div class="term">运动形态</div><strong>移动 → 降速</strong><span>B3 两日可比窗分别 {b3[0]['speedLower']}/{b3[0]['paired']}、{b3[1]['speedLower']}/{b3[1]['paired']} 末段更慢；自然阅读也会降速，需看目标和动作序列。</span></div>
<div class="fact"><div class="term">800 ms 潜在候选</div><strong>{a_all['candidate500']} → {a_all['candidate800']}</strong><span>两日自然阅读的规则候选减少 {a_all['reductionPct']}%。主动菜单 800 ms 的准确率尚无可测数据。</span></div></div>
<p class="callout small">这是同一位操作者、两种姿势、两种协议的探索结果。9/15 与 9/16 的内容目标和 C3 几何不同；百分比描述这两日样本，不代表人群误触率。</p></section>

<section id="motion"><div class="kicker">01 · Three behavior sequences</div><h2>接近、到达或确认、再离开：三种行为放在同一把尺上</h2><p>三列按不同事件对齐，上排是笔尖距当下目标／Home 中心的距离，中排是 Pencil XY 速度，下排是 Z 原值变化速度。Z 速度按每对悬停点的 <strong>|ΔZ|/Δt</strong> 计算，所以和 XY 速度一样从零开始；三列共用刻度：XY 0–{sequence['axes']['speedAxisPtPerS']} pt/s，Z 0–{sequence['axes']['zSpeedAxisRawPerS']} API 原值/s。每 50 ms 汇总一次，淡色为事件间四分位范围。触屏、缺失值和超过 100 ms 的缺口留空，不补零。</p>
<img class="evidence-fig" src="sequence-comparison.png" alt="三列三层轨迹：Touch、阅读 Home、B2 悬停单选及 B3 悬停多选的目标距离、XY 速度和非负的 Z 原值变化速度；每排共享纵轴刻度">
<div class="summary"><article class="fact"><div class="term">Touch · A1</div><strong>{sequence['groups']['Touch']['events']} 次</strong><span>0 点为 TOUCH_DOWN。点击试次通常很快结束，抬笔后的下一目标不在同一试次内，不延长或拼接轨迹。<a href="#touch-motion">查看其他触屏动作</a>。</span></article><article class="fact"><div class="term">阅读 Home · A5–A7</div><strong>{sequence['groups']['阅读 Home']['events']} 次进入</strong><span>来自 {sequence['groups']['阅读 Home']['trials']} 段前后位置复现的阅读试次。0 点只是进入回顾性 Home 圈，没有确认动作，也未使用停留阈值筛选。</span></article><article class="fact"><div class="term">Intentional Hover · B2 / B3</div><strong>B2 {sequence['groups']['B2 单选']['events']} / B3 {sequence['groups']['B3 多选']['events']} 次</strong><span>紫线为 {sequence['groups']['B2 单选']['trials']} 次单选试次，蓝线为 {sequence['groups']['B3 多选']['trials']} 次多选试次中的非末次选中。B2 观察接近与确认，B3 还可观察同试次内向下一目标迁移。</span></article></div>
<p class="small muted">Z 速度只表示 API 原值变化得多快，不含下沉或抬升方向；<a href="sequence-comparison.json">派生数据</a>另保留带符号的 ΔZ/Δt。Z 未校准成毫米，不能与 XY 的 pt/s 直接比较。曲线按事件取中位，同一次阅读可贡献多个 Home 进入，B3 一次试次可贡献两次选择；B2/B3 各自计算，没有混成一条线。上面的事件数不等于独立参与者数。三列 0 点事件语义不同，B2 与 B3 的目标布局也不同，速度形状不能直接称为意图分类准确率。</p></section>

<section id="touch-motion"><div class="kicker">Touch motion · A1–A7</div><h2>一次触屏分两段：接近屏幕，再保持接触</h2><p>上图的 Touch 只代表 <strong>A1 点击</strong>。下方把点击、拖动、横竖滚动和阅读中的触屏分开。选一张任务卡：先看每次接触的真实时长和已观测路径，再读落笔前 1 秒的速度变化，以及落笔到抬笔期间的运动。</p>
<p class="callout">这两日的 A1 点击接触中位为 <strong>{touch['tasks']['A1']['contactDurationMs']['median']:.0f} ms、实测路径 {touch['tasks']['A1']['observedPathPt']['median']:.0f} pt</strong>；A2 拖动为 <strong>{touch['tasks']['A2']['contactDurationMs']['median']:.0f} ms、{touch['tasks']['A2']['observedPathPt']['median']:.0f} pt</strong>。因此“普通触屏”至少要区分短接触和持续接触移动；两者落笔前的靠近动作也应分别看，不能用 A1 一条线代表全部 Touch。</p>
<div id="touch-picker" class="touch-picker" role="group" aria-label="选择触屏任务"></div>
<p id="touch-context" class="muted"></p><div id="touch-metrics" class="touch-metrics" aria-live="polite"></div>
<div class="touch-charts"><article class="touch-chart"><h3>接近 · XY 速度</h3><p>距 TOUCH_DOWN 的真实时间；落笔前 1 秒</p><div id="touch-pre-xy"></div></article><article class="touch-chart"><h3>接近 · Z 变化速度</h3><p>悬停 API 原值 |ΔZ|/Δt；不是毫米速度</p><div id="touch-pre-z"></div></article><article class="touch-chart"><h3>接触 · XY 速度</h3><p>TOUCH_DOWN → TOUCH_UP；横轴为各次接触的 0–100% 进度</p><div id="touch-contact-xy"></div></article></div>
<p class="small muted">实线为事件中位，浅色带为四分位；断点表示该时间箱无有效样本。接触过程按百分比对齐只用于看形态，<strong>真实时长请看任务卡</strong>。接触时没有悬停 Z，不把它画成 0。A5–A7 是阅读场景里的混合触屏行为，不能仅凭轨迹把每一次判成点击或滑动。这里是一位操作者用绑指 Pencil 完成的两日任务，不代表裸指人群。<a href="touch-motion.json">查看数据、覆盖与来源</a>。</p></section>

<section id="home"><div class="kicker">02 · Spatial reference</div><h2>阅读时，多久能找到 Home Position？</h2><p>彩色热区是这段阅读里 Pencil 在屏幕上方各位置的<strong>实际观测时间</strong>；黄圈是 50 pt 半径的高密度位置候选。它不看停留时长、速度或 Z。先选场景与姿势，再看首次候选与前后半段是否复现。</p>
<div id="scene-summary" class="scene-summary"></div>
<div class="controls"><label>日期<select id="home-day"></select></label><label>姿势<select id="home-posture"><option value="THUMB">拇指</option><option value="CRADLE_INDEX">托握＋食指</option></select></label><label>阅读场景<select id="home-scene"><option value="news">新闻长文</option><option value="notes">图文流</option><option value="video">短视频流</option></select></label></div>
<div class="home-layout"><div><div class="phone-wrap"><canvas id="home-map" width="390" height="830" role="img" aria-label="手机局部阅读悬停热区与Home位置"></canvas></div><div class="map-legend"><span class="gradient"></span> 低 → 高观测时间；黄圈 = Home 候选</div></div><div><div id="home-meta" class="home-meta"></div><div id="home-status" class="status"></div><h3 style="margin-top:18px">观察时间线</h3><p class="small muted">绿色：此时热点已在整段参考中心 30 pt 内；橙色：仍偏离。后续持续接近且前后半段复现，才报“稳定定位”。</p><div id="home-prefix" class="mini-strip"></div><p id="home-prefix-note" class="small muted"></p></div></div>
<details><summary>查看全部 12 段的定位时间与覆盖</summary><div class="table-wrap"><table><thead><tr><th>日期</th><th>场景</th><th>姿势</th><th>首次候选</th><th>复现后的稳定时间</th><th>前后中心距</th><th>有效悬停</th></tr></thead><tbody id="home-table"></tbody></table></div></details>
<p class="small muted">“首次候选”仅表示已有至少 1 秒有效悬停、且主热点包含≥20%已观测悬停。整段中心为回顾性参考；位置复现指前后两半中心相距≤50 pt。未复现的段落仍显示热点，但不能称稳定 Home。热区位置可能受页面布局、滚动和手部姿势影响。</p></section>


<section id="gaze"><div class="kicker">03 · Next collection</div><h2>视觉热区 × Pencil 热区：已接入采集，等待真机校准数据</h2><p>当前两日 CSV 只有 Pencil，没有前摄视线，因此这里没有绘制视觉热区或“眼手同目标准确率”。新 App 的可选前摄采集会自动做 9 点拟合和 4 点独立验证，记录同一手机区域的视线估计、追踪缺口与内容对象 ID。视觉与悬停热区将以相同网格和有效观测时间对比。</p><p class="callout">“眼睛和 Pencil 同看一个物体”适合作为附加证据，暂不作为硬性成功条件。阅读会自然看向手指附近的内容；B3 也可能先看下一目标才移笔。若小对象校准未达到预设精度，只报告较大内容区域，不把缺失视线判作无意图。</p><p class="small"><a href="gaze-protocol.md">查看 V2.4 采集和验证方案</a></p></section>

<section id="threshold"><div class="kicker">04 · Menu decision</div><h2>停留多久才弹菜单？</h2><p>拖动阈值，观察两天自然阅读里<strong>规则可能触发的候选</strong>怎样变化。一段完整的同对象停留最多计一次；500 ms 是当前采集规则的固定对照。</p>
<div class="threshold-picker"><label for="threshold-ms">菜单触发停留阈值 <output id="threshold-ms-value" for="threshold-ms">800 ms</output></label><input id="threshold-ms" type="range" min="100" max="1000" step="25" value="800" aria-label="菜单触发停留阈值，100 到 1000 毫秒"><div class="threshold-scale"><span>100 ms</span><span>500 ms · 现行规则</span><span>1000 ms</span></div></div>
<div class="controls"><label>日期<select id="threshold-day"><option value="BOTH">两天合看</option></select></label><label>场景<select id="threshold-scene"><option value="ALL">全部阅读场景</option><option value="news">新闻长文</option><option value="notes">图文流</option><option value="video">短视频流</option></select></label></div>
<div class="threshold-grid"><article class="threshold-card"><h3>A5–A7 · 自然阅读内容</h3><div id="a-threshold" class="big"></div><p id="a-threshold-sub" class="muted"></p><div id="a-threshold-bars"></div></article><article class="threshold-card"><h3>C3 · 指定内容对象</h3><div id="c-threshold" class="big accent"></div><p id="c-threshold-sub" class="muted"></p><div id="c-threshold-bars"></div></article></div>
<p id="threshold-day-note" class="small muted"></p>
<p class="callout"><strong id="threshold-accuracy-title">真实准确率无法从现有数据估计。</strong> <span id="threshold-accuracy-detail"></span></p>
<details><summary>逐日、逐场景候选数量</summary><div class="table-wrap"><table><thead><tr><th>日期</th><th>对象范围</th><th>场景</th><th>阅读段</th><th>分钟</th><th>500 ms</th><th id="threshold-table-ms">所选阈值</th><th>相对变化</th></tr></thead><tbody id="threshold-table"></tbody></table></div></details><p class="small muted">9/15 C3 是旧协议的大对象，9/16 C3 是 48×48 pt 内容对象，不能把跨日差额归因于时间阈值；A 阅读对象也不等于 B1 抽象菜单目标。滑杆只回算报告，不修改采集 App。</p></section>

<section id="le"><div class="kicker">05 · External reference</div><h2>和 Le 2019 能比较什么？</h2><div class="compare-table"><article><h3>Le 2019 · 非意图输入背景</h3><p>官方研究用光学动捕观察右手单手握机时拇指和支撑手指的自然动作，重点是手机背部潜在的非意图输入。当前本地派生表中，READ 拇指有 <strong>{le['readingRows']} 条≥1秒任务记录、{le['participants']} 位参与者</strong>；按本地严格规则得到 <strong>{le['readingStableEpisodes']} 段自然离屏稳定片段</strong>，时长中位 {le['readingStableMedianMs']:.0f} ms。</p><p class="small muted">严格规则：速度&lt;20 mm/s、≥400 ms、距触摸&gt;300 ms。指甲标记点、手机局部 mm；没有“主动 Hover”标签，和本实验同对象停留计数口径不同。</p></article><article><h3>本实验 · 主动悬停</h3><p>绑指 Pencil 在手机仿真区正面操作。B1/B2/B3 有任务指令与菜单/选择事件，可观察移向目标、减速、短暂停留；B3 再出现目标间迁移。A 阅读则提供同一设备、同一操作者的自然参照。</p><p class="small muted">笔尖 XY 为 pt、Z 为 API 原值；任务标签只是指令代理。</p></article></div>
<p class="callout">可比较的是<strong>形态问题</strong>：自然阅读有没有空间聚集和长停留，主动任务是否出现目标定向的移动与重复选择。不能把两套 3D 坐标直接重叠，也不能用 Le 的支撑手指当本实验的“无意图”真值来计算分类准确率。下一步若做识别，应在本实验同一传感器下用 A 训练基线、C1–C3 留作验证，并收集独立的真实意图标注。</p>
<p class="small"><a href="https://www.medien.ifi.lmu.de/pubdb/publications/pub/le2019investigatingunintended/le2019investigatingunintended.pdf">Le et al. 2019 论文</a> · <a href="https://github.com/interactionlab/unintended-input-dataset">官方数据仓库</a> · <a href="le-reference.json">本地对照来源与哈希</a></p></section>

<section id="atlas-section"><div class="kicker">Spatial exploration</div><h2>手机内 3D 热区</h2><p>选择 A5–A7 可看完整阅读段的悬停体素，手机平面上的黄圈是所选场景的 XY Home 候选；它没有指定 Z 高度。其他任务仍显示原事件前的热区。旋转观察时请留意高度轴是 API 原值 0–1，视觉比例不代表毫米。</p><div class="controls"><label>日期<select id="day"></select></label><label>姿势<select id="posture"><option value="THUMB">拇指</option><option value="CRADLE_INDEX">托握＋食指</option><option value="ALL">全部</option></select></label><label>任务<select id="group"></select></label><label>最低热度<input id="atlas-threshold" type="range" min="0" max="95" value="5"><output id="atlas-threshold-value">5%</output></label><span class="legend" aria-label="热度由蓝到红"></span></div><div id="atlas" aria-label="手机局部三维悬停热区"></div><p id="atlas-meta" class="muted small"></p></section>

<section id="evidence"><div class="kicker">Audit trail</div><h2>来源、图形与分析边界</h2><p>两日共 {summary['includedEvents']} 个有效对齐事件，{summary['excludedEvents']} 个因缺少连续悬停段排除。阅读 Home 另用完整 A5–A7 成功阅读段，不以候选事件切窗。手机外和手指样本不进入轨迹；缺口 >100 ms 不连接。两日均只有一位操作者；9/15 用户确认两轮均右手，9/16 日志无左右手字段。</p>
<details><summary>六组任务早期/末段速度与 Z 配对证据</summary><div class="kicker">02 · Behavior shape</div><h2>哪些运动变化值得看？</h2><p>用同一把尺显示事件前 <strong>800–500 ms</strong> 与最后 <strong>300 ms</strong> 的 XY 速度中位数。蓝点是前段、橙点是末段；橙点落在蓝点左侧表示减速。零点分别是菜单出现、悬停选择、静默候选或落笔，含义不能互换。</p>
<div class="tabs" id="motion-day"></div><div class="axis"><span>0 pt/s</span><span>275 pt/s</span><span>550 pt/s</span></div><div id="motion-rows"></div>
<div class="phase-grid"><article class="phase"><b>B1 / B2：接近并确认</b><p>连续接近段里的“速度下降 + Z 原值下降”较一致；自然阅读候选也可能出现同样组合，所以单一阈值不足以断言意图。</p></article><article class="phase"><b>B3 / B4：看完整动作</b><p>B3 的关键是多次“移动→停留→再次移动”；B4 是连续绕目标闭合的空间路径。两者不应压成一次 500 ms 静止判断。</p></article></div>
<p class="small muted">只纳入同一连续悬停段中早晚两个窗都可比的事件。每行显示可比窗/全部事件，缺口不补线；Z 是 API 原值，不是毫米。</p></section>
</details>
<details><summary>原报告的完整事件曲线与覆盖</summary><p class="small muted">六类行为、两天分面。用于核对原始曲线，不建议直接跨不同锚点或 Z 单位判断。</p><img class="evidence-fig" src="speed-curves.png" alt="原始XY速度曲线"><img class="evidence-fig" src="speed-change-curves.png" alt="原始有符号速度变化率曲线"><img class="evidence-fig" src="z-relative-curves.png" alt="原始相对Z曲线"><img class="evidence-fig" src="bin-coverage.png" alt="每个时间箱的有效事件覆盖"></details>
<details><summary>B3 第 1 / 2 / 3 次选择及全部任务表</summary><img class="evidence-fig" src="b3-order-curves.png" alt="B3按实际选择顺序的速度和相对Z"><div class="table-wrap"><table><thead><tr><th>日期</th><th>任务</th><th>事件/试次</th><th>可比窗</th><th>前段速度</th><th>末段速度</th><th>速度下降</th><th>Z 变小</th></tr></thead><tbody id="motion-table"></tbody></table></div></details>
<p class="small muted">逐点回放数据留在本机，当前页面只加载派生统计。9/15 V2.1 与 9/16 V2.3 的目标几何、内容与重试机制不同。Home 是空间候选，规则候选不是实际误触，主动任务标签不是心理意图真值。</p>
<div class="footlinks"><a href="method.md">方法文档</a><a href="home-position.json">Home 数据</a><a href="home-heat.json">阅读 3D 热区</a><a href="threshold-sweep.json">100–1000 ms 阈值曲线</a><a href="threshold-800.json">原 500/800 ms 回算</a><a href="event-metrics.csv">逐事件指标</a><a href="curves.json">完整曲线</a><a href="summary.json">汇总与来源</a></div><p class="small muted">来源 SHA-256：09-15 {source[0]['sha256']}；09-16 {source[1]['sha256']}。</p></section>
</main><script type="module" src="./decision_dashboard.js"></script><script type="module" src="./touch_motion.js"></script><script type="module" src="./atlas.js"></script></body></html>'''
    (output / "report.html").write_text(html, encoding="utf-8")
    shutil.copyfile(ROOT / "qa/decision_dashboard.js", output / "decision_dashboard.js")
    shutil.copyfile(ROOT / "qa/touch_motion.js", output / "touch_motion.js")
    shutil.copyfile(ROOT / "docs/protocol-gaze-v2-4.md", output / "gaze-protocol.md")
    return {"report": str(output / "report.html"), "homeTrials": len(home["trials"]),
            "homeReplicated": replicated, "reading500": a_all["candidate500"], "reading800": a_all["candidate800"]}
