"""S6 geometric preflight and evidence diagnostics. Pure Python; no model inference.

No visual association or crop can be inferred from screen position alone.
Future samples are used only to check the *same observed person within the same shot*.
"""
from collections import Counter
from .camera_geometry import geometry, subject_box, contains, crop_rect, base_size
from .temporal import number


def preflight_target(person, index, records, metadata, cfg, *, horizon=1.0, zoom=1.0):
    """Validate intended static crop on successive actual samples, not extrapolation.

    When future samples exist but subject leaves frame, return unsafe. Unknown future
    is not declared safe for digital zoom; baseline framing may remain permissible.
    """
    now = records[index]
    current = now['obs'].get(person)
    if current is None:
        return {'safe': False, 'reason': 'target_not_currently_visible'}
    baseline = geometry([current], metadata, cfg, zoom)
    if not baseline.get('safe'):
        return {**baseline, 'preflight_reason': baseline.get('reason', 'unsafe_geometry')}
    sid = now['shot'].get('shot_id')
    boxes = [subject_box(current, cfg)]
    samples = 1
    next_boundary = min(now['end'] + max(0., horizon), number(now['shot'].get('end'), now['end']))
    cursor = index + 1
    while cursor < len(records) and records[cursor]['mid'] <= next_boundary:
        other = records[cursor]
        if other['shot'].get('shot_id') != sid:
            break
        # Ignore intervals that reuse exactly the same visual source frame.
        if other['frame'] and now['frame'] and other['frame'].get('time') == now['frame'].get('time'):
            cursor += 1
            continue
        observation = other['obs'].get(person)
        if observation is None:
            return {**baseline, 'safe': False, 'preflight_reason': 'target_lost_in_lookahead',
                    'preflight_sample_count': samples}
        box = subject_box(observation, cfg)
        if box is None:
            return {**baseline, 'safe': False, 'preflight_reason': 'unsafe_face_in_lookahead',
                    'preflight_sample_count': samples}
        boxes.append(box)
        samples += 1
        cursor += 1
    union = [min(box[0] for box in boxes), min(box[1] for box in boxes),
             max(box[2] for box in boxes), max(box[3] for box in boxes)]
    base = base_size(metadata, cfg)
    if base is None:
        return {'safe': False, 'preflight_reason': 'unknown_source_dimensions'}
    allowed_zoom = min(baseline['max_zoom'], base[0]/max(union[2]-union[0], 1e-9),
                       base[1]/max(union[3]-union[1], 1e-9))
    if allowed_zoom < 1.0:
        return {**baseline, 'safe': False, 'preflight_reason': 'future_subjects_do_not_fit',
                'preflight_sample_count': samples}
    effective_zoom = min(max(1., zoom), allowed_zoom)
    midpoint = [(union[0]+union[2])/2, (union[1]+union[3])/2]
    rect = crop_rect(midpoint, effective_zoom, base)
    if not contains(rect, union):
        return {**baseline, 'safe': False, 'preflight_reason': 'future_crop_exits_frame',
                'preflight_sample_count': samples}
    # Forecast constrains crop geometry, not active speaker ID or expression.
    return {**baseline, 'safe': True, 'center': [rect['x']+rect['width']/2, rect['y']+rect['height']/2],
            'rect': rect, 'subject_bounds': union, 'max_zoom': allowed_zoom,
            'zoom': effective_zoom, 'preflight_reason': 'observed_safe_path',
            'preflight_sample_count': samples, 'future_evidence_seconds': max(0., records[min(cursor-1,len(records)-1)]['mid']-now['mid'])}


def preflight_split(pair, index, records, metadata, cfg, horizon=1.0):
    """Two separately verified panel crops using each panel's real aspect ratio."""
    if len(pair) != 2:
        return {'safe': False, 'reason': 'requires_exactly_two_people'}
    half_cfg = {**cfg, 'output_width': cfg['output_width']/2}
    panels = {}
    for person in pair:
        result = preflight_target(person, index, records, metadata, half_cfg, horizon=horizon)
        if not result.get('safe'):
            return {'safe': False, 'reason': 'split_panel_'+str(result.get('preflight_reason') or result.get('reason')),
                    'person_id': person}
        panels[person] = result
    ordered = tuple(sorted(pair, key=lambda pid: panels[pid]['center'][0]))
    return {'safe': True, 'left_person': ordered[0], 'right_person': ordered[1],
            'left_crop': panels[ordered[0]]['rect'], 'right_crop': panels[ordered[1]]['rect'],
            'left_crop_safe': True, 'right_crop_safe': True,
            'panel_aspect_correct': True, 'preflight_samples': {pid: panels[pid]['preflight_sample_count'] for pid in pair}}


def evidence_funnel(records, duration):
    """Exclusive causal buckets explaining missing camera focus; sampled, not accuracy."""
    windows = Counter()
    seconds = Counter()
    for row in records:
        dt = row['end']-row['start']
        if not row['shot'] or row['frame'] is None:
            reason = 'NO_CONTEMPORARY_VISUAL_SAMPLE'
        elif not row['obs']:
            reason = 'NO_PERSON_OBSERVATION'
        elif not any(o.get('face_visible') for o in row['obs'].values()):
            reason = 'NO_VISIBLE_FACE'
        elif row['overlap']:
            reason = 'AUDIO_OVERLAP'
        elif not row['confident']:
            reason = 'NO_CONFIRMED_AUDIO_VISUAL_TARGET'
        elif len(row['confident']) > 1:
            reason = 'AMBIGUOUS_CONFIRMED_TARGETS'
        elif row['confident'][0]['person_id'] not in row['safe']:
            reason = 'CONFIRMED_TARGET_UNSAFE_CROP'
        else:
            reason = 'CONFIRMED_TARGET_CROP_ELIGIBLE'
        windows[reason] += 1
        seconds[reason] += dt
    return {'window_counts': dict(windows), 'duration_seconds': {key: round(value, 4) for key,value in seconds.items()},
            'fractions_of_video': {key: round(value/max(duration, 1e-9), 6) for key,value in seconds.items()},
            'method': 'exclusive_predecision_buckets_not_identity_accuracy'}
