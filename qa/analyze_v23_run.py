#!/usr/bin/env python3
"""Read-only V2.3 run analysis. Separate planned tasks from recorded attempts."""
import argparse
import bisect
import collections
import csv
import json
import math
import shutil
import sys
from pathlib import Path

import numpy as np

from analyze_behavior_overview import loop_candidate, predict, report_html, task_features
from analyze_home_position import acquisition, learn_model, natural_windows
from analyze_two_runs import dump_csv, med, table
from build_motion_study import signed_motion
from build_v2_replay import decoded, reconstruct
from dwell_threshold_report import build_dataset as build_dwell_dataset, render_section as dwell_section, summarize as dwell_summary
from explore_hover_intent import assess, episodes

RUN_NAMES = {"THUMB": "拇指", "CRADLE_INDEX": "食指"}
SCENES = {"news": "新闻", "notes": "图文", "video": "视频"}
TASKS = ["A1", "A2", "A3", "A4", "A5", "A6", "A7", "B1", "B2", "B3", "B4", "C1", "C2", "C3"]
OLD = Path(__file__).resolve().parents[1] / "analysis/trajectory_2026-09-15/hands_run2"


def inventory(source):
    counts = collections.Counter()
    sources = collections.Counter()
    events = collections.Counter()
    sessions = {}
    malformed = []
    sequence_breaks = collections.Counter()
    last_sequence = {}
    with source.open(newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        fields = reader.fieldnames
        for line, row in enumerate(reader, 2):
            if None in row or any(value is None for value in row.values()):
                malformed.append(line)
                continue
            counts[row["recordType"]] += 1
            sid = row["sessionID"]
            s = sessions.setdefault(sid, dict(first=row["timestamp"], last=row["timestamp"], samples=0, events=0))
            s["last"] = row["timestamp"]
            seq = int(row["sequence"])
            if sid in last_sequence and seq <= last_sequence[sid]:
                sequence_breaks[sid] += 1
            last_sequence[sid] = seq
            if row["recordType"] == "SAMPLE":
                s["samples"] += 1
                sources[(row["sampleSource"], row["inputType"])] += 1
            else:
                s["events"] += 1
                events[row["eventType"]] += 1
                if row["eventType"] == "SESSION_START":
                    meta = decoded(row["metadata"], {})
                    s.update(protocol=meta.get("protocolVersion"), posture=meta.get("posture"),
                             simulation=meta.get("simulation"), planned=len(decoded(meta.get("schedule"), [])),
                             seed=row["randomSeed"])
                elif row["eventType"] == "SESSION_END":
                    s["ended"] = True
    return dict(fields=len(fields), rows=dict(counts), sampleSources=[
        dict(source=k[0], inputType=k[1], count=v) for k, v in sorted(sources.items())],
        eventCounts=dict(events), sessions=sessions, malformedLines=malformed,
        sequenceBreaks=dict(sequence_breaks), bytes=source.stat().st_size)


def prepare(trials):
    for tr in trials:
        start = next(e for e in tr["events"] if e["type"] == "TRIAL_START")
        meta = start["metadata"]
        tr["planKey"] = (tr["session"], int(meta["sessionPlannedIndex"]))
        tr["planNumber"] = int(meta["sessionPlannedIndex"])
        tr["attempt"] = int(meta.get("attempt", 1))
        tr["redoOf"] = meta.get("redoOf", "")
        tr["run"] = RUN_NAMES.get(tr["posture"], tr["posture"])
        tr["rawSuccess"] = tr.get("success", False)
        tr["rawError"] = tr.get("error", "")
        tr["actionSuccess"] = tr["rawSuccess"]
        tr["override"] = ""
        if tr["task"] == "B1" and tr["rawError"] == "WRONG_MENU_ITEM":
            menu_open = False
            for ev in tr["events"]:
                if ev["type"] == "MENU_OPEN":
                    menu_open = True
                if menu_open and ev["type"] == "MENU_SELECT" and ev["metadata"].get("item") == "B":
                    tr["actionSuccess"] = True
                    tr["override"] = "PRIOR_USER_B_ACTION_REVIEW"
        end = next((e["t"] for e in tr["events"] if e["type"] == "TRIAL_END"), tr["duration"])
        clipped = []
        removed = 0
        for segment in tr["segments"]:
            points = [p for p in segment if p["t"] <= end + 1e-9]
            removed += len(segment) - len(points)
            if points:
                clipped.append(points)
        tr["segments"] = clipped
        tr["duration"] = end
        tr["exclusions"]["outsideTrial"] = removed
    trials.sort(key=lambda t: (t["start"], t["planNumber"], t["attempt"]))


def plan_summary(trials):
    plans = collections.defaultdict(list)
    for tr in trials:
        plans[tr["planKey"]].append(tr)
    rows = []
    for key, attempts in plans.items():
        attempts.sort(key=lambda t: t["start"])
        first = attempts[0]
        rows.append(dict(sessionID=key[0], posture=first["run"], task=first["task"],
                         condition=first["condition"], scene=first["scene"], plannedIndex=key[1],
                         attempts=len(attempts), firstRawSuccess=first["rawSuccess"],
                         firstActionSuccess=first["actionSuccess"],
                         eventualRawSuccess=any(t["rawSuccess"] for t in attempts),
                         eventualActionSuccess=any(t["actionSuccess"] for t in attempts),
                         trialIDs=";".join(t["id"] for t in attempts)))
    rows.sort(key=lambda r: (r["sessionID"], r["plannedIndex"]))
    return rows


def summary_by_task(plans, trials):
    keys = sorted({(p["posture"], p["task"], p["condition"]) for p in plans},
                  key=lambda k: (list(RUN_NAMES.values()).index(k[0]), TASKS.index(k[1]), k[2]))
    rows = []
    for posture, task, condition in keys:
        ps = [p for p in plans if (p["posture"], p["task"], p["condition"]) == (posture, task, condition)]
        ts = [t for t in trials if (t["run"], t["task"], t["condition"]) == (posture, task, condition)]
        rows.append(dict(posture=posture, task=task, condition=condition, planned=len(ps),
                         attempts=len(ts), firstRaw=sum(p["firstRawSuccess"] for p in ps),
                         firstAction=sum(p["firstActionSuccess"] for p in ps),
                         eventualRaw=sum(p["eventualRawSuccess"] for p in ps),
                         eventualAction=sum(p["eventualActionSuccess"] for p in ps),
                         attemptRaw=sum(t["rawSuccess"] for t in ts),
                         attemptAction=sum(t["actionSuccess"] for t in ts),
                         overrides=sum(bool(t["override"]) for t in ts),
                         errors=dict(collections.Counter(t["rawError"] for t in ts if not t["rawSuccess"]))))
    return rows


def target_exposure(tr):
    """C3 object exposure from logged, changing selection bounds and continuous Pencil hover."""
    updates = []
    for ev in tr["events"]:
        if ev["type"] not in ("TARGET_PRESENT_REQUEST", "SCENE_STATE"):
            continue
        if "selectionObjects" not in ev["metadata"]:
            continue
        objects = decoded(ev["metadata"]["selectionObjects"], [])
        matching = [o for o in objects if o.get("id") in tr["trial"].get("requested", [])]
        updates.append((ev["t"], matching[0]["bounds"] if matching else None))
    times = [u[0] for u in updates]
    hover_points = inside_points = 0
    hover_seconds = inside_seconds = 0.0
    visits = 0
    for segment in tr["segments"]:
        if not segment or "HOVER" not in segment[0]["source"]:
            continue
        previous = None
        previous_inside = False
        previous_bounds = None
        for p in segment:
            i = bisect.bisect_right(times, p["t"]) - 1
            if i < 0:
                previous = None
                previous_inside = False
                previous_bounds = None
                continue
            b = updates[i][1]
            same_object_position = b == previous_bounds
            inside = bool(b and 60 <= p["y"] <= 800 and
                          b["x"] <= p["x"] <= b["x"] + b["width"] and
                          b["y"] <= p["y"] <= b["y"] + b["height"])
            hover_points += 1
            inside_points += inside
            if inside and (not previous_inside or not same_object_position):
                visits += 1
            if previous is not None:
                dt = p["t"] - previous["t"]
                if dt >= .001:
                    hover_seconds += dt
                    if inside and previous_inside and same_object_position:
                        inside_seconds += dt
            previous = p
            previous_inside = inside
            previous_bounds = b
    dwells = [float(e["metadata"]["durationMs"]) for e in tr["events"]
              if e["type"] == "DWELL_END" and e["metadata"].get("objectID") in tr["trial"].get("requested", [])]
    return dict(trialID=tr["id"], posture=tr["run"], scene=tr["scene"], condition=tr["condition"],
                plannedIndex=tr["planNumber"], rawSuccess=tr["rawSuccess"], attempts=tr["attempt"],
                hoverPoints=hover_points, insidePoints=inside_points,
                hoverObserved_s=hover_seconds, insideObserved_s=inside_seconds, visits=visits,
                dwellEnds=len(dwells), maxDwell_ms=max(dwells, default=0.0),
                candidates=sum(e["type"] == "CANDIDATE" for e in tr["events"]),
                selections=sum(e["type"] == "HOVER_SELECT" for e in tr["events"]),
                touchDowns=sum(e["type"] == "TOUCH_DOWN" for e in tr["events"]))


def approach_features(trials, windows):
    by_id = {t["id"]: t for t in trials}
    rows = []
    for w in windows:
        if w["task"] not in ("B1", "B2", "B3"):
            continue
        tr = by_id[w["trialID"]]
        segment = tr["segments"][w["segment"]]
        before = [p for p in segment if w["window_start"] - .3 <= p["t"] < w["window_start"]]
        if len(before) < 8 or before[-1]["t"] - before[0]["t"] < .2:
            continue
        edges = [e for e in signed_motion(before) if e["dt"] >= .001]
        if not edges:
            continue
        speeds = np.array([e["speed"] for e in edges])
        weights = np.array([e["dt"] for e in edges])
        order = np.argsort(speeds)
        approach = float(speeds[order][np.searchsorted(np.cumsum(weights[order]), weights.sum() / 2)])
        rows.append(dict(trialID=tr["id"], task=tr["task"], posture=tr["run"],
                         scene=tr["scene"], approachSpeed_pt_s=approach,
                         dwellSpeed_pt_s=w["speed_median_pt_s"],
                         slower=w["speed_median_pt_s"] < approach))
    return rows


def home_summary(trials):
    rows = []
    points = []
    for tr in trials:
        if tr["task"] in ("A5", "A6", "A7") and tr["rawSuccess"]:
            windows = natural_windows(tr)
            train = [w for w in windows if w["half"] == "TRAIN"]
            check = [w for w in windows if w["half"] == "CHECK"]
            model = learn_model(train, check)
            acq = acquisition(windows, model)
            rows.append(dict(posture=tr["run"], scene=tr["scene"], windows=len(windows),
                             lowMotionWindows=sum(w["lowMotion"] for w in windows),
                             trainWindows=model["train"]["clusterWindows"] if model["train"] else 0,
                             checkWindows=model["check"]["clusterWindows"] if model["check"] else 0,
                             centerX=model["train"]["cx"] if model["train"] else None,
                             centerY=model["train"]["cy"] if model["train"] else None,
                             centerShift_pt=model["centerShift_pt"],
                             replicated=model["replicated"],
                             firstCandidate_s=acq["firstCandidate_s"],
                             onlineTentative_s=acq["onlineTentative_s"]))
            points.extend(windows)
    return rows, points


def b4_summary(trials):
    rows = []
    for tr in trials:
        if tr["task"] != "B4":
            continue
        closes = [e["metadata"] for e in tr["events"] if e["type"] == "LASSO_CLOSE"]
        rows.append(dict(trialID=tr["id"], posture=tr["run"], plannedIndex=tr["planNumber"],
                         ordinal=tr["trial"]["ordinal"], success=tr["rawSuccess"],
                         error=tr["rawError"], closed=len(closes),
                         interruptions=sum(e["type"] == "LASSO_CANCEL" for e in tr["events"]),
                         area_pt2=float(closes[-1]["area"]) if closes else None,
                         path_pt=float(closes[-1]["pathLength"]) if closes else None,
                         closure_pt=float(closes[-1].get("closureDistance", "nan")) if closes else None))
    return rows


def action_structure(trials):
    menu = []
    selection_gaps = []
    selection_orders = collections.Counter()
    lasso_durations = []
    for tr in trials:
        if tr["task"] == "B1":
            opened = next((e for e in tr["events"] if e["type"] == "MENU_OPEN"), None)
            selected = next((e for e in tr["events"] if e["type"] == "MENU_SELECT"), None)
            if opened and selected:
                menu.append(dict(trialID=tr["id"], posture=tr["run"],
                                 seconds=selected["t"] - opened["t"],
                                 selected=selected["metadata"].get("item")))
        if tr["task"] == "B3" and tr["rawSuccess"]:
            selected = [e for e in tr["events"] if e["type"] == "HOVER_SELECT"]
            selection_orders[tuple(e["metadata"].get("objectID") for e in selected)] += 1
            selection_gaps.extend(b["t"] - a["t"] for a, b in zip(selected, selected[1:]))
        if tr["task"] == "B4":
            started = next((e for e in tr["events"] if e["type"] == "LASSO_START"), None)
            closed = next((e for e in tr["events"] if e["type"] == "LASSO_CLOSE"), None)
            if started and closed:
                lasso_durations.append(closed["t"] - started["t"])
    return dict(menuOpens=sum(t["task"] == "B1" and any(e["type"] == "MENU_OPEN" for e in t["events"]) for t in trials),
                menuSelections=len(menu), menuToSelectionMedian_s=med([r["seconds"] for r in menu]),
                menuItems=dict(collections.Counter(r["selected"] for r in menu)),
                b3SuccessfulOrders={"→".join(k): v for k, v in selection_orders.items()},
                b3InterSelectionMedian_s=med(selection_gaps),
                b4LassoDurationMedian_s=med(lasso_durations))


def loop_shapes(trials, features):
    rows = []
    for tr, f in zip(trials, features):
        if not f["loopCandidate"]:
            continue
        evidence = decoded(f["loopEvidence"], {})
        points = [p for segment in tr["segments"] for p in segment
                  if evidence["seq0"] <= p["sequence"] <= evidence["seq1"]]
        dx = max(p["x"] for p in points) - min(p["x"] for p in points)
        dy = max(p["y"] for p in points) - min(p["y"] for p in points)
        length = evidence["path"] + evidence["distance"]
        rows.append(dict(day="2026-09-16", trialID=tr["id"], task=tr["task"],
                         posture=tr["run"], rawSuccess=tr["rawSuccess"],
                         area_pt2=evidence["area"], path_pt=evidence["path"],
                         closingEdge_pt=evidence["distance"], spanX_pt=dx, spanY_pt=dy,
                         roundness=4 * math.pi * evidence["area"] / length**2,
                         candidateAfterRoundness05=4 * math.pi * evidence["area"] / length**2 >= .5))
    old_rows = []
    for r in csv.DictReader((OLD / "behavior_task_features.csv").open(encoding="utf-8-sig")):
        if r["loopCandidate"] != "True":
            continue
        e = decoded(r["loopEvidence"], {})
        length = e["path"] + e["distance"]
        old_rows.append(dict(day="2026-09-15", trialID=r["trialID"], task=r["task"],
                             posture=r["run"], rawSuccess=r["rawSuccess"],
                             area_pt2=e["area"], path_pt=e["path"],
                             closingEdge_pt=e["distance"], spanX_pt=None, spanY_pt=None,
                             roundness=4 * math.pi * e["area"] / length**2,
                             candidateAfterRoundness05=4 * math.pi * e["area"] / length**2 >= .5))
    return rows, old_rows


def build_replay(data, out):
    """Local-only replay: all measured points, scene preview limited to 20 Hz."""
    keep = []
    omitted_states = 0
    for tr in data["trials"]:
        last_preview = -math.inf
        events = []
        for ev in tr["events"]:
            meta = ev["metadata"]
            is_preview = ev["type"] in ("SCENE_STATE", "SCROLL_STATE") and meta.get(
                "action", "SCROLL") in ("SCROLL", "INERTIA", "VIDEO_PROGRESS")
            if is_preview and ev["t"] - last_preview < .05:
                omitted_states += 1
                continue
            if is_preview:
                last_preview = ev["t"]
            events.append(dict(t=ev["t"], type=ev["type"],
                               metadata={k: v for k, v in meta.items() if k not in (
                                   "protocolVersion", "taskID", "taskGroup", "scene", "posture",
                                   "condition", "contentVersion", "sessionPlannedIndex",
                                   "sampleSequence", "trial", "points")}))
        valid_sequences = {p["sequence"] for s in tr["segments"] for p in s}
        keep.append({k: tr[k] for k in ("id", "task", "group", "scene", "posture", "condition",
                                       "instruction", "index", "total", "session", "repeat",
                                       "trial", "start", "duration", "segments", "pollution",
                                       "exclusions", "coverage", "metrics", "success", "error")} |
                    dict(events=events, motion=[m for m in tr["motion"] if
                                                 m["seq0"] in valid_sequences and
                                                 m["seq1"] in valid_sequences and
                                                 m["t"] <= tr["duration"]]))
    payload = dict(source=data["source"], sha256=data["sha256"], legacyRows=0, trials=keep)
    (out / "replay-data.json").write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
                                          encoding="utf-8")
    root = Path(__file__).resolve().parents[1]
    bootstrap = json.dumps(dict(source=data["source"], trials=[], dataURL="./replay-data.json"),
                           ensure_ascii=False)
    html = (root / "qa/v2_replay.html").read_text(encoding="utf-8").replace("__DATA__", bootstrap)
    html = html.replace('<a href="./replay.html">旧协议回放</a>', "")
    html = html.replace("<div id=\"message\"></div>",
                        '<p>2026-09-16 V2.3 两轮正式采集。<a href="./report.html">查看分析报告</a>。'
                        '轨迹为手机内连续 Pencil 实测点；场景状态预览最高20Hz，原始事件保留在CSV。</p>'
                        '<div id="message">正在加载本地轨迹…</div>')
    (out / "replay-v2.html").write_text(html, encoding="utf-8")
    js = (root / "qa/v2_replay.js").read_text(encoding="utf-8")
    js = js.replace("refresh();requestAnimationFrame(animate);",
                    "if(data.dataURL){fetch(data.dataURL).then(r=>{if(!r.ok)throw Error(r.status);"
                    "return r.json()}).then(d=>{data=d;refresh()}).catch(e=>{"
                    "$('message').textContent='加载失败：'+e.message+'。请通过本地服务器打开本页。'})}"
                    "else refresh();requestAnimationFrame(animate);")
    (out / "v2_replay.js").write_text(js, encoding="utf-8")
    shutil.copytree(root / "src/App/StudyMedia", out / "Resources", dirs_exist_ok=True)
    shutil.copytree(root / "qa/vendor", out / "vendor", dirs_exist_ok=True)
    return dict(trials=len(keep), retainedPoints=sum(sum(map(len, t["segments"])) for t in keep),
                omittedPreviewStates=omitted_states, dataBytes=(out / "replay-data.json").stat().st_size)


