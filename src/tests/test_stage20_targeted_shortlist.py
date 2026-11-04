"""Offline selection, budgeting and evidence contracts; no model inference."""
from copy import deepcopy
import logging

import pytest

from ldporto.config import load_config
from ldporto.core import Context
from ldporto.targeted_asr import run_targeted_repair, select_repair_windows
from ldporto.subtitle_review import review_selected_clips


def candidate():
    return {'moment_id': 'FINAL', 'start': 10, 'end': 40,
            'ideal_start': 10, 'ideal_end': 40, 'default_shortlist_eligible': False}


def context(tmp_path, **settings):
    cfg = load_config()
    cfg['transcription'].update(settings)
    return Context(tmp_path / 'source.mp4', tmp_path / 'output', cfg, 'FIXTURE', logging.getLogger('stage20'))


def test_final_selected_candidate_without_audio_stays_in_dossier(tmp_path, monkeypatch):
    from ldporto import targeted_asr
    monkeypatch.setattr(targeted_asr, 'TranscriptionEngine', lambda *_: pytest.fail('must not load ASR'))
    original = {'words': [], 'segments': []}
    repair = run_targeted_repair(context(tmp_path), {'mono': str(tmp_path / 'absent.wav')},
                                 original, [candidate()], [], [], 50, shortlist_ids=['FINAL'])
    report = review_selected_clips([], [candidate()], ['FINAL'], targeted_report=repair)
    assert repair['selected_candidate_count'] == report['selected_candidate_count'] == 1
    assert repair['status'] == 'pending'
    assert repair['pending_reason'] == 'original_audio_unavailable'
    assert len(repair['unprocessed_regions']) == 2
    assert repair['candidate_coverage'] == {'FINAL': 0}
    assert report['dossier_candidate_count'] == 1
    assert report['candidates']['FINAL']['targeted_asr_status'] == 'pending'
    assert not report['candidates']['FINAL']['publication_ready']
    assert report['candidates']['FINAL']['word_review_fraction'] is None
    assert repair['alternatives'] == [] and original['words'] == []


@pytest.mark.parametrize('settings,reason', [({'targeted_max_regions': 0}, 'region_budget'),
                                           ({'targeted_max_audio_seconds': 0}, 'audio_seconds_budget')])
def test_budget_zero_is_pending_and_records_every_region(tmp_path, settings, reason):
    repair = run_targeted_repair(context(tmp_path, **settings), {}, {'words': []},
                                 [candidate()], [], [], 50, shortlist_ids=['FINAL'])
    assert repair['status'] == 'pending'
    assert repair['selected_candidate_count'] == 1 and repair['audio_seconds'] == 0
    assert {r['reason'] for r in repair['unprocessed_regions']} == {reason}
    assert {r['priority_reason'] for r in repair['unprocessed_regions']} == {'SHORTLIST_HOOK', 'SHORTLIST_PAYOFF'}


def test_question_hook_and_final_have_priority_and_budget_provenance():
    question = {'question_id': 'Q', 'question_start': 22, 'question_end': 24}
    word = {'word_id': 'W', 'word': 'uncertain', 'start': 30, 'end': 31, 'needs_review': True}
    deferred = []
    windows = select_repair_windows([word], [candidate()], [], [question], 50, 3, 12,
                                    shortlist_ids=['FINAL'], diagnostics=deferred)
    assert [w['priority_reason'] for w in windows] == ['SHORTLIST_PAYOFF', 'SHORTLIST_QUESTION', 'SHORTLIST_HOOK']
    assert sum(w['end'] - w['start'] for w in windows) == 12
    assert all('FINAL' in w['evidence_refs'] for w in windows)
    assert deferred[0]['reason'] == 'region_budget'
    assert deferred[0]['word_ids'] == ['W']


def test_ideal_only_range_reproduces_historical_shortlist_s7_mismatch():
    selected = {'moment_id': 'FINAL', 'start': None, 'end': None,
                'ideal_start': 10, 'ideal_end': 40, 'default_shortlist_eligible': True}
    words = [{'word': 'synthetic fixture', 'start': 22, 'end': 23,
              'needs_review': True, 'confidence': .3}]
    windows = select_repair_windows(words, [selected], [], [], 50, 8, 60,
                                    shortlist_ids=['FINAL'], speech_overlaps=[{'start': 32, 'end': 33}])
    report = review_selected_clips(words, [selected], ['FINAL'])
    assert report['selected_candidate_count'] == report['dossier_candidate_count'] == 1
    assert report['candidates']['FINAL']['start'] == 10
    assert report['candidates']['FINAL']['end'] == 40
    assert report['candidates']['FINAL']['word_count'] == 1
    assert {'SHORTLIST_HOOK', 'SHORTLIST_PAYOFF', 'OVERLAPPING_SPEECH',
            'HIGH_VALUE_CANDIDATE'} <= {w['priority_reason'] for w in windows}


