"""S5 deterministic synthetic regression: no claim of accuracy on real video."""
import json
from copy import deepcopy
from pathlib import Path

import pytest

from ldporto.active_speaker import build_active_speaker
from ldporto.config import DEFAULTS
from ldporto.camera_timeline import build_camera_timeline
from ldporto.camera_director import _prepare as director_prepare
from ldporto.speaker_roles import classify_people, contemporary_sync, lag_consistency
from ldporto.speaker_goldset import choose_review_windows, evaluate_goldset, export_csv, load_csv


def fixture():
    rows = []
    for n in range(24):
        t = n / 4 + .1
        rows.append({'time':t,'person_id':'P1','scene_id':'SH1','track_id':'T1',
                     'face_visible':True,'lip_opening':.1 + .02 * (n%2),
                     'mouth_activity':.03,'safe_crop_possible':True,
                     'center':{'x':.3,'y':.5}})
        rows.append({'time':t,'person_id':'P2','scene_id':'SH1','track_id':'T2',
                     'face_visible':True,'lip_opening':.02,
                     'mouth_activity':.00,'safe_crop_possible':True,
                     'center':{'x':.7,'y':.5}})
    vision = {'people':[{'person_id':'P1'},{'person_id':'P2'}], 'observations':rows,
              'frames':[{'time':x['time'],'visible_people':['P1','P2'],'scene_id':'SH1'}
                        for x in rows[::2]],
              'scene_intervals':[{'start':0,'end':6,'scene_id':'SH1'}]}
    diar = {'turns':[{'start':0,'end':6,'speaker':'S1'}]}
    raw = []
    for index, start in enumerate((0,3)):
        raw.append({'start':start,'end':start+3,'speaker_id':'S1',
                    'evidence_window_id':f'W{index}', 'turn_id':f'T{index}',
                    'candidates':[{'person_id':'P1','correlation':.92,
                     'correlation_lower_bound_proxy':.58,
                     'audio_lag_seconds':.04,'sample_count':12,
                     'visibility_coverage':.94,'face_visibility':1.,'track_stability':1.},
                     {'person_id':'P2','correlation':-.22,'correlation_upper_bound_proxy':-.1}]})
    return diar, vision, raw


def run(diar=None, vision=None, raw=None, cfg=None):
    d,v,r = fixture()
    return build_active_speaker(diar or d, vision or v, raw or r,
                                cfg or DEFAULTS['active_speaker'])['data']


def test_two_independent_synchronized_windows_confirm_speaker():
    data = run()
    assert data['mapping_summary'][0]['person_id'] == 'P1'
    assert data['mapping_summary'][0]['audio_video_sync']['consistent']
    assert all(row['active_person'] == 'P1' for row in data['intervals'] if row['start'] >= .1 and row['end'] < 6)
    assert data['metrics']['active_speaker_coverage'] > .8
    assert all(row['active_speaker_state'] == 'CONFIRMED' for row in data['intervals'] if row['active_person'])
    assert all('P2' not in [r['person_id'] for r in row['person_roles'] if r['role']=='SPEAKING'] for row in data['intervals'])


def test_global_mapping_not_same_as_current_active_person():
    diar, vis, raw = fixture()
    for row in raw:
        for c in row['candidates']:
            c.pop('correlation_lower_bound_proxy', None)
            c.pop('audio_lag_seconds', None)
            c.pop('sample_count', None)
    data = run(diar,vis,raw)
    assert data['mapping_summary'][0]['person_id'] == 'P1'
    assert not any(r['active_person'] for r in data['intervals'])
    assert data['metrics']['active_speaker_coverage'] == 0
    assert data['metrics']['speaker_person_mapping_coverage'] > 0
    assert all(row['active_speaker_state']!='CONFIRMED' for row in data['intervals'])


