from copy import deepcopy

import pytest

from ldporto.camera_motion import SmartZoomState, ease_in_out
from ldporto.director_config import resolve_smart_zoom


def decision(state, time=2., **changes):
    options = {'target': 'P1', 'confidence': .95, 'safe': True, 'zoom_cap': 1.3,
               'face_size': .2, 'source_close': False, 'source_motion': 0.,
               'speech_seconds': 10., 'remaining_seconds': 40., 'beat': None,
               'micro_interruption': False, 'cfg': resolve_smart_zoom()}
    options.update(changes)
    return state.decide(time, **options)


def test_zoom_easing_is_deterministic_smooth_and_bounded():
    assert ease_in_out(0) == 0 and ease_in_out(1) == 1
    assert ease_in_out(.5) == .5
    assert ease_in_out(.1) < .1 and ease_in_out(.9) > .9


def test_no_smart_zoom_without_grounded_editorial_beat():
    state = SmartZoomState()
    for time in range(50):
        assert decision(state, time)['zoom'] == 1
    assert not state.events


@pytest.mark.parametrize('changes,reason', [
    ({'confidence': .2}, 'INSUFFICIENT_CONFIDENCE'),
    ({'safe': False}, 'CROP_UNSAFE'),
    ({'source_close': True}, 'SOURCE_ALREADY_CLOSE'),
    ({'source_motion': .2}, 'SOURCE_CAMERA_MOVING'),
    ({'remaining_seconds': 2}, 'INSUFFICIENT_ZOOM_DURATION'),
    ({'micro_interruption': True}, 'MICRO_INTERRUPTION_SUPPRESSED'),
])
def test_smart_zoom_safety_rejects_invalid_beat_context(changes, reason):
    state = SmartZoomState()
    row = decision(state, beat={'id': 'HOOK_1', 'reason': 'HOOK_EMPHASIS'}, **changes)
    assert not state.events and row['zoom'] == 1
    assert reason in row['reason_codes']


def test_grounded_hook_starts_gradual_zoom_and_does_not_repeat_per_frame():
    state = SmartZoomState()
    beat = {'id': 'HOOK_1', 'reason': 'HOOK_EMPHASIS'}
    first = decision(state, 2, beat=beat)
    assert first['zoom'] == 1
    later = decision(state, 5, beat=beat)
    assert 1 < later['zoom'] < 1.2
    assert len(state.events) == 1
    assert state.events[0]['end'] - state.events[0]['start'] >= 6


@pytest.mark.parametrize('profile', ['conservative', 'natural', 'dynamic'])
def test_explicit_smart_zoom_profiles_remain_safety_bounded(profile):
    cfg = resolve_smart_zoom({'profile': profile})
    assert 1 <= cfg['max_zoom_factor'] <= 1.4
    assert cfg['min_hold_duration'] >= 5


def test_zoom_rate_and_dwell_do_not_pump_between_beats():
    state = SmartZoomState()
    cfg = resolve_smart_zoom({'max_zoom_events_per_minute': 1})
    decision(state, 2, beat={'id': 'HOOK_1', 'reason': 'HOOK_EMPHASIS'}, cfg=cfg)
    row = decision(state, 5, beat={'id': 'HOOK_2', 'reason': 'PAYOFF_EMPHASIS'}, cfg=cfg)
    assert 'ZOOM_RATE_LIMIT' in row['reason_codes']
    assert len(state.events) == 1


def test_camera_director_delivers_real_gradual_hook_zoom_with_grounded_target():
    from director_fixtures import fixture, turn
    from ldporto.camera_director import build_camera_director
    metadata, vision, shots = fixture(30)
    moment = {'moment_id': 'M1', 'start': 0, 'end': 8, 'evidence_segment_ids': ['SEG_1'],
              'categories': ['hook'], 'editorial': {'hook_strength': .9}, 'hook_score': .9}
    result = build_camera_director(metadata, vision, shots, [turn(0, 30)], [],
                                  {'output_width': 540, 'output_height': 960}, main_moments=[moment])['data']
    assert result['metrics']['zoom_event_count'] > 0
    assert result['metrics']['zoom_opportunity_window_count'] > 0
    assert result['metrics']['zoom_accepted_event_count'] > 0
    assert result['metrics']['zoom_delivered_event_count'] == result['metrics']['zoom_event_count']
    assert result['metrics']['zoom_diagnostics_contract'] == 'opportunity_request_accepted_delivered_aborted_v1'
    assert result['metrics']['max_zoom_factor'] > 1
    assert any(row['camera_mode'] == 'SMART_ZOOM_IN' for row in result['timeline'])
    assert all(row['crop']['upscale_ratio'] <= row['crop']['max_upscale_ratio'] + 1e-6 for row in result['timeline'] if row['crop']['safe'])


def test_director_source_close_up_does_not_receive_decorative_zoom():
    from director_fixtures import fixture, turn
    from ldporto.camera_director import build_camera_director
    metadata, vision, shots = fixture(30, kind='close_up')
    moment = {'moment_id': 'M1', 'start': 0, 'end': 8, 'evidence_segment_ids': ['SEG_1'], 'categories': ['hook'], 'hook_score': .9}
    result = build_camera_director(metadata, vision, shots, [turn(0, 30)], [], main_moments=[moment])['data']
    assert result['metrics']['zoom_event_count'] == 0
    assert result['metrics']['zoom_opportunity_window_count'] > 0
    assert result['metrics']['zoom_accepted_event_count'] == 0
    assert result['metrics']['zoom_block_reason_counts'].get('SOURCE_ALREADY_CLOSE', 0) > 0
    assert all(key['zoom'] == 1 for row in result['timeline'] for key in row['camera']['keyframes'])


def test_preview_zoom_diagnostics_detect_short_events_and_pumping():
    from ldporto.preview_verifier import zoom_diagnostics
    timeline = [{'start': index, 'end': index + 1, 'camera_mode': 'SMART_ZOOM_IN' if index % 2 == 0 else 'SMART_ZOOM_OUT',
                 'camera': {'keyframes': [{'time': index, 'zoom': zoom}, {'time': index + 1, 'zoom': next_zoom}]}}
                for index, (zoom, next_zoom) in enumerate(zip([1, 1.25, 1, 1.3], [1.25, 1, 1.3, 1]))]
    metrics, issues = zoom_diagnostics(timeline, 4)
    assert metrics['short_zoom_count'] == 4
    assert metrics['rapid_zoom_reversal_count'] > 0
    assert {issue['issue_type'] for issue in issues} >= {'SHORT_ZOOM', 'ZOOM_PUMPING'}


def test_preview_zoom_repair_is_targeted_and_source_preserving():
    from ldporto.preview_verifier import conservative_repair
    timeline = [{'director_id': 'D1', 'start': 0, 'end': 8, 'layout': 'single_person', 'focus_person': 'P1',
                 'camera': {'zoom_end': 1.3, 'keyframes': [{'time': 0, 'zoom': 1.3}]}},
                {'director_id': 'D2', 'start': 8, 'end': 20, 'layout': 'single_person', 'focus_person': 'P1'}]
    validation = {'issues': [{'issue_type': 'ZOOM_PUMPING', 'severity': 'warning', 'interval': [0, 8]}]}
    repaired, ids = conservative_repair(timeline, validation)
    assert ids == ['D1'] and repaired[0]['camera_mode'] == 'SOURCE_PRESERVE'
    assert repaired[0]['camera']['zoom_end'] == 1
    assert repaired[1]['layout'] == 'single_person'
    assert timeline[0]['camera']['zoom_end'] == 1.3