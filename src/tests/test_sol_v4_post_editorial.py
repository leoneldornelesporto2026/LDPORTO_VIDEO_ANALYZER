"""Synthetic triage canaries; no inference, human accuracy or autoapproval claims."""
from copy import deepcopy

import pytest

from ldporto.core import digest
from ldporto.editorial import deduplicate_candidates, rank_candidate
from ldporto.editorial_outcome import classify_editorial_outcome
from ldporto.integrity_contracts import human_review_queue
from ldporto.second_curation import (build_second_curation_package,
                                    candidate_editorial_review_plan, human_review_summary)
from test_v42_editorial import candidate as ranking_candidate
from test_v43_handoff import analysis_fixture


def review_candidate(cid='SYNTHETIC_A', start=10, score=.8):
    return {'candidate_id': cid, 'rank': 1, 'start': start, 'end': start + 40,
            'editorial_score_final': score, 'score_components': {'hook': .8},
            'segment_ids': ['SYNTHETIC_SEG'], 'transcript_literal': 'Texto original sintético de teste.',
            'context_before': [{'segment_id': 'BEFORE', 'start': 0, 'end': 9,
                                'speaker': 'ACOUSTIC_A', 'text': 'Contexto anterior sintético.'}],
            'context_after': [{'segment_id': 'AFTER', 'start': start + 41, 'end': start + 46,
                               'speaker': 'ACOUSTIC_A', 'text': 'Contexto posterior sintético.'}],
            'clean_opening': True, 'clean_ending': True, 'editorial_blockers': [],
            'ranking_uncertainty': {'missing_required_components': []},
            'duration_contract': {'target_min_seconds': 30, 'target_max_seconds': 90,
                                  'hard_min_seconds': 8, 'hard_max_seconds': 180},
            'eligible_for_human_review': True, 'human_review_provisional': False,
            'editorial_verified': True, 'commercial_review_state': 'verified',
            'default_shortlist_eligible': False,
            'invariant_reasons': {'human_approved': 'explicit_human_hash_review_required'},
            'selection_gate_diagnostics': {'quality_floor': .5, 'selection_status': 'rejected',
                                           'recorded_reasons': ['ineligible_by_quality_gate']}}


def test_review_explains_local_gates_and_keeps_literal_context_actionable():
    row = review_candidate()
    row.update(end=32.76, ranking_uncertainty={'missing_required_components': ['hook']})
    before = digest(row)
    entry = human_review_queue([row])['entries'][0]
    assert entry['review_state'] == 'PROVISIONAL_HUMAN_REVIEW'
    assert {'outside_target_duration', 'missing_required_score:hook'} <= set(entry['local_gate_reasons'])
    assert entry['transcript_literal'] == row['transcript_literal']
    assert entry['context_before'][0]['text'] == row['context_before'][0]['text']
    assert entry['context_after'][0]['segment_id'] == 'AFTER'
    assert entry['audio_review']['source_interval'] == {'start': 10, 'end': 32.76}
    assert entry['audio_review']['human_audio_verified'] is None
    assert entry['safe_visual_fallback']['mode'] == 'SOURCE_PRESERVE'
    assert not entry['official_shortlist_selected'] and not entry['publication_ready']
    assert {'listen_original_audio', 'assess_missing_editorial_evidence',
            'review_boundaries_and_context'} <= {task['action'] for task in entry['review_tasks']}
    assert digest(row) == before


def test_queue_priority_uses_recorded_score_and_preserves_source_rank():
    weak = review_candidate('WEAK', 100, .3)
    strong = review_candidate('STRONG', 200, .8)
    weak['rank'], strong['rank'] = 1, 99
    before = digest([weak, strong])
    queue = human_review_queue([weak, strong])
    assert queue['candidate_ids'] == ['STRONG', 'WEAK']
    assert [entry['priority_rank'] for entry in queue['entries']] == [1, 2]
    assert queue['entries'][0]['rank'] == 99
    assert 'below_editorial_quality_floor' in queue['entries'][1]['local_gate_reasons']
    assert not queue['publication_ready'] and digest([weak, strong]) == before


