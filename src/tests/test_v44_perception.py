from copy import deepcopy

from ldporto.config import DEFAULTS
from ldporto.active_speaker import build_active_speaker
from test_v43_perception import affinity_fixture


def test_tracker_counter_reconciliation_distinguishes_people_tracklets_and_log_time():
    from ldporto.baseline_audit import reconcile_tracking_counters
    people = [{'person_id': 'P1', 'first_seen': 0}, {'person_id': 'P2', 'first_seen': 9}]
    tracks = [{'source_person_ids': ['P1'], 'first_seen': 0, 'qualified': True},
              {'source_person_ids': ['P1'], 'first_seen': 5, 'qualified': True},
              {'source_person_ids': ['P2'], 'first_seen': 9, 'qualified': False}]
    result = reconcile_tracking_counters(people, tracks, 8, 1)
    assert result['logged_raw_person_hypotheses'] == 1
    assert result['final_raw_person_hypotheses'] == 2
    assert result['final_raw_tracklets'] == 3
    assert result['additional_tracklets_for_existing_hypotheses'] == 1
    assert result['valid_tracklets'] == 2 and result['micro_tracklets'] == 1
    assert result['log_counter_verified'] is True


def test_every_unresolved_speaker_has_observed_diagnostic_reason():
    diarization, vision, raw = affinity_fixture()
    for obs in vision['observations']:
        obs['mouth_activity'] = None
    result = build_active_speaker(diarization, vision, [], DEFAULTS['active_speaker'])['data']
    diagnostics = result['speaker_person_diagnostics']
    assert diagnostics[0]['person_id'] is None
    assert 'MOUTH_SIGNAL_UNAVAILABLE' in diagnostics[0]['reason_codes']
    assert diagnostics[0]['speech_duration'] == 6
    assert diagnostics[0]['mapping_confidence'] is None


def test_negative_correlation_is_retained_even_when_lower_bound_is_negative():
    diarization, vision, raw = affinity_fixture()
    for window in raw:
        window['candidates'][1]['correlation_lower_bound_proxy'] = -.7
    result = build_active_speaker(diarization, vision, raw, DEFAULTS['active_speaker'])['data']
    pair = next(row for row in result['affinity'] if row['person_id'] == 'P2')
    assert pair['negative_windows'] == 2


def test_noisy_negative_window_with_confidence_interval_crossing_zero_is_not_contradiction():
    diarization, vision, raw = affinity_fixture()
    raw.append({'start': 6, 'end': 9, 'speaker_id': 'S1', 'evidence_window_id': 'NOISE',
                'candidates': [{'person_id': 'P1', 'correlation': -.3, 'sample_count': 8,
                                'correlation_lower_bound_proxy': -.8}]})
    result = build_active_speaker(diarization, vision, raw, DEFAULTS['active_speaker'])['data']
    assert result['mapping_summary'][0]['person_id'] == 'P1'
    assert next(row for row in result['affinity'] if row['person_id'] == 'P1')['weak_negative_windows'] == 1


def test_weak_positive_correlation_with_nonpositive_lower_bound_is_not_accepted():
    diarization, vision, raw = affinity_fixture()
    for window in raw:
        window['candidates'][0]['correlation_lower_bound_proxy'] = -.1
    result = build_active_speaker(diarization, vision, raw, DEFAULTS['active_speaker'])['data']
    assert result['mapping_summary'][0]['person_id'] is None


def test_visibility_fraction_is_corroboration_not_an_audio_correlation_multiplier():
    diarization, vision, raw = affinity_fixture((.65, -.3))
    for window in raw:
        window['candidates'][0]['visibility_coverage'] = .75
        window['candidates'][0]['face_visibility'] = 1
    result = build_active_speaker(diarization, vision, raw, DEFAULTS['active_speaker'])['data']
    assert result['mapping_summary'][0]['person_id'] == 'P1'


def test_active_state_distinguishes_prior_from_contemporary_audio_evidence():
    diarization, vision, raw = affinity_fixture()
    result = build_active_speaker(diarization, vision, raw, DEFAULTS['active_speaker'])['data']
    assert all(row['active_speaker_state'] in {'CONFIRMED', 'PROBABLE', 'UNCERTAIN', 'OFFSCREEN'}
               for row in result['intervals'])
    assert all(row['active_speaker_reason'] for row in result['intervals'])
    assert not any(row['active_speaker_state'] == 'CONFIRMED' for row in result['intervals'])
    vision['observations'] = [row for row in vision['observations'] if row['person_id'] != 'P1']
    offscreen = build_active_speaker(diarization, vision, raw, DEFAULTS['active_speaker'])['data']
    assert any(row['active_speaker_state'] == 'OFFSCREEN' for row in offscreen['intervals'])


def test_fragmentation_profile_preserves_face_only_and_missing_embeddings():
    from ldporto.perception_diagnostics import tracking_profile
    rows = [{'track_id': 'T1', 'person_id': 'P1', 'time': t, 'scene_id': 'S1',
             'face_visible': True, 'body_visible': False, 'face_embedding': None}
            for t in (0, .5, 1)]
    profile = tracking_profile(rows, [{'start': 0, 'end': 60}], 60)
    assert profile['bins'][0]['face_only_tracks'] == 1
    assert profile['bins'][0]['embedding_missing_rate'] == 1
    assert profile['raw_tracklets'] == 1


def test_lag_tolerant_signal_requires_audio_and_varying_mouth():
    import numpy as np
    from ldporto.speaker_signals import mouth_audio_evidence
    rate = 16000
    times = np.arange(rate * 4) / rate
    audio = (.2 + .1 * np.sin(2 * np.pi * 2 * times)) * np.sin(2 * np.pi * 440 * times)
    rows = [{'time': float(t), 'lip_opening': .2 + .1 * np.sin(2 * np.pi * 2 * (t + .08)),
             'track_id': 'T1', 'scene_id': 'S1'} for t in np.arange(.3, 3.7, .12)]
    result = mouth_audio_evidence(rows, audio, rate, 0)
    assert result['correlation'] > .9 and result['audio_lag_seconds'] == .08
    assert result['correlation_lower_bound_proxy'] > 0
    assert mouth_audio_evidence(rows, np.zeros_like(audio), rate, 0) is None
    assert mouth_audio_evidence([{**row, 'lip_opening': .2} for row in rows], audio, rate, 0) is None
