"""Post-Foquinha dialogue regressions: synthetic text, no audio/model/human labels."""
from copy import deepcopy
from types import SimpleNamespace
import logging

import pytest

from ldporto.config import DEFAULTS
from ldporto.semantic import questions_answers, qa_contract
from ldporto.understanding import (recover_dialogue_links, build_story_arcs,
                                   _validate_story_arcs_contract, run_understanding,
                                   story_support_diagnostics)


def segment(sid, text, speaker, start, end):
    return {'segment_id': sid, 'text': text, 'speaker': speaker, 'start': start, 'end': end}


def dialogue():
    rows = [segment('Q', 'Como foi a gravação do disco?', 'ASKER', 0., 2.),
            segment('C', 'A gravação do disco aconteceu no estúdio antigo.', 'ASKER', 2., 4.),
            segment('A', 'A gravação do disco precisou de músicos novos.', 'RESPONDER', 4., 8.),
            segment('N', 'Onde vocês tocaram?', 'ASKER', 8., 10.)]
    topics = [{'topic_id': 'CHUNK_LEFT', 'start': 0., 'end': 4., 'evidence_segment_ids': ['Q', 'C']},
              {'topic_id': 'CHUNK_RIGHT', 'start': 4., 'end': 10., 'evidence_segment_ids': ['A', 'N']}]
    return rows, topics


def test_question_context_bridge_crosses_chunks_with_literal_owned_references():
    rows, topics = dialogue()
    original = questions_answers(rows)
    before_rows, before_pairs = deepcopy(rows), deepcopy(original)
    assert original[0]['answer_status'] == 'unresolved'
    recovered, diagnostics = recover_dialogue_links({'segments': rows}, original, topics)
    pair = recovered[0]
    assert pair['answer_status'] == 'linked_candidate'
    assert pair['answer_segment_ids'] == ['A'] and pair['answer'] == rows[2]['text']
    assert pair['answer_speaker'] == 'RESPONDER' and pair['question_speaker'] == 'ASKER'
    assert pair['question_segment_ids'] == ['Q', 'C']
    assert pair['question_start'] == 0 and pair['question_end'] == 4
    assert pair['answer_start'] == 4 and pair['answer_end'] == 8
    assert pair['question_id'] == original[0]['question_id']
    assert pair['stable_question_id'] == original[0]['stable_question_id']
    assert pair['dialogue_support']['cross_topic_references'] is True
    assert pair['needs_review'] and pair['audio_verified_complete'] is None
    assert diagnostics['counts']['recovered_provisional_links'] == 1
    assert rows == before_rows and original == before_pairs
    contract = qa_contract(recovered)
    assert contract['question_answer_pairs'][0]['question_id'] == pair['question_id']
    assert contract['qa_metrics']['verified_complete_qa_count'] is None


def test_reaction_is_intervening_evidence_not_answer_ownership():
    rows = [segment('Q', 'Como foi a gravação do disco?', 'ASKER', 0., 2.),
            segment('R', 'Nossa!', 'LISTENER', 2., 2.5),
            segment('A', 'A gravação do disco precisou de músicos novos.', 'RESPONDER', 2.5, 7.)]
    old = questions_answers(rows)
    assert old[0]['answer_status'] == 'unresolved'
    pairs, _ = recover_dialogue_links({'segments': rows}, old)
    pair = pairs[0]
    assert pair['answer_segment_ids'] == ['A'] and pair['answer_speaker'] == 'RESPONDER'
    assert pair['answer'] == rows[2]['text'] and 'Nossa' not in pair['answer']
    assert pair['intervening_segment_ids'] == ['R']
    assert pair['intervention_evidence'][0]['speaker'] == 'LISTENER'
    assert pair['association_evidence'][0]['intervening_segment_ids'] == ['R']
    assert pair['audio_verified_complete'] is None


@pytest.mark.parametrize('change', ['unknown_context_speaker', 'topic_shift', 'different_question',
                                  'unrelated_context', 'overlap', 'long_pause', 'unknown_answer_speaker'])
def test_unproven_context_or_ownership_does_not_become_linked_answer(change):
    rows, topics = dialogue()
    if change == 'unknown_context_speaker': rows[1]['speaker'] = None
    elif change == 'topic_shift': rows[1]['text'] = 'Mudando de assunto, a gravação do disco vai esperar.'
    elif change == 'different_question': rows[1]['text'] = 'Quando saiu a gravação do disco?'
    elif change == 'unrelated_context': rows[1]['text'] = 'O trânsito da cidade trouxe muitos problemas.'
    elif change == 'overlap': rows[1]['start'] = 1.9
    elif change == 'long_pause': rows[1]['start'], rows[1]['end'], rows[2]['start'], rows[2]['end'] = 8., 10., 10., 14.
    elif change == 'unknown_answer_speaker': rows[2]['speaker'] = None
    original = questions_answers(rows)
    assert original[0]['answer_status'] == 'unresolved'
    recovered, diagnostics = recover_dialogue_links({'segments': rows}, original, topics)
    assert recovered[0]['answer_status'] == 'unresolved'
    assert not recovered[0]['answer_segment_ids']
    assert diagnostics['human_accuracy_measured'] is False


