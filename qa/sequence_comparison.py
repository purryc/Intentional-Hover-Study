#!/usr/bin/env python3
"""Three anchor-specific motion sequences, read-only from verified replay caches.

The three 0-ms anchors have different meanings. No gaps or input sources are joined.
"""
from __future__ import annotations

import collections
import json
import math
from pathlib import Path

import numpy as np

from build_two_day_motion_atlas import INPUTS, file_hash, trial_end

PRE, POST, BIN = 1.0, 1.5, 0.05
CENTERS = np.arange(-PRE + BIN / 2, POST, BIN)
GROUPS = ("Touch", "阅读 Home", "B2 单选", "B3 多选")
COLUMNS = (("Touch",), ("阅读 Home",), ("B2 单选", "B3 多选"))
COLORS = {"Touch": "#267d76", "阅读 Home": "#bd7e45", "B2 单选": "#8656a7", "B3 多选": "#455baf"}


def eligible_segments(trial, include_touch):
    end = trial_end(trial)
    result = []
    allowed = ("PENCIL_HOVER", "PENCIL_TOUCH") if include_touch else ("PENCIL_HOVER",)
    for segment in trial["segments"]:
        kept = []
        for p in segment:
            valid = (p.get("input") == "PENCIL" and p.get("source") in allowed
                     and 0 <= p["t"] <= end + 1e-8 and 0 <= p["x"] <= 390
                     and 0 <= p["y"] <= 830)
            if not valid or (kept and p["source"] != kept[-1]["source"]):
                if kept:
                    result.append(kept)
                kept = []
            if valid:
                kept.append(p)
        if kept:
            result.append(kept)
    return result


def bins_for(segments, anchor, center):
    speeds = [[] for _ in CENTERS]
    distances = [[] for _ in CENTERS]
    z_rates = [[] for _ in CENTERS]
    z_speeds = [[] for _ in CENTERS]
    for segment in segments:
        for p in segment:
            index = int(math.floor((p["t"] - anchor + PRE) / BIN))
            if 0 <= index < len(CENTERS):
                distances[index].append(math.hypot(p["x"] - center[0], p["y"] - center[1]))
        for a, b in zip(segment, segment[1:]):
            dt = b["t"] - a["t"]
            if not 0.001 <= dt <= 0.100000001:
                continue
            time = (a["t"] + b["t"]) / 2 - anchor
            index = int(math.floor((time + PRE) / BIN))
            if 0 <= index < len(CENTERS):
                speeds[index].append(math.hypot(b["x"] - a["x"], b["y"] - a["y"]) / dt)
                # Z is an API-relative value. Speed takes the magnitude of each
                # valid hover pair before aggregation; keep direction separately.
                za, zb = a.get("z"), b.get("z")
                if (a.get("source") == b.get("source") == "PENCIL_HOVER"
                        and za is not None and zb is not None
                        and math.isfinite(za) and math.isfinite(zb)):
                    rate = (zb - za) / dt
                    z_rates[index].append(rate)
                    z_speeds[index].append(abs(rate))
    return {
        "speed": [float(np.median(v)) if v else None for v in speeds],
        "distance": [float(np.median(v)) if v else None for v in distances],
        "zRate": [float(np.median(v)) if v else None for v in z_rates],
        "zSpeed": [float(np.median(v)) if v else None for v in z_speeds],
    }


def home_entries(trial, home):
    if not home or not home.get("halfReplicated") or not home.get("home"):
        return []
    center = (home["home"]["x"], home["home"]["y"])
    radius = 50.0
    entries = []
    for segment in eligible_segments(trial, include_touch=False):
        last = -1e9
        for a, b in zip(segment, segment[1:]):
            if not 0.001 <= b["t"] - a["t"] <= 0.100000001:
                continue
            da = math.hypot(a["x"] - center[0], a["y"] - center[1])
            db = math.hypot(b["x"] - center[0], b["y"] - center[1])
            if da > radius >= db and b["t"] - last >= 2.0 and b["t"] >= 1.0 and b["t"] + POST <= trial_end(trial):
                entries.append((b["t"], center))
                last = b["t"]
    return entries


