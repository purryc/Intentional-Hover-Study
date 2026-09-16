#!/usr/bin/env python3
"""Task-specific Pencil-on-screen motion, derived from SHA-verified replay caches."""
from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np

from build_two_day_motion_atlas import INPUTS, file_hash, trial_end
from sequence_comparison import BIN, CENTERS, eligible_segments, bins_for


TASKS = {
    "A1": {"label": "点击", "context": "抽象目标", "kind": "primitive"},
    "A2": {"label": "拖动", "context": "将图块拖到目标", "kind": "primitive"},
    "A3": {"label": "竖向滚动", "context": "把标记滚入目标窗", "kind": "primitive"},
    "A4": {"label": "横向滚动", "context": "把标记滚入目标窗", "kind": "primitive"},
    "A5": {"label": "阅读 · 长文", "context": "阅读中触屏，包含不同操作", "kind": "reading"},
    "A6": {"label": "阅读 · 图文", "context": "浏览笔记／图片时触屏", "kind": "reading"},
    "A7": {"label": "阅读 · 短视频", "context": "切换／暂停内容时触屏", "kind": "reading"},
}
CONTACT_BINS = 20


def paired_contacts(trial):
    """Pair ordered down/up within a trial; ignore unmatched or reversed events."""
    pending = None
    pairs = []
    for event in sorted(trial["events"], key=lambda e: e["t"]):
        if event["type"] == "TOUCH_DOWN":
            pending = event["t"]
        elif event["type"] == "TOUCH_UP" and pending is not None:
            up = event["t"]
            if pending < up <= trial_end(trial) + 1e-6:
                pairs.append((pending, up))
            pending = None
    return pairs


def contact_shape(segments, down, up):
    """Observed same-source path and actual-time speed by contact progress."""
    speed_bins = [[] for _ in range(CONTACT_BINS)]
    path = 0.0
    covered = 0.0
    duration = up - down
    for segment in segments:
        if segment[0]["t"] > up or segment[-1]["t"] < down:
            continue
        for a, b in zip(segment, segment[1:]):
            if a["t"] < down or b["t"] > up:
                continue
            dt = b["t"] - a["t"]
            if not 0.001 <= dt <= 0.100000001:
                continue
            step = math.hypot(b["x"] - a["x"], b["y"] - a["y"])
            path += step
            covered += dt
            progress = ((a["t"] + b["t"]) / 2 - down) / duration
            index = min(CONTACT_BINS - 1, max(0, int(progress * CONTACT_BINS)))
            speed_bins[index].append(step / dt)
    return {
        "speed": [float(np.median(v)) if v else None for v in speed_bins],
        "coverage": min(1.0, covered / duration),
        "observedPathPt": path,
    }


def quantile(values):
    values = [v for v in values if v is not None and math.isfinite(v)]
    return {"n": len(values), "median": float(np.median(values)) if values else None,
            "q25": float(np.quantile(values, .25)) if values else None,
            "q75": float(np.quantile(values, .75)) if values else None}


def summarize(events):
    result = {}
    for task, description in TASKS.items():
        selected = [e for e in events if e["task"] == task]
        covered = [e for e in selected if e["contactCoverage"] >= .7]
        result[task] = {
            **description,
            "contacts": len(selected),
            "trials": len({(e["day"], e["trialID"]) for e in selected}),
            "contactDurationMs": quantile([e["durationMs"] for e in selected]),
            "observedPathPt": quantile([e["observedPathPt"] for e in covered]),
            "contactCoverage": quantile([e["contactCoverage"] for e in selected]),
            "preSpeed": [quantile([e["preSpeed"][i] for e in selected]) for i in range(20)],
            "preZSpeed": [quantile([e["preZSpeed"][i] for e in selected]) for i in range(20)],
            "contactSpeed": [quantile([e["contactSpeed"][i] for e in covered]) for i in range(CONTACT_BINS)],
        }
    return result


def build(output: Path):
    events = []
    sources = []
    for day, raw, replay in INPUTS:
        data = json.loads(replay.read_text())
        sha = file_hash(raw)
        if data["sha256"] != sha:
            raise ValueError(f"Replay cache does not match raw CSV: {raw}")
        sources.append({"day": day, "source": raw.name, "sha256": sha})
        for trial in data["trials"]:
            task = trial.get("task")
            if task not in TASKS or not trial.get("success"):
                continue
            pairs = paired_contacts(trial)
            if TASKS[task]["kind"] == "primitive":
                pairs = pairs[-1:]
            if not pairs:
                continue
            hover = eligible_segments(trial, include_touch=False)
            touch = [s for s in eligible_segments(trial, include_touch=True)
                     if s[0]["source"] == "PENCIL_TOUCH"]
            for down, up in pairs:
                pre = bins_for(hover, down, (0, 0))
                contact = contact_shape(touch, down, up)
                # bins_for uses 50 ms bins from -1000 ms; its first 20 bins end at TOUCH_DOWN.
                events.append({"day": day, "trialID": trial["id"], "task": task,
                               "downS": down, "upS": up, "durationMs": (up - down) * 1000,
                               "preSpeed": pre["speed"][:20], "preZSpeed": pre["zSpeed"][:20],
                               "contactSpeed": contact["speed"],
                               "contactCoverage": contact["coverage"],
                               "observedPathPt": contact["observedPathPt"]})
    payload = {
        "source": sources,
        "participantCount": 1,
        "preTouchWindowMs": [-1000, 0], "preTouchBinMs": round(BIN * 1000),
        "contactProgressBins": CONTACT_BINS,
        "pathCoverageMinimum": .7,
        "taskSelection": "A1-A4 successful trials: last complete touch; A5-A7 successful reading trials: all complete touches",
        "limits": "Finger-strapped Apple Pencil, one participant; A5-A7 are mixed in-context contacts. Z is API-relative and absent during touch. Normalized contact progress is not elapsed time. Observed path may miss edge samples.",
        "tasks": summarize(events),
    }
    output.mkdir(parents=True, exist_ok=True)
    (output / "touch-motion.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1]
    result = build(root / "analysis/trajectory_2026-09-16/two_day_motion_atlas")
    for name, info in result["tasks"].items():
        print(name, info["contacts"], info["trials"], info["contactDurationMs"]["median"],
              info["observedPathPt"]["median"])