def test_tampered_question_reference_is_not_repaired_into_new_evidence():
    rows, _ = dialogue()
    original = questions_answers(rows)
    original[0]['question'] = 'A pergunta foi inventada.'
    recovered, diagnostics = recover_dialogue_links({'segments': rows}, original)
    assert recovered[0]['answer_status'] == 'unresolved'
    assert diagnostics['counts']['question_reference_or_ownership_unresolved'] == 1


def test_already_linked_and_not_expected_records_are_preserved_exactly():
    rows = [segment('Q', 'Quando começou a gravação?', 'ASKER', 0., 2.),
            segment('A', 'Eu comecei a gravação ontem.', 'RESPONDER', 2., 5.),
            segment('T', 'Uma gravação difícil, né?', 'RESPONDER', 5., 7.)]
    original = questions_answers(rows)
    assert original[0]['answer_status'] == 'linked_candidate'
    assert original[-1]['answer_status'] == 'not_expected'
    recovered, _ = recover_dialogue_links({'segments': rows}, original)
    assert recovered == original


def test_duplicate_source_ids_disable_recovery_instead_of_guessing_reference():
    rows, _ = dialogue()
    original = questions_answers(rows)
    rows.append(dict(rows[-1], text='Outro conteúdo com ID reciclado.'))
    recovered, diagnostics = recover_dialogue_links({'segments': rows}, original)
    assert recovered == original and diagnostics['source_duplicate_ids_observed']


def test_search_prefix_never_skips_long_blocking_turn_to_link_overlapping_answer():
    rows = [segment('Q', 'Como foi a gravação do disco?', 'ASKER', 0., 2.),
            segment('R', 'Nossa!', 'LISTENER', 2., 3.),
            segment('BLOCK', 'Uma fala longa sem ligação demonstrada.', 'OTHER', 3., 200.),
            segment('A', 'A gravação do disco precisou de músicos novos.', 'RESPONDER', 4., 8.)]
    original = questions_answers(rows)
    assert original[0]['answer_status'] == 'unresolved'
    recovered, diagnostics = recover_dialogue_links({'segments': rows}, original)
    assert recovered[0] == original[0]
    assert diagnostics['counts']['source_prefix_stopped_at_invalid_interval_or_search_limit'] == 1
    assert not any(attempt['recovered'] for attempt in diagnostics['attempts'])


def test_polar_confirmation_cannot_be_skipped_to_assign_answer_to_third_speaker():
    rows = [segment('Q', 'Foi a gravação no estúdio antigo?', 'ASKER', 0., 2.),
            segment('R', 'Certo.', 'FIRST_RESPONDER', 2., 2.5),
            segment('A', 'A gravação no estúdio antigo teve problemas de equipamento.', 'OTHER', 3., 7.)]
    original = questions_answers(rows)
    assert original[0]['question_type'] == 'yes_no_question'
    assert original[0]['answer_status'] == 'unresolved'
    recovered, diagnostics = recover_dialogue_links({'segments': rows}, original)
    assert recovered[0] == original[0]
    assert diagnostics['attempts'][0]['stop_reason'] == 'polar_reaction_response_ownership_ambiguous'


@pytest.mark.parametrize('stop', ['overlap', 'horizon', 'segment_limit'])
def test_truncated_search_cannot_mark_observed_answer_as_complete(stop):
    rows, _ = dialogue()
    rows = rows[:3]
    if stop == 'overlap':
        rows.append(segment('BAD', 'Um trecho com intervalo conflitante.', 'OTHER', 7., 9.))
        reason = 'source_interval_unresolved'
    elif stop == 'horizon':
        rows.append(segment('BAD', 'Um trecho fora do limite de busca.', 'OTHER', 8., 200.))
        reason = 'answer_search_window_exhausted'
    else:
        rows += [segment(f'CONT_{i}', 'A gravação do disco continuou.', 'RESPONDER', 8.+i, 9.+i)
                 for i in range(32)]
        reason = 'answer_segment_search_limit'
    recovered, diagnostics = recover_dialogue_links({'segments': rows}, questions_answers(rows))
    assert recovered[0]['answer_status'] == 'linked_candidate'
    assert not recovered[0]['question_answer_complete']
    assert not recovered[0]['answer_closes_itself']
    assert recovered[0]['unresolved_reason'] == reason
    assert diagnostics['attempts'][0]['source_window_stop_reason'] == reason


def story_fixture():
    texts = ['Um dia eu fui gravar um disco no estúdio.',
             'Mas o disco ficou parado por um problema no estúdio.',
             'Eu continuei a gravar o disco com músicos novos.',
             'No final consegui terminar o disco.']
    rows = [segment(f'S{i}', text, 'NARRATOR', i*10., (i+1)*10.) for i, text in enumerate(texts)]
    topics = [{'topic_id': 'LEFT', 'start': 0., 'end': 20., 'evidence_segment_ids': ['S0', 'S1']},
              {'topic_id': 'RIGHT', 'start': 20., 'end': 40., 'evidence_segment_ids': ['S2', 'S3']}]
    return rows, topics


