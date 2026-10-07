"""R2: recovery must never substitute screen position for facial evidence."""

import numpy as np
from ldporto.person_reid import _buckets, build_person_identities


def _row(track, person, time, embedding, scene):
    return {"track_id": track, "person_id": person, "time": time,
            "scene_id": scene, "face_visible": True, "face_embedding": embedding}


def test_cross_shot_micro_face_recovers_when_banded_index_misses_neighbor():
    # The 4 band signatures disagree at near-zero coordinates although the
    # complete unit-normalized facial templates remain almost identical.
    original = np.ones(128)
    changed = original.copy()
    for band in range(4):
        index = (band * 29) % 128
        original[index] = 0.0001
        changed[index] = -0.0001
    assert not (set(_buckets(original)) & set(_buckets(changed)))
    observations = [_row('STABLE', 'P1', t, original.tolist(), 'S1') for t in (0., 1., 2.)]
    observations += [_row('MICRO', 'P2', t, changed.tolist(), 'S2') for t in (10., 10.15)]
    result = build_person_identities({"people": [], "observations": observations})['data']
    assert result['tracklet_to_person']['MICRO'] == result['tracklet_to_person']['STABLE']
    assert result['metrics']['micro_retrieval_fallback_accepted'] == 1
    assert any(decision.get('accepted') and decision.get('candidate_search') == 'strict_nearest_face_fallback'
               for decision in result['merge_decisions'] if decision['tracklet_id'] == 'MICRO')


def test_fallback_never_accepts_simultaneous_micro_tracklet():
    original = np.ones(128)
    changed = original.copy()
    for band in range(4):
        original[(band * 29) % 128] = 0.0001
        changed[(band * 29) % 128] = -0.0001
    observations = [_row('STABLE', 'P1', t, original.tolist(), 'S1') for t in (0., 1., 2.)]
    observations += [_row('MICRO', 'P2', t, changed.tolist(), 'S2') for t in (1.1, 1.2)]
    result = build_person_identities({"people": [], "observations": observations})['data']
    assert result['tracklet_to_person']['MICRO'] is None
    assert result['metrics']['micro_retrieval_fallback_accepted'] == 0
