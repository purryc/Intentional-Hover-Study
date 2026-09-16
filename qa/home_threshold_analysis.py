"""Spatial home and retrospective dwell-threshold comparison for two study days.

Home uses position/time only. No dwell, velocity or Z threshold is consulted.
"""
from __future__ import annotations

import collections
import csv
import json
import math
from pathlib import Path

from build_two_day_motion_atlas import INPUTS, clean_segments, file_hash


CHECKPOINTS = (2, 5, 10, 20, 30, 45, 60, 90, 120)
CELL_PT = 20
HOME_RADIUS_PT = 50
MIN_OBSERVED_S = 1.0
MIN_PEAK_SHARE = .20
STABLE_DIST_PT = 30
REPLICATE_DIST_PT = 50


def hover_edges(trial):
    """Each edge is a real, eligible Pencil hover interval within one segment."""
    edges = []
    for segment in clean_segments(trial):
        for a, b in zip(segment, segment[1:]):
            dt = b["t"] - a["t"]
            if .001 <= dt <= .100000001 and 0 <= a["x"] <= 390 and 0 <= a["y"] <= 830:
                edges.append((a["t"], b["t"], a["x"], a["y"]))
    return edges


def weighted_cells(edges, start=0., stop=None):
    cells = collections.defaultdict(float)
    for t0, t1, x, y in edges:
        clipped = max(0., min(t1, stop if stop is not None else t1) - max(t0, start))
        if clipped > 0:
            ix = min(int(x // CELL_PT), 19)
            iy = min(int(y // CELL_PT), 41)
            cells[(ix, iy)] += clipped
    return cells


def hotspot(cells):
    total = sum(cells.values())
    if total <= 0:
        return None
    best = None
    for ix, iy in cells:
        x, y = (ix + .5) * CELL_PT, (iy + .5) * CELL_PT
        mass = sum(weight for (cx, cy), weight in cells.items()
                   if math.hypot((cx - ix) * CELL_PT, (cy - iy) * CELL_PT) <= HOME_RADIUS_PT)
        candidate = (mass, cells[(ix, iy)], -iy, -ix)
        if best is None or candidate > best[0]:
            best = (candidate, x, y)
    return {"x": best[1], "y": best[2], "seconds": round(best[0][0], 3),
            "share": round(best[0][0] / total, 4), "observedS": round(total, 3)}


def distance(a, b):
    if a is None or b is None:
        return None
    return round(math.hypot(a["x"] - b["x"], a["y"] - b["y"]), 1)


def analyze_home_trial(trial, day):
    edges = hover_edges(trial)
    full = weighted_cells(edges, stop=trial["duration"])
    reference = hotspot(full)
    prefixes = []
    for t in CHECKPOINTS:
        if t > trial["duration"] + .05:
            continue
        h = hotspot(weighted_cells(edges, stop=t))
        eligible = bool(h and h["observedS"] >= MIN_OBSERVED_S and h["share"] >= MIN_PEAK_SHARE)
        prefixes.append({"wallS": t, "candidate": h if eligible else None,
                         "distanceToFullPt": distance(h, reference) if eligible else None,
                         "observedS": h["observedS"] if h else 0})
    first = next((p for p in prefixes if p["candidate"]), None)
    valid = [p for p in prefixes if p["candidate"]]
    stable = next((p for i, p in enumerate(valid)
                   if any(q["observedS"] >= p["observedS"] + .5 for q in valid[i + 1:])
                   and p["distanceToFullPt"] <= STABLE_DIST_PT
                   and all(q["distanceToFullPt"] <= STABLE_DIST_PT for q in valid[i:])), None)
    middle = trial["duration"] / 2
    first_half, second_half = hotspot(weighted_cells(edges, stop=middle)), hotspot(weighted_cells(edges, start=middle))
    replication = distance(first_half, second_half)
    replicated = bool(first_half and second_half and first_half["observedS"] >= MIN_OBSERVED_S
                      and second_half["observedS"] >= MIN_OBSERVED_S
                      and replication <= REPLICATE_DIST_PT)
    return {"day": day, "trialID": trial["id"], "scene": trial["scene"], "posture": trial["posture"],
            "durationS": round(trial["duration"], 3), "edgeCount": len(edges),
            "observedS": reference["observedS"] if reference else 0,
            "coverage": round(reference["observedS"] / trial["duration"], 4) if reference else 0,
            "home": reference, "cells": [[ix, iy, round(s, 4)] for (ix, iy), s in sorted(full.items())],
            "firstEstimableWallS": first["wallS"] if first else None,
            "firstEstimableObservedS": first["observedS"] if first else None,
            "stableWallS": stable["wallS"] if stable else None,
            "stableObservedS": stable["observedS"] if stable else None,
            "validatedStableWallS": stable["wallS"] if stable and replicated else None,
            "halfCentersDistancePt": replication, "halfReplicated": replicated,
            "firstHalf": first_half, "secondHalf": second_half, "prefixes": prefixes}


THRESHOLDS_MS = tuple(range(100, 1001, 25))


def threshold_trial(trial, day):
    requested = set(trial["trial"].get("requested", []))
    c3 = trial["task"] == "C3"
    ends = [e for e in trial["events"] if e["type"] == "DWELL_END"
            and (not c3 or e["metadata"].get("objectID") in requested)]
    logged = [e for e in trial["events"] if e["type"] == "CANDIDATE"
              and (not c3 or e["metadata"].get("objectID") in requested)]
    durations = []
    for e in ends:
        ms = float(e["metadata"].get("durationMs", 0))
        if math.isfinite(ms) and ms >= 0:
            if str(e["metadata"].get("candidate", "false")).lower() == "true":
                ms = max(ms, 500.)
            durations.append(ms)
    at500 = sum(ms + 1e-7 >= 500 for ms in durations)
    if at500 != len(logged):
        raise ValueError(f"500 ms mismatch {day} {trial['id']}: {at500} vs {len(logged)}")
    candidate_series = [sum(ms + 1e-7 >= threshold for ms in durations)
                        for threshold in THRESHOLDS_MS]
    return {"day": day, "task": trial["task"], "cohort": "C3" if c3 else "A",
            "scene": trial["scene"], "posture": trial["posture"], "trialID": trial["id"],
            "durationS": trial["duration"], "episodes": len(durations), "logged500": len(logged),
            "candidate500": at500, "candidate800": sum(ms + 1e-7 >= 800 for ms in durations),
            "candidateSeries": candidate_series}


def summarize_threshold(rows):
    groups = collections.defaultdict(list)
    for row in rows:
        for key in ((row["day"], row["cohort"], row["scene"]),
                    (row["day"], row["cohort"], "ALL"),
                    ("BOTH", row["cohort"], row["scene"]),
                    ("BOTH", row["cohort"], "ALL")):
            groups[key].append(row)
    out = []
    for key, rr in sorted(groups.items()):
        secs = sum(r["durationS"] for r in rr)
        n500, n800 = sum(r["candidate500"] for r in rr), sum(r["candidate800"] for r in rr)
        out.append({"day": key[0], "cohort": key[1], "scene": key[2], "trials": len(rr),
                    "episodes": sum(r["episodes"] for r in rr), "recordedMinutes": round(secs / 60, 3),
                    "candidate500": n500, "candidate800": n800,
                    "candidateSeries": [sum(r["candidateSeries"][i] for r in rr)
                                        for i in range(len(THRESHOLDS_MS))],
                    "perMinute500": round(n500 * 60 / secs, 3) if secs else None,
                    "perMinute800": round(n800 * 60 / secs, 3) if secs else None,
                    "reductionPct": round((n500 - n800) / n500 * 100, 1) if n500 else None})
    return out


def read_le_reference(root):
    """Read local upstream-derived table, preserving its foreign measurement regime."""
    path = root.parent / "le2019-posture-v1/data/summary.csv"
    if not path.exists():
        return {"available": False}
    with path.open(newline="", encoding="utf-8") as f:
        rows = [r for r in csv.DictReader(f) if r["task"] == "READ" and r["finger"] == "Thumb"
                and r["basis"] == "confirmed_core" and int(r["valid_frames"]) >= 240]
    participants = sorted({r["participant"] for r in rows})
    episode_path = path.parent / "episodes.csv"
    with episode_path.open(newline="", encoding="utf-8") as f:
        episodes = [r for r in csv.DictReader(f) if r["task"] == "READ"
                    and r.get("velocity_threshold") == "20" and r.get("min_duration_ms") == "400"
                    and r.get("exclusion_ms") == "300"]
    durations = sorted(float(r["duration_ms"]) for r in episodes)
    middle = len(durations) // 2
    median = (durations[middle] if len(durations) % 2 else
              (durations[middle - 1] + durations[middle]) / 2) if durations else None
    return {"available": True, "source": str(path), "sha256": file_hash(path),
            "readingRows": len(rows), "participants": len(participants),
            "episodesSource": str(episode_path), "episodesSha256": file_hash(episode_path),
            "readingStableEpisodes": len(episodes), "readingStableMedianMs": round(median, 1) if median else None,
            "readingStableRule": "<20 mm/s, at least 400ms, >300ms from touch",
            "task": "READ", "finger": "Thumb", "basis": "confirmed_core",
            "measurement": "optical motion capture of nail marker, local phone coordinates in mm",
            "comparability": "contextual only; no deliberate hover labels, different sensor and hand role"}


def add_reading_voxels(voxels, trial):
    for segment in clean_segments(trial):
        for a, b in zip(segment, segment[1:]):
            dt = b["t"] - a["t"]
            z = a.get("z")
            if .001 <= dt <= .100000001 and z is not None and 0 <= z <= 1:
                ix = min(int(a["x"] // CELL_PT), 19)
                iy = min(int(a["y"] // CELL_PT), 41)
                iz = min(int(z / .05), 19)
                voxels[(ix, iy, iz)] += dt


def build(root, output):
    output.mkdir(parents=True, exist_ok=True)
    homes, thresholds, source = [], [], []
    reading_heat = collections.defaultdict(lambda: collections.defaultdict(float))
    for day, raw, replay in INPUTS:
        data = json.loads(replay.read_text())
        digest = file_hash(raw)
        if digest != data["sha256"]:
            raise ValueError(f"Raw SHA mismatch: {raw}")
        source.append({"day": day, "name": raw.name, "sha256": digest})
        for trial in data["trials"]:
            if trial["task"] in ("A5", "A6", "A7") and trial["condition"] == "NATURAL" and trial["success"]:
                homes.append(analyze_home_trial(trial, day))
                for posture in (trial["posture"], "ALL"):
                    add_reading_voxels(reading_heat[(day, posture, trial["task"])], trial)
            if trial["task"] in ("A5", "A6", "A7", "C3") and trial["condition"] == "NATURAL" and trial["success"]:
                thresholds.append(threshold_trial(trial, day))
    home_data = {"cellPt": CELL_PT, "radiusPt": HOME_RADIUS_PT, "minObservedS": MIN_OBSERVED_S,
                 "minPeakShare": MIN_PEAK_SHARE, "stableDistancePt": STABLE_DIST_PT,
                 "replicateDistancePt": REPLICATE_DIST_PT, "checkpointsS": CHECKPOINTS,
                 "source": source, "trials": homes}
    threshold_summary = summarize_threshold(thresholds)
    without_series = lambda rows: [{k: v for k, v in row.items() if k != "candidateSeries"} for row in rows]
    threshold_data = {"source": source, "trials": without_series(thresholds),
                      "summary": without_series(threshold_summary),
                      "active800Accuracy": None, "reason": "B1 opens menu at 500ms; no 800ms active counterfactual"}
    threshold_sweep = {"source": source, "thresholdMs": list(THRESHOLDS_MS),
                       "baselineMs": 500, "defaultMs": 800,
                       "summary": threshold_summary, "activeAccuracy": None,
                       "reason": "Natural reading candidate counts only; no true error labels or active counterfactual at other thresholds"}
    le = read_le_reference(root)
    (output / "home-position.json").write_text(json.dumps(home_data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    (output / "threshold-800.json").write_text(json.dumps(threshold_data, ensure_ascii=False, indent=2), encoding="utf-8")
    (output / "threshold-sweep.json").write_text(json.dumps(threshold_sweep, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    (output / "le-reference.json").write_text(json.dumps(le, ensure_ascii=False, indent=2), encoding="utf-8")
    labels = {"A5": "A5 新闻", "A6": "A6 图文流", "A7": "A7 短视频"}
    heat_payload = {"xyCellPt": CELL_PT, "zCellRaw": .05, "groups": {
        "|".join((day, posture, labels[task])): {
            "seconds": round(sum(voxels.values()), 3), "voxelCount": len(voxels),
            "voxels": [[*xyz, round(s, 5)] for xyz, s in voxels.items()]}
        for (day, posture, task), voxels in reading_heat.items()}}
    (output / "home-heat.json").write_text(json.dumps(heat_payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    return home_data, threshold_data, le