def charts(out, trials, task_rows, exposure, home_rows, home_points, approach, features, loops, old_loops):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Circle
    from matplotlib import font_manager
    font_manager.fontManager.addfont("/System/Library/Fonts/Supplemental/Arial Unicode.ttf")
    plt.rcParams.update({"font.family": "Arial Unicode MS", "axes.unicode_minus": False, "font.size": 10})

    old = list(csv.DictReader((OLD / "task_summary.csv").open(encoding="utf-8-sig")))
    old_map = {(r["run"], r["task"], r["condition"]): r for r in old}
    keys = [("B4", "HOVER"), ("C1", "HOVER"), ("C2", "HOVER"), ("C2", "SCROLL"), ("C3", "HOVER")]
    fig, ax = plt.subplots(figsize=(11, 5))
    labels = []
    for i, (task, condition) in enumerate(keys):
        for j, posture in enumerate(("拇指", "食指")):
            n = next(r for r in task_rows if (r["posture"], r["task"], r["condition"]) == (posture, task, condition))
            o = old_map[(posture, task, condition)]
            x = i * 2.6 + j
            ax.bar(x - .2, int(o["rawSuccess"]) / int(o["attempts"]) * 100, .38, color="#9ca9b4")
            ax.bar(x + .2, n["firstRaw"] / n["planned"] * 100, .38, color="#386eac")
            labels.append((x, f"{task} {condition}\n{posture}"))
    ax.set(xticks=[x for x, _ in labels], xticklabels=[s for _, s in labels], ylim=(0, 108),
           ylabel="首次尝试成功率 (%)", title="跨日描述对比：旧 V2.1 与新 V2.3（同一人；任务几何/练习不同）")
    ax.tick_params(axis="x", labelsize=8)
    ax.grid(axis="y", alpha=.17)
    fig.text(.12, .03, "灰：9/15 原始判定；蓝：9/16 每题首次尝试。A/C 最终补做成功不计入首次成功。", fontsize=9)
    fig.tight_layout(rect=(0, .05, 1, 1))
    fig.savefig(out / "first_attempt_comparison.png", dpi=170)
    plt.close(fig)

    fig, axes = plt.subplots(1, 3, figsize=(12, 4.6), sharey=True)
    for ax, scene in zip(axes, SCENES):
        for x, condition, color in [(0, "NATURAL", "#78a1a4"), (1, "HOVER", "#715fba")]:
            rs = [r for r in exposure if r["scene"] == scene and r["condition"] == condition]
            ax.scatter([x + (j - (len(rs) - 1) / 2) * .035 for j in range(len(rs))],
                       [r["maxDwell_ms"] for r in rs], alpha=.75, s=25, color=color)
        ax.axhline(500, ls="--", lw=1, color="#ae5b51")
        ax.set(xticks=[0, 1], xticklabels=["自然", "主动"], xlim=(-.4, 1.4),
               title=SCENES[scene] + " · 蝴蝶 48×48 pt")
        ax.grid(axis="y", alpha=.15)
    axes[0].set_ylabel("每次对该对象最长实测悬停 (ms)")
    fig.suptitle("C3 同一内容对象：自然停留与主动 500 ms 确认；0 表示未进入目标")
    fig.tight_layout()
    fig.savefig(out / "c3_object_dwell.png", dpi=170)
    plt.close(fig)

    fig, axes = plt.subplots(2, 3, figsize=(11, 9))
    for row, posture in enumerate(("拇指", "食指")):
        for col, scene in enumerate(SCENES):
            ax = axes[row, col]
            w = [v for v in home_points if v["run"] == posture and v["scene"] == scene and v["lowMotion"]]
            for half, color in (("TRAIN", "#3a8faf"), ("CHECK", "#d79452")):
                rs = [v for v in w if v["half"] == half]
                ax.scatter([v["cx"] for v in rs], [v["cy"] for v in rs], s=14, alpha=.55, color=color)
            h = next(r for r in home_rows if r["posture"] == posture and r["scene"] == scene)
            if h["centerX"] is not None:
                ax.add_patch(Circle((h["centerX"], h["centerY"]), 50, fill=False, color="#27668d"))
            ax.set(xlim=(0, 390), ylim=(830, 0), aspect="equal",
                   title=f"{posture} · {SCENES[scene]} · {'复现' if h['replicated'] else '未复现'}")
            ax.grid(alpha=.12)
    fig.suptitle("A5–A7 自然阅读低运动热点：蓝前60秒、橙后60秒；圆是统计位置，不是轨迹")
    fig.tight_layout()
    fig.savefig(out / "home_hotspots.png", dpi=170)
    plt.close(fig)

    fig, axes = plt.subplots(1, 4, figsize=(14, 5))
    choices = []
    for posture in ("拇指", "食指"):
        ts = [t for t in trials if t["task"] == "B4" and t["run"] == posture and t["rawSuccess"]]
        choices.append(min(ts, key=lambda t: abs(t["duration"] - np.median([a["duration"] for a in ts]))))
    failures = [t for t in trials if t["task"] == "B4" and not t["rawSuccess"]]
    choices += failures[:2]
    for ax, tr in zip(axes, choices):
        for obj in tr["trial"]["objects"]:
            b = obj["bounds"]
            ax.add_patch(Circle((b["x"] + b["width"] / 2, b["y"] + b["height"] / 2),
                                b["width"] / 2, fill=False,
                                ec="#3b9b67" if obj["id"] in tr["trial"]["requested"] else "#adb6bd"))
        for seg in tr["segments"]:
            if seg and "HOVER" in seg[0]["source"] and len(seg) > 1:
                ax.plot([p["x"] for p in seg], [p["y"] for p in seg], lw=.65, alpha=.7, color="#326d9e")
        ax.set(xlim=(0, 390), ylim=(830, 0), aspect="equal",
               title=f"{tr['run']} · {'成功' if tr['rawSuccess'] else tr['rawError']}")
        ax.grid(alpha=.12)
    fig.suptitle("B4 实测悬停路径（绿圈为指定目标；缺口断线；未画算法闭合边）")
    fig.tight_layout()
    fig.savefig(out / "b4_paths.png", dpi=170)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(6.5, 5.7))
    for task, color in (("B1", "#8359ad"), ("B2", "#3586ae"), ("B3", "#d08346")):
        rs = [r for r in approach if r["task"] == task]
        ax.scatter([r["approachSpeed_pt_s"] for r in rs], [r["dwellSpeed_pt_s"] for r in rs],
                   s=35, alpha=.72, color=color, label=f"{task}（{len(rs)}窗）")
    ax.plot([1, 1800], [1, 1800], ls="--", color="#687781", lw=1)
    ax.set(xscale="log", yscale="log", xlim=(2, 1800), ylim=(2, 1800),
           xlabel="进入驻留前300ms的XY速度中位（pt/s）",
           ylabel="随后500ms驻留速度中位（pt/s）",
           title="同一连续悬停段：接近→驻留（虚线为等速）")
    ax.grid(alpha=.15)
    ax.legend()
    fig.tight_layout()
    fig.savefig(out / "approach_deceleration.png", dpi=170)
    plt.close(fig)

    false = [(tr, f) for tr, f in zip(trials, features) if tr["task"] == "A3" and f["loopCandidate"]]
    true = [(tr, f) for tr, f in zip(trials, features) if tr["task"] == "B4" and f["loopCandidate"] and tr["rawSuccess"]]
    fig, axes = plt.subplots(1, 4, figsize=(13, 5))
    for ax, (tr, f) in zip(axes, false[:2] + true[:2]):
        evidence = decoded(f["loopEvidence"], {})
        for seg in tr["segments"]:
            if not seg or "HOVER" not in seg[0]["source"] or len(seg) < 2:
                continue
            ax.plot([p["x"] for p in seg], [p["y"] for p in seg], color="#a8b8c6", lw=.65)
            selected = [p for p in seg if evidence["seq0"] <= p["sequence"] <= evidence["seq1"]]
            if len(selected) > 1:
                ax.plot([p["x"] for p in selected], [p["y"] for p in selected],
                        color="#d0604b" if tr["task"] == "A3" else "#5664af", lw=1.15)
        ax.set(xlim=(0, 390), ylim=(830, 0), aspect="equal",
               title=f"{tr['task']} {tr['run']} · 面积{evidence['area']:.0f}pt²")
        ax.grid(alpha=.12)
    fig.suptitle("独立闭合轮廓扫描：红色A3基线误报，紫色B4；仅实测悬停段")
    fig.tight_layout()
    fig.savefig(out / "loop_diagnostics.png", dpi=170)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(8.5, 4.8))
    for day, marker in (("2026-09-15", "o"), ("2026-09-16", "^")):
        for group, x, color in (("B4", 1, "#5664af"), ("non-B4", 0, "#d0604b")):
            rows = [r for r in old_loops + loops if r["day"] == day and
                    ("B4" if r["task"] == "B4" else "non-B4") == group]
            ax.scatter([x + (i - (len(rows)-1)/2) * .028 for i in range(len(rows))],
                       [r["roundness"] for r in rows], color=color, marker=marker, s=44, alpha=.8,
                       label=f"{day} {group}" if rows else None)
    ax.axhline(.5, color="#667789", ls="--", lw=1)
    ax.set(xticks=[0, 1], xticklabels=["其他任务的闭合候选", "B4闭合候选"],
           ylim=(0, 1.03), ylabel="圆整度 4π×面积／(路径＋闭合边)²",
           title="闭合后再看轮廓形状：0.5阈值为事后探索")
    ax.grid(axis="y", alpha=.15)
    ax.legend(fontsize=8, ncol=2)
    fig.tight_layout()
    fig.savefig(out / "loop_roundness.png", dpi=170)
    plt.close(fig)


