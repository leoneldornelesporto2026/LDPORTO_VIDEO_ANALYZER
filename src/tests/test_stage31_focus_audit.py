"""Offline synthetic evidence: no identity or quality claims about real people."""
import json
import pytest

from director_fixtures import fixture, turn
from ldporto.camera_director import build_camera_director
from ldporto.global_camera_planner import build_global_camera_plan
from ldporto.director_integration import attach_director, PLANNER_CODE


def direct(data, voices, **cfg):
    m, v, shots = data
    return build_camera_director(m, v, shots, voices, [], cfg)['data']


@pytest.mark.parametrize('state', ['PROBABLE', 'UNCERTAIN', 'OFFSCREEN', 'UNKNOWN', 'MULTIPLE_SPEAKERS'])
def test_explicit_unconfirmed_state_never_becomes_speaker_focus(state):
    result = direct(fixture(8), [dict(turn(0, 8), active_person='PERSON_A', active_speaker_state=state)],
                    dominant_face_fallback=False)
    assert not any(r['focus_person'] for r in result['timeline'])
    assert result['metrics']['focus_decision_audit']['duration_seconds']['NO_CONFIRMED_ACTIVE_SPEAKER'] == 8


def test_downgrade_exits_incumbent_and_does_not_keep_confirmed_label():
    voices = [dict(turn(0, 4), active_person='PERSON_A', active_speaker_state='CONFIRMED'),
              dict(turn(4, 8), active_person=None, active_speaker_state='PROBABLE')]
    result = direct(fixture(8), voices, dominant_face_fallback=False)
    assert any(r['focus_person'] for r in result['timeline'] if r['start'] < 4)
    assert all(r['focus_person'] is None for r in result['timeline'] if r['start'] >= 4)


def test_contradiction_cannot_be_resolved_by_dominant_face_or_hold():
    voices = [turn(0, 4), dict(turn(4, 8), active_person='PERSON_B', active_speaker_state='CONFIRMED')]
    result = direct(fixture(8), voices, dominant_face_fallback=True)
    blocked = [w for w in result['focus_window_audit'] if w['start'] >= 4]
    assert blocked and all(w['focus_person'] is None for w in blocked)
    assert all(w['reason_code'] == 'CONTRADICTORY_TARGET_EVIDENCE' for w in blocked)


@pytest.mark.parametrize('mode,expected', [
    ('no_face', 'NO_VISIBLE_FACE'), ('no_frame', 'NO_CONTEMPORARY_VISUAL_SAMPLE'),
    ('close', 'SAFE_ORIGINAL_CLOSEUP_PRESERVED'), ('unknown', 'NO_CONFIRMED_ACTIVE_SPEAKER')])
def test_source_preserve_causes_remain_distinct(mode, expected):
    data = fixture(8, kind='close_up' if mode == 'close' else 'medium')
    if mode == 'no_face':
        for obs in data[1]['observations']:
            obs.update(face_visible=False, face_bbox=None)
    if mode == 'no_frame':
        data[1]['frames'] = []
    result = direct(data, [dict(turn(0, 8), active_person=None, active_speaker_state='PROBABLE')],
                    dominant_face_fallback=False)
    audit = result['focus_window_audit']
    assert all(w['reason_code'] == expected and w['focus_person'] is None for w in audit)
    assert sum(w['coverage_effect']['source_preserve_seconds'] for w in audit) == 8


def test_visual_fallback_reports_coverage_without_promoting_global_identity():
    result = direct(fixture(12), [dict(turn(0, 12), active_person=None, active_speaker_state='PROBABLE')],
                    dominant_face_fallback=True)
    audit = result['focus_window_audit']
    visual = [w for w in audit if w['reason_code'] == 'VISUAL_ONLY_FALLBACK']
    assert visual and all(w['evidence']['confirmed_local_people'] == [] for w in visual)
    assert all(not r['speaker_identity_confirmed'] for r in result['timeline'])
    assert sum(w['end']-w['start'] for w in audit) == 12
    assert len(audit) == result['metrics']['director_evaluation_windows']
    assert sum(w['coverage_effect']['resolved_focus_seconds'] for w in audit)/12 == pytest.approx(
        result['metrics']['camera_director_coverage'])
    attached = attach_director({'metadata': {'duration': 12}}, result)
    assert attached['camera_director_focus_window_audit'] == audit
    json.dumps(attached, allow_nan=False)


@pytest.mark.parametrize('voices', [[], [dict(turn(0, 8), active_person=None, active_speaker_state='PROBABLE')],
                                   [dict(turn(0, 8), active_person='PERSON_B', active_speaker_state='CONFIRMED')]])
def test_global_planner_cannot_trust_stale_timeline_active_person(voices):
    m, v, shots = fixture(8)
    timeline = [{'start': 0, 'end': 8, 'shot_id': 'SHOT_0', 'active_person': 'PERSON_A',
                 'active_person_confidence': .99}]
    result = build_global_camera_plan(m, v, shots, timeline, active_speaker=voices)['data']
    assert all(r['focus_person'] is None for r in result['selected_global_path'])
    assert result['rejected_candidates'][0]['reason'] == 'no_confirmed_local_active_speaker'
    assert 'camera_evidence.py' in PLANNER_CODE


def test_local_confirmation_keeps_existing_focus_available():
    m, v, shots = fixture(8)
    timeline = [{'start': 0, 'end': 8, 'shot_id': 'SHOT_0', 'active_person': 'PERSON_A',
                 'active_person_confidence': .99}]
    voices = [dict(turn(0, 8), active_person='PERSON_A', active_speaker_state='CONFIRMED')]
    plan = build_global_camera_plan(m, v, shots, timeline, active_speaker=voices)['data']
    assert plan['selected_global_path'][0]['focus_person'] == 'PERSON_A'
    result = direct((m, v, shots), voices)
    assert any(w['reason_code'] == 'LOCAL_SPEAKER_FOCUS' for w in result['focus_window_audit'])


@pytest.mark.parametrize('wrong_track', [False, True])
def test_reaction_requires_motion_of_contemporary_listener_track(wrong_track):
    m, v, shots = fixture(25, pair=True)
    samples = [{'time': i/4, 'movement_intensity': .9 if 8 <= i/4 <= 8.5 else 0,
                'track_id': 'OTHER_TRACK' if wrong_track else 'PERSON_B_SHOT_0', 'scene_id': 'SCENE_0'}
               for i in range(100)]
    motion = [{'person_id': 'PERSON_B', 'samples': samples}]
    result = build_camera_director(m, v, shots, [turn(0, 25)], motion)['data']
    reactions = [w for w in result['focus_window_audit'] if w['reason_code'] == 'LOCAL_VISUAL_REACTION']
    assert bool(reactions) is not wrong_track
    assert all(w['focus_person'] == 'PERSON_B' for w in reactions)
    assert all(not r['speaker_identity_confirmed'] for r in result['timeline'] if r.get('reaction'))
