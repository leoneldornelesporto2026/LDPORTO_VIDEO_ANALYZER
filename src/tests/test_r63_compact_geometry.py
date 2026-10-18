"""Pure geometry regressions on synthetic observations, never model outputs."""
from copy import deepcopy
import json
import math

import pytest

from ldporto.compact_geometry import simplify_visual_trajectories


SHOTS = [{'shot_id': 'SHOT_A', 'scene_id': 'SCENE_A', 'start': 0., 'end': 10.}]


def observation(time, x=.25, *, track='TRACK_A', person='PERSON_A', **changes):
    return {'appearance_id': 'SYNTHETIC_'+str(time)+'_'+track, 'observed_at': time,
            'track_id': track, 'person_id': person, 'raw_person_id': 'RAW_NOT_IDENTITY',
            'scene_id': 'SCENE_A', 'face_bbox': {'x': x, 'y': .2, 'width': .08, 'height': .15},
            'face_visible': True, 'body_visible': False, 'confidence': .91,
            'identity_status': 'UNKNOWN_PERSON' if person is None else 'ANONYMOUS_PERSON',
            'source_artifact': 'synthetic_fixture.json', **changes}


def simplify(rows, **changes):
    return simplify_visual_trajectories(rows, changes.pop('shots', SHOTS), source_width=1920,
        source_height=1080, **changes)


def test_static_repeated_geometry_compacts_to_observed_endpoints_without_identity_inference():
    rows = [observation(i/10) for i in range(80)]
    before = deepcopy(rows)
    result = simplify(rows)
    assert rows == before and len(result['trajectories']) == 1
    trajectory = result['trajectories'][0]
    assert [key['source_time_s'] for key in trajectory['keyframes']] == [0., 7.9]
    assert trajectory['input_sample_count'] == 80 and trajectory['max_measured_error_px'] == 0
    assert trajectory['nominal_identity_confirmed'] is False
    assert result['statistics']['all_spatial_samples_accounted_for'] is True
    assert result['preview_approved'] is False and result['publication_ready'] is False


def test_uneven_sample_times_preserve_motion_that_spatial_rdp_would_remove():
    result = simplify([observation(0, .1), observation(.1, .2), observation(1, .3)])
    assert len(result['trajectories'][0]['keyframes']) == 3
    assert result['statistics']['measured_max_error_px'] <= 2


def test_rapid_position_excursion_and_global_extrema_are_preserved():
    rows = [observation(i/10, .2 + (.015 if i == 5 else .00001*i)) for i in range(11)]
    result = simplify(rows)
    keys = result['trajectories'][0]['keyframes']
    assert .5 in [key['source_time_s'] for key in keys]
    assert min(key['bbox']['x'] for key in keys) == min(row['face_bbox']['x'] for row in rows)
    assert max(key['bbox']['x'] for key in keys) == max(row['face_bbox']['x'] for row in rows)


def test_configurable_error_is_measured_against_every_original_sample():
    rows = [observation(i/10, .3+.001*math.sin(i*.8)) for i in range(70)]
    fine, coarse = simplify(rows, max_error_px=.1), simplify(rows, max_error_px=4.)
    assert fine['statistics']['retained_keyframe_count'] >= coarse['statistics']['retained_keyframe_count']
    for result, maximum in [(fine, .1), (coarse, 4.)]:
        assert result['statistics']['measured_max_error_px'] <= maximum
        assert result['statistics']['configured_max_error_px'] == maximum


def test_same_person_and_track_are_split_at_source_cut_with_end_exclusive_shots():
    shots = [{'shot_id': 'SHOT_A', 'start': 0., 'end': 5.}, {'shot_id': 'SHOT_B', 'start': 5., 'end': 10.}]
    result = simplify([observation(4.5), observation(5.), observation(5.25)], shots=shots)
    assert [(row['source_shot_id'], row['start'], row['end']) for row in result['trajectories']] == [
        ('SHOT_A', 4.5, 4.5), ('SHOT_B', 5., 5.25)]


def test_missing_or_repeated_shot_labels_never_merge_across_actual_cut():
    for label in (None, 'REPEATED_UPSTREAM_LABEL'):
        shots = [{'shot_id': label, 'start': 0., 'end': 5.}, {'shot_id': label, 'start': 5., 'end': 10.}]
        result = simplify([observation(4.75), observation(5.), observation(5.25)], shots=shots)
        assert len(result['trajectories']) == 2
        assert {row['source_shot_index'] for row in result['trajectories']} == {0, 1}


