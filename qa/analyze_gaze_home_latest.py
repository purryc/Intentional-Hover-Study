#!/usr/bin/env python3
"""Read-only, session-scoped gaze/home audit for the latest V2.4 collection.

All spatial metrics use phone-local pt. Gaze quality is reported, never treated
as an eye-tracker ground truth or a task success label.
"""
from __future__ import annotations

import argparse
import bisect
import collections
import csv
import hashlib
import json
import math
import statistics
from pathlib import Path

import numpy as np

PHONE_W, PHONE_H = 390, 830
CELL = 20
HOME_R = 50
MAX_GAP = .100


def number(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def inside(point):
    return point['x'] is not None and point['y'] is not None and 0 <= point['x'] <= PHONE_W and 0 <= point['y'] <= PHONE_H


def dist(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def quantiles(values):
    if not values:
        return None
    a = np.asarray(values, dtype=float)
    return {'median': round(float(np.median(a)), 2), 'p10': round(float(np.percentile(a, 10)), 2),
            'p90': round(float(np.percentile(a, 90)), 2)}


def read_session(source, session_id):
    trials = {}
    order = []
    calibrations = []
    quality = collections.Counter()
    invalid_rows = 0
    for row in csv.DictReader(source.open(newline='', encoding='utf-8')):
        if row['sessionID'] != session_id:
            continue
        tid = row['trialID']
        try:
            meta = json.loads(row['metadata'] or '{}')
        except json.JSONDecodeError:
            invalid_rows += 1
            meta = {}
        t = number(row['monotonicTime'])
        if row['eventType'] == 'GAZE_CALIBRATION':
            calibrations.append({'at': t, 'quality': meta.get('quality'),
                                 'p90Pt': number(meta.get('validationP90Pt')),
                                 'coverage': number(meta.get('validationCoverage')),
                                 'id': meta.get('calibrationID')})
        if row['inputType'] == 'GAZE':
            quality[(meta.get('gazeValidity'), meta.get('gazeQuality'), meta.get('phoneRegion'))] += 1
        if not tid:
            continue
        tr = trials.setdefault(tid, {'id': tid, 'events': [], 'gaze': [], 'hover': [], 'touch': []})
        if row['recordType'] == 'EVENT':
            tr['events'].append({'type': row['eventType'], 't': t, 'success': row['success'], 'meta': meta})
            if row['eventType'] == 'TRIAL_START':
                tr.update(start=t, task=meta.get('taskID') or row['testID'],
                          condition=meta.get('condition') or row['conditionID'],
                          scene=meta.get('scene'), posture=meta.get('posture'),
                          target=json.loads(meta.get('trial', '{}')).get('objects', []))
                order.append(tid)
            elif row['eventType'] == 'TRIAL_END':
                tr.update(end=t, success=row['success'] == 'true')
        elif row['recordType'] == 'SAMPLE' and t is not None:
            point = {'t': t, 'x': number(row['localX']), 'y': number(row['localY']),
                     'phase': meta.get('sequencePhase'), 'source': row['sampleSource']}
            if row['inputType'] == 'GAZE':
                point.update(validity=meta.get('gazeValidity'), gazeQuality=meta.get('gazeQuality'),
                             calibrationID=meta.get('calibrationID'),
                             frameTime=number(meta.get('arFrameTimestamp')),
                             calibrationAgeS=number(meta.get('calibrationAgeS')))
                tr['gaze'].append(point)
            elif row['inputType'] == 'PENCIL' and row['sampleSource'] == 'PENCIL_HOVER' and row['hoverState'] not in ('ENDED', 'CANCELLED'):
                tr['hover'].append(point)
            elif row['inputType'] == 'PENCIL' and row['sampleSource'] == 'PENCIL_TOUCH':
                tr['touch'].append(point)
    return [trials[tid] for tid in order], calibrations, quality, invalid_rows


def task_points(tr, key):
    return [p for p in tr[key] if tr.get('start') is not None and tr.get('end') is not None
            and tr['start'] <= p['t'] <= tr['end'] and p['phase'] != 'INTER_TRIAL']


def intervals(points, gaze=False):
    """Assign only a measured short interval to its first measured location."""
    for a, b in zip(points, points[1:]):
        dt = b['t'] - a['t']
        if not .001 <= dt <= MAX_GAP or not inside(a) or not inside(b):
            continue
        if gaze and (a['validity'] != 'TRACKED' or b['validity'] != 'TRACKED'
                     or a['calibrationID'] != b['calibrationID']):
            continue
        yield a, dt


def hotspot(weighted, radius=HOME_R):
    grid = np.zeros((math.ceil(PHONE_H / CELL), math.ceil(PHONE_W / CELL)))
    for p, dt in weighted:
        grid[min(int(p['y'] // CELL), grid.shape[0]-1), min(int(p['x'] // CELL), grid.shape[1]-1)] += dt
    if grid.sum() <= 0:
        return None, 0., grid
    yy, xx = np.indices(grid.shape)
    best = (None, -1.)
    for y in range(grid.shape[0]):
        for x in range(grid.shape[1]):
            cx, cy = x * CELL + CELL / 2, y * CELL + CELL / 2
            mask = ((xx + .5) * CELL - cx) ** 2 + ((yy + .5) * CELL - cy) ** 2 <= radius ** 2
            weight = float(grid[mask].sum())
            if weight > best[1]:
                best = ((cx, cy), weight)
    return best[0], best[1] / float(grid.sum()), grid


def share_within(weighted, center, radius):
    total = sum(dt for _, dt in weighted)
    return round(sum(dt for p, dt in weighted if dist((p['x'], p['y']), center) <= radius) / total, 4) if total else None


def paired_distances(gaze, hover):
    hover_segments = [(p['t'], p['t'] + dt, p) for p, dt in intervals(hover)]
    times = [a for a, _, _ in hover_segments]
    distances = []
    for p, dt in intervals(gaze, gaze=True):
        idx = bisect.bisect_right(times, p['t']) - 1
        if idx < 0:
            continue
        a, b, h = hover_segments[idx]
        if not a <= p['t'] < b:
            continue
        weight = min(dt, b - p['t'])
        if weight > 0:
            distances.append((dist((p['x'], p['y']), (h['x'], h['y'])), weight))
    seconds = sum(w for _, w in distances)
    return {'seconds': round(seconds, 3), 'medianPt': quantiles([d for d, _ in distances]),
            'within50': round(sum(w for d, w in distances if d <= 50) / seconds, 4) if seconds else None,
            'within100': round(sum(w for d, w in distances if d <= 100) / seconds, 4) if seconds else None}


def reading_stats(tr):
    gaze = task_points(tr, 'gaze')
    hover = task_points(tr, 'hover')
    gi, pi = list(intervals(gaze, True)), list(intervals(hover))
    home, home_grid_share, pg = hotspot(pi)
    eye, eye_grid_share, gg = hotspot(gi)
    result = {'task': tr['task'], 'scene': tr.get('scene'), 'trialID': tr['id'],
              'success': tr.get('success'), 'recordedS': round(tr['end']-tr['start'], 3),
              'gazeSamplesInPhone': sum(inside(p) and p['validity'] == 'TRACKED' for p in gaze),
              'hoverSamplesInPhone': sum(inside(p) for p in hover),
              'gazeObservedS': round(sum(dt for _, dt in gi), 3),
              'hoverObservedS': round(sum(dt for _, dt in pi), 3),
              'cameraReceiptLagMs': quantiles([(p['t'] - p['frameTime']) * 1000 for p in gaze
                                                if p['frameTime'] is not None]),
              'calibrationAgeS': quantiles([p['calibrationAgeS'] for p in gaze
                                            if p['calibrationAgeS'] is not None]),
              'homeCenter': home, 'homeGridShareR50': round(home_grid_share, 4),
              'gazeHotspotCenter': eye, 'gazeGridShareR50': round(eye_grid_share, 4),
              'paired': paired_distances(gaze, hover)}
    if home and eye:
        result.update(centerDistancePt=round(dist(home, eye), 2),
                      gazeWithinHomeR50=share_within(gi, home, 50),
                      gazeWithinHomeR100=share_within(gi, home, 100),
                      hoverWithinHomeR50=share_within(pi, home, 50))
    return result, pg, gg


def a1_stats(trials):
    rows = []
    for tr in trials:
        if tr.get('task') != 'A1' or 'start' not in tr or 'end' not in tr:
            continue
        objects = [o for o in tr.get('target', []) if o.get('id') == 'target']
        touches = [e['t'] for e in tr['events'] if e['type'] == 'TOUCH_DOWN' and e['t'] is not None]
        if not objects or not touches:
            continue
        b = objects[0]['bounds']
        center = (b['x'] + b['width']/2, b['y'] + b['height']/2)
        anchor = min(touches)
        eye = [p for p in task_points(tr, 'gaze') if anchor-.3 <= p['t'] <= anchor]
        hover = [p for p in task_points(tr, 'hover') if anchor-.3 <= p['t'] <= anchor]
        gi = list(intervals(eye, True))
        valid_eye = [p for p in eye if inside(p) and p['validity'] == 'TRACKED']
        valid_hover = [p for p in hover if inside(p)]
        rows.append({'trialID': tr['id'], 'success': tr.get('success'),
                     'targetDiameterPt': b['width'], 'targetCenter': center,
                     'gazeObservedS': round(sum(dt for _, dt in gi), 4),
                     'gazeWithinTargetR50': share_within(gi, center, 50),
                     'gazeWithinTargetR100': share_within(gi, center, 100),
                     'gazeMedianDistancePt': quantiles([dist((p['x'], p['y']), center) for p in valid_eye]),
                     'hoverMedianDistancePt': quantiles([dist((p['x'], p['y']), center) for p in valid_hover]),
                     'paired': paired_distances(eye, hover)})
    return rows


def make_plot(reading, grids, out):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib import font_manager
    font_manager.fontManager.addfont('/System/Library/Fonts/Supplemental/Arial Unicode.ttf')
    plt.rcParams.update({'font.family': 'Arial Unicode MS', 'axes.unicode_minus': False})
    fig, axes = plt.subplots(2, 3, figsize=(11, 11), layout='constrained')
    for col, row in enumerate(reading):
        pg, gg = grids[row['task']]
        for ri, (grid, title) in enumerate(((pg, 'Pencil hover'), (gg, 'Front-camera gaze'))):
            ax = axes[ri, col]
            normalized = grid / grid.sum() if grid.sum() else grid
            ax.imshow(normalized, cmap='magma', origin='upper', extent=(0, 390, 830, 0), vmin=0,
                      vmax=max(.02, float(max(pg.max()/pg.sum() if pg.sum() else 0, gg.max()/gg.sum() if gg.sum() else 0))))
            ax.set(title=f"{row['task']} {title} · {row['gazeObservedS' if ri else 'hoverObservedS']:.1f}s",
                   xlim=(0, 390), ylim=(830, 0), xlabel='Phone X · pt', ylabel='Phone Y · pt')
            if row['homeCenter']:
                ax.add_patch(plt.Circle(row['homeCenter'], HOME_R, fill=False, color='#21d4a7', lw=2))
                ax.scatter(*row['homeCenter'], marker='+', s=80, c='#21d4a7')
            if row['gazeHotspotCenter'] and ri == 1:
                ax.scatter(*row['gazeHotspotCenter'], marker='x', s=90, c='cyan')
    fig.suptitle('Reading scenes · green circle: Pencil Home R50 · cyan x: gaze hotspot\nGaze calibration P90 = 211.9 pt; coarse spatial comparison only', fontsize=13)
    fig.savefig(out, dpi=150)
    plt.close(fig)


def make_contrast_plot(reading, targets, calibration_p90, out):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib import font_manager
    font_manager.fontManager.addfont('/System/Library/Fonts/Supplemental/Arial Unicode.ttf')
    plt.rcParams.update({'font.family': 'Arial Unicode MS', 'axes.unicode_minus': False})
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.5), layout='constrained')
    valid = [r for r in targets if r['gazeMedianDistancePt'] and r['hoverMedianDistancePt']]
    x = np.arange(len(valid))
    axes[0].scatter(x, [r['gazeMedianDistancePt']['median'] for r in valid], label='Gaze → target', c='#d95f02')
    axes[0].scatter(x, [r['hoverMedianDistancePt']['median'] for r in valid], label='Pencil → target', c='#138b77')
    if calibration_p90:
        axes[0].axhline(calibration_p90, ls='--', c='#9c7894', label=f'Calibration P90 {calibration_p90:.0f} pt')
    axes[0].set(title=f'A1: last 300 ms before touch · {len(valid)} trials with gaze',
                xlabel='Successful target-tap trials', ylabel='Median distance to target · pt')
    axes[0].legend(fontsize=8)
    labels = [r['task'] for r in reading]
    x = np.arange(len(labels))
    width = .35
    axes[1].bar(x-width/2, [r['hoverWithinHomeR50']*100 for r in reading], width,
                label='Pencil in its Home', color='#138b77')
    axes[1].bar(x+width/2, [r['gazeWithinHomeR50']*100 for r in reading], width,
                label='Gaze in Pencil Home', color='#d95f02')
    axes[1].set(xticks=x, xticklabels=labels, ylim=(0, 55),
                title='Natural reading · share of observed time in R50 Home', ylabel='Observed time · %')
    axes[1].legend(fontsize=8)
    fig.suptitle('Coarse gaze estimate fails the small-target quality gate; bars are descriptive only', fontsize=12)
    fig.savefig(out, dpi=150)
    plt.close(fig)


def main(source, session_id, output):
    output.mkdir(parents=True, exist_ok=True)
    sha = hashlib.sha256()
    with source.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            sha.update(block)
    trials, calibrations, quality, invalid_rows = read_session(source, session_id)
    reading = []
    grids = {}
    for tr in trials:
        if tr.get('task') in ('A5', 'A6', 'A7') and tr.get('condition') == 'NATURAL' and tr.get('success'):
            row, pg, gg = reading_stats(tr)
            reading.append(row)
            grids[row['task']] = (pg, gg)
    targets = a1_stats(trials)
    payload = {'source': str(source), 'sha256': sha.hexdigest(), 'sessionID': session_id,
               'sessionTasks': dict(collections.Counter(t.get('task') for t in trials)),
               'calibrations': calibrations,
               'gazeQualityCounts': [{'validity': k[0], 'quality': k[1], 'phoneRegion': k[2], 'count': v}
                                     for k, v in sorted(quality.items(), key=lambda x: str(x[0]))],
               'metadataParseErrors': invalid_rows, 'reading': reading, 'a1': targets,
               'method': {'gridPt': CELL, 'homeRadiusPt': HOME_R, 'maxContinuityGapMs': 100,
                          'a1WindowMs': 300, 'pairedMaxReceivedTimeDifferenceMs': 100,
                          'timeBasis': 'monotonicTime is camera receipt for gaze; camera capture time remains in metadata',
                          'limits': 'Home is retrospective Pencil spatial density; gaze is COARSE_ONLY and cannot validate small-object match or intent.'}}
    (output/'metrics.json').write_text(json.dumps(payload, ensure_ascii=False, indent=2))
    if len(reading) == 3:
        make_plot(reading, grids, output/'reading-home-gaze.png')
        make_contrast_plot(reading, targets, calibrations[0]['p90Pt'] if calibrations else None,
                           output/'target-vs-reading.png')
    print(json.dumps({'sha256': payload['sha256'], 'trials': len(trials), 'reading': reading,
                      'a1Count': len(targets), 'calibrations': calibrations}, ensure_ascii=False))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('source', type=Path)
    parser.add_argument('--session', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    main(args.source, args.session, args.output)
