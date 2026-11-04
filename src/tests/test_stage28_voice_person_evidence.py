"""Stage 28 synthetic evidence: no media, model, or real-person labels."""
import numpy as np
import pytest

from ldporto.active_speaker import build_active_speaker
from ldporto.config import DEFAULTS
from ldporto.speaker_roles import evidence_spans, lag_consistency
from ldporto.speaker_signals import mouth_audio_evidence
from test_s5_speaker_person_active import fixture


def run(diar, vision, raw, **options):
    cfg = {**DEFAULTS['active_speaker'], **options}
    return build_active_speaker(diar, vision, raw, cfg)['data']


def test_known_voice_offscreen_keeps_only_provisional_identity():
    diar, vision, raw = fixture()
    diar['turns'][0]['end'] = 9
    for stamp in (6.1, 6.6, 7.1, 7.6, 8.1, 8.6):
        vision['frames'].append(dict(time=stamp, scene_id='SH2', visible_people=['P2']))
        vision['observations'].append(dict(time=stamp, scene_id='SH2', person_id='P2', face_visible=True))
    vision['scene_intervals'] = [dict(start=0, end=6, scene_id='SH1'), dict(start=6, end=9, scene_id='SH2')]
    data = run(diar, vision, raw)
    assert data['mapping_summary'][0]['person_id'] == 'P1'
    rows = [r for r in data['intervals'] if r['start'] >= 6]
    assert rows and all(r['person_id'] is None and r['active_person'] is None for r in rows)
    assert all(r['global_mapped_person_id'] == 'P1' for r in rows)
    assert all(r['association_status'] == 'PROVISIONAL' for r in rows)
    assert any(r['active_speaker_state'] == 'OFFSCREEN' for r in rows)


def test_duplicate_window_id_cannot_establish_lag_consensus():
    _, _, raw = fixture()
    raw[1]['evidence_window_id'] = raw[0]['evidence_window_id']
    report = lag_consistency(raw, 'S1', 'P1', DEFAULTS['active_speaker'])
    assert report['independent_windows'] == 1
    assert report['consistent'] is False


def test_overlapping_windows_are_not_independent_support():
    diar, vision, raw = fixture()
    raw[1].update(start=1, end=4)
    data = run(diar, vision, raw)
    assert data['mapping_summary'][0]['evidence_windows'] == 1
    assert data['mapping_summary'][0]['person_id'] is None


def test_support_seconds_intersect_actual_speaker_turns():
    diar, vision, raw = fixture()
    diar['turns'] = [dict(start=1, end=2, speaker='S1'), dict(start=4, end=5, speaker='S1')]
    data = run(diar, vision, raw)
    assert data['mapping_summary'][0]['support_seconds'] == 2
    assert data['metrics']['diarized_speech_seconds'] == 2
    assert all(1 <= r['start'] < r['end'] <= 2 or 4 <= r['start'] < r['end'] <= 5 for r in data['intervals'])


def test_windows_outside_diarization_cannot_create_identity_or_sync():
    diar, vision, raw = fixture()
    diar['turns'] = [dict(start=10, end=12, speaker='S1')]
    data = run(diar, vision, raw)
    summary = data['mapping_summary'][0]
    assert summary['person_id'] is None and summary['support_seconds'] == 0
    assert summary['audio_video_sync']['independent_windows'] == 0


def test_measured_mouth_span_uses_audio_lag_and_union_of_duplicate_turns():
    row = dict(start=0, end=3, speaker_id='S1')
    candidate = dict(mouth_start=.5, mouth_end=2, audio_lag_seconds=.1)
    turns = [dict(start=1, end=1.5, speaker='S1')] * 2
    from ldporto.temporal import union_duration
    assert union_duration(evidence_spans(row, candidate, turns)) == .5
    assert evidence_spans(row, candidate) == [dict(start=.6, end=2.1)]
    candidate['mouth_end'] = None
    assert evidence_spans(row, candidate) == []


