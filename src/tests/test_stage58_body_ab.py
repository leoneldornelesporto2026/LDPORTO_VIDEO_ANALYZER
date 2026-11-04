"""Synthetic truth only. No production measurements, models, network or GPU."""
from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import numpy as np
import pytest

from ldporto.body_ab import (create_manifest, manifest_basis, compare_ab, run_backend,
                            derive_frames, file_sha, _matches)
from ldporto.core import digest
from ldporto.person_reid import build_person_identities
from test_stage25_body_backends import config, Faces, Hog, no_network
from test_stage57_local_yolo import fake_local


BOX = dict(x=.1, y=.1, width=.3, height=.7)


def manifest():
    m = create_manifest({'sha256': 'a'*64, 'duration': 140., 'filename': 'SYNTHETIC'})
    for s in m['samples']:
        s['image_evidence'] = {'sha256': digest(s['sample_id']), 'source_sha256': 'a'*64,
                               'requested_time': s['time'], 'consent_local': True, 'path': 'unused'}
    m['manifest_sha256'] = manifest_basis(m)
    return m


def reviewed():
    m = manifest()
    m['ground_truth_consent'] = {'allowed': True, 'reviewer': 'synthetic_reviewer',
                                 'source_sha256': 'a'*64, 'manifest_sha256': m['manifest_sha256']}
    for i, label in enumerate(('A', 'A', 'B')):
        m['samples'][i]['human'].update(status='verified', reviewer='synthetic_reviewer',
            bodies=[{'bbox': BOX, 'instance_id': f'I{i}', 'identity_label': label}],
            speaker_person={f'V{i}': label})
    return m


def run(m, mode, predictions=('P1', 'P2', 'P3')):
    backend = 'hog' if mode == 'baseline' else 'yolo'
    return {'mode': mode, 'source_sha256': m['source']['sha256'],
            'manifest_sha256': m['manifest_sha256'], 'config': {'synthetic': True},
            'config_sha256': digest({'synthetic': True}),
            'wall_seconds': None, 'body_seconds': None,
            'execution': {'initialized': backend, 'successful_backends': [backend]},
            'frames': [{'sample_id': s['sample_id'], 'time': s['time'],
                        'image_sha256': s['image_evidence']['sha256'],
                        'executed_backends': [backend],
                        'detections': [{'bbox': deepcopy(BOX), 'body_visible': True,
                                        'body_detection_source': backend,
                                        'track_id': f'{backend}_T{i}', 'person_id': predictions[i]}] if i < 3 else [],
                        'speaker_person': {f'V{i}': predictions[i]} if i < 3 else None}
                       for i, s in enumerate(m['samples'])]}


def test_manifest_empty_truth_editable_requests_and_bounded():
    m = create_manifest({'sha256': 'a'*64, 'duration': 140., 'filename': 'SYNTHETIC'})
    assert m == create_manifest(m['source'])
    assert len(m['samples']) == 14 and len({s['requested_stratum'] for s in m['samples']}) == 7
    assert all(s['human']['bodies'] is None and s['image_evidence'] is None for s in m['samples'])
    assert m['strata_are_requests_not_labels'] and not m['publish_ready']
    for count in (9, 21):
        with pytest.raises(ValueError):
            create_manifest(m['source'], count=count)
    short = create_manifest({**m['source'], 'duration': .1})
    assert len(short['samples']) == 14
    with pytest.raises(ValueError):
        create_manifest(m['source'], windows=[{'start': 0, 'end': 2}]*10)


def test_unlabeled_is_descriptive_never_accuracy():
    m = manifest()
    report = compare_ab(m, run(m, 'baseline'), run(m, 'candidate'))
    assert report['status'] == 'NOT_MEASURED'
    assert report['baseline']['detection_count'] == 3
    assert report['candidate']['body']['precision'] is None
    assert report['candidate']['reid']['false_merge'] is None
    assert report['editorial_benefit']['value'] is None and report['improvement_accepted'] is None
    json.dumps(report, allow_nan=False)