@pytest.mark.parametrize('rows,reason', [([], 'selected_candidate_missing'),
                                      ([{'moment_id': 'FINAL', 'start': None, 'end': None}], 'invalid_candidate_range')])
def test_unresolved_selection_never_turns_into_zero_or_success(tmp_path, rows, reason):
    repair = run_targeted_repair(context(tmp_path), {}, {'words': []}, rows, [], [], 50, shortlist_ids=['FINAL'])
    report = review_selected_clips([], rows, ['FINAL'], targeted_report=repair)
    assert repair['status'] == 'pending'
    assert repair['selected_candidate_count'] == report['selected_candidate_count'] == 1
    assert report['dossier_candidate_count'] == 0
    assert report['unresolved_selected_candidates'] == {'FINAL': reason}


def test_extraction_failure_is_pending_not_a_hypothesis(tmp_path, monkeypatch):
    from ldporto import targeted_asr
    source = tmp_path / 'fixture.wav'
    source.write_bytes(b'offline placeholder, not usable audio')
    def unavailable(*args, **kwargs):
        raise RuntimeError('synthetic extraction failure')
    monkeypatch.setattr(targeted_asr, 'ffmpeg_audio', unavailable)
    repair = run_targeted_repair(context(tmp_path), {'mono': str(source)}, {'words': []},
                                 [candidate()], [], [], 50, shortlist_ids=['FINAL'],
                                 recognize=lambda *_: pytest.fail('no extracted audio'))
    assert repair['status'] == 'pending' and repair['alternatives'] == []
    assert repair['candidate_coverage'] == {'FINAL': 0}
    assert {r['reason'] for r in repair['unprocessed_regions']} == {'audio_extraction_unavailable'}


def test_partial_budget_hypotheses_provenance_and_cache_are_preserved(tmp_path, monkeypatch):
    from ldporto import targeted_asr
    source = tmp_path / 'synthetic.wav'
    source.write_bytes(b'synthetic source; extraction and recognition are mocked')
    def extract(source, destination, **kwargs):
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(b'synthetic extracted region')
    monkeypatch.setattr(targeted_asr, 'ffmpeg_audio', extract)
    calls = []
    def recognize(path, offset):
        calls.append(offset)
        return {'words': [{'word': 'fixture alternative', 'start': offset, 'end': offset + 1, 'confidence': .8}]}
    ctx = context(tmp_path, targeted_max_regions=1)
    args = (ctx, {'mono': str(source)}, {'words': []}, [candidate()], [], [], 50)
    first = run_targeted_repair(*args, shortlist_ids=['FINAL'], recognize=recognize)
    cached = run_targeted_repair(*args, shortlist_ids=['FINAL'], recognize=recognize)
    assert first['status'] == cached['status'] == 'partial_pending'
    assert first['candidate_coverage'] == {'FINAL': 1}
    assert len(calls) == 1 and cached['cache_hits'] == 1
    assert first['unprocessed_regions'][0]['priority_reason'] == 'SHORTLIST_HOOK'
    evidence = first['alternatives'][0]
    assert len(evidence['provenance']['audio_sha256']) == 64
    assert len(evidence['provenance']['cache_key']) == 64
    assert evidence['replacement_applied'] is False
    assert first['original_audio_verified'] is False
    report = review_selected_clips([], [candidate()], ['FINAL'], alternatives=first['alternatives'], targeted_report=first)
    dossier = report['candidates']['FINAL']
    assert dossier['asr_alternatives'][0]['provenance'] == evidence['provenance']
    assert dossier['targeted_unprocessed_regions'] == first['unprocessed_regions']


def test_hypothesis_words_and_provenance_reach_dossier_without_raw_replacement():
    words = [{'word': 'original fixture', 'start': 22, 'end': 23, 'confidence': .3}]
    alternative = {'start': 21, 'end': 25, 'priority_reason': 'SHORTLIST_QUESTION',
                   'evidence_refs': ['FINAL', 'Q'], 'selected_text': 'original fixture',
                   'audio_source': 'original_mono', 'selected_source': 'canonical_raw_preserved',
                   'provenance': {'audio_sha256': 'synthetic_hash', 'independent_audio_verification': False},
                   'alternatives': [{'source': 'original_targeted', 'text': 'synthetic alternative',
                                     'words': [{'word': 'synthetic alternative', 'start': 22, 'end': 23}],
                                     'comparison': {'independent_audio_verification': False}}]}
    before = deepcopy((words, alternative))
    report = review_selected_clips(words, [candidate()], ['FINAL'], alternatives=[alternative])
    dossier = report['candidates']['FINAL']
    evidence = dossier['asr_alternatives'][0]
    assert evidence['provenance'] == alternative['provenance']
    assert evidence['alternatives'] == alternative['alternatives']
    assert dossier['captions'][0]['asr_text'] == 'original fixture'
    assert dossier['captions'][0]['final_text'] is None
    assert evidence['replacement_applied'] is False and not dossier['publication_ready']
    evidence['alternatives'][0]['words'][0]['word'] = 'edited dossier only'
    assert (words, alternative) == before
