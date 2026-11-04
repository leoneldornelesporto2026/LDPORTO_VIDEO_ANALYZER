"""Synthetic evidence and tiny generated frames only; no detector pipeline/models."""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path

import pytest
from ldporto.core import digest
from ldporto.visual_review import create_goldset, compare_goldset, fallback_diagnosis
from ldporto.zoom_delivery import delivery_report
from ldporto.camera_geometry import geometry
from ldporto.director_config import resolve_config
from ldporto.preview_renderer import render_preview
from ldporto.preview_verifier import verify_preview, conservative_repair
from director_fixtures import fixture, turn
from ldporto.camera_director import build_camera_director


def analysis():
    return {'metadata': {'sha256': 'a' * 64, 'duration': 120, 'filename': 'SYNTHETIC'},
            'people_observations': [{'track_id': f'T{i}', 'person_id': f'P{i}', 'time': i*6 + 2,
                                     'scene_id': f'S{i//2}', 'face_bbox': dict(x=.4, y=.2, width=.1, height=.2),
                                     'face_visible': True} for i in range(20)],
            'camera_director_focus_window_audit': [
                {'start': i*6, 'end': i*6+6, 'focus_person': None,
                 'reason_code': 'NO_VISIBLE_FACE' if i%2 else 'NO_CONFIRMED_ACTIVE_SPEAKER'} for i in range(20)],
            'active_speaker': [{'start': i*6, 'end': i*6+6, 'speaker_id': f'V{i}', 'person_id': f'P{i}'} for i in range(20)],
            'shots': [{'start': 0, 'end': 60, 'shot_id': 'FAKE_TV_A'},
                      {'start': 60, 'end': 120, 'shot_id': 'FAKE_TV_B'}]}


def annotated(a):
    gold = create_goldset(a)
    for s in gold['samples']:
        s['annotation_status'] = 'verified'
        identities = {o['track_id']: 'H' + o['track_id'][1:] for o in s['evidence']['observations']}
        s['human'].update(tracklet_identities=identities, uncertainty=False, reviewer='fixture_reviewer',
                          speaker_person_bindings={'V'+t[1:]: h for t, h in identities.items()})
    return gold


def test_goldset_human_fields_empty_reproducible_and_origin_bound():
    a = analysis()
    gold = create_goldset(a)
    assert gold == create_goldset(a)
    assert 10 <= len(gold['samples']) <= 20
    assert gold['status'] == 'READY_FOR_REVIEW' and not gold['publish_ready']
    assert gold['origin_analysis_sha256'] == digest(a)
    assert {s['stratum'] for s in gold['samples']} >= {'NO_VISIBLE_FACE', 'NO_CONFIRMED_ACTIVE_SPEAKER'}
    for s in gold['samples']:
        assert all(v is None for v in s['human'].values())
        assert s['image_evidence'] is None
        assert digest(s['evidence']) == s['evidence_sha256']
    assert compare_goldset(gold, a, a)['improvement_accepted'] is None
    json.dumps(gold, allow_nan=False)


def test_shortfall_and_missing_origin_do_not_fabricate_samples():
    a = analysis()
    a['people_observations'] = []
    a['camera_director_focus_window_audit'] = []
    gold = create_goldset(a)
    assert gold['status'] == 'PARTIAL' and gold['samples'] == []
    a = analysis()
    a['metadata']['sha256'] = None
    assert create_goldset(a)['status'] == 'PARTIAL'


def test_false_merge_split_binding_and_abstention_not_coverage_improvement():
    a = analysis()
    gold = annotated(a)
    reviewed_tracks = [t for s in gold['samples'] for t in s['human']['tracklet_identities']]
    first, second = reviewed_tracks[:2]
    bad = deepcopy(a)
    for o in bad['people_observations']:
        if o['track_id'] == second:
            o['person_id'] = 'P' + first[1:]
    result = compare_goldset(gold, a, bad)
    assert result['after']['false_merge_pairs'] == 1
    assert result['after']['verified_identity_coverage'] < result['after']['predicted_identity_coverage']
    assert result['after']['speaker_person_false_binding_count'] >= 1
    assert result['improvement_accepted'] is False
    assert compare_goldset(gold, bad, a)['improvement_accepted'] is True
    # Same true identity with two predicted clusters = false split, not better Re-ID.
    for s in gold['samples']:
        if second in s['human']['tracklet_identities']:
            s['human']['tracklet_identities'][second] = 'H' + first[1:]
            s['human']['speaker_person_bindings']['V'+second[1:]] = 'H' + first[1:]
    assert compare_goldset(gold, a, a)['after']['false_split_pairs'] == 1
    absent = deepcopy(a)
    absent['people_observations'] = []
    absent['active_speaker'] = []
    result = compare_goldset(gold, a, absent)
    assert result['after']['identity_abstentions'] == len(reviewed_tracks)
    assert result['after']['speaker_person_binding_abstentions'] > 0
    assert result['improvement_accepted'] is False


