#!/usr/bin/env python3
"""Check replay points against CSV and original continuous segment adjacency."""
import argparse
import csv
import hashlib
import json
from pathlib import Path
from reconstruct_trajectories import reconstruct


def check(source, output):
    original = reconstruct(source)
    data = json.loads((output / 'phone_trajectories.json').read_text())
    assert data['sha256'] == hashlib.sha256(source.read_bytes()).hexdigest()
    assert len(original['trials']) == len(data['trials'])
    expected_points, edges = {}, 0
    for old, trial in zip(original['trials'], data['trials']):
        assert (old['id'], old['index'], old['success'], old['error']) == (
            trial['id'], trial['index'], trial['success'], trial['error'])
        contaminated = any(p[11] != 'PENCIL' for p in old['points'])
        assert trial['excluded'] == contaminated
        eligible = {p[6]: p for p in old['points'] if not contaminated and
                    p[11] == 'PENCIL' and 976 <= p[1] <= 1366 and
                    194 <= p[2] <= 1024 and not
                    (p[4] == 0 and (p[5] in ('ENDED', 'CANCELLED') or p[3] is None))}
        assert {p[6]: p for p in trial['points']} == eligible
        expected_points.update(eligible)
        original_edges = {(old['points'][a][6], old['points'][b][6])
                          for segment in old['segments']
                          for a, b in zip(segment, segment[1:])}
        for segment in trial['segments']:
            for a, b in zip(segment, segment[1:]):
                pa, pb = trial['points'][a], trial['points'][b]
                assert (pa[6], pb[6]) in original_edges
                assert pa[10] == pb[10] and 0 <= pb[0] - pa[0] <= 100
                edges += 1
    with source.open(newline='', encoding='utf-8') as f:
        rows = {int(r['sequence']): r for r in csv.DictReader(f)
                if r['recordType'] == 'SAMPLE'}
    with (output / 'phone_pencil_samples.csv').open(newline='', encoding='utf-8') as f:
        exported = list(csv.DictReader(f))
    assert len(exported) == len(expected_points) == data['sampleCount']
    assert {int(r['sequence']) for r in exported} == set(expected_points)
    assert all(r == rows[int(r['sequence'])] for r in exported)
    return {'status': 'PASS', 'retainedPhonePencilSamples': len(expected_points),
            'excludedTrials': data['excludedTrials'], 'verifiedEdges': edges,
            'noBridgingAcrossRemovedPoints': True, 'originalCSVUnchanged': True,
            'originalOutcomesRetained': True, 'exportedSampleFieldsUnchanged': True}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('csv', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    report = check(args.csv, args.output)
    if args.report:
        args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps(report, ensure_ascii=False, indent=2))
