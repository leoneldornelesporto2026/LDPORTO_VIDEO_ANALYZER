"""Synthetic regressions for honest visual diagnostics; no models, media or CUDA."""
import json
import sys
from copy import deepcopy
from types import SimpleNamespace

import pytest

from director_fixtures import fixture as camera_fixture, turn
from ldporto.active_speaker import build_active_speaker
from ldporto.camera_director import build_camera_director
from ldporto.config import DEFAULTS
from ldporto.vision import load_local_yolo
from test_s5_speaker_person_active import fixture as speaker_fixture
from test_stage25_body_backends import config, no_network


def same_person_solo_evidence(overlapping):
    diarization, vision, source = speaker_fixture()
    diarization['turns'] = [dict(start=0., end=2., speaker='S1'),
                            dict(start=2., end=4., speaker='S2')]
    if overlapping:
        diarization['turns'] += [dict(start=4., end=6., speaker='S1'),
                                dict(start=5., end=6., speaker='S2')]
    evidence = []
    for index, speaker in enumerate(('S1', 'S1', 'S2', 'S2')):
        row = deepcopy(source[0])
        row.update(start=float(index), end=float(index+1), speaker_id=speaker,
                   evidence_window_id=f'INDEPENDENT_{index}')
        row['candidates'] = [row['candidates'][0]]
        evidence.append(row)
    return diarization, vision, evidence


def test_simultaneous_person_collision_removes_acceptance_from_every_contract():
    diarization, vision, evidence = same_person_solo_evidence(overlapping=True)
    original = deepcopy(evidence)
    result = build_active_speaker(diarization, vision, evidence, DEFAULTS['active_speaker'])['data']
    assert evidence == original
    assert all(row['person_id'] is None and row['confidence'] is None
               and row['association_status'] == 'UNRESOLVED'
               and row['method'] == 'insufficient_consensus'
               and row['unresolved_reason'] == 'simultaneous_speaker_person_conflict'
               for row in result['mapping_summary'])
    assert all(row['confidence'] is None for row in result['affinity'])
    assert all(row['person_id'] is None and row['active_person'] is None
               and row['unresolved_reason'] == 'simultaneous_speaker_person_conflict'
               for row in result['intervals'])
    solo = [row for row in result['intervals'] if not row['overlap']]
    assert solo and all(row['active_speaker_reason'] == 'simultaneous_speaker_person_conflict'
                        for row in solo)
    assert result['metrics']['speaker_person_mapping_coverage'] == 0
    assert result['metrics']['conflicting_mapping_fraction'] == pytest.approx(1)
    # Keep the measured support available for human investigation.
    assert all(len(row['evidence_refs']) == 2 for row in result['mapping_summary'])


def test_sequential_diarization_labels_can_still_share_a_person_without_conflict():
    diarization, vision, evidence = same_person_solo_evidence(overlapping=False)
    result = build_active_speaker(diarization, vision, evidence, DEFAULTS['active_speaker'])['data']
    assert all(row['person_id'] == 'P1' and row['association_status'] == 'PROVISIONAL'
               for row in result['mapping_summary'])
    assert {row['speaker_id'] for row in result['intervals'] if row['active_person'] == 'P1'} == {'S1', 'S2'}
    assert result['metrics']['conflicting_mapping_fraction'] == 0


def test_missing_yolo_reports_actionable_path_and_format_without_loading(tmp_path, monkeypatch):
    cfg = config(tmp_path, body_backend='yolo')['vision']
    monkeypatch.setitem(sys.modules, 'ultralytics', SimpleNamespace(
        YOLO=lambda *args: pytest.fail('Missing model must not reach YOLO')))
    model, report = load_local_yolo(cfg)
    assert model is None
    assert report['configured_model'] == cfg['yolo_model']
    assert report['resolved_model_path'] == str((tmp_path/'missing.pt').resolve())
    assert report['model_validation_reason'] == 'missing_file'
    assert report['expected_model_format'] == '.pt'
    assert report['expected_model_task'] == 'detect'
    assert report['expected_person_class'] == {'id': 0, 'name': 'person'}
    assert report['allow_model_downloads'] is False
    assert report['allow_dependency_install'] is False
    assert report['model_path'] is None and report['model_sha256'] is None
    assert report['readiness'] == 'NOT_READY'
    json.dumps(report, allow_nan=False)


@pytest.mark.parametrize('suffix,content,reason', [
    ('.onnx', b'synthetic placeholder', 'unsupported_format'),
    ('.yaml', b'synthetic placeholder', 'unsupported_format'),
    ('.pt', b'', 'empty_file')])