def test_sparse_frame_coverage_has_exact_gap_boundaries():
    diar = {'turns': [dict(start=0, end=2, speaker='S1')]}
    vision = {'people': [dict(person_id='P1')],
              'frames': [dict(time=.5, visible_people=['P1'], scene_id='SH1')],
              'observations': [dict(time=.5, person_id='P1', face_visible=True, scene_id='SH1')]}
    raw = [dict(start=0, end=2, speaker_id='S1', person_id='P1', method='user_verified')]
    data = run(diar, vision, raw, max_observation_gap_seconds=.1)
    assert data['metrics']['known_person_speech_seconds'] == pytest.approx(.2)
    assert data['metrics']['no_contemporary_frame_speech_seconds'] == pytest.approx(1.8)
    assert data['speaker_person_diagnostics'][0]['visible_overlap'] == pytest.approx(.2)


def test_wide_shot_and_speech_without_face_are_observed_without_match():
    diar, vision, _ = fixture()
    for frame in vision['frames']:
        frame['visible_people'] = []
        frame['shot_type'] = 'wide'
    data = run(diar, vision, [])
    assert all(r['person_id'] is None and r['active_person'] is None for r in data['intervals'])
    assert data['metrics']['observed_wide_shot_speech_seconds'] > 5
    assert data['metrics']['speech_without_resolved_face_seconds'] > 5
    report = data['speaker_person_diagnostics'][0]
    assert report['speech_without_resolved_face_seconds'] > 5
    # Missing shot labels are not inferred as wide from the number of people.
    for frame in vision['frames']:
        frame.pop('shot_type')
    assert run(diar, vision, [])['metrics']['observed_wide_shot_speech_seconds'] == 0


def test_wrong_source_shot_never_confirms_local_speech():
    diar, vision, raw = fixture()
    for row in raw:
        row['candidates'][0]['source_shot_id'] = 'ANOTHER_SHOT'
    data = run(diar, vision, raw)
    assert data['mapping_summary'][0]['person_id'] == 'P1'
    assert not any(r['active_person'] for r in data['intervals'])
    assert any(r['contemporary_sync']['reason'] == 'no_same_shot_face_at_lag_adjusted_time' for r in data['intervals'])


def test_constant_large_lag_is_not_valid_sync():
    _, _, raw = fixture()
    for row in raw:
        row['candidates'][0]['audio_lag_seconds'] = .5
    assert not lag_consistency(raw, 'S1', 'P1', DEFAULTS['active_speaker'])['consistent']


def test_visible_face_confidence_without_audio_evidence_never_maps_voice():
    diar, vision, raw = fixture()
    for row in raw:
        row.update(method='single_visible_face', person_id='P1', confidence=.99,
                   candidates=[dict(person_id='P1', confidence=.99)])
    data = run(diar, vision, raw)
    assert data['mapping_summary'][0]['person_id'] is None
    assert not any(r['person_id'] or r['active_person'] for r in data['intervals'])


def test_measured_support_excludes_unobserved_window_edges():
    diar, vision, raw = fixture()
    for row in raw:
        row['candidates'][0].update(mouth_start=row['start']+.5, mouth_end=row['end']-.5)
    data = run(diar, vision, raw)
    assert data['mapping_summary'][0]['support_seconds'] == pytest.approx(4)
    assert not any(r['active_person'] for r in data['intervals'] if r['end'] <= .54)


def test_signal_exports_span_of_matched_samples_only():
    rate = 1000
    audio = np.zeros(2400, dtype=np.float32)
    rows = []
    for index in range(10):
        stamp = .2 + index*.2
        amplitude = .05 + (index % 3)*.05
        audio[round((stamp-.08)*rate):round((stamp+.08)*rate)] = amplitude
        rows.append(dict(time=stamp, lip_opening=amplitude, scene_id='SH1'))
    signal = mouth_audio_evidence(rows, audio, rate, 0, lags=(0.,))
    assert signal is not None
    assert signal['mouth_start'] == pytest.approx(.2)
    assert signal['mouth_end'] == pytest.approx(2)
    assert signal['sample_count'] == 10
    assert signal['temporal_support_basis'] == 'matched_mouth_sample_span'
