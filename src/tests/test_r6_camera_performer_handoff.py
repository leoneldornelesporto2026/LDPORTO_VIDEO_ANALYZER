"""Focused synthetic contracts; no model, source-media or identity accuracy claims."""
from copy import deepcopy
import json
from pathlib import Path

import jsonschema

from ldporto.camera_handoff import build_camera_handoff, COMPOSITION_MODES
from ldporto.camera_motion import CameraMotion
from ldporto.camera_director import build_camera_director
from ldporto.director_config import resolve_config
from ldporto.performer_evidence import build_performer_evidence
from ldporto.zoom_delivery import delivery_report
from ldporto.core import digest
from director_fixtures import fixture, turn


def test_deliberate_zoom_increments_survive_tracking_deadzone_with_motion_limits():
    cfg = resolve_config(None)
    deliberate, tracking = CameraMotion(), CameraMotion()
    for i in range(24):
        t = i / 4
        target = [.5, .5, 1. + .025 * (i + 1) / 24]
        before, after, _ = deliberate.move(target, t, .25, cfg, intentional_zoom=True)
        tracking.move(target, t, .25, cfg)
        assert abs(after[2] - before[2]) <= cfg['max_zoom_speed'] * .25 + 1e-9
        assert abs(deliberate.zoom.acceleration) <= cfg['max_zoom_acceleration'] + 1e-9
    assert deliberate.zoom.position > 1.001
    assert tracking.zoom.position == 1.


def test_safe_timeline_stays_distinct_from_render_and_final_frame_proof():
    m, v, shots = fixture(25)
    data = build_camera_director(m, v, shots, [turn(0, 25)], [],
        {'output_width': 540, 'output_height': 960}, main_moments=[{
            'moment_id': 'SYNTHETIC', 'start': 0., 'end': 10., 'categories': ['hook'],
            'hook_score': .9, 'evidence_segment_ids': ['SYNTHETIC_SEGMENT']}])['data']
    report = delivery_report(data['zoom_events'], data['timeline'])
    assert report['proposal_outcomes']
    assert any(r['evidence_stages']['movement_present_in_timeline'] for r in report['proposal_outcomes'])
    assert report['zoom_delivered_event_count'] == 0
    assert all(r['evidence_stages']['movement_confirmed_in_final_frames'] is None for r in report['proposal_outcomes'])


def test_unrelated_canary_does_not_supply_zoom_failure_or_decoded_frame_evidence():
    row = camera_analysis()['camera_director_timeline'][0]
    proposal = {'start': 2., 'end': 4., 'target_person_id': 'ANONYMOUS', 'mode': 'SMART_ZOOM_IN'}
    canary = {'interval': {'start': 15., 'end': 17.},
        'render': {'timeline_sha256': digest([row]), 'preview_sha256': 'SYNTHETIC'},
        'validation': {'preview_sha256': 'SYNTHETIC', 'verifier_uses_rendered_frames': True,
            'sampled_frames': 10, 'issues': [{'issue_type': 'FACE_OR_HEAD_CLIPPED'}]}}
    result = delivery_report([proposal], [row], [canary])['proposal_outcomes'][0]
    assert result['reason_codes'] == ['no_verified_preview_motion']
    assert result['evidence_stages']['preview_frames_decoded'] is False


def test_keyframe_motion_outside_proposal_is_not_timeline_support():
    row = camera_analysis()['camera_director_timeline'][0]
    row['camera']['keyframes'] = [{'time': 0., 'zoom': 1.}, {'time': 1., 'zoom': 1.1},
                                   {'time': 20., 'zoom': 1.1}]
    proposal = {'start': 2., 'end': 4., 'target_person_id': 'ANONYMOUS', 'mode': 'SMART_ZOOM_IN'}
    result = delivery_report([proposal], [row])['proposal_outcomes'][0]
    assert result['render_timeline_supported'] is False
    assert result['reason_codes'] == ['no_render_timeline_support']


def camera_analysis():
    return {'metadata': {'duration': 20.}, 'camera_director_timeline': [{
        'director_id': 'D', 'start': 0., 'end': 20., 'layout': 'single_person',
        'focus_person': 'ANONYMOUS', 'camera_mode': 'SMART_ZOOM_IN',
        'crop': {'safe': True, 'rect_end': {'x': .2, 'y': 0., 'width': .3, 'height': 1.},
                 'preflight_sample_count': 3},
        'camera': {'keyframes': [{'time': 0., 'zoom': 1.}, {'time': 20., 'zoom': 1.1}]}}]}


