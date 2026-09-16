#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Read-only, event-aligned two-day Pencil hover curves and time-weighted 3D atlas."""
import argparse
import collections
import csv
import hashlib
import json
import math
import shutil
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
INPUTS = [
    ("09-15 · V2.1", ROOT / "data/HoverIntent_2026-09-15 2.csv", ROOT / "analysis/trajectory_2026-09-15/hands_run2/replay-data.json"),
    ("09-16 · V2.3", ROOT / "data/HoverIntent_2026-09-16.csv", ROOT / "analysis/trajectory_2026-09-16/run1/replay-data.json"),
]
GROUPS = ["B1 菜单", "B2 单选", "B3 多选", "C 主动 Hover", "自然阅读候选", "点击前悬停"]
COLORS = {"B1 菜单": "#6e57d7", "B2 单选": "#bc55b5", "B3 多选": "#e17670", "C 主动 Hover": "#2b91b1", "自然阅读候选": "#6e9180", "点击前悬停": "#df9d41"}
BIN = .05
N_BINS = 20
XY_CELL = 20
Z_CELL = .05


def file_hash(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def group_for(trial, event):
    task, condition, typ = trial["task"], trial.get("condition"), event["type"]
    if typ == "MENU_OPEN" and task == "B1": return "B1 菜单"
    if typ == "HOVER_SELECT":
        if task == "B2": return "B2 单选"
        if task == "B3": return "B3 多选"
        if task in ("C1", "C2", "C3") and condition == "HOVER": return "C 主动 Hover"
    if typ == "CANDIDATE" and task in ("A5", "A6", "A7"):
        return "自然阅读候选"
    if typ == "TOUCH_DOWN" and (task == "A1" or (task == "C1" and condition == "TAP")):
        return "点击前悬停"
    return None


def trial_end(trial):
    return next((e["t"] for e in trial["events"] if e["type"] == "TRIAL_END"), trial["duration"])


def clean_segments(trial):
    end = trial_end(trial)
    return [[p for p in segment if p["t"] <= end + 1e-8 and p["input"] == "PENCIL"]
            for segment in trial["segments"] if segment and segment[0]["source"] == "PENCIL_HOVER"]


def coverage(points, lo, hi):
    return sum(max(0., min(hi, b["t"]) - max(lo, a["t"]))
               for a, b in zip(points, points[1:]) if .001 <= b["t"] - a["t"] <= .100000001)


def choose_segment(segments, anchor):
    candidates = []
    for si, segment in enumerate(segments):
        if len(segment) < 12: continue
        observed = coverage(segment, anchor - .5, anchor)
        if observed >= .45 and segment[0]["t"] <= anchor - .45 and segment[-1]["t"] >= anchor - .055:
            candidates.append((observed, si, segment))
    return max(candidates, default=(0, None, None), key=lambda row: row[0])


def motion_edges(segment):
    result = []
    previous = None
    for i, (a, b) in enumerate(zip(segment, segment[1:])):
        dt = b["t"] - a["t"]
        if not .001 <= dt <= .100000001:
            previous = None
            continue
        speed = math.hypot(b["x"] - a["x"], b["y"] - a["y"]) / dt
        midpoint = (a["t"] + b["t"]) / 2
        rate = (speed - previous[1]) / (midpoint - previous[0]) if previous else None
        result.append((i, midpoint, dt, speed, rate))
        previous = (midpoint, speed)
    return result


def one_event(trial, day, event, group, order, segments):
    anchor = event["t"]
    observed, si, segment = choose_segment(segments, anchor)
    if segment is None: return None
    edges = motion_edges(segment)
    output = {"day": day, "trialID": trial["id"], "task": trial["task"], "scene": trial.get("scene"),
              "posture": trial.get("posture"), "group": group, "order": order, "event": event["type"],
              "anchor": anchor, "coverageMs": round(observed * 1000, 1), "segment": si,
              "speed": [], "rate": [], "z": [], "zRelative": [], "paired": None}
    reference = [p["z"] for p in segment if p.get("z") is not None and anchor - .8 <= p["t"] < anchor - .5]
    z_ref = float(np.median(reference)) if len(reference) >= 2 else None
    for bi in range(N_BINS):
        lo = anchor - 1 + bi * BIN
        hi = lo + BIN
        e = [row for row in edges if lo <= row[1] < hi]
        zz = [p["z"] for p in segment if p.get("z") is not None and lo <= p["t"] < hi]
        output["speed"].append(float(np.median([row[3] for row in e])) if e else None)
        output["rate"].append(float(np.median([row[4] for row in e if row[4] is not None])) if any(row[4] is not None for row in e) else None)
        raw_z = float(np.median(zz)) if zz else None
        output["z"].append(raw_z)
        output["zRelative"].append(raw_z - z_ref if raw_z is not None and z_ref is not None else None)
    early_edges = [r[3] for r in edges if anchor - .8 <= r[1] < anchor - .5]
    late_edges = [r[3] for r in edges if anchor - .3 <= r[1] < anchor]
    late_z = [p["z"] for p in segment if p.get("z") is not None and anchor - .3 <= p["t"] < anchor]
    early_coverage = coverage(segment, anchor - .8, anchor - .5)
    late_coverage = coverage(segment, anchor - .3, anchor)
    if early_coverage >= .15 and late_coverage >= .2 and len(early_edges) >= 2 and len(late_edges) >= 2 and z_ref is not None and len(late_z) >= 2:
        output["paired"] = {"approachSpeed": float(np.median(early_edges)), "lateSpeed": float(np.median(late_edges)),
                            "speedChange": float(np.median(late_edges) - np.median(early_edges)),
                            "zEarly": z_ref, "zLate": float(np.median(late_z)),
                            "zChange": float(np.median(late_z) - z_ref),
                            "earlyCoverageMs": round(early_coverage * 1000, 1), "lateCoverageMs": round(late_coverage * 1000, 1)}
    return output, segment, edges


def summarize_curves(rows):
    curves = {}
    for key in sorted({(r["day"], r["group"]) for r in rows}):
        selected = [r for r in rows if (r["day"], r["group"]) == key]
        record = {"day": key[0], "group": key[1], "events": len(selected),
                  "trials": len({r["trialID"] for r in selected}), "metrics": {}}
        for metric in ("speed", "rate", "z", "zRelative"):
            bins = []
            for bi in range(N_BINS):
                values = [r[metric][bi] for r in selected if r[metric][bi] is not None]
                bins.append({"n": len(values), "median": float(np.median(values)) if values else None,
                             "q25": float(np.quantile(values, .25)) if values else None,
                             "q75": float(np.quantile(values, .75)) if values else None})
            record["metrics"][metric] = bins
        curves[f"{key[0]}|{key[1]}"] = record
    return curves


def add_heat(heat, day, posture, group, trial_id, segment, edges, anchor=None, seen=None):
    for i, t, dt, _, _ in edges:
        if anchor is not None:
            dt = max(0., min(segment[i + 1]["t"], anchor) - max(segment[i]["t"], anchor - 1))
            if dt <= 0: continue
        p = segment[i]
        z = p.get("z")
        if z is None or not 0 <= z <= 1: continue
        edge_key = (trial_id, p["sequence"], segment[i + 1]["sequence"])
        if seen is not None:
            if edge_key in seen: continue
            seen.add(edge_key)
        xyz = (min(int(p["x"] / XY_CELL), 19), min(int(p["y"] / XY_CELL), 41), min(int(z / Z_CELL), 19))
        for posture_key in (posture, "ALL"):
            heat[(day, posture_key, group)][xyz] += dt


def to_heat_json(heat):
    out = {}
    for key, voxels in heat.items():
        total = sum(voxels.values())
        out["|".join(key)] = {"seconds": round(total, 3), "voxelCount": len(voxels),
                              "voxels": [[*xyz, round(sec, 5)] for xyz, sec in voxels.items() if sec > 0]}
    return out


def table_rows(rows):
    result = []
    for day in [entry[0] for entry in INPUTS]:
        for group in GROUPS:
            rr = [r for r in rows if r["day"] == day and r["group"] == group]
            paired = [r["paired"] for r in rr if r["paired"]]
            result.append({"day": day, "group": group, "events": len(rr), "trials": len({r["trialID"] for r in rr}),
                           "paired": len(paired), "speedEarly": float(np.median([p["approachSpeed"] for p in paired])) if paired else None,
                           "speedLate": float(np.median([p["lateSpeed"] for p in paired])) if paired else None,
                           "speedLower": sum(p["speedChange"] < 0 for p in paired),
                           "zEarly": float(np.median([p["zEarly"] for p in paired])) if paired else None,
                           "zLate": float(np.median([p["zLate"] for p in paired])) if paired else None,
                           "zLower": sum(p["zChange"] < 0 for p in paired),
                           "zChange": float(np.median([p["zChange"] for p in paired])) if paired else None})
    return result


def plot_curves(curves, output):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib import font_manager
    font_manager.fontManager.addfont("/System/Library/Fonts/Supplemental/Arial Unicode.ttf")
    plt.rcParams.update({"font.family": "Arial Unicode MS", "axes.unicode_minus": False, "font.size": 10})
    days = [item[0] for item in INPUTS]
    x = np.array([-975 + 50 * i for i in range(N_BINS)])
    for metric, filename, label, ylim in [
        ("speed", "speed-curves.png", "XY 速度 · pt/s", (0, 520)),
        ("rate", "speed-change-curves.png", "有符号速度变化率 · pt/s²", (-8000, 8000)),
        ("z", "z-curves.png", "原始 Z · API 值", (0, 1)),
        ("zRelative", "z-relative-curves.png", "相对早期 Z · API 值", (-.35, .35)),
    ]:
        fig, axes = plt.subplots(1, 2, figsize=(15, 5.4), sharex=True, sharey=True)
        for ax, day in zip(axes, days):
            for group in GROUPS:
                rec = curves.get(f"{day}|{group}")
                if not rec or rec["events"] == 0: continue
                values = rec["metrics"][metric]
                yy = np.array([v["median"] if v["median"] is not None else np.nan for v in values])
                low = np.array([v["q25"] if v["q25"] is not None else np.nan for v in values])
                high = np.array([v["q75"] if v["q75"] is not None else np.nan for v in values])
                if metric == "rate":
                    yy, low, high = (np.clip(v, -8000, 8000) for v in (yy, low, high))
                ax.plot(x, yy, color=COLORS[group], lw=2, marker=".", ms=3, label=f"{group} · {rec['events']}事件/{rec['trials']}次")
                ax.fill_between(x, low, high, color=COLORS[group], alpha=.10)
            ax.axvspan(-500, 0, color="#d4dce7", alpha=.16)
            ax.axvline(0, color="#314557", lw=.8)
            if metric in ("rate", "zRelative"): ax.axhline(0, color="#82909e", lw=.7)
            ax.set(title=day, xlabel="事件前时间 · ms", xlim=(-1000, 0), ylim=ylim, ylabel=label)
            ax.grid(alpha=.16)
            ax.legend(loc="best", fontsize=7.7, framealpha=.9)
        fig.suptitle(f"两日事件对齐 · {label}\n阴影=事件间四分位范围；灰区=确认前500ms；0点按任务定义（选择/候选/落笔）", fontsize=13)
        fig.tight_layout()
        fig.savefig(output / filename, dpi=160)
        plt.close(fig)


def plot_b3(rows, output):
    import matplotlib.pyplot as plt
    days = [item[0] for item in INPUTS]
    x = np.array([-975 + 50 * i for i in range(N_BINS)])
    fig, axes = plt.subplots(2, 2, figsize=(13, 9), sharex=True)
    for ci, day in enumerate(days):
        for order, color in [(1, "#7954db"), (2, "#dc6b9d"), (3, "#ed9c45")]:
            selected = [r for r in rows if r["day"] == day and r["group"] == "B3 多选" and r["order"] == order]
            for ri, metric in enumerate(("speed", "zRelative")):
                y = [float(np.median([r[metric][i] for r in selected if r[metric][i] is not None]))
                     if any(r[metric][i] is not None for r in selected) else np.nan for i in range(N_BINS)]
                supported = len(selected) if metric == "speed" else sum(any(v is not None for v in r["zRelative"]) for r in selected)
                axes[ri, ci].plot(x, y, color=color, lw=2, marker=".", ms=3, label=f"第{order}次选择 · {supported}事件")
        for ri, metric in enumerate(("speed", "zRelative")):
            ax = axes[ri, ci]
            ax.axvspan(-500, 0, color="#d4dce7", alpha=.18)
            ax.axvline(0, color="#314557", lw=.8)
            if ri: ax.axhline(0, color="#82909e", lw=.7)
            ax.set(title=day, xlim=(-1000, 0), xlabel="选中前时间 · ms", ylabel="XY 速度 · pt/s" if ri == 0 else "相对早期 Z · API 值")
            ax.grid(alpha=.16)
            ax.legend(fontsize=8)
    fig.suptitle("B3 多选：按真实选择顺序对齐（同一试次最多3个对象）\n相对 Z 参考窗为 -800 至 -500 ms；无参考窗不补线", fontsize=13)
    fig.tight_layout()
    fig.savefig(output / "b3-order-curves.png", dpi=165)
    plt.close(fig)


def plot_coverage(curves, output):
    import matplotlib.pyplot as plt
    x = np.array([-975 + 50 * i for i in range(N_BINS)])
    fig, axes = plt.subplots(2, 2, figsize=(14, 8), sharex=True)
    for col, (day, _, _) in enumerate(INPUTS):
        for row, metric in enumerate(("speed", "zRelative")):
            ax = axes[row, col]
            for group in GROUPS:
                record = curves.get(f"{day}|{group}")
                if record:
                    ax.plot(x, [b["n"] for b in record["metrics"][metric]], color=COLORS[group], lw=1.7, label=group)
            ax.set(title=f"{day} · {'XY 速度' if row == 0 else '相对 Z'}", ylabel="实际贡献事件数", xlim=(-1000, 0), ylim=(0, None), xlabel="事件前时间 · ms")
            ax.grid(alpha=.16)
            if col == 1: ax.legend(fontsize=7.5)
    fig.suptitle("每个 50 ms 时间箱的真实事件覆盖\n相对 Z 需有早期参考窗，覆盖数通常少于 XY 速度", fontsize=13)
    fig.tight_layout()
    fig.savefig(output / "bin-coverage.png", dpi=150)
    plt.close(fig)


def fmt(value, digits=2):
    return "—" if value is None else f"{value:.{digits}f}"


def build_report(output, summary, paired, excluded, inputs):
    from html import escape
    rows = []
    for r in paired:
        rows.append("<tr>" + "".join(f"<td>{escape(str(v))}</td>" for v in (
            r["day"], r["group"], f"{r['events']} / {r['trials']}", r["paired"], fmt(r["speedEarly"], 1), fmt(r["speedLate"], 1),
            f"{r['speedLower']}/{r['paired']}", fmt(r["zChange"], 3), f"{r['zLower']}/{r['paired']}")) + "</tr>")
    b3 = [r for r in paired if r["group"] == "B3 多选"]
    b3_html = "".join(f"<strong>{escape(r['day'])}</strong>：{r['paired']} 个连续可比窗口，{r['speedLower']} 个末段速度更低，{r['zLower']} 个 Z 原值更低；Z 变化中位 {fmt(r['zChange'],3)}。" for r in b3)
    b3_order_html = "；".join(f"{escape(r['day'])} 第 {r['order']} 次 {r['paired']}/{r['events']} 可比" for r in summary["b3Order"])
    b3_trial_html = "；".join(f"{escape(r['day'])} 有连续配对的 {r['pairedTrials']}/{r['trials']} 次试次中，{r['slowerTrials']} 次速度中位下降、{r['zLowerTrials']} 次 Z 中位变小" for r in summary["b3TrialSummary"])
    cards = "".join("<div class=\"card\"><strong>{}</strong><br>{} 个重建试次 · {} 个有效对齐事件<br><span class=\"small\">SHA-256 {}</span></div>".format(
        escape(item["day"]), item["trials"], item["events"], escape(item["sha256"])) for item in inputs)
    html = f'''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Intentional Hover · 两日运动图谱</title><style>
    :root{{--ink:#20354b;--muted:#5b6d7c;--accent:#335cd2;--line:#dbe5f0;--bg:#f5f8fc}}
    *{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--ink);font:16px/1.65 system-ui,-apple-system,"PingFang SC",sans-serif}}header{{background:linear-gradient(135deg,#162b52,#4052a0 65%,#7456a8);color:white;padding:46px max(24px,calc((100vw - 1220px)/2))}}header h1{{font-size:clamp(28px,4vw,48px);margin:0 0 8px}}header p{{max-width:1000px;margin:0;color:#e4e9fa}}main{{max-width:1260px;margin:auto;padding:28px 20px 64px}}nav a{{color:#3b53a7;margin-right:16px}}section{{background:white;border:1px solid var(--line);border-radius:18px;padding:24px;margin:22px 0;box-shadow:0 10px 28px #203e6509}}h2{{margin:0 0 10px;font-size:25px}}h3{{margin:20px 0 8px}}p{{margin:8px 0 14px}}.lead{{font-size:19px;font-weight:650}}.muted{{color:var(--muted)}}.fig{{width:100%;height:auto;border:1px solid #edf1f5;border-radius:12px;margin:10px 0 22px}}table{{border-collapse:collapse;width:100%;font-size:13px}}th,td{{padding:9px;border-bottom:1px solid var(--line);text-align:left}}th{{background:#edf3fb;position:sticky;top:0}}.scroll{{overflow:auto}}.pill{{background:#e6edff;padding:4px 10px;border-radius:999px;font-size:13px;font-weight:650}}#atlas{{height:min(68vh,680px);min-height:440px;border-radius:14px;background:#111b2d;overflow:hidden}}.controls{{display:flex;gap:14px;flex-wrap:wrap;align-items:center;margin:14px 0}}select,input[type=range]{{font:inherit}}select{{border:1px solid #cbd6e5;border-radius:9px;padding:7px;background:white}}.legend{{height:12px;width:230px;border-radius:99px;background:linear-gradient(90deg,#294c9e,#2da9af,#f6d36a,#f47450)}}.small{{font-size:13px}}.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:12px}}.card{{background:#f1f5fb;border-radius:12px;padding:13px}}.card strong{{font-size:23px}}a{{color:#315cbd}}</style><script type="importmap">{{"imports":{{"three":"./vendor/three.module.js"}}}}</script></head><body>
    <header><span class="pill">两日实测 · 探索性分析</span><h1>Intentional Hover 运动图谱</h1><p>对齐主动选择、自然阅读候选与点击前的连续悬停。速度、速度变化率与原始 Z 分开呈现；3D 热区显示手机内 Pencil 悬停的实际观测时长。</p></header>
    <main><nav><a href="#curves">运动曲线</a><a href="#b3">多选下沉</a><a href="#atlas-section">3D 热区</a><a href="#quality">数据口径</a></nav>
    <section><h2>先看结论</h2><p class="lead">主动 Hover 的“移向对象 → 降速 → 约 500 ms 停留”可见；自然阅读也能产生同样长的稳定停留。单一速度或 Z 阈值不足以把两者可靠分开。</p><p>B3 多选按真实第 1/2/3 次选择分开看：{b3_html} 按试次合并重复选择后：{b3_trial_html}。这里的“Z 更低”仅指 API 原值变小，不能直接等同笔尖下降了多少毫米。B1 菜单与 B2 单选也有接近时降速、Z 变小；B3 更有辨识度的是连续多个目标的“移动→停留→再移动”序列，而非一次下降。</p><p class="muted">两天由同一位操作者采集；9/15 为 V2.1，9/16 为 V2.3。两日自然阅读曲线均只用 A5–A7；9/15 C3 自然条件的 69 个候选另有记录，但 9/16 C3 自然条件没有记录 CANDIDATE，故未纳入跨日曲线。两日阅读对象与目标几何不完全一致。</p></section>
    <section id="curves"><h2>事件前 1 秒：哪些特征不同？</h2><p>每条线是各事件在 50 ms 时间箱的中位；淡色为事件间四分位范围。灰区是事件前 500 ms。点击的 0 点是落笔，主动 Hover 是选择/菜单出现，阅读是静默候选达标；这些时间零点语义不同。</p><img class="fig" src="speed-curves.png" alt="两日 XY 速度曲线"><img class="fig" src="speed-change-curves.png" alt="两日有符号速度变化率曲线"><img class="fig" src="z-curves.png" alt="两日原始 Z 曲线"><img class="fig" src="z-relative-curves.png" alt="两日相对 Z 变化曲线"><h3>每箱有多少事件实际贡献？</h3><img class="fig" src="bin-coverage.png" alt="两日每个时间箱实际事件覆盖数"><p class="muted small">速度变化率为有符号速度导数：正值加速、负值减速。原始采样的导数噪声较大，图上将显示值限定为 ±8000 pt/s²；原始箱统计与逐箱覆盖数保留在 <a href="curves.json">curves.json</a>。</p></section>
    <section id="b3"><h2>B3 多选：有一致的下沉手势吗？</h2><p>下图按实际选中的第 1、2、3 个对象对齐。相对 Z 以确认前 -800 至 -500 ms 为参考；追踪断开或缺少参考窗时不补线。应先看同一事件的 Z 变化，再与其 XY 降速同时出现的比例比较。</p><img class="fig" src="b3-order-curves.png" alt="B3 选择顺序的速度和 Z 变化"><p class="small muted">按选择顺序的完整配对：{b3_order_html}。第 1 次较少取得连续接近段，其曲线不能代表所有第 1 次选择。</p><div class="scroll"><table><thead><tr><th>日期</th><th>任务</th><th>事件 / 试次</th><th>可比窗</th><th>前段速度</th><th>末段速度</th><th>速度下降</th><th>Z 变化中位</th><th>Z 变小</th></tr></thead><tbody>{''.join(rows)}</tbody></table></div><p class="small muted">前段为事件前 800–500 ms（至少 150 ms 实测覆盖），末段为事件前 300–0 ms（至少 200 ms 覆盖）。速度单位 pt/s，Z 为 API 原值。配对数可能远低于选择事件数；缺少前段连续采样不能被解读为“没有减速/下沉”。</p></section>
    <section id="atlas-section"><h2>手机内 Pencil 3D 热区</h2><p>每个体素的热度是观察到的悬停时间份额，不是回调点数量。XY 单位 pt；垂直轴是 Apple Pencil API Z 原值，按 0–1 显示，视觉比例不代表毫米。拖动旋转、滚轮缩放、右键平移。</p><div class="controls"><label>日期 <select id="day"></select></label><label>姿势 <select id="posture"><option value="ALL">全部</option><option value="THUMB">拇指</option><option value="CRADLE_INDEX">托握＋食指</option></select></label><label>任务 <select id="group"></select></label><label>最低热度 <input id="threshold" type="range" min="0" max="95" value="5"><output id="threshold-value">5%</output></label><div class="legend" aria-label="蓝低红高"></div></div><div id="atlas" aria-label="手机局部三维悬停热区"></div><p id="atlas-meta" class="muted"></p><p class="small muted">蓝→青→黄→红表示所选组内体素观测时长的相对强度；颜色会按组重标定，跨组请读实际秒数与份额。网格 XY 20 pt、Z 0.05。只纳入曲线事件前的有效窗口，B4 另纳入全部有效圈选悬停段。</p></section>
    <section id="quality"><h2>来源与分析边界</h2><div class="grid">{cards}</div><p>事件因缺少同一连续悬停段而排除：{excluded} 个。只保留手机内 Pencil 样本，过滤手指/污染时段、试次结束点和大于 100 ms 的缺口。9/15 两轮分别为右手拇指与右手食指（来自此前用户确认）；9/16 记录了姿势，但数据没有左右手字段，本报告不推断其左右手。</p><p>3D 热区受任务位置、页面内容和暴露时长影响；不能将热区直接解释为意图概率。阅读候选是规则可能触发，不代表实际误触。主动标签来自任务指令，不是心理意图真值。</p><p><a href="method.md">完整方法</a> · <a href="event-metrics.csv">逐事件指标 CSV</a> · <a href="b3-trial-metrics.csv">B3 逐试次 CSV</a> · <a href="summary.json">汇总 JSON</a> · <a href="curves.json">曲线与覆盖 JSON</a> · <a href="heat.json">热区数据 JSON</a></p></section>
    </main><script type="module" src="atlas.js"></script></body></html>'''
    (output / "report.html").write_text(html, encoding="utf-8")


def build(output):
    output.mkdir(parents=True, exist_ok=True)
    rows, heat = [], collections.defaultdict(lambda: collections.defaultdict(float))
    excluded, inputs = 0, []
    b3_trials = collections.Counter()
    for day, raw_path, cache_path in INPUTS:
        print(f"Loading {day}…", flush=True)
        data = json.loads(cache_path.read_text())
        sha = file_hash(raw_path)
        if sha != data["sha256"]: raise ValueError(f"Raw CSV and replay cache differ: {raw_path}")
        count = 0
        for trial in data["trials"]:
            segments = clean_segments(trial)
            seen = collections.defaultdict(set)
            order = 0
            for event in trial["events"]:
                group = group_for(trial, event)
                if not group: continue
                if group == "B3 多选": order += 1
                picked = one_event(trial, day, event, group, order if group == "B3 多选" else None, segments)
                if picked is None:
                    excluded += 1
                    continue
                record, segment, edges = picked
                rows.append(record)
                add_heat(heat, day, trial.get("posture") or "UNKNOWN", group, trial["id"], segment, edges,
                         anchor=event["t"], seen=seen[group])
                count += 1
            if trial["task"] == "B4":
                b3_trials[(day, "B4 试次")] += 1
                for segment in segments:
                    add_heat(heat, day, trial.get("posture") or "UNKNOWN", "B4 圈选", trial["id"], segment,
                             motion_edges(segment), seen=seen["B4 圈选"])
        inputs.append({"day": day, "source": raw_path.name, "sha256": sha, "trials": len(data["trials"]), "events": count,
                       "protocol": "HOVER_INTENT_V2_1" if "15" in day else "HOVER_INTENT_V2_3"})
        del data
    paired = table_rows(rows)
    curves = summarize_curves(rows)
    plot_curves(curves, output)
    plot_b3(rows, output)
    plot_coverage(curves, output)
    b3_order = []
    for day in [item[0] for item in INPUTS]:
        for order in (1, 2, 3):
            selected = [r for r in rows if r["day"] == day and r["group"] == "B3 多选" and r["order"] == order]
            b3_order.append({"day": day, "order": order, "events": len(selected),
                             "paired": sum(r["paired"] is not None for r in selected)})
    trial_metrics = []
    for day in [item[0] for item in INPUTS]:
        ids = sorted({r["trialID"] for r in rows if r["day"] == day and r["group"] == "B3 多选"})
        for tid in ids:
            selected = [r["paired"] for r in rows if r["day"] == day and r["group"] == "B3 多选" and r["trialID"] == tid and r["paired"]]
            trial_metrics.append({"day": day, "trialID": tid, "pairedSelections": len(selected),
                                  "medianSpeedChange": float(np.median([p["speedChange"] for p in selected])) if selected else None,
                                  "medianZChange": float(np.median([p["zChange"] for p in selected])) if selected else None})
    b3_trial_summary = []
    for day in [item[0] for item in INPUTS]:
        selected = [r for r in trial_metrics if r["day"] == day]
        eligible = [r for r in selected if r["pairedSelections"]]
        b3_trial_summary.append({"day": day, "trials": len(selected), "pairedTrials": len(eligible),
                                  "slowerTrials": sum(r["medianSpeedChange"] < 0 for r in eligible),
                                  "zLowerTrials": sum(r["medianZChange"] < 0 for r in eligible)})
    summary = {"inputs": inputs, "includedEvents": len(rows), "excludedEvents": excluded, "b4Trials": dict((k[0], v) for k, v in b3_trials.items()), "b3Order": b3_order, "b3TrialSummary": b3_trial_summary,
               "table": paired, "method": "event-aligned 50ms bins, single continuous hover segment, phone Pencil only; heat time-weighted"}
    (output / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    (output / "curves.json").write_text(json.dumps(curves, ensure_ascii=False, separators=(",", ":")))
    (output / "heat.json").write_text(json.dumps({"xyCellPt": XY_CELL, "zCellRaw": Z_CELL, "groups": to_heat_json(heat)}, ensure_ascii=False, separators=(",", ":")))
    with (output / "event-metrics.csv").open("w", newline="", encoding="utf-8") as f:
        cols = ["day", "trialID", "task", "scene", "posture", "group", "order", "event", "anchor", "coverageMs", "segment", "approachSpeed", "lateSpeed", "speedChange", "zEarly", "zLate", "zChange", "earlyCoverageMs", "lateCoverageMs"]
        writer = csv.DictWriter(f, fieldnames=cols)
        writer.writeheader()
        for r in rows:
            writer.writerow({k: r.get(k) if k not in ("approachSpeed", "lateSpeed", "speedChange", "zEarly", "zLate", "zChange", "earlyCoverageMs", "lateCoverageMs") else (r["paired"] or {}).get(k) for k in cols})
    with (output / "b3-trial-metrics.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["day", "trialID", "pairedSelections", "medianSpeedChange", "medianZChange"])
        writer.writeheader()
        writer.writerows(trial_metrics)
    shutil.copyfile(ROOT / "qa/two_day_motion_atlas.js", output / "atlas.js")
    shutil.copyfile(ROOT / "docs/two-day-motion-atlas-method.md", output / "method.md")
    shutil.copytree(ROOT / "qa/vendor", output / "vendor", dirs_exist_ok=True)
    build_report(output, summary, paired, excluded, inputs)
    from decision_dashboard import render as render_decision_dashboard
    dashboard = render_decision_dashboard(output)
    print(json.dumps({"output": str(output / "report.html"), "events": len(rows), "excluded": excluded, "B3": [r for r in paired if r["group"] == "B3 多选"]}, ensure_ascii=False, indent=2))
    print(json.dumps(dashboard, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=ROOT / "analysis/trajectory_2026-09-16/two_day_motion_atlas")
    build(parser.parse_args().output)