def test_only_observed_ordered_story_parts_can_support_cross_chunk_narrative():
    rows, topics = story_fixture()
    arcs, _ = _validate_story_arcs_contract(build_story_arcs({'segments': rows}, topics), rows)
    supported = [arc for arc in arcs if arc.get('narrative_supported')]
    assert supported
    support = supported[0]['support_diagnostics']
    assert support['ordered_setup_development_payoff'] and not support['context_incomplete']
    assert support['components']['payoff']['segment_ids'] == ['S3']
    partial, _ = _validate_story_arcs_contract(build_story_arcs({'segments': rows[:-1]}, topics), rows[:-1])
    assert partial and not any(arc.get('narrative_supported') for arc in partial)
    assert any('no_payoff' in arc['support_diagnostics']['missing_support_reasons'] for arc in partial)


@pytest.mark.parametrize('change', ['invented_text', 'invented_time', 'unknown_reference'])
def test_real_story_ids_cannot_authorize_invented_payoff_text_or_time(change):
    rows, topics = story_fixture()
    arc = next(arc for arc in build_story_arcs({'segments': rows}, topics) if arc.get('narrative_supported'))
    if change == 'invented_text': arc['payoff']['text'] = 'O desfecho foi inventado.'
    elif change == 'invented_time': arc['payoff']['end'] = 999.
    else: arc['payoff']['segment_ids'] = ['UNKNOWN']
    normalized, events = _validate_story_arcs_contract([arc], rows)
    assert normalized[0]['payoff'] is None
    assert not normalized[0]['narrative_supported'] and normalized[0]['kind'] == 'partial_story'
    assert events


@pytest.mark.parametrize('invalid_source', ['overlapping_components', 'empty_source_text'])
def test_story_support_requires_nonoverlapping_canonical_intervals_and_nonempty_text(invalid_source):
    rows = [segment('SETUP', 'Um dia eu fui gravar um disco.', 'NARRATOR', 0., 10.),
            segment('DEVELOPMENT', 'Continuei a gravar o disco.', 'NARRATOR', 10., 15.),
            segment('PAYOFF', 'No final terminei o disco.', 'NARRATOR', 15., 20.)]
    if invalid_source == 'overlapping_components':
        rows[1]['start'], rows[2]['start'] = 5., 14.
    else:
        rows[1]['text'] = ''
    arc = {'kind': 'complete_story', 'narrative_supported': True,
           'evidence_segment_ids': ['SETUP', 'DEVELOPMENT', 'PAYOFF'],
           'setup': {'segment_ids': ['SETUP']}, 'development': {'segment_ids': ['DEVELOPMENT']},
           'payoff': {'segment_ids': ['PAYOFF']}}
    support = story_support_diagnostics(arc, rows)
    assert not support['ordered_setup_development_payoff'] and support['context_incomplete']
    normalized, _ = _validate_story_arcs_contract([arc], rows)
    assert normalized[0]['kind'] == 'partial_story' and not normalized[0]['narrative_supported']


@pytest.mark.parametrize('kind', ['partial_story', 'discussion_segment'])
def test_narrative_claim_in_any_kind_requires_actual_payoff_support(kind):
    rows, topics = story_fixture()
    arc = next(arc for arc in build_story_arcs({'segments': rows}, topics) if arc.get('narrative_supported'))
    arc.update(kind=kind, payoff=None, narrative_supported=True)
    normalized, events = _validate_story_arcs_contract([arc], rows)
    assert not normalized[0]['narrative_supported'] and normalized[0]['needs_review']
    assert 'no_payoff' in normalized[0]['support_diagnostics']['missing_support_reasons']
    assert any(event['action'] == 'unsupported_narrative_claim_removed' for event in events)


def test_run_understanding_returns_reconciled_qa_contract_and_diagnostics(tmp_path, monkeypatch):
    rows, topics = dialogue()
    topics = [dict(topic, topic='Gravação', summary='Contexto sintético.', speakers=[], context_required='none') for topic in topics]
    original = questions_answers(rows)
    semantic = {'topics': topics, 'moments': [], 'questions_answers': original, 'program_sections': []}
    cfg = deepcopy(DEFAULTS['understanding']); cfg['extract_frames'] = False
    ctx = SimpleNamespace(output=tmp_path, logger=logging.getLogger('synthetic-dialogue'))
    result = run_understanding(ctx, {'duration': 10.}, {'segments': rows},
        {'speakers': [{'speaker_id': 'ASKER'}, {'speaker_id': 'RESPONDER'}]},
        {'people': [], 'observations': [], 'thumbnails': []}, {'mapping_summary': []}, semantic, [], cfg)['data']
    assert result['questions_answers'][0]['answer_status'] == 'linked_candidate'
    assert result['question_candidates'][0]['question_id'] == result['question_answer_pairs'][0]['question_id']
    assert result['qa_metrics']['answered_question_count'] == 1
    assert result['dialogue_diagnostics']['counts']['recovered_provisional_links'] == 1
    assert semantic['questions_answers'] == original