def test_legacy_schema_reproduces_original_layout_order_and_values():
    row = review_candidate()
    queue = human_review_queue([row], schema_version='1.0')
    expected = {'schema_version': '1.0', 'entries': [{
        'candidate_id': 'SYNTHETIC_A', 'rank': 1, 'start': 10, 'end': 50,
        'editorial_score_final': .8, 'score_components': {'hook': .8},
        'commercial_review_state': 'verified', 'human_review_provisional': False,
        'priority': 'editorial_review', 'reasons': row['invariant_reasons'],
        'candidate_ref': 'candidates/SYNTHETIC_A.json',
        'transcript_ref': 'transcript/relevant_segments.jsonl', 'segment_ids': ['SYNTHETIC_SEG'],
        'visual_refs': [], 'alternative_ids': []}],
        'candidate_ids': ['SYNTHETIC_A'], 'publication_ready': False}
    assert queue == expected
    weak, strong = review_candidate('WEAK', 100, .3), review_candidate('STRONG', 200, .9)
    assert human_review_queue([weak, strong], schema_version='1.0')['candidate_ids'] == ['WEAK', 'STRONG']
    with pytest.raises(ValueError, match='unsupported_human_review_queue_schema'):
        human_review_queue([row], schema_version='unknown')


def test_complete_recorded_candidate_keeps_current_automatic_policy_without_approval():
    ranked = rank_candidate(ranking_candidate('SYNTHETIC_COMPLETE'))
    assert ranked['default_shortlist_eligible'] and ranked['editorial_score_final'] >= .5
    row = {**review_candidate(), **ranked, 'candidate_id': ranked['moment_id'],
           'start': ranked['ideal_start'], 'end': ranked['ideal_end']}
    row['selection_gate_diagnostics'] = {'selection_status': 'selected', 'quality_floor': .5,
                                       'upstream_default_shortlist_eligible': True, 'recorded_reasons': []}
    plan = candidate_editorial_review_plan(row)
    assert plan['review_state'] == 'ELIGIBLE_AUTOMATIC_SHORTLIST'
    assert plan['automatic_shortlist_eligible'] and plan['official_shortlist_selected']
    assert not plan['human_approved'] and not plan['preview_approved'] and not plan['publication_ready']


@pytest.mark.parametrize('blocker', ['clean_opening', 'clean_ending', 'answer_or_payoff_unresolved'])
def test_high_score_incomplete_unit_stays_outside_automatic_shortlist(blocker):
    source = ranking_candidate('SYNTHETIC_INCOMPLETE')
    if blocker.startswith('clean_'):
        source[blocker] = False
    else:
        source['editorial_blockers'] = [blocker]
    ranked = rank_candidate(source)
    ranked['editorial_score_final'] = .99  # Explicit synthetic high-score negative.
    row = {**review_candidate(), **ranked, 'candidate_id': ranked['moment_id'],
           'start': ranked['ideal_start'], 'end': ranked['ideal_end']}
    plan = candidate_editorial_review_plan(row)
    assert not ranked['default_shortlist_eligible'] and not plan['automatic_shortlist_eligible']
    assert plan['review_state'] == 'PROVISIONAL_HUMAN_REVIEW'
    assert any(blocker in reason for reason in plan['local_gate_reasons'])
    assert not plan['publication_ready']


def test_asd_partial_does_not_block_provisional_text_review_or_manufacture_identity():
    analysis = analysis_fixture()
    analysis['editorial_shortlist'] = []
    analysis['stage_status'] = {'04_transcription': {'status': 'partial'}, '15_semantic': {'status': 'ok'},
                                '16_understanding': {'status': 'ok'}, '10_active_speaker': {'status': 'partial'}}
    analysis['active_speaker'] = []
    analysis['main_moments'][0].update(default_shortlist_eligible=False, clean_opening=True, clean_ending=True,
        ranking_uncertainty={'missing_required_components': ['hook']}, editorial_score_final=.7)
    original_shortlist = list(analysis['editorial_shortlist'])
    package = build_second_curation_package(analysis)
    row = package['candidates'][0]
    assert row['eligible_for_human_review'] and row['review_state'] == 'PROVISIONAL_HUMAN_REVIEW'
    assert row['person_ids'] == [] and row['review_plan']['safe_visual_fallback']['preserve_original_frame']
    assert not row['review_plan']['safe_visual_fallback']['speaker_person_mapping_required_for_text_review']
    assert not row['publication_ready'] and not row['human_approved']
    assert analysis['editorial_shortlist'] == original_shortlist == []
    assert package['human_review_summary']['human_review_queue_count'] == 1