def test_shared_handoff_preserves_source_gaps_and_does_not_promote_final_approval():
    analysis = camera_analysis()
    prior = deepcopy(analysis)
    report = build_camera_handoff(analysis, intervals=[{'start': 1., 'end': 3.}, {'start': 15., 'end': 17.}])
    assert [(r['start'], r['end']) for r in report['segments']] == [(1., 3.), (15., 17.)]
    assert report['applies_to'] == ['REEL', 'STORY']
    assert len(COMPOSITION_MODES) == 6
    assert all(r['recommended_composition'] == 'FOCUS_PERSON_9X16' for r in report['segments'])
    assert all(r['evidence']['movement_confirmed_in_final_frames'] is None for r in report['segments'])
    assert report['preview_approved'] is False and report['publish_ready'] is False
    assert analysis == prior
    schema = json.loads((Path(__file__).resolve().parents[2] / 'schemas/camera_handoff.schema.json').read_text(encoding='utf-8'))
    jsonschema.Draft202012Validator(schema).validate(report)


def test_instrument_intent_without_observed_instrument_geometry_falls_back():
    analysis = camera_analysis()
    analysis['camera_director_timeline'][0]['composition_intent'] = 'INSTRUMENT_FOCUS'
    segment = build_camera_handoff(analysis)['segments'][0]
    assert segment['composition_intent'] == 'INSTRUMENT_FOCUS'
    assert segment['recommended_composition'] == 'SOURCE_FIT_BLUR'
    assert segment['evidence']['instrument_preservation_verified'] is None
    analysis['camera_director_timeline'][0]['crop']['rect_end']['x'] = .9
    assert build_camera_handoff(analysis)['segments'][0]['evidence']['crop_geometrically_valid'] is False


def test_performer_contract_retains_raw_abstention_and_does_not_name_from_title():
    analysis = {'metadata': {'source': {'title': 'Thiago Castanho e Marcão Britto'}},
        'raw_tracks': [{'track_id': 'T1', 'person_id': None}],
        'tracklet_observations': [{'time': 1., 'track_id': 'T1', 'person_id': 'RAW_ONLINE_ID',
                                  'scene_id': 'SCENE', 'face_visible': True}],
        'participants': [{'participant_id': 'PARTICIPANT', 'person_id': None,
                          'possible_name': 'Thiago', 'role': 'likely_host'}],
        'speaker_person_summary': [{'speaker_id': 'S', 'person_id': None, 'association_status': 'UNRESOLVED'}]}
    result = build_performer_evidence(analysis)
    assert result['person_appearances'][0]['person_id'] is None
    assert result['person_appearances'][0]['raw_person_id'] == 'RAW_ONLINE_ID'
    assert result['participants'][0]['confirmed_name'] is None
    assert result['participants'][0]['observed_role_status'] == 'HYPOTHESIS'
    assert result['instrument_observations'] == []
    assert result['metrics']['instrument_measurement_status'] == 'NOT_MEASURED'
    assert result['speaker_person_mapping'][0]['review_state'] == 'UNRESOLVED'
    assert result['inference_executed'] is False
    analysis['people_observations'] = [{'time': 2., 'track_id': 'OTHER', 'person_id': 'MAPPED'}]
    raw_preserved = build_performer_evidence(analysis)['person_appearances']
    assert len(raw_preserved) == 1 and raw_preserved[0]['track_id'] == 'T1'


def test_only_explicit_human_name_confirmation_with_evidence_is_retained():
    participant = {'participant_id': 'P', 'person_id': 'PERSON', 'identity_confirmation': {
        'method': 'user_verified', 'confirmed_name': 'Nome informado', 'evidence_refs': ['USER_CREDIT_1']}}
    result = build_performer_evidence({'participants': [participant]})
    assert result['participants'][0]['confirmed_name'] == 'Nome informado'
    assert result['performer_review_queue'] == []
    participant['identity_confirmation']['evidence_refs'] = []
    result = build_performer_evidence({'participants': [participant]})
    assert result['participants'][0]['confirmed_name'] is None
    assert len(result['performer_review_queue']) == 1
