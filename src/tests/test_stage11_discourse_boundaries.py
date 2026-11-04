"""Offline source-unit fixtures, not claims about the historical video."""
from copy import deepcopy

import pytest

from ldporto.editorial import optimize_boundaries, rank_candidate
from ldporto.understanding import build_main_moments
from ldporto.second_curation import build_second_curation_package


def seg(sid, start, end, text):
    return dict(segment_id=sid, start=start, end=end, text=text, speaker='A')


def moment(start=5, end=15, ids=None):
    return dict(moment_id='M', start=start, end=end, evidence_segment_ids=ids or ['A'],
                categories=[], text='A resposta.', context_requirement='none', standalone_class='excellent')


def qa():
    return dict(question_id='Q1', question_start=0, question_end=5, answer_start=5, answer_end=15,
                question_answer_complete=True, answer_expected=True, evidence_segment_ids=['Q', 'A'])


def rows():
    return [seg('Q', 0, 5, 'Como você resolveu o problema?'),
            seg('A', 5, 15, 'Eu reparei a máquina e ela voltou a funcionar.')]


def test_question_partly_before_core_expands_whole_unit_without_mutation():
    source, core = rows(), moment(3, 15, ['Q', 'A'])
    saved = deepcopy((source, core))
    result = optimize_boundaries(core, source, qa_pairs=[qa()])
    assert result['boundary_decision'] == 'expand'
    assert (result['ideal_start'], result['ideal_end']) == (0, 15)
    assert result['original_interval'] == {'start': 3, 'end': 15}
    assert result['alternate_start']['evidence'][0]['text'] == source[0]['text']
    assert result['clean_start'] and result['clean_ending']
    assert result['standalone_context_evidence']['semantic_completeness_confirmed'] is None
    assert (source, core) == saved


def test_question_only_clip_includes_later_answer_even_with_punctuation():
    result = optimize_boundaries(moment(0, 5, ['Q']), rows(), qa_pairs=[qa()])
    assert result['ideal_end'] == 15 and result['boundary_decision'] == 'expand'


def test_payoff_after_clip_uses_grounded_arc():
    source = [seg('S', 0, 5, 'Eu precisava consertar a máquina.'),
              seg('D', 5, 10, 'Troquei a peça.'), seg('P', 10, 15, 'No fim, ela funcionou.')]
    story = dict(start=0, end=15, kind='complete_story',
                 setup={'segment_ids': ['S']}, development={'segment_ids': ['D']}, payoff={'segment_ids': ['P']})
    result = optimize_boundaries(moment(5, 10, ['D']), source, story=story)
    assert result['boundary_decision'] == 'expand'
    assert result['boundary_segment_ids'] == ['S', 'D', 'P']


@pytest.mark.parametrize('barrier,risk', [
    ('Mudando de assunto, agora vamos falar de futebol.', 'explicit_topic_transition_crossed'),
    ('Oferecimento: o patrocinador deste programa.', 'commercial_boundary_crossed'),
])
def test_no_expansion_across_transition_or_ad(barrier, risk):
    source = [seg('Q', 0, 3, 'Como você resolveu?'), seg('B', 3, 5, barrier), rows()[1]]
    pair = qa(); pair['evidence_segment_ids'] = ['Q', 'B', 'A']
    result = optimize_boundaries(moment(), source, qa_pairs=[pair])
    assert result['boundary_decision'] == 'pending'
    assert (result['ideal_start'], result['ideal_end']) == (5, 15)
    assert risk in result['boundary_risks']
    assert result['alternate_start']['time'] == 0
    assert 0 in result['alternate_starts']
    assert result['clean_start'] is False


def test_topic_envelope_blocks_general_qa_expansion():
    result = optimize_boundaries(moment(), rows(), qa_pairs=[qa()], topic={'start': 5, 'end': 15})
    assert result['ideal_start'] == 5 and result['boundary_decision'] == 'pending'
    assert 'topic_boundary_crossed' in result['boundary_risks']


def test_duration_budget_blocks_unit_and_does_not_pad_to_target():
    result = optimize_boundaries(moment(), rows(), cfg={'hard_max_seconds': 12}, qa_pairs=[qa()])
    assert result['boundary_decision'] == 'pending'
    assert result['ideal_start'] == 5 and result['clean_start'] is False
    assert result['boundary_duration_budget']['remaining_hard_seconds'] == 2
    assert result['boundary_duration_budget']['selected_seconds'] == 10
    assert result['boundary_duration_budget']['proposed_seconds'] == 15
    assert 'duration_budget_exceeded' in result['boundary_risks']
    assert result['qa_boundary_expansion_ids'] == []