def test_invalid_yolo_files_explain_rejection_before_loading(tmp_path, monkeypatch, suffix, content, reason):
    path = tmp_path/('synthetic'+suffix)
    path.write_bytes(content)
    cfg = config(tmp_path, body_backend='yolo')['vision']
    cfg['yolo_model'] = str(path)
    monkeypatch.setitem(sys.modules, 'ultralytics', SimpleNamespace(
        YOLO=lambda *args: pytest.fail('Rejected file must not reach YOLO')))
    model, report = load_local_yolo(cfg)
    assert model is None and report['model_validation_reason'] == reason
    assert report['fallback_reason'] == 'yolo_local_model_invalid'
    assert report['diagnostic_reason'] == 'model_file_invalid'
    assert report['resolved_model_path'] == str(path.resolve())
    assert report['device_actually_used'] is None


@pytest.mark.parametrize('task,names,reason', [
    ('classify', {0: 'person'}, 'unsupported_task'),
    ('detect', {0: 'car'}, 'person_class_missing')])
def test_yolo_model_contract_is_explicit_without_real_weights(tmp_path, monkeypatch, task, names, reason):
    path = tmp_path/'synthetic.pt'
    path.write_bytes(b'synthetic placeholder, never a real checkpoint')
    cfg = config(tmp_path, body_backend='yolo')['vision']
    cfg['yolo_model'] = str(path)
    monkeypatch.setitem(sys.modules, 'ultralytics', SimpleNamespace(
        YOLO=lambda *args: SimpleNamespace(task=task, names=names)))
    model, report = load_local_yolo(cfg)
    assert model is None and report['model_validation_reason'] == reason
    assert report['diagnostic_reason'] == 'model_load_error'
    assert report['device_actually_used'] is None and report['readiness'] == 'NOT_READY'


def direct(voices, data=None):
    metadata, vision, shots = data or camera_fixture(8)
    return build_camera_director(metadata, vision, shots, voices, [],
                                 {'dominant_face_fallback': False})['data']


def test_camera_proposal_delivery_audit_survives_timeline_compaction():
    result = direct([turn(0, 8)])
    windows = result['focus_window_audit']
    assert len(windows) == result['metrics']['director_evaluation_windows']
    assert len(windows) > len(result['timeline'])
    for window in windows:
        delivery = window['candidate_delivery']
        assert delivery['delivered']['focus_person'] == window['focus_person']
        assert delivery['delivered']['layout'] == window['layout']
        assert delivery['delivered']['candidate'] == window['decision']
        assert delivery['reason_codes']
        assert delivery['execution_scope'] == 'camera_recommendation_not_rendered_video'
    audit = result['metrics']['focus_decision_audit']
    assert sum(audit['candidate_outcome_window_counts'].values()) == len(windows)
    assert audit['candidate_outcome_window_counts']['ACCEPTED'] > 0
    assert audit['switch_suppression_window_counts']['speaker_confirmation'] > 0
    assert sum(audit['switch_suppression_window_counts'].values()) == result['metrics']['switches_suppressed']
    json.dumps(result, allow_nan=False)


def test_camera_safe_source_preservation_is_a_decision_without_fabricated_focus():
    voice = dict(turn(0, 8), active_person=None, active_speaker_state='PROBABLE')
    result = direct([voice])
    assert all(window['candidate_delivery']['outcome'] == 'SOURCE_PRESERVED'
               and window['candidate_delivery']['delivered']['focus_person'] is None
               and window['reason_code'] == 'NO_CONFIRMED_ACTIVE_SPEAKER'
               for window in result['focus_window_audit'])
    assert result['metrics']['camera_director_coverage'] == 0


def test_temporal_crop_rejection_reports_full_frame_as_the_delivered_candidate():
    data = camera_fixture(8)
    data[1]['observations'] = [row for row in data[1]['observations'] if row['time'] < 6]
    result = direct([turn(0, 8)], data)
    rejected = [window for window in result['focus_window_audit']
                if 'CROP_PREFLIGHT_UNSAFE' in window['director_reasons']]
    assert rejected
    assert all(window['candidate_delivery']['proposed']['layout'] == 'single_person'
               and window['candidate_delivery']['outcome'] == 'REPLACED_BY_SOURCE'
               and window['candidate_delivery']['delivered']['candidate'] == 'FULL_FRAME'
               and window['layout'] == 'full_frame'
               for window in rejected)
    assert all(row['decision']['selected_candidate'] == 'FULL_FRAME'
               for row in result['timeline'] if 'CROP_PREFLIGHT_UNSAFE' in row['decision']['reasons'])


def test_brief_challenger_keeps_requested_person_and_suppression_evidence():
    data = camera_fixture(12, pair=True, distant=True)
    result = direct([turn(0, 4), turn(4, 4.5, person='PERSON_B'), turn(4.5, 12)], data)
    challenged = [window for window in result['focus_window_audit']
                  if window['candidate_delivery']['requested_person'] == 'PERSON_B']
    assert challenged
    assert all(window['candidate_delivery']['switch_suppressed']
               and window['candidate_delivery']['outcome'] == 'SUPPRESSED'
               and window['candidate_delivery']['delivered']['focus_person'] == 'PERSON_A'
               and window['candidate_delivery']['switch_suppression_reason']
               for window in challenged)