def test_bad_lag_consensus_keeps_active_person_null():
    diar, vis, raw = fixture()
    raw[1]['candidates'][0]['audio_lag_seconds'] = -.08
    cfg = deepcopy(DEFAULTS['active_speaker'])
    cfg['max_sync_lag_deviation_seconds'] = .02
    data = run(diar,vis,raw,cfg)
    assert data['mapping_summary'][0]['person_id'] == 'P1'
    assert data['mapping_summary'][0]['audio_video_sync']['consistent'] is False
    assert not any(r['active_person'] for r in data['intervals'])
    assert 'AUDIO_VIDEO_LAG_INCONSISTENT' in data['speaker_person_diagnostics'][0]['reason_codes']


def test_overlap_never_attributes_mixed_audio_automatically():
    diar, vis, raw = fixture()
    diar['turns'].append({'start':2,'end':4,'speaker':'S2'})
    data = run(diar,vis,raw)
    overlapping = [row for row in data['intervals'] if row.get('overlap')]
    assert overlapping and all(row['active_person'] is None for row in overlapping)
    assert all(row['active_speaker_state'] != 'CONFIRMED' for row in overlapping)


def test_explicit_manual_mapping_can_confirm_but_no_guess_on_conflict():
    diar, vis, raw = fixture()
    raw = [{'start':0,'end':6,'speaker':'S1','method':'user_verified', 'person_id':'P1'}]
    data = run(diar,vis,raw)
    assert any(row['active_person']=='P1' for row in data['intervals'])
    conflicting = raw + [{'start':0,'end':6,'speaker':'S1','method':'user_verified', 'person_id':'P2'}]
    result = run(diar,vis,conflicting)
    assert all(row['active_person'] is None for row in result['intervals'])


def test_reaction_requires_positive_reaction_detector_evidence():
    observed = {'P1':{'face_visible':True},'P2':{'face_visible':True, 'reaction_type':'laugh'},
                'P3':{'face_visible':True,'reaction_type':'smile','reaction_detected':True}}
    roles = classify_people(observed, speaker='S1', speaking_person='P1',
                            state='CONFIRMED', simultaneous=False)
    labels = {r['person_id']:r['role'] for r in roles}
    assert labels == {'P1':'SPEAKING','P2':'LISTENING','P3':'REACTING'}
    unknown = classify_people(observed, speaker='S1', speaking_person=None,
                               state='UNCERTAIN',simultaneous=False)
    assert all(row['role'] != 'SPEAKING' for row in unknown)


def test_camera_does_not_crop_global_identity_without_active_audio():
    diar, vis, raw = fixture()
    for row in raw:
        row['candidates'][0].pop('correlation_lower_bound_proxy')
    data = run(diar,vis,raw)
    timeline = build_camera_timeline({'duration':6},vis,
                   [{'start':0,'end':6,'shot_id':'SH1'}],data['intervals'],[],
                   {'max_window_seconds':1,'min_window_seconds':.25})['data']['timeline']
    assert all(row['active_person'] is None for row in timeline)
    assert all(row['evidence'] == ['sampled_frame'] or row['active_person'] is None for row in timeline)


def test_diagnostics_explain_unresolved_speakers():
    diar, vis, raw = fixture()
    diar['turns'] = [{'start':0,'end':6,'speaker':'S_UNRESOLVED'}]
    data = run(diar,vis,raw)
    report = data['speaker_person_diagnostics'][0]
    assert report['speaker_id'] == 'S_UNRESOLVED'
    assert report['window_diagnostics']['MAPPED_PERSON_NOT_IN_LOCAL_CANDIDATES'] == 0 if 'MAPPED_PERSON_NOT_IN_LOCAL_CANDIDATES' in report['window_diagnostics'] else True
    assert report['window_diagnostics']['BOUNDED_SYNC_CANDIDATE'] == 2 if 'BOUNDED_SYNC_CANDIDATE' in report['window_diagnostics'] else True
    assert report['unresolved_reason'] == 'insufficient_independent_evidence'
    assert len(choose_review_windows(data['speaker_person_diagnostics'],data['intervals'])) > 0


