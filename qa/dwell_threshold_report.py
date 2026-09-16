"""Retrospective dwell-threshold data for the local V2.3 report.

One completed DWELL_END is one candidate at most, regardless of how long it lasts.
The 500 ms point is reconciled with the app's recorded CANDIDATE event.
"""

from __future__ import annotations

import math
import json


NATURAL_TASKS = {"A5", "A6", "A7", "C3"}


def observed_hover_seconds(trial):
    seconds = 0.0
    for segment in trial["segments"]:
        if not segment or "HOVER" not in segment[0]["source"]:
            continue
        seconds += sum(b["t"] - a["t"] for a, b in zip(segment, segment[1:])
                       if b["t"] - a["t"] >= .001)
    return seconds


def build_dataset(trials, exposure):
    """Preserve measured durations and the app's 500 ms trigger evidence."""
    exposure_by_id = {row["trialID"]: row for row in exposure}
    rows = []
    for trial in trials:
        if trial["task"] not in NATURAL_TASKS or trial["condition"] != "NATURAL":
            continue
        is_c3 = trial["task"] == "C3"
        requested = set(trial["trial"].get("requested", []))
        ends = [event for event in trial["events"] if event["type"] == "DWELL_END"
                and (not is_c3 or event["metadata"].get("objectID") in requested)]
        logged = [event for event in trial["events"] if event["type"] == "CANDIDATE"
                  and (not is_c3 or event["metadata"].get("objectID") in requested)]
        episodes = []
        for event in ends:
            meta = event["metadata"]
            duration = float(meta["durationMs"])
            assert math.isfinite(duration) and duration >= 0
            fired = str(meta.get("candidate", "false")).lower() == "true"
            episodes.append(dict(durationMs=duration,
                                 thresholdMs=max(duration, 500.0 if fired else 0.0),
                                 logged500=fired))
        at_500 = sum(episode["thresholdMs"] + 1e-7 >= 500 for episode in episodes)
        if at_500 != len(logged):
            raise ValueError(f"500 ms candidate mismatch in trial {trial['id']}: "
                             f"computed {at_500}, logged {len(logged)}")
        target = exposure_by_id.get(trial["id"]) if is_c3 else None
        if is_c3 and target is None:
            raise ValueError(f"Missing C3 target exposure for trial {trial['id']}")
        rows.append(dict(cohort="C3" if is_c3 else "A", task=trial["task"],
                         scene=trial["scene"], posture=trial["posture"],
                         trialDurationS=trial["duration"],
                         hoverObservedS=target["hoverObserved_s"] if target else observed_hover_seconds(trial),
                         targetInsideS=target["insideObserved_s"] if target else None,
                         targetVisits=target["visits"] if target else None,
                         logged500=len(logged), episodes=episodes))
    return dict(protocol="HOVER_INTENT_V2_3", minMs=100, maxMs=1000, stepMs=25,
                defaultMs=500, trials=rows)


def summarize(dataset, threshold_ms, cohort, posture=None, scene=None):
    if not dataset["minMs"] <= threshold_ms <= dataset["maxMs"]:
        raise ValueError("Threshold outside report slider range")
    rows = [row for row in dataset["trials"] if row["cohort"] == cohort
            and (posture is None or row["posture"] == posture)
            and (scene is None or row["scene"] == scene)]
    episodes = [episode for row in rows for episode in row["episodes"]]
    candidates = sum(episode["thresholdMs"] + 1e-7 >= threshold_ms for episode in episodes)
    duration = sum(row["trialDurationS"] for row in rows)
    visits = sum(row["targetVisits"] or 0 for row in rows)
    return dict(trials=len(rows), episodes=len(episodes), candidates=candidates,
                minutes=duration / 60, perMinute=candidates * 60 / duration if duration else None,
                episodeShare=candidates / len(episodes) if episodes else None,
                hoverObservedS=sum(row["hoverObservedS"] for row in rows),
                targetInsideS=sum(row["targetInsideS"] or 0 for row in rows),
                targetVisits=visits,
                perVisit=candidates / visits if visits else None,
                logged500=sum(row["logged500"] for row in rows))


