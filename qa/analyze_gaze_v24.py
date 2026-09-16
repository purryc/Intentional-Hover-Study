#!/usr/bin/env python3
"""Read-only V2.4 gaze/Pencil reading heatmaps on the same phone-local XY grid."""
from __future__ import annotations

import argparse
import collections
import csv
import json
from pathlib import Path

import numpy as np

from build_v2_replay import reconstruct

CELL = 20
WIDTH, HEIGHT = 390, 830
TASKS = {"A5": "新闻长文", "A6": "图文流", "A7": "短视频流"}


def cell(point):
    if point.get("x") is None or point.get("y") is None:
        return None
    x, y = point["x"], point["y"]
    if not 0 <= x <= WIDTH or not 0 <= y <= HEIGHT:
        return None
    return min(int(x // CELL), 19), min(int(y // CELL), 41)


def heat_edges(points, source):
    """Measured consecutive intervals only; invalid frames and gaps break the path."""
    heat = collections.defaultdict(float)
    observed = 0.0
    for a, b in zip(points, points[1:]):
        dt = b["t"] - a["t"]
        if not 0.001 <= dt <= 0.100000001:
            continue
        if source == "gaze":
            if a.get("validity") != "TRACKED" or b.get("validity") != "TRACKED":
                continue
            if a.get("calibrationID") != b.get("calibrationID"):
                continue
        index = cell(a)
        if index is None or cell(b) is None:
            continue
        heat[index] += dt
        observed += dt
    return heat, observed


def reading_heat(trials):
    groups = collections.defaultdict(lambda: {"gaze": collections.defaultdict(float),
                                            "pencil": collections.defaultdict(float),
                                            "trials": 0, "gazeSamples": 0, "validGazeSamples": 0,
                                            "quality": collections.Counter(), "observedGazeS": 0.,
                                            "observedPencilS": 0., "recordedS": 0.})
    for trial in trials:
        if trial.get("task") not in TASKS or trial.get("condition") != "NATURAL" or not trial.get("success"):
            continue
        key = (trial["task"], trial.get("posture") or "UNKNOWN")
        record = groups[key]
        record["trials"] += 1
        record["recordedS"] += trial["duration"]
        gaze = [p for p in trial.get("gaze", []) if 0 <= p["t"] <= trial["duration"] and p.get("sequencePhase") != "INTER_TRIAL"]
        record["gazeSamples"] += len(gaze)
        record["validGazeSamples"] += sum(p.get("validity") == "TRACKED" and cell(p) is not None for p in gaze)
        record["quality"].update(p.get("quality") or "UNKNOWN" for p in gaze)
        gh, seconds = heat_edges(gaze, "gaze")
        record["observedGazeS"] += seconds
        for index, weight in gh.items():
            record["gaze"][index] += weight
        for segment in trial.get("segments", []):
            if not segment or segment[0].get("source") != "PENCIL_HOVER":
                continue
            segment = [p for p in segment if 0 <= p["t"] <= trial["duration"] and p.get("sequencePhase") != "INTER_TRIAL"]
            ph, seconds = heat_edges(segment, "pencil")
            record["observedPencilS"] += seconds
            for index, weight in ph.items():
                record["pencil"][index] += weight
    return groups


def payload(groups, source, sha):
    return {"source": source, "sha256": sha, "cellPt": CELL, "phone": [WIDTH, HEIGHT],
            "groups": [{"task": key[0], "posture": key[1], "trials": row["trials"],
                        "recordedS": round(row["recordedS"], 3),
                        "gazeSamples": row["gazeSamples"], "validGazeSamples": row["validGazeSamples"],
                        "quality": dict(row["quality"]),
                        "observedGazeS": round(row["observedGazeS"], 3),
                        "observedPencilS": round(row["observedPencilS"], 3),
                        "gazeCells": [[*index, round(value, 5)] for index, value in sorted(row["gaze"].items())],
                        "pencilCells": [[*index, round(value, 5)] for index, value in sorted(row["pencil"].items())]}
                       for key, row in sorted(groups.items())],
            "limits": "The front camera yields calibrated gaze estimates, not an eye-tracker ground truth. Cell weights are measured eligible intervals. Natural reading candidates are not confirmed errors."}


def eye_hand_alignment(trials):
    """Pre-confirmation object agreement, with explicit quality/coverage abstention."""
    rows = []
    for trial in trials:
        if trial.get("task") not in ("B1", "B2", "B3", "C1", "C2", "C3"):
            continue
        if trial.get("task", "").startswith("C") and trial.get("condition") != "HOVER":
            continue
        gaze = trial.get("gaze", [])
        for event in trial.get("events", []):
            if event["type"] not in ("MENU_OPEN", "HOVER_SELECT"):
                continue
            object_id = "target" if trial["task"] == "B1" else event["metadata"].get("objectID")
            if not object_id:
                continue
            anchor = event["t"]
            window = [p for p in gaze if anchor - .3 <= p["t"] <= anchor]
            quality = {p.get("quality") for p in window}
            valid = [p for p in window if p.get("quality") == "OBJECT_LEVEL_PILOT"
                     and p.get("validity") == "TRACKED" and cell(p) is not None]
            valid_duration = 0.
            match_duration = 0.
            for a, b in zip(window, window[1:]):
                dt = b["t"] - a["t"]
                if not 0.001 <= dt <= 0.100000001:
                    continue
                if a in valid and b in valid:
                    valid_duration += dt
                    if a.get("objectID") == object_id and b.get("objectID") == object_id:
                        match_duration += dt
            if "OBJECT_LEVEL_PILOT" not in quality:
                result = "ABSTAIN_CALIBRATION"
            elif valid_duration < .15:
                result = "ABSTAIN_LOW_COVERAGE"
            else:
                result = "MATCH" if match_duration >= .10 else "NO_MATCH"
            rows.append({"trialID": trial["id"], "task": trial["task"],
                         "condition": trial.get("condition"), "event": event["type"],
                         "anchorS": round(anchor, 4), "objectID": object_id,
                         "validGazeS": round(valid_duration, 4),
                         "sameObjectS": round(match_duration, 4), "result": result})
    return rows


def plot(data, output):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib import font_manager
    font_manager.fontManager.addfont("/System/Library/Fonts/Supplemental/Arial Unicode.ttf")
    plt.rcParams.update({"font.family": "Arial Unicode MS", "axes.unicode_minus": False})
    rows = data["groups"]
    if not any(row["observedGazeS"] > 0 for row in rows):
        return False
    postures = sorted({row["posture"] for row in rows})
    fig, axes = plt.subplots(len(postures) * 2, 3, figsize=(12, 7 * len(postures)), squeeze=False)
    for pi, posture in enumerate(postures):
        for ci, task in enumerate(TASKS):
            row = next((r for r in rows if r["posture"] == posture and r["task"] == task), None)
            grids = []
            for kind in ("gaze", "pencil"):
                grid = np.zeros((42, 20))
                if row:
                    for x, y, sec in row[f"{kind}Cells"]:
                        grid[y, x] += sec
                grids.append(grid)
            shared_max = max(0.001, *(float(grid.max()) for grid in grids))
            for ri, (kind, grid) in enumerate(zip(("gaze", "pencil"), grids)):
                ax = axes[pi * 2 + ri, ci]
                ax.imshow(grid, origin="upper", cmap="YlOrRd", vmin=0, vmax=shared_max,
                          extent=(0, 390, 830, 0), aspect="auto", interpolation="nearest")
                name = "前摄视线" if kind == "gaze" else "Pencil 悬停"
                observed = row[f"observed{kind.title()}S"] if row else 0
                ax.set_title(f"{TASKS[task]} · {posture} · {name}\n有效观测 {observed:.1f} s / {row['trials'] if row else 0} 段")
                ax.set(xlim=(0, 390), ylim=(830, 0), xlabel="手机 X · pt", ylabel="手机 Y · pt")
    fig.suptitle("阅读：视线与 Pencil 悬停热区（每场景共用色标；颜色为有效观测秒数）", fontsize=16)
    fig.tight_layout()
    fig.savefig(output / "reading-gaze-vs-hover.png", dpi=150)
    plt.close(fig)
    return True


def build(source: Path, output: Path):
    output.mkdir(parents=True, exist_ok=True)
    replay = reconstruct(source)
    groups = reading_heat(replay["trials"])
    data = payload(groups, replay["source"], replay["sha256"])
    alignment = eye_hand_alignment(replay["trials"])
    data["alignmentSummary"] = dict(collections.Counter(row["result"] for row in alignment))
    (output / "reading-gaze-vs-hover.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    with (output / "eye-hand-alignment.csv").open("w", newline="", encoding="utf-8") as stream:
        fields = ["trialID", "task", "condition", "event", "anchorS", "objectID",
                  "validGazeS", "sameObjectS", "result"]
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(alignment)
    has_image = plot(data, output)
    return {"source": data["source"], "groups": len(groups), "hasGazeHeatmap": has_image,
            "output": str(output / "reading-gaze-vs-hover.json")}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(build(args.source, args.output), ensure_ascii=False))
