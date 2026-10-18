"""Compact existing spatial observations with an explicit temporal error bound.

No detection, Re-ID, camera decision or render occurs here. Unknown people stay
separate by upstream track, and no trajectory crosses a source shot or a gap.
"""
from bisect import bisect_right
from collections import Counter, defaultdict
import hashlib
import json
import math


def _number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _bbox(value):
    if not isinstance(value, dict) or not all(_number(value.get(key)) for key in ('x', 'y', 'width', 'height')):
        return None
    box = {key: float(value[key]) for key in ('x', 'y', 'width', 'height')}
    if (min(box['x'], box['y']) < 0 or min(box['width'], box['height']) <= 0
            or box['x']+box['width'] > 1.000001 or box['y']+box['height'] > 1.000001):
        return None
    # Correct only floating point excess at the normalized source boundary.
    box['width'] = min(box['width'], 1.-box['x'])
    box['height'] = min(box['height'], 1.-box['y'])
    return box if min(box['width'], box['height']) > 0 else None


def _features(box, width, height):
    # Also bound right/bottom edges: separate xywh bounds alone would permit
    # twice the advertised error where a head meets the final crop edge.
    return (box['x']*width, box['y']*height, box['width']*width, box['height']*height,
            (box['x']+box['width'])*width, (box['y']+box['height'])*height)


def _error(sample, first, last):
    fraction = (sample['time']-first['time'])/(last['time']-first['time'])
    return max(abs(value-(left+fraction*(right-left)))
               for value, left, right in zip(sample['features'], first['features'], last['features']))


def _simplify(samples, maximum):
    if len(samples) <= 2:
        return list(range(len(samples))), 0.
    # Preserve extrema beyond the endpoint envelope by more than the error
    # budget. Subpixel extrema in a short noisy track must not disable useful
    # simplification; every original sample is still checked against the bound.
    retained = {0, len(samples)-1}
    for axis in range(len(samples[0]['features'])):
        lowest = min(range(len(samples)), key=lambda i: samples[i]['features'][axis])
        highest = max(range(len(samples)), key=lambda i: samples[i]['features'][axis])
        if samples[lowest]['features'][axis] < min(samples[0]['features'][axis], samples[-1]['features'][axis])-maximum:
            retained.add(lowest)
        if samples[highest]['features'][axis] > max(samples[0]['features'][axis], samples[-1]['features'][axis])+maximum:
            retained.add(highest)
    anchors = sorted(retained)
    pending = list(zip(anchors, anchors[1:]))
    while pending:
        first, last = pending.pop()
        if last-first <= 1:
            continue
        error, index = max((_error(samples[i], samples[first], samples[last]), i)
                           for i in range(first+1, last))
        if error > maximum:
            retained.add(index)
            pending.extend(((first, index), (index, last)))
    retained = sorted(retained)
    measured = 0.
    for first, last in zip(retained, retained[1:]):
        measured = max(measured, max((_error(samples[i], samples[first], samples[last])
                                     for i in range(first+1, last)), default=0.))
    return retained, measured