def test_producer_preserves_recorded_local_rejection_provenance():
    analysis = analysis_fixture()
    analysis['main_moments'][0]['default_shortlist_eligible'] = False
    analysis['candidate_metrics'] = {'selection_report': {'min_score': .6,
        'rejected': [{'moment_id': 'M1', 'reasons': ['topic_boundary_crossed']}],
        'candidate_diagnostics': [{'moment_id': 'M1', 'selection_status': 'rejected',
                                  'selection_reasons': ['topic_boundary_crossed', 'ineligible_by_quality_gate']}]}}
    row = build_second_curation_package(analysis)['candidates'][0]
    assert row['selection_gate_diagnostics']['quality_floor'] == .6
    assert row['selection_gate_diagnostics']['recorded_reasons'] == ['ineligible_by_quality_gate', 'topic_boundary_crossed']
    assert 'topic_boundary_crossed' in row['review_plan']['local_gate_reasons']
    assert row['selection_gate_diagnostics']['scope'] == 'candidate_local_selection'


def test_review_summary_preserves_80_members_77_units_and_three_alternatives():
    rows = [review_candidate(f'PRIMARY_{index:02}', index * 100, .8 - index / 1000) for index in range(77)]
    for index in range(3):
        alternate = deepcopy(rows[index])
        alternate.update(candidate_id=f'ALTERNATE_{index}', rank=100 + index, alternate_of=rows[index]['candidate_id'])
        rows.append(alternate)
    before = digest(rows)
    queue = human_review_queue(rows)
    assert len(rows) == 80 and len(queue['entries']) == 77
    assert sum(len(entry['alternative_ids']) for entry in queue['entries']) == 3
    assert human_review_summary(rows)['human_review_queue_count'] == 77
    assert digest(rows) == before


def test_empty_official_shortlist_reports_existing_human_queue_without_new_queue():
    analysis = analysis_fixture()
    analysis['editorial_shortlist'] = []
    analysis['main_moments'][0].update(default_shortlist_eligible=False,
        ranking_uncertainty={'missing_required_components': ['hook']}, editorial_score_final=.8)
    analysis['second_curation_package'] = build_second_curation_package(analysis)
    original = digest(analysis['second_curation_package'])
    result = classify_editorial_outcome(analysis)
    assert result['shortlist_count'] == 0 and result['human_review_available']
    assert result['human_review_summary']['human_review_queue_count'] == 1
    assert result['human_review_summary']['queue_ref'] == 'editorial/human_review_queue.json'
    assert 'entries' not in result['human_review_summary']
    assert not result['publication_ready'] and digest(analysis['second_curation_package']) == original


def test_failed_transcription_or_excluded_commercial_stays_out_of_queue():
    rows = [review_candidate('NO_AUDIO', 0), review_candidate('EXCLUDED', 100)]
    for row in rows:
        row['eligible_for_human_review'] = False
    assert human_review_queue(rows)['entries'] == []
    assert human_review_summary(rows)['human_review_queue_count'] == 0


def test_legacy_default_does_not_manufacture_verified_automatic_eligibility():
    row = review_candidate()
    row['default_shortlist_eligible'] = True
    row['selection_gate_diagnostics']['upstream_default_shortlist_eligible'] = None
    assert candidate_editorial_review_plan(row)['review_state'] == 'PROVISIONAL_HUMAN_REVIEW'


def test_recorded_local_flag_cannot_bypass_the_unchanged_quality_floor():
    row = review_candidate(score=.49)
    row['default_shortlist_eligible'] = True
    before = digest(row)
    plan = candidate_editorial_review_plan(row)
    assert plan['review_state'] == 'PROVISIONAL_HUMAN_REVIEW'
    assert 'below_editorial_quality_floor' in plan['local_gate_reasons']
    assert not plan['automatic_shortlist_eligible'] and digest(row) == before