def anchors(trial, home):
    if trial["task"] == "A1" and trial.get("success"):
        obj = next((o for o in trial["trial"].get("objects", []) if o["id"] == "target"), None)
        if obj:
            b = obj["bounds"]
            center = (b["x"] + b["width"] / 2, b["y"] + b["height"] / 2)
            for event in trial["events"]:
                if event["type"] == "TOUCH_DOWN":
                    yield "Touch", event["t"], center
    if trial["task"] in ("A5", "A6", "A7") and trial.get("success"):
        for anchor, center in home_entries(trial, home):
            yield "阅读 Home", anchor, center
    if trial["task"] in ("B2", "B3") and trial.get("success"):
        selected = [e for e in trial["events"] if e["type"] == "HOVER_SELECT"]
        objects = {o["id"]: o["bounds"] for o in trial["trial"].get("objects", [])}
        # B2 has one confirmation per trial; only B3 has a later target in that trial.
        for event in selected if trial["task"] == "B2" else selected[:-1]:
            object_id = event["metadata"].get("objectID")
            if object_id in objects:
                b = objects[object_id]
                group = "B2 单选" if trial["task"] == "B2" else "B3 多选"
                yield group, event["t"], (b["x"] + b["width"] / 2, b["y"] + b["height"] / 2)


def summarize(events):
    summary = {}
    for group in GROUPS:
        selected = [e for e in events if e["group"] == group]
        out = {"events": len(selected), "trials": len({(e["day"], e["trialID"]) for e in selected}), "metrics": {}}
        for metric in ("speed", "distance", "zRate", "zSpeed"):
            bins = []
            for i in range(len(CENTERS)):
                values = [e[metric][i] for e in selected if e[metric][i] is not None]
                bins.append({"n": len(values), "median": float(np.median(values)) if values else None,
                             "q25": float(np.quantile(values, .25)) if values else None,
                             "q75": float(np.quantile(values, .75)) if values else None})
            out["metrics"][metric] = bins
        summary[group] = out
    return summary


