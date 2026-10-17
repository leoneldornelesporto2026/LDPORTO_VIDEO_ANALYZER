"""Focused synthetic camera regressions; no real-video accuracy claims."""
from copy import deepcopy

from director_fixtures import fixture
from ldporto.camera_director import build_camera_director, replan_camera_from_snapshot
from ldporto.camera_evidence import VisualTargetEvidence
from ldporto.camera_motion import SmartZoomState
from ldporto.director_config import resolve_config


def test_confidence_dip_retains_history_but_does_not_qualify_weak_current_face():
    _, vision, _ = fixture(6)
    evidence, cfg = VisualTargetEvidence(), resolve_config(None)
    for obs in vision['observations'][:13]:
        assert evidence.update({'PERSON_A': obs}, obs['time'], 'SHOT_0', cfg) is not None or obs['time'] < 2
    weak = deepcopy(vision['observations'][13])
    weak['detection_confidence'] = .83
    assert evidence.update({'PERSON_A': weak}, weak['time'], 'SHOT_0', cfg) is None
    assert not evidence.diagnostics['PERSON_A']['target_stable']
    recovered = vision['observations'][14]
    assert evidence.update({'PERSON_A': recovered}, recovered['time'], 'SHOT_0', cfg)
    assert evidence.tracks['PERSON_A']['first'] == 0
    assert cfg['minimum_target_confidence'] == .85


def test_velocity_outlier_expires_and_history_never_crosses_track_or_source_cut():
    _, vision, _ = fixture(9)
    evidence, cfg = VisualTargetEvidence(), resolve_config(None)
    for obs in vision['observations']:
        sample = deepcopy(obs)
        if sample['time'] == 3:
            sample['face_bbox']['x'] += .10
        evidence.update({'PERSON_A': sample}, sample['time'], 'SHOT_0', cfg)
        if sample['time'] == 3:
            assert not evidence.diagnostics['PERSON_A']['target_stable']
        if sample['time'] == 6:
            assert evidence.diagnostics['PERSON_A']['target_stable']
    sample['track_id'] = 'ANOTHER_TRACK'
    assert evidence.update({'PERSON_A': sample}, 9, 'SHOT_0', cfg) is None
    sample['time'] = 9.25
    assert evidence.update({'PERSON_A': sample}, 9.25, 'SHOT_1', cfg) is None
    assert evidence.tracks['PERSON_A']['first'] == 9.25


def test_safe_visual_closeup_has_baseline_focus_without_claiming_speaker_or_instrument():
    metadata, vision, shots = fixture(10, kind='close_up')
    data = build_camera_director(metadata, vision, shots, [], [],
                                 {'dominant_face_fallback': True})['data']
    focused = [row for row in data['timeline'] if row['focus_person']]
    assert focused
    assert all(not row['speaker_identity_confirmed'] for row in focused)
    assert all(key['zoom'] == 1 for row in focused for key in row['camera']['keyframes'])
    state = next(window['target_states']['PERSON_A'] for window in data['focus_window_audit']
                 if window['focus_person'])
    assert state['target_seen'] and state['target_stable'] and state['crop_safe']
    assert not state['speaker_linked'] and not state['identity_confirmed']
    assert state['instrument_linked'] is None
    assert data['metrics']['independent_target_evidence']['identity_accuracy_measured'] is False


def test_snapshot_replay_projects_existing_ids_without_mutation_and_keeps_absolute_time():
    metadata, vision, shots = fixture(7)
    for frame in vision['frames']:
        frame['visible_people'] = ['UPSTREAM_ONLINE_ID']
    snapshot = {'metadata': metadata, 'frame_samples': vision['frames'],
                'people_observations': vision['observations'], 'shots': shots,
                'camera_director_config': {'dominant_face_fallback': True}}
    before = deepcopy(snapshot)
    data = replan_camera_from_snapshot(snapshot)['data']
    assert snapshot == before
    assert any(row['focus_person'] == 'PERSON_A' for row in data['timeline'])
    assert data['timeline'][0]['start'] == 0 and data['timeline'][-1]['end'] == 7
    assert data['snapshot_replay']['inference_executed'] is False
    assert data['snapshot_replay']['timestamp_basis'] == 'absolute_source_seconds'
    assert data['metrics']['zoom_delivered_event_count'] == 0


def test_visual_zoom_provenance_never_claims_active_speaker():
    state = SmartZoomState()
    result = state.decide(0, target='ANONYMOUS', confidence=.95, safe=True, zoom_cap=1.2,
        face_size=.17, source_close=False, source_motion=0, speech_seconds=3,
        remaining_seconds=30, micro_interruption=False, cfg=resolve_config(None)['smart_zoom'],
        beat={'id': 'SYNTHETIC', 'reason': 'HOOK_EMPHASIS'}, target_evidence_role='DOMINANT_FACE')
    assert result['new_zoom_request']
    assert state.events[0]['target_evidence_role'] == 'DOMINANT_FACE'
    assert 'VISUAL_TARGET_FOCUS' in state.events[0]['reason_codes']
    assert 'ACTIVE_SPEAKER_FOCUS' not in state.events[0]['reason_codes']


def visual_zoom_fixture():
    metadata, vision, shots = fixture(15)
    for obs in vision['observations']:
        if obs['time'] >= 4:
            obs['face_bbox']['x'] += .04
    moment = {'moment_id': 'SYNTHETIC', 'start': 0., 'end': 10., 'categories': ['hook'],
              'hook_score': .9, 'evidence_segment_ids': ['SYNTHETIC_SEGMENT']}
    planner = {'selected_global_path': [{'start': 0., 'end': 15., 'layout': 'full_frame',
                                        'focus_person': None, 'planner_id': 'SYNTHETIC_SOURCE'}]}
    return metadata, vision, shots, moment, planner


def test_observed_visual_incumbent_keeps_safe_zoom_when_dominance_temporarily_unstable():
    metadata, vision, shots, moment, planner = visual_zoom_fixture()
    data = build_camera_director(metadata, vision, shots, [], [],
        {'dominant_face_fallback': True}, main_moments=[moment], camera_plan=planner)['data']
    assert data['zoom_events']
    assert all(window['focus_person'] == 'PERSON_A' for window in data['focus_window_audit']
               if 3.25 <= window['start'] <= 9)
    assert max(key['zoom'] for row in data['timeline'] for key in row['camera']['keyframes']) > 1.02
    assert data['metrics']['zoom_delivered_event_count'] == 0
    assert all(event['target_evidence_role'] == 'DOMINANT_FACE' for event in data['zoom_events']
               if event['mode'] == 'SMART_ZOOM_IN')


def test_zoom_rejected_before_acceptance_when_full_transition_loses_face():
    metadata, vision, shots, moment, planner = visual_zoom_fixture()
    for obs in vision['observations']:
        if obs['time'] >= 7:
            obs.update(face_visible=False, face_bbox=None)
    data = build_camera_director(metadata, vision, shots, [], [],
        {'dominant_face_fallback': True}, main_moments=[moment], camera_plan=planner)['data']
    assert any(row['focus_person'] for row in data['timeline'])
    assert data['zoom_events'] == []
    assert data['metrics']['zoom_full_transition_preflight_rejected_windows'] > 0