def test_goldset_abstention_and_false_merge_counted(tmp_path):
    rows = [{'speaker_id':'S1','start':0,'end':1,'predicted_person_id':'P1',
             'predicted_active_person':'P1','predicted_state':'CONFIRMED',
             'human_person_id':'P2','human_role':'speaking','annotation_status':'verified'},
            {'speaker_id':'S2','start':1,'end':2,'predicted_person_id':'',
             'predicted_active_person':'','predicted_state':'UNCERTAIN',
             'human_person_id':'P3','human_role':'speaking','annotation_status':'verified'},
            {'speaker_id':'S3','start':2,'end':3,'predicted_person_id':'',
             'predicted_active_person':'','predicted_state':'UNCERTAIN',
             'human_person_id':'','human_role':'offscreen','annotation_status':'verified'}]
    export_csv(rows,tmp_path/'gold.csv')
    labels = load_csv(tmp_path/'gold.csv')
    result = evaluate_goldset(labels)
    assert result['false_positive_or_wrong_person'] == 1
    assert result['missed_speaking_windows'] == 1
    assert result['correct_abstentions'] == 1
    with pytest.raises(FileExistsError):
        export_csv(rows,tmp_path/'gold.csv')


def test_offline_diagnostic_folder_and_zip_without_media(tmp_path):
    import zipfile
    from scripts.dev.audit_speaker_s5 import replay, main
    diar, vis, raw = fixture()
    folder = tmp_path/'analysis'
    folder.mkdir()
    payloads = {'05_diarization.json':{'data':diar},
                '08_person_reid.json':{'data':vis},
                '10_active_speaker.json':{'data':{'mappings':raw}}}
    for name, data in payloads.items():
        (folder/name).write_text(json.dumps(data),encoding='utf-8')
    zipped = tmp_path/'snapshot.zip'
    with zipfile.ZipFile(zipped, 'w') as z:
        for name in payloads:
            z.write(folder/name, 'analysis/'+name)
    a = replay(folder)
    b = replay(zipped)
    assert a['metrics']['active_speaker_coverage'] == b['metrics']['active_speaker_coverage']
    report = main([str(zipped),'--output',str(tmp_path/'report')])
    assert report['global_unresolved_speakers'] == 0
    assert (tmp_path/'report'/'speaker_s5_diagnostics.json').exists()
    assert (tmp_path/'report'/'speaker_annotations.csv').exists()


def test_director_rejects_probable_even_when_global_identity_is_visible():
    from director_fixtures import fixture as director_fixture, turn
    from ldporto.director_config import resolve_config
    metadata, vision, shots = director_fixture(8)
    probable = {**turn(0, 8, confidence=.99), 'active_speaker_state':'PROBABLE',
                'active_person':None}
    segments = director_prepare(metadata, vision, shots, [probable], resolve_config(None))
    assert segments and all(not row['confident'] for row in segments)


def test_offline_neural_pilot_compares_without_promoting_model(tmp_path):
    from scripts.dev.audit_speaker_s5 import main
    diar, vis, raw = fixture()
    folder = tmp_path/'analysis'
    folder.mkdir()
    for name, obj in {'05_diarization.json':diar,
                      '08_person_reid.json':vis,
                      '10_active_speaker.json':{'mappings':raw}}.items():
        (folder/name).write_text(json.dumps({'data':obj}),encoding='utf-8')
    output = tmp_path/'report'
    main([str(folder),'--output',str(output)])
    rows = load_csv(output/'speaker_annotations.csv')
    # All speakers confirmed => reviewer may have no samples. Provide explicit goldset.
    assert not rows
    gold = [{'speaker_id':'S1','start':0,'end':3,'predicted_person_id':'P1',
             'predicted_active_person':'P1','predicted_state':'CONFIRMED',
             'human_person_id':'P1','human_role':'speaking','annotation_status':'verified'}]
    path = tmp_path/'gold.csv'
    export_csv(gold,path)
    external = tmp_path/'external.json'
    external.write_text(json.dumps([{'speaker_id':'S1','start':0,'end':3,'person_id':None}]),encoding='utf-8')
    main([str(folder),'--output',str(output),'--evaluate',str(path),'--neural-predictions',str(external)])
    metrics = json.loads((output/'speaker_goldset_metrics.json').read_text(encoding='utf-8'))
    assert metrics['heuristic_consensus']['true_correct_identifications'] == 1
    assert metrics['neural_pilot']['missed_speaking_windows'] == 1