def render_chart(summary, output):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib import font_manager

    font_manager.fontManager.addfont("/System/Library/Fonts/Supplemental/Arial Unicode.ttf")
    plt.rcParams.update({"font.family": "Arial Unicode MS", "axes.unicode_minus": False, "font.size": 10})
    speed_values = [b["median"] for r in summary.values() for b in r["metrics"]["speed"] if b["median"] is not None]
    distance_values = [b["median"] for r in summary.values() for b in r["metrics"]["distance"] if b["median"] is not None]
    z_speed_values = [b[key] for r in summary.values() for b in r["metrics"]["zSpeed"]
                      for key in ("median", "q25", "q75") if b[key] is not None]
    speed_max = max(100, math.ceil(max(speed_values) / 100) * 100) if speed_values else 100
    distance_max = max(100, math.ceil(float(np.quantile(distance_values, .98)) / 100) * 100) if distance_values else 100
    z_speed_max = max(1, math.ceil(max(z_speed_values))) if z_speed_values else 1
    fig, axes = plt.subplots(3, 3, figsize=(16, 10.1), sharex=True, constrained_layout=True)
    fig.patch.set_facecolor("#f7fbf9")
    headings = {
        "Touch": ("A1 抽象点击", "0 ms = TOUCH_DOWN；之后可能接触并抬笔"),
        "阅读 Home": ("A5–A7 自然阅读", "0 ms = 进入回顾性 Home 区；没有确认动作"),
        "Intentional Hover": ("主动 Hover · B2 单选 / B3 多选", "0 ms = HOVER_SELECT；B2 结束，B3 转向下一目标"),
    }
    x = CENTERS * 1000
    for col, groups in enumerate(COLUMNS):
        for row, (metric, limit) in enumerate((("distance", distance_max), ("speed", speed_max),
                                                ("zSpeed", z_speed_max))):
            ax = axes[row, col]
            ax.set_facecolor("#fff")
            ax.axvspan(-1000, -500, facecolor="#e6f2ee", alpha=.65)
            ax.axvspan(-500, 0, facecolor="#edf4f0", alpha=.75)
            ax.axvspan(0, 500, facecolor="#f1f7f3", alpha=.75)
            ax.axvspan(500, 1500, facecolor="#f7faf8", alpha=.85)
            for group in groups:
                values = summary[group]["metrics"][metric]
                yy = np.array([v["median"] if v["median"] is not None else np.nan for v in values])
                low = np.array([v["q25"] if v["q25"] is not None else np.nan for v in values])
                high = np.array([v["q75"] if v["q75"] is not None else np.nan for v in values])
                ax.plot(x, yy, color=COLORS[group], linewidth=2.1, marker="o", markersize=2.4,
                        label=group if col == 2 and row == 0 else None)
                ax.fill_between(x, low, high, color=COLORS[group], alpha=.11)
            ax.axvline(0, color="#526a67", linewidth=.9, linestyle="--")
            ax.set_xlim(-1000, 1500)
            ax.set_ylim(0, limit)
            ax.grid(axis="y", color="#dce6e2", linewidth=.55)
            ax.spines[["top", "right"]].set_visible(False)
            if col == 0:
                ax.set_ylabel(("至目标 / Home 中心距离 · pt", "Pencil XY 速度 · pt/s",
                               "Pencil Z 变化速度 · API 原值/s")[row], fontsize=11)
            if row == 2:
                ax.set_xlabel("相对事件时间 · ms")
            if col == 2 and row == 0:
                ax.legend(loc="upper right", frameon=True, facecolor="white", framealpha=.92, fontsize=9)
        heading = "Intentional Hover" if col == 2 else groups[0]
        count = (f"B2 {summary['B2 单选']['events']}次/{summary['B2 单选']['trials']}试次 · "
                 f"B3 {summary['B3 多选']['events']}次/{summary['B3 多选']['trials']}试次") if col == 2 else (
                     f"{summary[groups[0]]['events']}事件/{summary[groups[0]]['trials']}试次")
        axes[0, col].set_title(
            f"{headings[heading][0]} · {count}\n{headings[heading][1]}",
            fontsize=11, color=COLORS[groups[-1]], weight="bold", pad=14)
    fig.suptitle("Touch、阅读 Home、Intentional Hover：接近 → 到达 / 确认 → 后续移动\n每列 0 点定义不同；Z 速度 = |ΔZ|/Δt，单位为 API 原值/s（非毫米速度）",
                 fontsize=17, color="#203d39", weight="bold")
    fig.savefig(output / "sequence-comparison.png", dpi=160, facecolor=fig.get_facecolor())
    plt.close(fig)
    return {"speedAxisPtPerS": speed_max, "distanceAxisPt": distance_max,
            "zSpeedAxisRawPerS": z_speed_max}


def build(output: Path, home_data):
    home_by_id = {(row["day"], row["trialID"]): row for row in home_data["trials"]}
    events = []
    sources = []
    for day, raw, replay in INPUTS:
        data = json.loads(replay.read_text())
        sha = file_hash(raw)
        if data["sha256"] != sha:
            raise ValueError(f"Replay cache does not match raw CSV: {raw}")
        sources.append({"day": day, "sha256": sha, "source": raw.name})
        for trial in data["trials"]:
            for group, anchor, center in anchors(trial, home_by_id.get((day, trial["id"]))):
                curves = bins_for(eligible_segments(trial, include_touch=group == "Touch"), anchor, center)
                if not any(v is not None for v in curves["speed"]):
                    continue
                events.append({"day": day, "trialID": trial["id"], "task": trial["task"],
                               "group": group, "anchorS": anchor, **curves})
    summary = summarize(events)
    axes = render_chart(summary, output)
    payload = {"source": sources, "windowMs": [-1000, 1500], "binMs": 50,
               "anchors": {"Touch": "TOUCH_DOWN", "阅读 Home": "first entry into retrospective Home zone",
                           "B2 单选": "B2 HOVER_SELECT; single target trial ends",
                           "B3 多选": "B3 HOVER_SELECT with later selection in same trial"},
               "axes": axes, "groups": summary,
               "limits": "Single participant; Touch, Home, and Hover use different 0-ms events; B2 and B3 use separate curves with different geometry and selection sequences; Home is retrospective; no gaze was captured in these CSVs."}
    (output / "sequence-comparison.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload
