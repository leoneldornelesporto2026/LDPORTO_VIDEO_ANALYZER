"""R2 completion: identity safety and exact-neighbor retrieval regression."""
import numpy as np
from ldporto.person_reid import build_person_identities, _buckets


def row(tid, pid, when, vector, scene='S1'):
    return {'track_id': tid, 'person_id': pid, 'time': when, 'scene_id': scene,
            'face_visible': vector is not None, 'face_embedding': vector}


def run(rows):
    return build_person_identities({'people': [], 'observations': rows})['data']


def test_stable_track_fallback_crosses_hash_boundary_without_position():
    a = np.ones(128); b = a.copy()
    for band in range(4):
        index = (band * 29) % 128
        a[index], b[index] = 0.0001, -0.0001
    assert not set(_buckets(a)) & set(_buckets(b))
    rows = [row('a','P1',t,a.tolist()) for t in [0, 1, 2]]
    rows += [row('b','P2',t,b.tolist(),'S2') for t in [10,11,12]]
    result=run(rows)
    assert result['tracklet_to_person']['a']==result['tracklet_to_person']['b']
    assert result['metrics']['stable_exact_fallback_accepted'] == 1
    assert any(x.get('candidate_search')=='strict_full_face_fallback' and x['accepted'] for x in result['merge_decisions'])


def test_micro_ambiguous_nearest_two_persons_is_not_assigned():
    a = np.ones(128).tolist()
    # Two concurrent, independently rooted people with identical embedding:
    # both are plausible matches. Micro cannot choose just one arbitrarily.
    rows = [row('a','P1',t,a) for t in [0,1,2]]
    rows += [row('b','P2',t,a) for t in [0.3,1.3,2.3]]
    rows += [row('micro','P3',t,a,'S2') for t in [10,10.15]]
    result=run(rows)
    assert result['tracklet_to_person']['micro'] is None
    assert result['metrics']['micro_reid_attachment_count']==0


def test_nearest_conflict_does_not_let_runnerup_win():
    a = np.ones(128).tolist()
    b = np.ones(128); b[0] = -1.0
    # P1 wins but is on-screen at the same time, so cannot be same person;
    # fallback to weaker P2 would be an ungrounded identity assumption.
    rows=[row('a','P1',t,a) for t in [0,1,2]]
    rows += [row('b','P2',t,b.tolist()) for t in [0.2,1.2,2.2]]
    rows += [row('micro','P3',t,a,'S2') for t in [1.5,1.6]]
    result=run(rows)
    assert result['tracklet_to_person']['micro'] is None


def test_single_face_sample_has_stricter_threshold():
    a = np.ones(128, dtype=float)
    b = a.copy(); b[:22] *= -1
    # normalized dot around .66; avoid over-fitting exact synthetic cosine.
    rows=[row('a','P1',t,a.tolist()) for t in [0,1,2]]
    rows += [row('micro','P2',10,b.tolist(),'S2')]
    result=run(rows)
    assert result['tracklet_to_person']['micro'] is None
    assert result['metrics']['micro_reid_attached_one_sample_count']==0


def test_embedding_free_micro_unresolved_and_evidence_preserved():
    a = np.ones(128).tolist()
    rows = [row('a','P1',t,a) for t in [0,1,2]]
    rows += [row('micro','P2',10,None,'S2')]
    result=run(rows)
    assert result['tracklet_to_person']['micro'] is None
    assert result['metrics']['raw_track_count']==2
    assert result['metrics']['micro_without_embedding_count']==1
    assert len(result['tracklets'])==2