def test_high_score_146_seconds_stays_pending_without_fabricated_context():
    source = [seg('A', 0, 1.46, 'Uma frase sintética.')]
    result = optimize_boundaries(moment(0, 1.46), source)
    ranked = rank_candidate({**result, 'standalone_score': 1, 'hook_score': 1, 'information_score': 1})
    assert result['boundary_decision'] == 'pending'
    assert result['standalone_assessment'] == 'context_required'
    assert result['ideal_end'] == 1.46
    assert not ranked['default_shortlist_eligible']


@pytest.mark.parametrize('source', [[], [seg('A', 5, 15, '')], [seg('A', 5, 15, '[inaudível].')]])
def test_missing_text_or_source_preserves_unknown(source):
    result = optimize_boundaries(moment(), source)
    assert result['boundary_decision'] == 'pending'
    assert result['clean_start'] is None and result['clean_ending'] is None


def test_unfinished_end_gets_literal_continuation():
    source = [seg('A', 0, 10, 'Eu consertei a máquina porque'), seg('B', 10, 15, 'a peça estava quebrada.')]
    result = optimize_boundaries(moment(0, 10), source)
    assert result['ideal_end'] == 15 and result['boundary_decision'] == 'expand'
    assert result['alternate_end']['evidence'][-1]['segment_id'] == 'B'


def test_mid_sentence_start_remains_pending_if_not_resolved():
    source = [seg('Q', 0, 5, 'Eu resolvi o problema usando'), seg('A', 5, 15, 'uma peça nova.')]
    result = optimize_boundaries(moment(), source)
    assert result['boundary_decision'] == 'pending' and result['clean_start'] is False
    assert 'mid_sentence' in result['boundary_blockers']


def test_complete_source_unit_cut_decision_and_sorted_copy():
    source = [seg('B', 40, 50, 'Outro trecho.'), seg('A', 0, 35, 'Uma explicação sobre a máquina.')]
    saved = deepcopy(source)
    result = optimize_boundaries(moment(0, 35), source)
    assert result['boundary_decision'] == 'cut'
    assert result['standalone_assessment'] == 'standalone_candidate_requires_review'
    assert source == saved


def test_blocked_context_reaches_ranking_and_curation_without_score_promotion():
    core = moment(); core['editorial'] = {'clarity': 1, 'hook_strength': 1}
    candidates = build_main_moments({'segments': rows()}, [{'topic_id': 'T', 'start': 5, 'end': 15}],
                                  [core], [qa()], [], [])
    item = candidates[0]
    assert item['standalone_score'] is None and item['original_standalone_class'] == 'excellent'
    assert item['boundary_decision'] == 'pending' and not item['default_shortlist_eligible']
    analysis = {'main_moments': candidates, 'transcript_segments': rows(), 'topics': [], 'metadata': {}}
    exported = build_second_curation_package(analysis)['candidates'][0]
    assert exported['candidate_id'] == 'M'
    assert exported['standalone_assessment'] == 'context_required'
    assert exported['alternate_start'] == item['alternate_start']
    assert exported['core_interval'] == {'start': 5, 'end': 15}


def test_legacy_export_without_context_assessment_remains_unresolved():
    item = {**moment(), 'ideal_start': 5, 'ideal_end': 15, 'clean_opening': True,
            'clean_ending': True, 'standalone_score': 1}
    exported = build_second_curation_package({'main_moments': [item], 'metadata': {},
                                              'transcript_segments': rows()})['candidates'][0]
    assert exported['standalone_assessment'] == 'unresolved_requires_review'


def test_pending_boundary_is_blocked_even_when_ranked_directly():
    source = [seg('A', 0, 30, 'Uma explicação completa.'),
              seg('B', 30, 60, 'Mudando de assunto, vamos falar de futebol.')]
    result = optimize_boundaries(moment(0, 60, ['A', 'B']), source)
    ranked = rank_candidate({**result, 'standalone_score': 1, 'hook_score': 1})
    assert ranked['clean_opening'] and ranked['clean_ending']
    assert 'explicit_topic_transition_crossed' in ranked['editorial_blockers']
    assert not ranked['default_shortlist_eligible']