def test_safe_fragmentation_vs_unsafe_merge_and_different_track_ids():
    m = reviewed()
    safe = compare_ab(m, run(m, 'baseline'), run(m, 'candidate', ('P1', 'P1', 'P3')))
    assert safe['baseline']['reid']['false_split'] == 1
    assert safe['candidate']['reid']['false_split'] == 0
    assert safe['candidate']['body']['recall'] == 1
    assert safe['improvement_accepted'] is True
    unsafe = compare_ab(m, run(m, 'baseline'), run(m, 'candidate', ('P1', 'P1', 'P1')))
    assert unsafe['candidate']['reid']['false_merge'] == 2
    assert unsafe['candidate']['speaker_person']['false_bindings'] == 3
    assert unsafe['improvement_accepted'] is False
    assert unsafe['editorial_benefit']['status'] == 'NOT_MEASURED'
    assert not safe['publish_ready']


@pytest.mark.parametrize('mutation', ['none', 'denied', 'source', 'manifest'])
def test_truth_requires_explicit_source_bound_consent(mutation):
    m = reviewed()
    if mutation == 'none':
        m['ground_truth_consent'] = None
    elif mutation == 'denied':
        m['ground_truth_consent']['allowed'] = False
    else:
        m['ground_truth_consent'][mutation+'_sha256'] = 'b'*64
    r = compare_ab(m, run(m, 'baseline'), run(m, 'candidate'))
    assert r['status'] == 'NOT_MEASURED' and r['improvement_accepted'] is None


@pytest.mark.parametrize('field', ['source_sha256', 'manifest_sha256', 'config', 'time', 'image_sha256', 'missing_frame'])
def test_mixed_source_hash_parameters_or_frames_rejected(field):
    m = reviewed()
    a, b = run(m, 'baseline'), run(m, 'candidate')
    if field in ('source_sha256', 'manifest_sha256'):
        b[field] = 'b'*64
    elif field == 'config':
        b['config'] = {'synthetic': False}
        b['config_sha256'] = digest(b['config'])
    elif field == 'missing_frame':
        b['frames'].pop()
    else:
        b['frames'][0][field] = 999 if field == 'time' else 'b'*64
    r = compare_ab(m, a, b)
    assert r['status'] == 'NOT_MEASURED' and r['improvement_accepted'] is None


def test_frame_anchor_tamper_requires_regeneration():
    m = manifest()
    m['samples'][0]['time'] += .1
    with pytest.raises(ValueError, match='anchors changed'):
        compare_ab(m, {}, {})


def test_mixed_image_source_rejected_even_with_new_manifest_seal():
    m = reviewed()
    m['samples'][0]['image_evidence']['source_sha256'] = 'b'*64
    m['manifest_sha256'] = manifest_basis(m)
    m['ground_truth_consent']['manifest_sha256'] = m['manifest_sha256']
    report = compare_ab(m, run(m, 'baseline'), run(m, 'candidate'))
    assert report['status'] == 'NOT_MEASURED'
    assert report['reason'] == 'frame_hash_or_timestamp_mismatch'


def test_candidate_fallback_and_skipped_frame_not_yolo_substitution():
    m = reviewed()
    a, b = run(m, 'baseline'), run(m, 'candidate', ('P1', 'P1', 'P3'))
    b['execution']['successful_backends'] = ['hog']
    r = compare_ab(m, a, b)
    assert not r['candidate']['backend_substitution_verified']
    assert r['improvement_accepted'] is None
    b = run(m, 'candidate', ('P1', 'P1', 'P3'))
    b['frames'][-1]['executed_backends'] = []
    assert compare_ab(m, a, b)['improvement_accepted'] is None


def test_missing_id_abstains_and_detection_duplicates_are_false_positives():
    m = reviewed()
    a, b = run(m, 'baseline'), run(m, 'candidate', (None, None, None))
    b['frames'][0]['detections'].append(deepcopy(b['frames'][0]['detections'][0]))
    r = compare_ab(m, a, b)
    assert r['candidate']['body']['false_positive'] == 1
    assert r['candidate']['reid']['false_merge'] == 0
    assert r['candidate']['reid']['false_split'] == 0
    assert r['candidate']['reid']['abstentions'] == 3
    assert r['candidate']['speaker_person']['abstentions'] == 3
    assert r['improvement_accepted'] is False