def test_review_tamper_wrong_source_and_unknown_bindings_stay_null():
    a = analysis()
    gold = annotated(a)
    b = deepcopy(a)
    b['metadata']['sha256'] = 'b'*64
    assert compare_goldset(gold, a, b)['before'] is None
    for s in gold['samples']:
        s['human']['speaker_person_bindings'] = None
    assert compare_goldset(gold, a, a)['improvement_accepted'] is None
    gold['samples'][0]['evidence']['shots'].append({'fake': True})
    assert compare_goldset(gold, a, a)['reason'] == 'review_evidence_changed'


def test_binding_segmentation_cannot_create_improvement():
    a = analysis()
    gold = annotated(a)
    segmented = deepcopy(a)
    segmented['active_speaker'] = [dict(row, start=left, end=right)
        for row in a['active_speaker'] for left, right in
        ((row['start'],row['start']+3),(row['start']+3,row['end']))]
    result = compare_goldset(gold, segmented, a)
    assert result['before']['speaker_person_reviewed_seconds'] == result['after']['speaker_person_reviewed_seconds']
    assert result['before']['verified_binding_coverage'] == result['after']['verified_binding_coverage'] == 1
    assert result['improvement_accepted'] is False


def test_recycled_track_ids_at_other_times_are_not_reviewed_anchors():
    a = analysis()
    gold = annotated(a)
    recycled = deepcopy(a)
    for obs in recycled['people_observations']:
        obs['time'] += .5
    result = compare_goldset(gold, a, recycled)
    assert result['after']['tracks_without_matching_review_anchor'] >= 10
    assert result['after']['verified_identity_coverage'] == 0
    assert result['improvement_accepted'] is False


def test_fallback_causes_duration_and_gaps_are_reproducible():
    a = analysis()
    report = fallback_diagnosis(a)
    assert report['fallback_seconds_by_reason'] == {'NO_VISIBLE_FACE': 60, 'NO_CONFIRMED_ACTIVE_SPEAKER': 60}
    assert report['fallback_fraction_of_audited_windows'] == 1
    assert report['unaccounted_video_seconds'] == 0
    a['camera_director_focus_window_audit'].pop()
    assert fallback_diagnosis(a)['unaccounted_video_seconds'] == 6
    a['camera_director_focus_window_audit'].append(a['camera_director_focus_window_audit'][0])
    with pytest.raises(ValueError):
        fallback_diagnosis(a)


@pytest.mark.parametrize('dimensions', [(540, 960), (960, 540)])
@pytest.mark.parametrize('box', [dict(x=.4,y=.02,width=.1,height=.2),
                               dict(x=.95,y=.2,width=.1,height=.2),
                               dict(x=.9,y=.2,width=.1,height=.2),
                               dict(x=0,y=.2,width=.1,height=.2),
                               dict(x=float('nan'),y=.2,width=.1,height=.2)])
def test_head_and_border_canaries_never_safe(dimensions, box):
    m,v,_ = fixture(8)
    o = deepcopy(v['observations'][0])
    o['face_bbox'] = box
    cfg = resolve_config(dict(output_width=dimensions[0], output_height=dimensions[1]))
    assert geometry([o],m,cfg)['safe'] is False


def proposal_and_row():
    p = dict(start=0,end=2,mode='SMART_ZOOM_IN',target_person_id='P')
    r = dict(start=0,end=2,director_id='D',focus_person='P',layout='single_person',
             camera_mode='SMART_ZOOM_IN', crop={'safe': True}, camera={'keyframes': [
                 {'time':0,'zoom':1,'center':[.5,.5]}, {'time':2,'zoom':1.1,'center':[.5,.5]}]})
    return p,r


def test_planner_and_keyframes_never_delivered_without_render():
    p,r = proposal_and_row()
    report = delivery_report([p], [r])
    assert report['zoom_delivered_event_count'] == 0
    assert report['proposal_outcomes'][0]['reason_codes'] == ['no_verified_preview_motion']
    r['layout'] = 'full_frame'
    assert delivery_report([p], [r])['proposal_outcomes'][0]['reason_codes'] == ['no_render_timeline_support']