def simplify_visual_trajectories(observations, shots, *, source_width, source_height,
                                 max_error_px=2., max_gap_s=1.):
    """Simplify all observed face/body boxes, independently of camera fallback.

    Error is measured at every original sample using time-linear interpolation
    and the L-infinity norm of source-pixel x/y/width/height/right/bottom. Output
    spans end at the last actual observation, including zero-duration singleton
    samples; they do not certify continuous visibility between observations.
    """
    if not all(_number(v) and v > 0 for v in (source_width, source_height, max_gap_s)):
        raise ValueError('compact_geometry_invalid_dimensions_or_gap')
    if not _number(max_error_px) or max_error_px < 0:
        raise ValueError('compact_geometry_invalid_error_bound')
    observations = list(observations)
    shots = sorted(shots, key=lambda row: row.get('start', -1))
    for index, shot in enumerate(shots):
        if not all(_number(shot.get(k)) for k in ('start', 'end')) or not 0 <= shot['start'] < shot['end']:
            raise ValueError('compact_geometry_invalid_source_shot')
        if index and shots[index-1]['end'] > shot['start']+1e-9:
            raise ValueError('compact_geometry_overlapping_source_shots')
    starts = [row['start'] for row in shots]
    groups = defaultdict(list)
    counts = Counter({key: 0 for key in ('input_spatial_sample_count', 'observations_with_valid_geometry',
        'unknown_identity_observation_count', 'unassigned_shot_observation_count',
        'source_scene_label_mismatch_count', 'floating_boundary_correction_count')})
    rejection_reasons = Counter()
    unresolved = []
    for input_index, row in enumerate(observations):
        time = row.get('observed_at', row.get('time'))
        if not _number(time) or time < 0:
            rejection_reasons['INVALID_OBSERVATION_TIMESTAMP'] += 1
            unresolved.append({'input_index': input_index, 'appearance_id': row.get('appearance_id'),
                               'reason': 'INVALID_OBSERVATION_TIMESTAMP'})
            continue
        position = bisect_right(starts, time)-1
        shot = shots[position] if position >= 0 and time < shots[position]['end'] else None
        if shot is None:
            counts['unassigned_shot_observation_count'] += 1
        elif row.get('scene_id') and shot.get('scene_id') and row['scene_id'] != shot['scene_id']:
            counts['source_scene_label_mismatch_count'] += 1
        person, track = row.get('person_id'), row.get('track_id')
        if not person:
            counts['unknown_identity_observation_count'] += 1
        # Never join anonymous tracks by raw online person ID or screen position.
        target = ('person', person) if person else ('track', track) if track else ('sample', input_index)
        valid = 0
        for field, label in (('face_bbox', 'face'), ('body_bbox', 'person')):
            raw_box = row.get(field)
            if raw_box is None:
                continue
            box = _bbox(raw_box)
            if box is None:
                rejection_reasons['INVALID_'+field.upper()] += 1
                continue
            if any(box[k] != raw_box[k] for k in ('x', 'y', 'width', 'height')):
                counts['floating_boundary_correction_count'] += 1
            confidence = row.get('confidence', row.get('detection_confidence'))
            confidence = float(confidence) if _number(confidence) else None
            # Missing shot or track prevents any temporal interpolation.
            scope = (shot.get('shot_id') or shot.get('scene_id')) if shot else None
            isolation = input_index if shot is None or not track else None
            key = (target, track, scope, label, isolation, position if shot else None)
            groups[key].append({'time': float(time), 'bbox': box, 'confidence': confidence,
                'features': _features(box, source_width, source_height), 'person_id': person, 'track_id': track,
                'identity_status': row.get('identity_status') or 'UNKNOWN',
                'scene_id': shot.get('scene_id') if shot else row.get('scene_id'),
                'appearance_id': row.get('appearance_id'),
                'source_observation_index': row.get('source_observation_index', input_index),
                'source_artifact': row.get('source_artifact')})
            valid += 1
        counts['input_spatial_sample_count'] += valid
        if valid:
            counts['observations_with_valid_geometry'] += 1
        else:
            rejection_reasons['OBSERVATION_WITHOUT_VALID_GEOMETRY'] += 1
            unresolved.append({'input_index': input_index, 'appearance_id': row.get('appearance_id'),
                               'source_time_s': time, 'reason': 'OBSERVATION_WITHOUT_VALID_GEOMETRY'})
    trajectories, gaps, measured_max = [], [], 0.
    for key in sorted(groups, key=repr):
        samples = sorted(groups[key], key=lambda row: row['time'])
        fragments, fragment, preceding_gap = [], [], None
        for sample in samples:
            if fragment and (sample['time']-fragment[-1]['time'] > max_gap_s or sample['time'] <= fragment[-1]['time']):
                gap = {'start': fragment[-1]['time'], 'end': sample['time'],
                       'reason': 'OBSERVATION_GAP_EXCEEDS_MAX_GAP' if sample['time'] > fragment[-1]['time'] else 'SIMULTANEOUS_GEOMETRY_CONFLICT',
                       'person_id': sample['person_id'], 'track_id': sample['track_id'],
                       'source_shot_id': key[2], 'class': key[3], 'interpolation_allowed': False}
                gaps.append(gap)
                fragments.append((fragment, preceding_gap))
                fragment, preceding_gap = [], gap
            fragment.append(sample)
        if fragment:
            fragments.append((fragment, preceding_gap))
        for fragment, gap in fragments:
            retained, measured = _simplify(fragment, float(max_error_px))
            measured_max = max(measured_max, measured)
            first, last = fragment[0], fragment[-1]
            ident = hashlib.sha256(json.dumps([key, first['time'], last['time'],
                first['source_observation_index'], last['source_observation_index']],
                sort_keys=True, separators=(',', ':')).encode('utf-8')).hexdigest()[:20]
            confidence_values = [row['confidence'] for row in fragment if row['confidence'] is not None]
            trajectories.append({'trajectory_id': 'TRAJECTORY_'+ident, 'person_id': first['person_id'],
                'track_id': first['track_id'], 'source_shot_id': key[2], 'scene_id': first['scene_id'],
                'source_shot_index': key[5],
                'class': key[3], 'bbox_kind': 'face' if key[3] == 'face' else 'body',
                'start': first['time'], 'end': last['time'],
                'keyframes': [{'source_time_s': fragment[i]['time'], 'bbox': fragment[i]['bbox'],
                    'confidence': fragment[i]['confidence'], 'appearance_id': fragment[i]['appearance_id'],
                    'source_observation_index': fragment[i]['source_observation_index']} for i in retained],
                'input_sample_count': len(fragment), 'max_measured_error_px': measured,
                'confidence_min': min(confidence_values) if confidence_values else None,
                'confidence_max': max(confidence_values) if confidence_values else None,
                'identity_status': first['identity_status'], 'identity_statuses': sorted({row['identity_status'] for row in fragment}),
                'nominal_identity_confirmed': False, 'occlusion_status': 'UNKNOWN',
                'evidence_scope': 'single_observed_sample' if len(fragment) == 1 else 'sampled_span_with_bounded_interpolation',
                'gaps': [gap] if gap else [],
                'fragmentation_policy': 'same_person_track_shot_and_class_only',
                'provenance': {'source_artifact': 'people/person_appearances.json',
                    'upstream_source_artifacts': sorted({row['source_artifact'] for row in fragment if row['source_artifact']}),
                    'identity_inferred_from_geometry': False},
                'preview_approved': False, 'publication_ready': False})
    trajectories.sort(key=lambda row: (row['start'], row['source_shot_id'] or '', row['trajectory_id']))
    retained_count = sum(len(row['keyframes']) for row in trajectories)
    return {'schema_version': 'r6.3', 'trajectories': trajectories, 'gaps': gaps,
        'unresolved_observations': unresolved,
        'statistics': {'input_observation_count': len(observations), **dict(counts),
            'trajectory_count': len(trajectories), 'retained_keyframe_count': retained_count,
            'removed_spatial_sample_count': counts['input_spatial_sample_count']-retained_count,
            'spatial_sample_reduction_fraction': (1.-retained_count/counts['input_spatial_sample_count']
                if counts['input_spatial_sample_count'] else 0.),
            'singleton_trajectory_count': sum(r['start'] == r['end'] for r in trajectories),
            'class_trajectory_counts': dict(Counter(r['class'] for r in trajectories)),
            'class_input_sample_counts': dict(Counter({label: sum(r['input_sample_count'] for r in trajectories if r['class'] == label)
                                                      for label in ('face', 'person')})),
            'track_id_count': len({row['track_id'] for row in trajectories if row['track_id']}),
            'persistent_person_id_count': len({row['person_id'] for row in trajectories if row['person_id']}),
            'rejection_reason_counts': dict(rejection_reasons), 'gap_count': len(gaps),
            'measured_max_error_px': measured_max, 'configured_max_error_px': float(max_error_px),
            'configured_max_gap_s': float(max_gap_s),
            'source_shot_count': len(shots), 'inference_executed': False,
            'all_spatial_samples_accounted_for': sum(r['input_sample_count'] for r in trajectories) == counts['input_spatial_sample_count']},
        'coordinate_contract': {'origin': 'top_left', 'bbox': 'normalized_source_xywh',
            'reference_width': source_width, 'reference_height': source_height,
            'source_aspect_ratio': source_width/source_height, 'timebase': 'absolute_source_seconds',
            'trajectory_end': 'last_observed_sample_inclusive_not_end_exclusive_coverage',
            'singleton_interval': 'start_equals_end_no_duration_inferred',
            'shot_intervals': 'start_inclusive_end_exclusive',
            'gap_intervals': 'between_observed_samples_no_interpolation',
            'interpolation': 'linear_bbox_in_source_time_within_same_person_track_shot_class',
            'error_norm': 'L_infinity_source_pixel_xywh_right_bottom_at_all_original_samples',
            'significant_extrema_preserved': True,
            'significant_extrema_policy': 'outside_endpoint_coordinate_envelope_by_more_than_configured_error',
            'floating_boundary_tolerance': 1e-6,
            'floating_boundary_policy': 'clip_only_sub_tolerance_width_height_excess',
            'confidence_semantics': 'upstream_score_not_calibrated_identity_probability'},
        'preview_approved': False, 'publication_ready': False}