def test_tracking_gap_splits_interpolation_and_retains_explicit_gap():
    result = simplify([observation(0.), observation(.5), observation(2.), observation(2.5)], max_gap_s=1.)
    assert len(result['trajectories']) == 2
    assert result['gaps'][0]['start'] == .5 and result['gaps'][0]['end'] == 2.
    assert result['gaps'][0]['interpolation_allowed'] is False
    assert result['trajectories'][1]['gaps'] == result['gaps']


def test_anonymous_tracks_and_fragmented_persistent_tracks_are_never_merged():
    rows = [observation(0., track='T1', person=None), observation(.2, track='T2', person=None),
            observation(.5, track='T3'), observation(.7, track='T4')]
    result = simplify(rows)
    assert len(result['trajectories']) == 4
    assert result['statistics']['unknown_identity_observation_count'] == 2
    assert {row['track_id'] for row in result['trajectories']} == {'T1', 'T2', 'T3', 'T4'}


def test_face_and_body_geometry_remain_independent_of_camera_decision():
    rows = [observation(i/4, body_bbox={'x': .2, 'y': .1, 'width': .25, 'height': .75},
                        body_visible=True, camera_mode='SOURCE_FIT_BLUR') for i in range(9)]
    result = simplify(rows)
    assert {row['class'] for row in result['trajectories']} == {'face', 'person'}
    assert result['statistics']['input_observation_count'] == 9
    assert result['statistics']['input_spatial_sample_count'] == 18
    assert sum(row['input_sample_count'] for row in result['trajectories']) == 18


def test_singletons_and_missing_shots_do_not_invent_continuous_visibility():
    result = simplify([observation(2.), observation(2.1)], shots=[])
    assert len(result['trajectories']) == 2
    assert all(row['start'] == row['end'] and row['source_shot_id'] is None for row in result['trajectories'])
    assert result['statistics']['unassigned_shot_observation_count'] == 2
    assert result['coordinate_contract']['singleton_interval'] == 'start_equals_end_no_duration_inferred'


def test_invalid_geometry_and_times_are_accounted_for_instead_of_fabricated():
    result = simplify([observation(0.), observation(math.nan),
                       observation(1., face_bbox={'x': .99, 'y': .2, 'width': .4, 'height': .2})])
    assert result['statistics']['input_observation_count'] == 3
    assert result['statistics']['observations_with_valid_geometry'] == 1
    assert len(result['unresolved_observations']) == 2
    assert result['statistics']['rejection_reason_counts']['INVALID_FACE_BBOX'] == 1
    json.dumps(result, allow_nan=False)


def test_simultaneous_conflicting_boxes_are_separate_and_flagged():
    result = simplify([observation(0.), observation(.2), observation(.2, .5), observation(.4)])
    assert len(result['trajectories']) == 2
    assert result['gaps'][0]['reason'] == 'SIMULTANEOUS_GEOMETRY_CONFLICT'
    assert result['statistics']['all_spatial_samples_accounted_for']


def test_right_and_bottom_edges_have_the_same_error_bound_as_xywh():
    rows = [observation(i/8, .2+.0005*math.sin(i)) for i in range(49)]
    for index, row in enumerate(rows):
        row['face_bbox']['width'] += .0005*math.cos(index*.7)
    result = simplify(rows, max_error_px=1.)
    trajectory = result['trajectories'][0]
    keys = trajectory['keyframes']
    largest = 0.
    for row in rows:
        time = row['observed_at']
        first, last = next((a, b) for a, b in zip(keys, keys[1:]) if a['source_time_s'] <= time <= b['source_time_s'])
        fraction = (time-first['source_time_s'])/(last['source_time_s']-first['source_time_s'])
        reconstructed = {key: first['bbox'][key]+fraction*(last['bbox'][key]-first['bbox'][key])
                         for key in ('x', 'y', 'width', 'height')}
        actual = row['face_bbox']
        error = max(abs((actual['x']+actual['width'])-(reconstructed['x']+reconstructed['width']))*1920,
                    abs((actual['y']+actual['height'])-(reconstructed['y']+reconstructed['height']))*1080)
        largest = max(largest, error)
    assert largest <= 1. + 1e-9


@pytest.mark.parametrize('values', [dict(max_error_px=-1), dict(max_error_px=math.nan), dict(max_gap_s=0)])
def test_invalid_configuration_is_rejected(values):
    with pytest.raises(ValueError):
        simplify([observation(0.)], **values)


def test_overlapping_source_shots_are_rejected_instead_of_choosing_a_cut_silently():
    with pytest.raises(ValueError, match='overlapping_source_shots'):
        simplify([observation(1.)], shots=[{'start': 0., 'end': 3.}, {'start': 2., 'end': 4.}])
