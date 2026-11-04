"""Offline stage 29 fixtures; invented labels test logic, not human accuracy."""
from copy import deepcopy

import numpy as np
import pytest

from ldporto.active_speaker import build_active_speaker
from ldporto.asd_backend import available_backends
from ldporto.config import DEFAULTS
from ldporto.speaker_goldset import evaluate_goldset
from ldporto.speaker_roles import lag_consistency
from ldporto.speaker_signals import mouth_audio_evidence
from test_s5_speaker_person_active import fixture


def run(diar, vision, raw):
    return build_active_speaker(diar, vision, raw, DEFAULTS['active_speaker'])['data']


def test_listener_moving_mouth_and_explicit_reaction_are_not_speech():
    diar, vision, raw = fixture()
    for observation in vision['observations']:
        if observation['person_id'] == 'P2':
            observation.update(mouth_activity=.9, lip_opening=.8)
    data = run(diar, vision, raw)
    roles = [role for row in data['intervals'] if row['active_person']
             for role in row['person_roles'] if role['person_id'] == 'P2']
    assert roles and all(role['role'] == 'LISTENING' for role in roles)
    for observation in vision['observations']:
        if observation['person_id'] == 'P2':
            observation.update(reaction_type='laugh', reaction_detected=True)
    reacting = run(diar, vision, raw)
    assert any(role['role'] == 'REACTING' for row in reacting['intervals']
               for role in row['person_roles'] if role['person_id'] == 'P2')
    assert not any(row['active_person'] == 'P2' for row in reacting['intervals'])


def test_offscreen_voice_does_not_use_listener_mouth_motion():
    diar, vision, raw = fixture()
    for frame in vision['frames']:
        frame['visible_people'] = ['P2']
    data = run(diar, vision, raw)
    assert data['mapping_summary'][0]['person_id'] == 'P1'
    assert all(row['active_person'] is None for row in data['intervals'])
    assert any(row['active_speaker_reason'] == 'mapped_person_offscreen' for row in data['intervals'])


@pytest.mark.parametrize('field,value', [('sample_count', 3), ('visibility_coverage', .1),
                                       ('track_stability', .1), ('correlation', .1),
                                       ('audio_activity_rms', 0.)])
def test_weak_second_window_cannot_supply_temporal_vote(field, value):
    diar, vision, raw = fixture()
    raw[1]['candidates'][0][field] = value
    report = lag_consistency(raw, 'S1', 'P1', DEFAULTS['active_speaker'], diar['turns'])
    assert report['independent_windows'] == 1
    assert not report['consistent']
    assert not any(row['active_person'] for row in run(diar, vision, raw)['intervals'])


def test_rival_listener_sync_prevents_second_vote():
    diar, vision, raw = fixture()
    raw[1]['candidates'][1]['correlation'] = .9
    assert lag_consistency(raw, 'S1', 'P1', DEFAULTS['active_speaker'])['independent_windows'] == 1
    assert not any(row['active_person'] for row in run(diar, vision, raw)['intervals'])


def test_unmarked_interruption_invalidates_whole_mixdown_window():
    diar, vision, raw = fixture()
    diar['turns'].append(dict(start=1, end=1.2, speaker='S2'))
    data = run(diar, vision, raw)
    summary = next(row for row in data['mapping_summary'] if row['speaker_id'] == 'S1')
    assert summary['positive_windows'] == 1 and summary['person_id'] is None
    assert not any(row['active_person'] for row in data['intervals'])
    assert raw[0].get('overlap') is None  # Caller/cache evidence is not mutated.


def test_two_speakers_with_independent_solo_windows_and_simultaneous_speech():
    diar, vision, raw = fixture()
    # S1 has two independent solo windows, S2 has two more; their final turn overlaps.
    diar['turns'] = [dict(start=0, end=2, speaker='S1'), dict(start=2, end=4, speaker='S2'),
                     dict(start=4, end=6, speaker='S1'), dict(start=5, end=6, speaker='S2')]
    base = deepcopy(raw[0])
    raw = []
    for index, (start, end, speaker, person) in enumerate(
            [(0, 1, 'S1', 'P1'), (1, 2, 'S1', 'P1'),
             (2, 3, 'S2', 'P2'), (3, 4, 'S2', 'P2'), (4, 6, 'S1', 'P1')]):
        row = deepcopy(base)
        row.update(start=start, end=end, speaker_id=speaker, evidence_window_id=f'W{index}')
        row['candidates'] = [dict(base['candidates'][0], person_id=person)]
        raw.append(row)
    data = run(diar, vision, raw)
    assert {r['speaker_id']: r['person_id'] for r in data['mapping_summary']} == {'S1': 'P1', 'S2': 'P2'}
    assert any(r['active_person'] == 'P1' for r in data['intervals'])
    assert any(r['active_person'] == 'P2' for r in data['intervals'])
    simultaneous = [r for r in data['intervals'] if r['overlap']]
    assert simultaneous and all(r['active_person'] is None for r in simultaneous)
    assert all(r['active_speaker_reason'] == 'simultaneous_audio_ambiguous' for r in simultaneous)
    assert not any(r['active_person'] for r in data['intervals'] if r['start'] >= 4)


def test_duplicate_samples_and_silence_do_not_create_signal():
    rows = [dict(time=.2+i*.2, lip_opening=.02+i*.02, scene_id='SH1') for i in range(4)]
    assert mouth_audio_evidence(rows*4, np.ones(1200, dtype=np.float32), 1000, 0) is None
    rows += [dict(time=1+i*.2, lip_opening=.05+i*.03, scene_id='SH1') for i in range(4)]
    assert mouth_audio_evidence(rows, np.zeros(2400, dtype=np.float32), 1000, 0) is None


def annotation(start, role, expected, predicted, status='verified'):
    return dict(speaker_id='S1', start=start, end=start+1, annotation_status=status,
                human_role=role, human_person_id=expected, predicted_active_person=predicted)


def test_benchmark_counts_abstention_wrong_identity_and_excluded_labels():
    # Synthetic annotations deliberately include errors. No real human labels claimed.
    rows = [annotation(0, 'speaking', 'P1', 'P1'), annotation(1, 'speaking', 'P1', 'P2'),
            annotation(2, 'speaking', 'P1', None), annotation(3, 'listening', 'P2', None),
            annotation(4, 'reacting', 'P2', 'P2'), annotation(5, 'offscreen', '', None),
            annotation(6, 'uncertain', '', None), annotation(7, '', '', None, 'unreviewed')]
    result = evaluate_goldset(rows)
    assert result['eligible_windows'] == 6
    assert result['wrong_person_windows'] == 1
    assert result['false_positive_or_wrong_person'] == 2
    assert result['correct_abstentions'] == 2
    assert result['abstained_windows'] == 3
    assert result['abstention_rate'] == .5
    assert result['recall'] == pytest.approx(1/3)
    assert result['error_rate_when_predicting'] == pytest.approx(2/3)
    assert evaluate_goldset([])['abstention_rate'] is None


@pytest.mark.parametrize('start', [0, .5])
def test_benchmark_rejects_recycled_or_overlapping_same_speaker_window(start):
    with pytest.raises(ValueError, match='independentes'):
        evaluate_goldset([annotation(0, 'speaking', 'P1', 'P1'),
                          annotation(start, 'speaking', 'P1', 'P1')])


def test_neural_candidates_remain_unimplemented_and_not_default():
    for name in ('lr_asd', 'talknet'):
        capability = available_backends()[name]
        assert not capability['default'] and not capability['adapter_implemented']
        assert capability['requires_local_benchmark']