def render_section(dataset):
    a = summarize(dataset, 500, "A")
    c3 = summarize(dataset, 500, "C3")
    payload = json.dumps(dataset, ensure_ascii=False, separators=(",", ":")).replace("<", "\\u003c")
    return f"""
<style>
.dwell-panel{{margin:28px 0 42px;padding:26px;border:1px solid #cbdce9;border-radius:18px;background:#f6fbff;color:#163147}}
.dwell-panel *{{box-sizing:border-box}}.dwell-panel h3{{margin:0;font-size:25px;line-height:1.3}}
.dwell-panel p{{margin:9px 0 0;line-height:1.55}}.dwell-kicker{{font-size:12px;font-weight:800;letter-spacing:.12em;color:#126593;text-transform:uppercase}}
.dwell-controls{{display:grid;grid-template-columns:minmax(300px,2fr) repeat(2,minmax(150px,1fr));gap:14px;align-items:end;margin:22px 0}}
.dwell-controls label{{display:grid;gap:7px;font-size:14px;font-weight:650}}
.dwell-controls output{{font-size:22px;color:#075b9a;font-weight:850}}.dwell-controls select{{width:100%;padding:11px;border:1px solid #a8c5d9;border-radius:9px;background:white;color:#163147;font:inherit}}
.dwell-controls input[type=range]{{width:100%;accent-color:#0c77b5;cursor:pointer}}
.dwell-range-labels{{display:flex;justify-content:space-between;font-size:12px;color:#557082;font-weight:400}}
.dwell-presets{{display:flex;flex-wrap:wrap;gap:7px;margin:-3px 0 20px}}.dwell-presets button{{border:1px solid #9bc3d9;border-radius:99px;padding:7px 13px;background:white;color:#205272;font:inherit;cursor:pointer}}
.dwell-presets button[aria-pressed=true]{{background:#0b689e;border-color:#0b689e;color:white}}
.dwell-grid{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px}}.dwell-card{{padding:19px;border:1px solid #d5e3ec;border-radius:14px;background:white}}
.dwell-card h4{{margin:0 0 8px;font-size:18px}}.dwell-card .dwell-main{{font-size:32px;font-weight:850;line-height:1.1;color:#075b9a}}
.dwell-card.c3 .dwell-main{{color:#7b4b9b}}.dwell-card .dwell-sub{{font-size:14px;color:#445e71}}
.dwell-card .dwell-support{{font-size:13px;color:#526a79;min-height:40px}}.dwell-chart{{width:100%;height:160px;margin-top:10px}}
.dwell-table-wrap{{overflow-x:auto;margin-top:17px}}.dwell-panel table{{min-width:650px;background:white}}.dwell-panel td,.dwell-panel th{{padding:8px 10px;border:1px solid #d4e1ea;text-align:right;font-size:13px}}
.dwell-panel td:first-child,.dwell-panel th:first-child{{text-align:left}}.dwell-panel thead{{background:#e5f1f8}}
.dwell-note{{padding:11px 13px;border-left:3px solid #c18728;background:#fff8eb;font-size:14px}}.dwell-method{{font-size:13px;color:#476175}}
@media(max-width:780px){{.dwell-controls{{grid-template-columns:1fr 1fr}}.dwell-controls label:first-child{{grid-column:1/-1}}.dwell-grid{{grid-template-columns:1fr}}}}
</style>
<section id="dwell-filter" class="dwell-panel" aria-labelledby="dwell-heading">
 <div class="dwell-kicker">Natural reading · threshold explorer</div>
 <h3 id="dwell-heading">停留多久会触发规则？</h3>
 <p>拖动阈值查看 100–1000 ms 的潜在误触候选。计数单位是一段连续的同对象悬停；长停留只算一次。</p>
 <div class="dwell-controls">
  <label for="dwell-ms">停留阈值 <output id="dwell-ms-value" for="dwell-ms">500 ms</output>
   <input id="dwell-ms" type="range" min="100" max="1000" step="25" value="500" aria-label="停留阈值，100 到 1000 毫秒">
   <span class="dwell-range-labels"><span>100 ms</span><span>500 ms（采集规则）</span><span>1000 ms</span></span>
  </label>
  <label for="dwell-scene">阅读场景<select id="dwell-scene"><option value="">全部场景</option><option value="news">新闻长文</option><option value="notes">图文流</option><option value="video">短视频流</option></select></label>
  <label for="dwell-posture">姿势<select id="dwell-posture"><option value="">两种姿势</option><option value="THUMB">拇指</option><option value="CRADLE_INDEX">托握＋食指</option></select></label>
 </div>
 <div class="dwell-presets" aria-label="常用停留阈值"><button type="button" data-dwell-preset="100">100 ms</button><button type="button" data-dwell-preset="250">250 ms</button><button type="button" data-dwell-preset="500" aria-pressed="true">500 ms</button><button type="button" data-dwell-preset="750">750 ms</button><button type="button" data-dwell-preset="1000">1000 ms</button></div>
 <div class="dwell-grid">
  <article class="dwell-card"><h4>A5–A7 · 自然阅读内容</h4><div class="dwell-main" id="dwell-A-count">{a['candidates']} 次候选</div><div class="dwell-sub" id="dwell-A-rate">{a['perMinute']:.2f} 次/记录分钟</div><p class="dwell-support" id="dwell-A-support">{a['candidates']}/{a['episodes']} 段停留达标 · {a['minutes']:.1f} 分钟自然阅读</p><svg class="dwell-chart" id="dwell-chart-A" viewBox="0 0 480 160" role="img" aria-label="A5 到 A7 自然阅读候选随停留阈值变化"></svg></article>
  <article class="dwell-card c3"><h4>C3 · 蝴蝶内容对象</h4><div class="dwell-main" id="dwell-C3-count">{c3['candidates']} 次候选</div><div class="dwell-sub" id="dwell-C3-rate">{c3['perMinute']:.2f} 次/记录分钟</div><p class="dwell-support" id="dwell-C3-support">{c3['candidates']}/{c3['episodes']} 段停留达标 · 进入目标 {c3['targetVisits']} 次 · 目标内实测 {c3['targetInsideS']:.2f} 秒</p><svg class="dwell-chart" id="dwell-chart-C3" viewBox="0 0 480 160" role="img" aria-label="C3 蝴蝶对象候选随停留阈值变化"></svg></article>
 </div>
 <div class="dwell-table-wrap"><table><thead><tr><th scope="col">阈值</th><th scope="col">A 候选</th><th scope="col">A 次/分钟</th><th scope="col">C3 候选</th><th scope="col">C3 次/分钟</th></tr></thead><tbody id="dwell-table"></tbody></table></div>
 <p class="dwell-note">这里的“误触”只表示自然阅读时规则可能触发，日志没有真实误触或心理意图标签。A 面向阅读内容对象，C3 只面向 48×48 pt 蝴蝶；两组的目标暴露不同，不能把候选率差直接解释为阈值性能。改变滑杆只回算本地数据，不改变采集 App。</p>
 <p class="dwell-method">分母是筛选后自然试次的记录分钟；同时列出达标段／全部同对象停留段。两张曲线的纵轴分别缩放，请用“次/分钟”比较数值。C3 显示目标进入次数及目标内实测时间。500 ms 档与原始 CANDIDATE 事件逐试次校准；记录时长略短于 500 ms 但已有触发事件时，以该事件为准。超过 500 ms 的主动选择召回无法从现有自动结束的试次推断。<a href="dwell_threshold_data.json">查看回算数据与原始时长</a>。</p>
</section>
<script id="dwell-threshold-data" type="application/json">{payload}</script><script src="./dwell_threshold.js" defer></script>
"""
