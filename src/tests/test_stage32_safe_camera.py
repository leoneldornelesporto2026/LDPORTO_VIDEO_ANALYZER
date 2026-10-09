"""Offline synthetic camera evidence; no real-video accuracy claims."""
from copy import deepcopy

import pytest

from director_fixtures import fixture, turn
from ldporto.camera_director import _prepare, build_camera_director
from ldporto.camera_geometry import contains
from ldporto.camera_motion import SmartZoomState
from ldporto.camera_preflight import preflight_target, preflight_split
from ldporto.director_config import resolve_config


def hook():
    return {'moment_id': 'M', 'start': 0, 'end': 10,
            'categories': ['hook'], 'hook_score': .9,
            'evidence_segment_ids': ['SYNTHETIC_SEG']}


@pytest.mark.parametrize('sharpness,expected_safe,cap', [(5, False, None), (None, True, 1.)])
def test_future_quality_is_checked(sharpness, expected_safe, cap):
    m, v, shots = fixture(8)
    v['observations'][2]['sharpness'] = sharpness
    cfg = resolve_config({'output_width': 540, 'output_height': 960})
    records = _prepare(m, v, shots, [turn(0, 8)], cfg)
    result = preflight_target('PERSON_A', 0, records, m, cfg, horizon=1, zoom=1.2)
    assert result['safe'] is expected_safe
    if cap is not None:
        assert result['max_zoom'] == cap and result['zoom'] == 1.
    else:
        assert result['preflight_reason'] == 'unsafe_face_in_lookahead'


def test_reused_future_frame_is_not_multiple_samples():
    m, v, shots = fixture(8)
    cfg = resolve_config(None)
    records = _prepare(m, v, shots, [turn(0, 8)], cfg)
    for row in records[2:5]:
        row['frame'] = deepcopy(records[1]['frame'])
        row['obs'] = deepcopy(records[1]['obs'])
    result = preflight_target('PERSON_A', 0, records, m, cfg, horizon=.9)
    assert result['preflight_sample_count'] == 2


@pytest.mark.parametrize('lost', [True, False])
def test_split_requires_two_distinct_visible_faces(lost):
    m, v, shots = fixture(8, pair=True, distant=True)
    cfg = resolve_config({'output_width': 540, 'output_height': 960})
    records = _prepare(m, v, shots, [turn(0, 8)], cfg)
    if lost:
        del records[2]['obs']['PERSON_B']
    result = preflight_split(('PERSON_A', 'PERSON_B'), 0, records, m, cfg)
    assert result['safe'] is (not lost)
    if not lost:
        for side in ('left', 'right'):
            assert contains(result[side+'_crop'], result['subject_bounds'][result[side+'_person']])
            crop = result[side+'_crop']
            assert crop['width']/crop['height'] == pytest.approx((270/960)/(3840/2160))
    assert not preflight_split(('PERSON_A', 'PERSON_A'), 0, records, m, cfg)['safe']


def test_fixed_split_anchor_must_contain_future_path():
    m, v, shots = fixture(18, pair=True, distant=True)
    for obs in v['observations']:
        if obs['person_id'] == 'PERSON_A' and obs['time'] >= 10:
            obs['face_bbox']['x'] += .065
    turns = [turn(i, i+1, person='PERSON_A' if i % 2 == 0 else 'PERSON_B') for i in range(18)]
    cfg = resolve_config({'output_width': 540, 'output_height': 960})
    data = build_camera_director(m, v, shots, turns, [], cfg)['data']
    records = _prepare(m, v, shots, turns, cfg)
    splits = [row for row in data['timeline'] if row['split']]
    assert splits
    for row in splits:
        for i, record in enumerate(records):
            if row['start'] <= record['start'] < row['end']:
                verified = preflight_split(('PERSON_A', 'PERSON_B'), i, records, m, cfg)
                assert verified['safe']
                for side in ('left', 'right'):
                    pid = row['split'][side+'_person']
                    assert contains(row['split'][side+'_crop'], verified['subject_bounds'][pid])