def test_simultaneous_people_overlap_voices_and_verified_empty_frame():
    m = reviewed()
    right = dict(x=.6, y=.1, width=.3, height=.7)
    m['samples'][0]['human'].update(bodies=[{'bbox': BOX, 'instance_id': 'I0', 'identity_label': 'A'},
        {'bbox': right, 'instance_id': 'I3', 'identity_label': 'B'}], speaker_person={'VA': 'A', 'VB': 'B'})
    m['samples'][3]['human'].update(status='verified', reviewer='synthetic', bodies=[])
    a, b = run(m, 'baseline'), run(m, 'candidate')
    for r in (a, b):
        r['frames'][0]['detections'].append(dict(bbox=right, body_visible=True,
            body_detection_source=r['frames'][0]['executed_backends'][0], person_id='P3'))
        r['frames'][0]['speaker_person'] = {'VA': 'P1', 'VB': 'P3'}
    out = compare_ab(m, a, b)
    assert out['candidate']['body']['reviewed_frames'] == 4
    assert out['candidate']['body']['true_positive'] == 4
    assert out['candidate']['reid']['false_merge'] == 0
    assert out['candidate']['speaker_person']['false_bindings'] == 0


def test_maximum_matching_crowded_frame():
    # One flexible prediction and one restricted: greedy IoU would miss a match.
    t = [{'bbox': dict(x=0., y=0., width=.5, height=.9)},
         {'bbox': dict(x=.25, y=0., width=.5, height=.9)}]
    p = [{'bbox': dict(x=.1, y=0., width=.5, height=.9)},
         {'bbox': dict(x=0., y=0., width=.26, height=.9)}]
    assert len(_matches(t, p, .5)) == 2


def image_manifest(tmp_path):
    import cv2
    m = manifest()
    path = tmp_path/'synthetic.png'
    assert cv2.imwrite(str(path), np.zeros((180, 320, 3), np.uint8))
    for s in m['samples']:
        s['image_evidence'].update(path=str(path), sha256=file_sha(path))
    m['manifest_sha256'] = manifest_basis(m)
    return m


def test_real_engine_fake_yolo_replaces_hog_and_preserves_two_face_rois(tmp_path, monkeypatch):
    def row(coords):
        return SimpleNamespace(xyxy=[SimpleNamespace(cpu=lambda: SimpleNamespace(numpy=lambda: np.array(coords)))],
                               conf=[.8], cls=[0])
    cfg = fake_local(tmp_path, monkeypatch, lambda *a, **kw: [SimpleNamespace(boxes=[
        row([0, 0, 150, 180]), row([160, 0, 320, 180])])])
    m = image_manifest(tmp_path)
    from ldporto.vision import PersonDetectionEngine
    def factory(settings, notes, offline):
        engine = PersonDetectionEngine(settings, notes, offline)
        engine.face = Faces([(30, 30, 30, 40), (210, 30, 30, 40)])
        if engine.hog:
            engine.hog = Hog()
        return engine
    a = run_backend(m, cfg, mode='baseline', consent_local=True, detector_factory=factory)
    b = run_backend(m, cfg, mode='candidate', consent_local=True, detector_factory=factory)
    assert b['execution']['successful_calls']['yolo'] == 14
    assert b['execution']['inference_calls']['hog'] == 0
    first = b['frames'][0]['detections']
    assert all(d['face_visible'] and d['body_visible'] for d in first)
    assert first[0]['face_bbox']['x'] < first[0]['bbox']['x'] + first[0]['bbox']['width']
    assert first[1]['face_bbox']['x'] >= first[1]['bbox']['x']
    assert all('person_id' not in d for f in b['frames'] for d in f['detections'])
    result = compare_ab(m, a, b)
    assert result['candidate']['backend_substitution_verified']
    assert result['status'] == 'NOT_MEASURED'
    assert b['execution']['identity_evidence'] is False