def make_report(out, source, data, quality, plans, task_rows, exposure, windows, exclusions,
                frozen, approach, home_rows, b4_rows, features, structure, loops, old_loops,
                dwell_data):
    by = {(r["posture"], r["task"], r["condition"]): r for r in task_rows}
    old = {(r["run"], r["task"], r["condition"]): r
           for r in csv.DictReader((OLD / "task_summary.csv").open(encoding="utf-8-sig"))}
    e_scene = []
    for scene in SCENES:
        natural = [r for r in exposure if r["scene"] == scene and r["condition"] == "NATURAL"]
        active = [r for r in exposure if r["scene"] == scene and r["condition"] == "HOVER"]
        e_scene.append([SCENES[scene], str(len(natural)), str(sum(r["candidates"] for r in natural)),
                        str(sum(r["visits"] for r in natural)),
                        f"{sum(r['insideObserved_s'] for r in natural):.2f}",
                        f"{sum(r['hoverObserved_s'] for r in natural):.1f}",
                        f"{max(r['maxDwell_ms'] for r in natural):.0f}",
                        f"{sum(r['rawSuccess'] for r in active)}/{len(active)}"])
    compares = []
    for task, condition in (("B4", "HOVER"), ("C1", "HOVER"), ("C2", "HOVER"), ("C2", "SCROLL"), ("C3", "HOVER")):
        prior = sum(int(old[(p, task, condition)]["rawSuccess"]) for p in RUN_NAMES.values())
        prior_total = sum(int(old[(p, task, condition)]["attempts"]) for p in RUN_NAMES.values())
        new = sum(by[(p, task, condition)]["firstRaw"] for p in RUN_NAMES.values())
        new_total = sum(by[(p, task, condition)]["planned"] for p in RUN_NAMES.values())
        compares.append([task + " / " + condition, f"{prior}/{prior_total}", f"{new}/{new_total}",
                         f"{sum(by[(p, task, condition)]['eventualRaw'] for p in RUN_NAMES.values())}/{new_total}"])
    key_rates = []
    for task in TASKS:
        for condition in sorted({r["condition"] for r in task_rows if r["task"] == task}):
            rs = [r for r in task_rows if r["task"] == task and r["condition"] == condition]
            key_rates.append([task + " / " + condition, str(sum(r["planned"] for r in rs)),
                              str(sum(r["attempts"] for r in rs)),
                              str(sum(r["firstRaw"] for r in rs)),
                              str(sum(r["eventualRaw"] for r in rs)),
                              str(sum(r["attemptRaw"] for r in rs))])
    b4_stat = []
    for posture in ("拇指", "食指"):
        rs = [r for r in b4_rows if r["posture"] == posture]
        good = [r for r in rs if r["success"] and r["closed"]]
        b4_stat.append([posture, f"{sum(r['success'] for r in rs)}/{len(rs)}",
                        str(sum(r["closed"] > 0 for r in rs)),
                        str(sum(r["interruptions"] for r in rs)),
                        f"{med([r['path_pt'] for r in good]):.0f}" if good else "—",
                        f"{med([r['area_pt2'] for r in good]):.0f}" if good else "—"])
    approach_stat = []
    for task in ("B1", "B2", "B3"):
        rs = [r for r in approach if r["task"] == task]
        approach_stat.append([task, str(len(rs)), str(sum(r["slower"] for r in rs)),
                              f"{med([r['approachSpeed_pt_s'] for r in rs]):.1f}" if rs else "—",
                              f"{med([r['dwellSpeed_pt_s'] for r in rs]):.1f}" if rs else "—"])
    home_stat = []
    for r in home_rows:
        home_stat.append([r["posture"] + " / " + SCENES[r["scene"]],
                          f"{r['trainWindows']} / {r['checkWindows']}",
                          f"{r['centerShift_pt']:.1f}" if r["centerShift_pt"] is not None else "—",
                          "是" if r["replicated"] else "否",
                          str(r["firstCandidate_s"]) if r["firstCandidate_s"] else "—"])
    source_quality = collections.Counter()
    for t in data["trials"]:
        source_quality.update(t["exclusions"])
    c3_natural = [r for r in exposure if r["condition"] == "NATURAL"]
    c3_active = [r for r in exposure if r["condition"] == "HOVER"]
    c3_active_planned = sum(r["planned"] for r in task_rows if r["task"] == "C3" and r["condition"] == "HOVER")
    c3_active_final = sum(r["eventualRaw"] for r in task_rows if r["task"] == "C3" and r["condition"] == "HOVER")
    natural_inside = sum(r["insideObserved_s"] for r in c3_natural)
    natural_hover = sum(r["hoverObserved_s"] for r in c3_natural)
    loop_counts = {task: sum(f["loopCandidate"] for tr, f in zip(data["trials"], features) if tr["task"] == task)
                   for task in TASKS}
    loop_trials = {task: sum(tr["task"] == task for tr in data["trials"]) for task in TASKS}
    old_c3 = json.loads((OLD / "behavior-overview.json").read_text())["c3"]
    lines = [
        "# Hover Intent Study：2026-09-16 新数据复测",
        "",
        "**今天更清楚的是任务可完成性与动作结构：C1/C2 有完整的纯悬停和滚动正例，B4 圈线在两姿势下更常闭合。C3 的小蝴蝶目标在自然短段中没有产生一次 500 ms 候选，但自然笔尖很少在该对象内停留，不能据此宣布已解决误触。**",
        "",
        f"两轮分别记录为拇指和托握＋食指，都是 V2.3 真机 Pencil 采集；日志不含左右手字段。共 {len(plans)} 道计划题、{len(data['trials'])} 次实际尝试。9月15日的分析对象是 V2.1，同一参与者但目标与推进规则已变化；跨日数字只作描述。",
        "",
        "## 1. 质量与计数口径",
        "",
        table(["采集轮次", "时间", "计划题", "实际尝试", "样本", "完整结束"],
              [[RUN_NAMES.get(s["posture"], s["posture"]), s["first"][11:19] + "–" + s["last"][11:19],
                s["planned"], sum(t["session"] == sid for t in data["trials"]), s["samples"],
                "是" if s.get("ended") else "否"] for sid, s in quality["sessions"].items()]),
        "",
        f"原文件 {quality['bytes']:,} 字节、{quality['rows']['SAMPLE']:,} 条 SAMPLE、{quality['rows']['EVENT']:,} 条 EVENT，56列；文件哈希 SHA-256 `{data['sha256']}`。CSV 残缺行 {len(quality['malformedLines'])}，会话内序号倒退/重复 {sum(quality['sequenceBreaks'].values())}。输入包括 Pencil {sum(x['count'] for x in quality['sampleSources'] if x['inputType']=='PENCIL'):,} 点、手指 {sum(x['count'] for x in quality['sampleSources'] if x['inputType']=='FINGER')} 点；重建时排除手机外 {source_quality['outside']} 点、手指 {source_quality['finger']} 点、试次结束后 {source_quality['outsideTrial']} 点。不跨来源或 >100ms 缺口连接。",
        "",
        "A/C 失败后会自动重试同一道计划题，因此“最终完成”不能替代首次成功率。B 按预设尝试数推进。B1 原始成功与用户此前“选 B 算动作完成”的覆核分开记录；仅 MENU_OPEN 后点 B 且原错误是 WRONG_MENU_ITEM 时覆核，不改 CSV。",
        "",
        f"B1 原始成功 {sum(r['attemptRaw'] for r in task_rows if r['task']=='B1')}/24；符合上述用户说明的覆核 {sum(r['overrides'] for r in task_rows if r['task']=='B1')} 次，动作完成 {sum(r['attemptAction'] for r in task_rows if r['task']=='B1')}/24。其余错误仍判失败。",
        "",
        table(["任务 / 条件", "计划题", "实际尝试", "首次原始成功", "最终原始完成", "全部原始成功尝试"], key_rates),
        "",
        "## 2. 与上一轮相比，哪些正例真的补齐",
        "",
        table(["任务 / 条件", "9/15 V2.1 原始成功", "9/16 V2.3 首次成功", "9/16 补做后最终成功"], compares),
        "",
        "![首次成功率对比](first_attempt_comparison.png)",
        "",
        "C1/C2 现在能提供此前缺失的成功 Hover/Scroll 轨迹，可用于检查动作阶段。C1 目标直径、C2 标记与起点、C3 内容目标以及重试逻辑都改了；这些成功率变化包含任务设计和练习效应，不能当作算法识别率提升。B4 从旧轮 7/12 到今天 19/24 原始成功，有更多圈线样本；仍是同一人先后练习。",
        "",
        "## 3. C3 小内容对象：误触机会与实际覆盖",
        "",
        table(["场景", "自然短段", "500ms候选", "进入目标次数", "目标内实测秒", "全部有效悬停秒", "自然最长驻留ms", "主动成功/尝试"], e_scene),
        "",
        "![C3 对象停留](c3_object_dwell.png)",
        "",
        f"自然条件 {sum(r['candidates'] for r in c3_natural)}/{len(c3_natural)} 段触发候选；主动条件 {sum(r['rawSuccess'] for r in c3_active)}/{len(c3_active)} 次尝试成功，补做后 {c3_active_final}/{c3_active_planned} 道计划题完成。自然笔尖在目标内仅有 {natural_inside:.2f}/{natural_hover:.1f} 秒实测悬停（{natural_inside/natural_hover*100:.1f}%）；缺少足够的目标暴露，是0候选的重要解释。C3 目标是同一授权配图中的蝴蝶，48×48 pt，视频播放继续。目标边界随日志 SCENE_STATE 更新；统计只用手机内连续 Pencil hover，接触/手指不计入。0候选描述这位参与者此轮操作，并非真实误触率或未来参与者保证。",
        "",
        f"上一轮 C3 自然条件有 {old_c3['natural']} 个达标窗口，但当时是更大或不同的内容/控件对象；新对象更小，且阅读时进入目标机会有限，因此两轮候选数不能当作同几何 A/B 实验。真正的误触验证还需要让人自然浏览到该对象附近，同时不要求其主动选择。",
        "",
        "### 100–1000 ms 停留阈值回看",
        "",
        "[在 HTML 报告中拖动停留阈值滑杆](report.html#dwell-filter)，并按场景和姿势筛选。这里仅回算自然阅读中同对象连续停留形成的规则候选；每个停留段最多计一次。500 ms 与采集日志的 CANDIDATE 逐试次核对。候选/记录分钟和达标段比例均不是真实误触率；主动试次在 500 ms 自动结束，无法推断更长阈值的主动识别率。",
        "",
        table(["阈值", "A5–A7 自然阅读候选", "C3 蝴蝶目标候选"], [
            [f"{threshold} ms", dwell_summary(dwell_data, threshold, "A")["candidates"],
             dwell_summary(dwell_data, threshold, "C3")["candidates"]]
            for threshold in (100, 250, 500, 750, 1000)]),
        "",
        "## 4. 轨迹规律：接近、驻留、多对象、圈选",
        "",
        table(["B任务", "同段有效接近+500ms窗", "停留速度低于接近", "接近速度中位 pt/s", "停留速度中位 pt/s"], approach_stat),
        "",
        "只用有效悬停达标前 300 ms 的同一连续段（至少200ms覆盖），与其后的 500 ms 窗比较；缺口不补齐。减速可辅助描述“接近→驻留”，但 A1 点击也会减速，因此不是独立意图判据。B1 的菜单出现后点击、B3 的三次离散选择是明确的**完成动作结构**；菜单出现或选中后的信息不能用于预测其出现前的意图。",
        "",
        "![接近与驻留速度](approach_deceleration.png)",
        "",
        table(["姿势", "B4成功", "有闭合提交", "圈线中断", "成功圈线路径中位pt", "成功圈线面积中位pt²"], b4_stat),
        "",
        "![B4 空中圈选实测路径](b4_paths.png)",
        "",
        f"B1 有 {structure['menuOpens']} 次菜单出现、{structure['menuSelections']} 次菜单项点击，菜单出现到点击中位 {structure['menuToSelectionMedian_s']:.2f}秒。B3 的22次成功均按 t0→t1→t2 选中，选择间隔中位 {structure['b3InterSelectionMedian_s']:.2f}秒；该顺序受目标布局/任务引导，不能当作自发偏好。B4 有闭合的尝试从圈线开始到闭合中位 {structure['b4LassoDurationMedian_s']:.2f}秒。",
        "",
        f"B4 主要特征是无触屏、连续移动并形成较大面积闭合轮廓；圈选成功还要求选中集合正确。独立扫描在 B4 找到 {loop_counts['B4']}/{loop_trials['B4']} 个闭合候选，也在 A3 垂直滚动的前期悬停中找到 {loop_counts['A3']}/{loop_trials['A3']} 个；A1–A7 合计 2/109 次尝试。独立扫描采用0.5–3秒、≥12点、离起点≥40pt、路径≥120pt、面积≥2000pt²、闭合误差≤20pt的固定阈值，不读任务标签作为特征，但扫描面积按有向多边形近似，不能代替App奇偶填充的选中判定。图只连接连续实测点，不把算法闭合边伪装成采样。圈形本身不等于心理意图。",
        "",
        "![闭合轮廓的A3假阳性与B4](loop_diagnostics.png)",
        "",
        "### 一个更有希望的圈选形状特征",
        "",
        f"计算闭合候选的**圆整度** `4π×围合面积／(实测路径＋算法闭合边)²`。今天 {len([r for r in loops if r['task']=='B4'])} 个 B4 候选范围 {min(r['roundness'] for r in loops if r['task']=='B4'):.2f}–{max(r['roundness'] for r in loops if r['task']=='B4'):.2f}；两条 A3 细长折返只有 {min(r['roundness'] for r in loops if r['task']!='B4'):.2f}–{max(r['roundness'] for r in loops if r['task']!='B4'):.2f}。从今天数据事后选0.5门槛后，回看9/15的 {len([r for r in old_loops if r['task']=='B4'])} 个 B4 候选都在 {min(r['roundness'] for r in old_loops if r['task']=='B4'):.2f}–{max(r['roundness'] for r in old_loops if r['task']=='B4'):.2f}，另2个非B4候选仅 {min(r['roundness'] for r in old_loops if r['task']!='B4'):.2f}–{max(r['roundness'] for r in old_loops if r['task']!='B4'):.2f}。合计保留27/27个B4闭合候选，排除4/4个其他闭合候选；但原扫描本身只找到27/36次B4尝试，且仍缺同布局自然负例。这是动作轮廓探索，不是经独立验证的意图分类器。",
        "",
        "![两天闭合候选的圆整度](loop_roundness.png)",
        "",
        "## 5. 冻结旧特征在新数据上的检查",
        "",
        table(["旧速度+RMS模型应用到新数据", "主动识别", "自然候选误报", "适用限制"],
              [["A5–A7候选 vs B1–B3主动", f"{frozen['ab']['true_active']}/{frozen['ab']['active']}",
                f"{frozen['ab']['natural_called_active']}/{frozen['ab']['natural']}",
                "任务族跨日；内容和练习改变"],
               ["C3蝴蝶主动", f"{frozen['c3']['true_active']}/{frozen['c3']['active']}",
                "无法估计（C3自然达标窗为0）", "只能测主动召回，不能算特异度/AUC"]]),
        "",
        "模型系数、标准化与0.5阈值全部沿用9/15 A/B拟合结果，没有用今天的 C3 调参。这里的自然/主动仍由任务指令代理，不是每段真实心理意图。**C3没有自然达标窗口，不能声称分类器已经能区分 C3 两类。**",
        "",
        f"同一冻结模型在 C3 三场景主动窗分别识别 新闻 {sum(r['frozenPositive'] for r in windows if r['task']=='C3' and r['scene']=='news')}/12、图文 {sum(r['frozenPositive'] for r in windows if r['task']=='C3' and r['scene']=='notes')}/12、视频 {sum(r['frozenPositive'] for r in windows if r['task']=='C3' and r['scene']=='video')}/12；旧轮C3主动为23/27。新目标更小且视觉内容变了，55.6%的召回下降提示旧静态阈值不稳定，不能把新轮作为同条件独立复现。",
        "",
        "## 6. Home position 是否更稳定",
        "",
        table(["姿势 / 场景", "前/后60秒主簇窗", "中心差pt", "复现热点", "首次候选秒"], home_stat),
        "",
        "![自然阅读位置热点](home_hotspots.png)",
        "",
        f"今天 {sum(r['replicated'] for r in home_rows)}/{len(home_rows)} 个姿势×场景在固定50pt圆内复现；上一轮为 3/6。两分钟内热点复现只说明笔尖常出现于某个屏幕位置，不能确认那是心理意义上的休息位。C3 自然没有达标候选，因此今天无法用它验证 home 过滤是否降低误报；不要启用硬过滤。",
        "",
        "## 7. 下一步最有信息量的验证",
        "",
        "在同一新闻/图文/视频页面让参与者自然经过蝴蝶附近，记录目标实际可见时的 hover 进入次数与完整500ms机会；随后随机穿插主动选择。B3 加相同六目标布局的自然经过/B4 加不闭合空中划动，冻结特征后交给新的参与者。这样能检验路径结构的误报，而不只重复当前任务要求。",
        "",
        "[3D 手机轨迹回放](replay-v2.html) · [逐试次原始与覆核](trial_metrics.csv) · [计划题进度](planned_tasks.csv) · [任务汇总](task_summary.csv) · [C3对象覆盖](c3_target_exposure.csv) · [闭合形状](loop_candidates.csv) · [500ms窗口](intent_windows.csv) · [质量与模型参数](report.json)",
        "",
        f"数据来源：`{source.name}`；SHA-256 `{data['sha256']}`。旧对照：`HoverIntent_2026-09-15 2.csv`；SHA-256 `{json.loads((OLD/'quality.json').read_text())['sha256'] if 'sha256' in json.loads((OLD/'quality.json').read_text()) else '见旧报告'}`。无右/左手日志，不把姿势当作左右手。单参与者、单日各一轮，不报告统计显著性或独立泛化。",
    ]
    (out / "report.md").write_text("\n".join(lines), encoding="utf-8")
    report_html(lines, out / "report.html", '<nav><a href="#dwell-filter">100–1000 ms 停留分析</a> · <a href="report.md">Markdown</a> · <a href="report.json">指标 JSON</a></nav>')
    html_path = out / "report.html"
    html = html_path.read_text(encoding="utf-8").replace(
        "<title>A/B 行为特征与 C 验证</title>", "<title>2026-09-16 V2.3 行为轨迹复测</title>")
    heading = "<h3>100–1000 ms 停留阈值回看</h3>"
    marker = "<h2>4. 轨迹规律：接近、驻留、多对象、圈选</h2>"
    assert html.count(heading) == 1 and html.count(marker) == 1
    html = html[:html.index(heading)] + dwell_section(dwell_data) + html[html.index(marker):]
    html_path.write_text(html, encoding="utf-8")
    return e_scene, compares