def test_face_leaving_scene_cancels_executable_crop_before_loss():
    m, v, shots = fixture(18)
    v['observations'] = [o for o in v['observations'] if o['time'] < 8]
    data = build_camera_director(m, v, shots, [turn(0, 18)], [],
                                {'output_width': 540, 'output_height': 960}, main_moments=[hook()])['data']
    assert any(row['focus_person'] for row in data['timeline'])
    assert all(row['layout'] == 'full_frame' or row['crop']['safe'] for row in data['timeline'])
    assert all(row['focus_person'] is None for row in data['timeline'] if row['start'] >= 8)
    assert any('CROP_PREFLIGHT_UNSAFE' in row['decision']['reasons'] for row in data['timeline'])


@pytest.mark.parametrize('kind,state', [('medium', 'UNCERTAIN'), ('close_up', 'CONFIRMED')])
def test_uncertain_focus_and_source_close_never_zoom(kind, state):
    m, v, shots = fixture(18, kind=kind)
    active = [{**turn(0, 18), 'active_speaker_state': state,
               'active_person': 'PERSON_A' if state == 'CONFIRMED' else None}]
    data = build_camera_director(m, v, shots, active, [], main_moments=[hook()])['data']
    metrics = data['metrics']
    assert metrics['zoom_raw_opportunity_window_count'] > 0
    assert sum(metrics['zoom_opportunity_outcome_counts'].values()) == metrics['zoom_raw_opportunity_window_count']
    assert metrics['zoom_accepted_event_count'] == metrics['zoom_delivered_event_count'] == 0
    assert metrics['max_zoom_factor'] == 1.


def test_requests_acceptances_and_deliveries_are_separate_and_speed_limited():
    m, v, shots = fixture(30)
    data = build_camera_director(m, v, shots, [turn(0, 30)], [],
                                {'output_width': 540, 'output_height': 960}, main_moments=[hook()])['data']
    metrics = data['metrics']
    assert metrics['zoom_request_window_count'] >= metrics['zoom_accepted_window_count'] > 0
    assert metrics['zoom_delivered_event_count'] > 0
    assert sum(metrics['zoom_opportunity_outcome_counts'].values()) == metrics['zoom_raw_opportunity_window_count']
    assert metrics['zoom_accepted_event_count'] == (metrics['zoom_accepted_push_in_event_count'] +
                                                  metrics['zoom_accepted_pull_out_event_count'])
    for row in data['timeline']:
        for a, b in zip(row['camera']['keyframes'], row['camera']['keyframes'][1:]):
            assert abs(b['zoom']-a['zoom']) <= .035*(b['time']-a['time']) + 1e-9


def test_unsafe_requested_crop_and_hold_are_counted_without_acceptance():
    state = SmartZoomState()
    cfg = resolve_config(None)['smart_zoom']
    args = dict(target='PERSON_A', confidence=.95, safe=True, zoom_cap=1.2,
                face_size=.17, source_close=False, source_motion=0, speech_seconds=3,
                remaining_seconds=30, micro_interruption=False, cfg=cfg)
    beat = {'id': 'A', 'reason': 'HOOK_EMPHASIS'}
    result = state.decide(0, **{**args, 'safe': False}, beat=beat)
    assert result['zoom_attempted'] and not result['new_zoom_request']
    accepted = state.decide(1, **args, beat=beat)
    assert accepted['new_zoom_request']
    held = state.decide(2, **args, beat={'id': 'B', 'reason': 'HOOK_EMPHASIS'})
    assert held['zoom_attempted'] and not held['new_zoom_request']
    assert 'MINIMUM_ZOOM_DWELL' in held['reason_codes']
    switched = state.decide(3, **{**args, 'target': 'PERSON_B'},
                            beat={'id': 'C', 'reason': 'HOOK_EMPHASIS'})
    assert not switched['new_zoom_request']
    assert 'MINIMUM_ZOOM_DWELL' in switched['reason_codes']
    state.reset_shot(4)
    cut = state.decide(4, **args, beat={'id': 'D', 'reason': 'HOOK_EMPHASIS'})
    assert not cut['new_zoom_request']
    assert len(state.events) == 1