def test_execution_requires_consent_and_checks_all_hashes_before_detector(tmp_path):
    m = image_manifest(tmp_path)
    with pytest.raises(ValueError, match='consent'):
        run_backend(m, {}, mode='candidate')
    Path(m['samples'][-1]['image_evidence']['path']).write_bytes(b'changed synthetic image')
    with pytest.raises(ValueError, match='hash'):
        run_backend(m, {}, mode='candidate', consent_local=True,
                    detector_factory=lambda *a: pytest.fail('detector loaded before validation'))


def test_derivation_optin_hash_and_bounded_decode(tmp_path, monkeypatch):
    import cv2
    source = tmp_path/'synthetic-source'
    source.write_bytes(b'synthetic media placeholder')
    m = create_manifest({'sha256': file_sha(source), 'duration': 140., 'filename': 'SYNTHETIC'})
    with pytest.raises(ValueError, match='consent'):
        derive_frames(m, source, tmp_path/'denied')
    calls = []
    monkeypatch.setattr(cv2, 'VideoCapture', lambda *a: SimpleNamespace(isOpened=lambda: True,
        set=lambda prop, time: calls.append(time), read=lambda: (True, np.zeros((20, 20, 3), np.uint8)),
        get=lambda prop: None, release=lambda: None))
    derived = derive_frames(m, source, tmp_path/'derived', consent_local=True)
    assert len(calls) == 14 and all(s['image_evidence']['consent_local'] for s in derived['samples'])
    assert derived['source_hash_basis'] == 'rehash_local_media_before_derivation'
    assert derived['samples'][0]['human']['bodies'] is None
    with pytest.raises(FileExistsError):
        derive_frames(m, source, tmp_path/'derived', consent_local=True)
    source.write_bytes(b'different source')
    with pytest.raises(ValueError, match='hash mismatch'):
        derive_frames(m, source, tmp_path/'mismatch', consent_local=True)


def test_body_without_face_cannot_merge_real_reid():
    observations = [dict(track_id=t, time=i*10+j, scene_id=t, body_visible=True,
                         face_visible=False, face_embedding=None, body_detection_source='yolo')
                    for i, t in enumerate(('A', 'B')) for j in range(3)]
    reid = build_person_identities({'observations': observations}, {})['data']
    assert reid['tracklet_to_person']['A'] != reid['tracklet_to_person']['B']
    assert not any(d.get('accepted') for d in reid['merge_decisions'])


def test_cli_offline_manifest_compare_exclusive_output(tmp_path):
    script = Path(__file__).resolve().parents[2]/'scripts/dev/body_ab_stage58.py'
    metadata = tmp_path/'metadata.json'
    metadata.write_text(json.dumps({'sha256': 'a'*64, 'duration': 140., 'filename': 'SYNTHETIC'}))
    output = tmp_path/'manifest.json'
    cmd = [sys.executable, '-B', str(script), 'manifest', '--source-metadata', str(metadata), '--output', str(output)]
    completed = subprocess.run(cmd, capture_output=True, text=True)
    assert completed.returncode == 0, completed.stderr
    assert json.loads(output.read_text())['samples'][0]['human']['bodies'] is None
    assert subprocess.run(cmd, capture_output=True).returncode == 2
    m = manifest()
    for name, value in (('m', m), ('a', run(m, 'baseline')), ('b', run(m, 'candidate'))):
        (tmp_path/(name+'.json')).write_text(json.dumps(value))
    completed = subprocess.run([sys.executable, '-B', str(script), 'compare', '--manifest', str(tmp_path/'m.json'),
        '--baseline', str(tmp_path/'a.json'), '--candidate', str(tmp_path/'b.json'), '--output', str(tmp_path/'report.json')],
        capture_output=True, text=True)
    assert completed.returncode == 0, completed.stderr
    assert json.loads((tmp_path/'report.json').read_text())['status'] == 'NOT_MEASURED'