def build(source, out):
    out.mkdir(parents=True, exist_ok=True)
    quality = inventory(source)
    data = reconstruct(source)
    prepare(data["trials"])
    plans = plan_summary(data["trials"])
    assert all(s["protocol"] == "HOVER_INTENT_V2_3" and s["simulation"] == "false"
               for s in quality["sessions"].values())
    assert len(plans) == sum(s["planned"] for s in quality["sessions"].values())
    task_rows = summary_by_task(plans, data["trials"])
    exposure = [target_exposure(t) for t in data["trials"] if t["task"] == "C3"]
    dwell_data = build_dwell_dataset(data["trials"], exposure)
    dwell_data.update(source=data["source"], sha256=data["sha256"])
    (out / "dwell_threshold_data.json").write_text(json.dumps(dwell_data, ensure_ascii=False, indent=2), encoding="utf-8")
    shutil.copyfile(Path(__file__).resolve().parent / "dwell_threshold.js", out / "dwell_threshold.js")
    features = [task_features(t) for t in data["trials"]]
    windows, excluded = episodes(data["trials"])
    for row in windows:
        row["hand"] = "UNRECORDED"
    model = json.loads((OLD / "behavior-overview.json").read_text())["model"]
    ab = [r for r in windows if r["task"] in ("A5", "A6", "A7", "B1", "B2", "B3")]
    c3 = [r for r in windows if r["task"] == "C3"]
    frozen = dict(model=model, ab=assess(ab, predict(model, ab)),
                  c3=assess(c3, predict(model, c3)), excluded=excluded)
    for row, score in zip(windows, predict(model, windows)):
        row["frozenScore"] = float(score)
        row["frozenPositive"] = bool(score >= .5)
    approach = approach_features(data["trials"], windows)
    home_rows, home_points = home_summary(data["trials"])
    b4_rows = b4_summary(data["trials"])
    structure = action_structure(data["trials"])
    loops, old_loops = loop_shapes(data["trials"], features)
    metrics = []
    for tr, feat in zip(data["trials"], features):
        metrics.append(dict(trialID=tr["id"], sessionID=tr["session"], posture=tr["run"],
                            task=tr["task"], condition=tr["condition"], scene=tr["scene"],
                            plannedIndex=tr["planNumber"], taskOrdinal=tr["trial"]["ordinal"],
                            attempt=tr["attempt"], redoOf=tr["redoOf"], rawSuccess=tr["rawSuccess"],
                            rawError=tr["rawError"], actionSuccess=tr["actionSuccess"],
                            override=tr["override"], duration_s=tr["duration"],
                            retainedPoints=sum(map(len, tr["segments"])), exclusions=json.dumps(tr["exclusions"]),
                            targetHover_ms=feat.get("preTargetHover_ms"), loopCandidate=feat["loopCandidate"],
                            loopEvidence=feat["loopEvidence"],
                            hoverObserved_s=feat["hover_observed"], hoverSpeed_pt_s=feat["hover_speed"],
                            touchObserved_s=feat["touch_observed"], touchSpeed_pt_s=feat["touch_speed"]))
    dump_csv(out / "trial_metrics.csv", metrics)
    dump_csv(out / "planned_tasks.csv", plans)
    dump_csv(out / "task_summary.csv", task_rows)
    dump_csv(out / "c3_target_exposure.csv", exposure)
    dump_csv(out / "intent_windows.csv", windows)
    dump_csv(out / "approach_speed.csv", approach)
    dump_csv(out / "home_positions.csv", home_rows)
    dump_csv(out / "b4_metrics.csv", b4_rows)
    dump_csv(out / "loop_candidates.csv", old_loops + loops)
    quality.update(source=source.name, sha256=data["sha256"], retainedPoints=sum(m["retainedPoints"] for m in metrics),
                   excluded=dict(sum((collections.Counter(t["exclusions"]) for t in data["trials"]), collections.Counter())))
    quality["replay"] = build_replay(data, out)
    (out / "quality.json").write_text(json.dumps(quality, ensure_ascii=False, indent=2), encoding="utf-8")
    charts(out, data["trials"], task_rows, exposure, home_rows, home_points, approach, features, loops, old_loops)
    e_scene, compares = make_report(out, source, data, quality, plans, task_rows, exposure,
                                     windows, excluded, frozen, approach, home_rows, b4_rows, features,
                                     structure, loops, old_loops, dwell_data)
    result = dict(source=source.name, sha256=data["sha256"], protocol="HOVER_INTENT_V2_3",
                  planned=len(plans), attempts=len(data["trials"]), sessions=quality["sessions"],
                  c3Scenes=e_scene, comparisons=compares, frozenModel=frozen,
                  dwellThresholds=dict(file="dwell_threshold_data.json", defaultMs=500,
                                       A=dwell_summary(dwell_data, 500, "A"),
                                       C3=dwell_summary(dwell_data, 500, "C3")),
                  b4=b4_rows, actionStructure=structure, loopShapes=dict(current=loops, old=old_loops),
                  home=home_rows, quality=quality)
    (out / "report.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(dict(planned=len(plans), attempts=len(data["trials"]),
                          c3NaturalCandidates=sum(r["candidates"] for r in exposure if r["condition"] == "NATURAL"),
                          frozenC3=frozen["c3"], output=str(out / "report.html")), ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    build(args.source, args.output)