@pytest.mark.parametrize('dimensions', [(96,160), (160,90)])
def test_actual_synthetic_render_receipt_preview_hash_and_clipping(tmp_path, monkeypatch, dimensions):
    import cv2
    import numpy as np
    import ldporto.preview_renderer as renderer
    import ldporto.preview_verifier as verifier
    monkeypatch.setattr(renderer, 'find_media_tool', lambda name: None)
    monkeypatch.setattr(verifier, '_ffprobe', lambda path: None)
    source = tmp_path/'synthetic.avi'
    writer = cv2.VideoWriter(str(source), cv2.VideoWriter_fourcc(*'MJPG'), 10, (320,180))
    assert writer.isOpened()
    for _ in range(20):
        writer.write(np.full((180,320,3),130,np.uint8))
    writer.release()
    p,r = proposal_and_row()
    target = tmp_path/'preview.mp4'
    rendered = render_preview(source,[r],dict(duration=2,width=320,height=180),target,
                              output_width=dimensions[0],output_height=dimensions[1])
    assert rendered['status'] == 'ok'
    validation = verify_preview(target, {'duration':2}, [r])
    canary = dict(canary_id='SYNTHETIC',render=rendered['data'],validation=validation['data'])
    report = delivery_report([p],[r],[canary])
    # Uniform source pixels stay uniform after a real crop transform. Render
    # receipts therefore prove execution, not visible final-frame zoom motion.
    assert report['rendered_zoom_event_count'] == 1
    assert report['zoom_delivered_event_count'] == 0
    assert report['zoom_delivery_verified'] is None
    assert report['proposal_outcomes'][0]['reason_codes'] == ['final_frame_motion_unverified']
    assert report['preview_approved'] is None and not report['publish_ready']
    bad = deepcopy(canary)
    bad['validation']['preview_sha256'] = 'b'*64
    assert delivery_report([p],[r],[bad])['rendered_zoom_event_count'] == 0
    assert delivery_report([p],[r],[bad])['zoom_delivered_event_count'] == 0
    static = deepcopy(canary)
    for receipt in static['render']['rendered_motion']:
        receipt['scale_samples'] = [[t, 1.] for t, _ in receipt['scale_samples']]
    assert delivery_report([p],[r],[static])['rendered_zoom_event_count'] == 0
    assert delivery_report([p],[r],[static])['zoom_delivered_event_count'] == 0
    bad = deepcopy(canary)
    bad['validation']['issues'] = [{'issue_type':'FACE_OR_HEAD_CLIPPED'}]
    report = delivery_report([p],[r],[bad])
    assert report['zoom_delivered_event_count'] == 0
    assert report['proposal_outcomes'][0]['reason_codes'] == ['head_clipping']
    repaired,_ = conservative_repair([r],bad['validation'])
    assert delivery_report([p],repaired,[canary])['zoom_delivered_event_count'] == 0


def test_fake_tv_cut_two_planes_uncertainty_and_synthetic_canary():
    m,v,shots = fixture(12,pair=True,cuts=(6,))
    voices = [dict(turn(0,6),active_speaker_state='CONFIRMED',active_person='PERSON_A'),
              dict(turn(6,12,person='PERSON_B'),active_speaker_state='UNCERTAIN',active_person=None)]
    data = build_camera_director(m,v,shots,voices,[], {'dominant_face_fallback':False})['data']
    assert all(r['focus_person'] is None for r in data['timeline'] if r['start'] >= 6)
    assert all(r['end'] <= 6 or r['start'] >= 6 for r in data['timeline'])
    assert data['metrics']['zoom_delivered_event_count'] == 0


def test_cli_json_only_exclusive_output(tmp_path):
    path = Path(__file__).resolve().parents[2]/'scripts/dev/visual_review_stage50.py'
    spec = importlib.util.spec_from_file_location('visual_review_cli', path)
    cli = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cli)
    source, out = tmp_path/'analysis.json', tmp_path/'gold.json'
    source.write_text(json.dumps(analysis()),encoding='utf-8')
    assert cli.main(['create','--analysis',str(source),'--output',str(out)]) == 0
    saved = out.read_bytes()
    with pytest.raises(FileExistsError):
        cli.main(['create','--analysis',str(source),'--output',str(out)])
    assert out.read_bytes() == saved


def test_resource_diagnostic_never_promotes_legacy_keyframes_to_delivery():
    path = Path(__file__).resolve().parents[2]/'scripts/dev/performance_diagnostics_r3.py'
    spec = importlib.util.spec_from_file_location('stage50_resource_diagnostic', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.analyze({}, {'zoom_event_count':6})['camera_readiness']['zoom_delivered'] is None
    assert module.analyze({}, {'zoom_event_count':6,'zoom_delivered_event_count':0})['camera_readiness']['zoom_delivered'] == 0


def test_finalizer_summary_never_labels_timeline_as_delivery(tmp_path, monkeypatch, capsys):
    path = Path(__file__).resolve().parents[2]/'scripts/dev/finalize_v44.py'
    spec = importlib.util.spec_from_file_location('stage50_finalizer', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, 'ROOT', tmp_path)
    comparison = tmp_path/'docs/benchmarks/V43_V44_COMPARE.json'
    comparison.parent.mkdir(parents=True)
    comparison.write_text(json.dumps({'changes': {'zoom_event_count': {'new':6}}}), encoding='utf-8')
    monkeypatch.setattr(module, 'completion_state', lambda: {'ready':True})
    monkeypatch.setattr(module.report_full_v44, 'main', lambda: None)
    assert module.main() == 0
    output = json.loads(capsys.readouterr().out)
    assert output['zoom_delivered'] is None
    assert output['zoom_timeline'] == {'new':6}
