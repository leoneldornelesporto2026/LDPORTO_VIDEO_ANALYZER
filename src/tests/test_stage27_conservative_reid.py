"""Offline synthetic geometry/labels, never measurements of real people."""
import json
import math

import numpy as np
import pytest

from ldporto.person_reid import build_person_identities, _buckets
from ldporto.identity_goldset import compare_identity_annotations, sample_reid_pairs


def track(tid, start, vector, **extras):
    return [dict(track_id=tid, person_id='P_'+tid, time=start+i,
                 scene_id='SCENE_'+tid, face_visible=True, face_embedding=vector,
                 **extras) for i in range(3)]


def run(rows, cfg=None):
    return build_person_identities({'observations': rows}, cfg)['data']


def angle(degrees):
    return [math.cos(math.radians(degrees)), math.sin(math.radians(degrees))]


def test_same_person_across_cuts_ignores_screen_position():
    result = run(track('a', 0, angle(15), bbox={'x': 0.0}) +
                 track('b', 10, angle(17), bbox={'x': 0.9}))
    assert result['tracklet_to_person']['a'] == result['tracklet_to_person']['b']
    pairs = result['review_pairs']
    assert len(pairs) == 1 and pairs[0]['decision_kind'] == 'merge'
    assert pairs[0]['annotation_same_person'] is None
    assert pairs[0]['image_evidence'] is None
    json.dumps(result, allow_nan=False)


def test_lookalikes_and_low_margin_stable_return_abstains():
    result = run(track('a', 0, angle(10)) + track('b', 0, angle(12)) +
                 track('c', 10, angle(11)))
    assert len(set(result['tracklet_to_person'].values())) == 3
    decisions = [d for d in result['merge_decisions'] if d['tracklet_id'] == 'c']
    assert decisions and all(not d['accepted'] for d in decisions)
    assert all(d['margin'] < d['required_margin'] for d in decisions)
    assert {'temporal_veto', 'abstention'} <= {p['decision_kind'] for p in result['review_pairs']}


def test_stronger_competitor_outside_buckets_blocks_indexed_merge():
    a = np.ones(128)
    b = a.copy()
    for band in range(4):
        index = (band * 29) % 128
        a[index], b[index] = .0001, -.0001
    assert not set(_buckets(a)) & set(_buckets(b))
    result = run(track('a', 0, a.tolist()) + track('b', 0, b.tolist()) +
                 track('c', 10, a.tolist()))
    assert result['tracklet_to_person']['c'] not in (
        result['tracklet_to_person']['a'], result['tracklet_to_person']['b'])


def test_simultaneous_nearest_never_falls_back_to_runnerup():
    result = run(track('a', 0, angle(5)) + track('b', 0, angle(55)) +
                 track('c', 0, angle(5)))
    assert len(set(result['tracklet_to_person'].values())) == 3
    assert any(d.get('temporal_conflict') for d in result['merge_decisions'] if d['tracklet_id'] == 'c')


def test_cluster_drift_cannot_chain_weak_links():
    result = run(track('a', 0, angle(5)) + track('b', 10, angle(55)) +
                 track('c', 20, angle(80)))
    mapping = result['tracklet_to_person']
    assert mapping['a'] == mapping['b']
    assert mapping['c'] != mapping['a']
    rejected = [d for d in result['merge_decisions'] if d['tracklet_id'] == 'c']
    assert rejected[0]['embedding_similarity'] > .55
    assert rejected[0]['cluster_min_similarity'] < .55


@pytest.mark.parametrize('vector,quality', [
    ([1, 0], {'embedding_eligible': False, 'rejection_reasons': ['face_blurred']}),
    ('invalid', None), ([float('nan'), 0], None), ([0, 0], None),
])
def test_bad_embedding_cannot_merge_or_crash(vector, quality):
    result = run(track('a', 0, [1, 0]) + track('b', 10, vector, face_quality=quality))
    assert result['tracklet_to_person']['a'] != result['tracklet_to_person']['b']
    assert result['metrics']['reid_embedding_rejected_sample_count'] == 3


def annotations(predictions):
    return {'source_sha256': 'a'*64, 'protocol_sha256': 'b'*64,
            'annotations': [dict(track_id=tid, annotation_label=label,
                                 annotation_status='verified', predicted_person_id=prediction)
                            for tid, label, prediction in zip('abc', ('A', 'A', 'B'), predictions)]}


def test_fragmentation_improvement_requires_acceptable_false_merges():
    before = annotations(('P1', 'P2', 'P3'))
    safe = compare_identity_annotations(before, annotations(('P1', 'P1', 'P3')))
    unsafe = compare_identity_annotations(before, annotations(('P1', 'P1', 'P1')))
    assert safe['improvement_accepted'] is True
    assert safe['after']['false_merge_pairs'] == 0
    assert safe['after']['false_split_pairs'] == 0
    assert unsafe['improvement_accepted'] is False
    assert unsafe['after']['false_merge_pairs'] == 2


def test_comparison_requires_real_review_and_comparable_records():
    before, after = annotations(('1', '2', '3')), annotations(('1', '1', '3'))
    after['source_sha256'] = 'c'*64
    assert compare_identity_annotations(before, after)['improvement_accepted'] is None
    after['source_sha256'] = before['source_sha256']
    after['annotations'][0]['annotation_status'] = 'unreviewed'
    assert compare_identity_annotations(before, after)['improvement_accepted'] is None
    assert sample_reid_pairs({}, limit=5) == []


def test_gallery_bound_abstains_instead_of_accepting_indexed_candidate(monkeypatch):
    import ldporto.person_reid as reid
    monkeypatch.setattr(reid, '_face_neighbors', lambda *args: [])
    result = run(track('a', 0, angle(10)) + track('b', 10, angle(10)))
    assert result['tracklet_to_person']['a'] != result['tracklet_to_person']['b']


def test_anchor_retained_when_template_history_is_bounded():
    rows = track('000', 0, angle(5))
    for i in range(1, 35):
        rows += track(f'{i:03}', i*10, angle(45))
    result = run(rows)
    assert len(result['identities']) == 1
    templates = result['identities'][0]['face_embedding_templates']
    assert len(templates) == 32
    assert np.allclose(templates[0], angle(5))


def test_cli_exports_pairs_and_guarded_comparison_offline(tmp_path):
    import subprocess
    import sys
    from pathlib import Path
    source = tmp_path/'source'
    source.mkdir()
    (source/'07_people_tracking.json').write_text(json.dumps({
        'observations': track('a', 0, angle(10)) + track('b', 10, angle(12))}), encoding='utf-8')
    comparison = tmp_path/'comparison.json'
    comparison.write_text(json.dumps({'before': annotations(('1', '2', '3')),
                                     'after': annotations(('1', '1', '3'))}), encoding='utf-8')
    output = tmp_path/'audit'
    script = Path(__file__).resolve().parents[2]/'scripts/dev/audit_tracking_s4.py'
    completed = subprocess.run([sys.executable, '-B', str(script), str(source),
        '--output', str(output), '--identity-comparison-records', str(comparison)],
        capture_output=True, text=True)
    assert completed.returncode == 0, completed.stderr
    report = json.loads((output/'tracking_s4_report.json').read_text(encoding='utf-8'))
    assert report['reid_review_pairs'][0]['annotation_status'] == 'unreviewed'
    assert report['identity_comparison']['improvement_accepted'] is True
    assert (output/'identity_annotations.csv').exists()
