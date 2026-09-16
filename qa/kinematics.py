"""Planar derivatives from measured samples; no interpolation or gap bridging."""
import math


def derive(trial):
    curves = {name: [] for name in ('speed', 'acceleration', 'distance', 'z')}
    rows = []
    units = {'speed': 'pt/s', 'acceleration': 'pt/s^2', 'distance': 'pt', 'z': 'API raw'}
    for segment_id, segment in enumerate(trial['segments']):
        points = [trial['points'][i] for i in segment]
        if not points:
            continue
        series = {name: [] for name in curves}

        def record(metric, time, value, support, **extra):
            series[metric].append([time, value, points[0][4]])
            rows.append({'trialID': trial['id'], 'plannedIndex': trial['index'],
                         'distanceConditionPt': trial['distance'], 'targetDiameterPt': trial['target'][2],
                         'success': trial['success'], 'segmentID': segment_id,
                         'inputSource': points[0][10], 'metric': metric, 'timeFromTrialMs': time,
                         'value': value, 'unit': units[metric],
                         'supportSequences': ';'.join(str(p[6]) for p in support), **extra})

        for p in points:
            record('distance', p[0], math.hypot(p[1]-trial['target'][0], p[2]-trial['target'][1]), [p])
            if p[4] == 0 and p[3] is not None:
                record('z', p[0], p[3], [p])
        velocities = []
        for a, b in zip(points, points[1:]):
            dt = (b[0]-a[0])/1000
            if dt <= 0:
                if series['speed']:
                    curves['speed'].append(series['speed']);series['speed']=[]
                velocities.append(None)
                continue
            vx, vy = (b[1]-a[1])/dt, (b[2]-a[2])/dt
            time, speed = (a[0]+b[0])/2, math.hypot(vx, vy)
            record('speed', time, speed, [a, b], vx=vx, vy=vy)
            velocities.append((time, vx, vy, speed))
        for i, (a, b) in enumerate(zip(velocities, velocities[1:])):
            if a is None or b is None:
                if series['acceleration']:
                    curves['acceleration'].append(series['acceleration']);series['acceleration']=[]
                continue
            dt = (b[0]-a[0])/1000
            if dt <= 0:
                continue
            ax, ay = (b[1]-a[1])/dt, (b[2]-a[2])/dt
            # Signed rate of planar speed change, distinct from acceleration magnitude.
            record('acceleration', (a[0]+b[0])/2, (b[3]-a[3])/dt, points[i:i+3],
                   ax=ax, ay=ay, accelerationMagnitude=math.hypot(ax, ay))
        for metric, values in series.items():
            if values:
                curves[metric].append(values)
    touch = next((e['t'] for e in trial['events'] if e['type'] == 'TOUCH_DOWN'), None)
    return {'touchMs': touch, 'curves': curves}, rows


def build_kinematics(data):
    trials, rows = {}, []
    for trial in data['trials']:
        curves, derived = derive(trial)
        trials[str(trial['index'])] = curves
        rows.extend(derived)
    return {'trials': trials, 'method': 'Adjacent-pair planar velocity at pair midpoint; '
            'adjacent-velocity finite difference at velocity-time midpoint. acceleration curve '
            'is signed speed change rate; CSV also includes ax, ay and accelerationMagnitude. '
            'Derivatives never cross source, segment or removed samples. No interpolation.',
            'alignment': 'First retained Pencil TOUCH_DOWN per trial; milliseconds relative to contact.'}, rows
