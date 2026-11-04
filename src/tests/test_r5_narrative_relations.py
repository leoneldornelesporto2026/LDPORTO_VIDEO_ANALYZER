"""R5 synthetic text-only canaries; no model, audio or human accuracy claims."""
from copy import deepcopy

import pytest

from ldporto.narrative_relations import build_question_answer_links, build_arc_context_links
from ldporto.semantic import questions_answers
from ldporto.understanding import build_story_arcs, _validate_story_arcs_contract


def row(sid, text, speaker, start, end):
    return {'segment_id': sid, 'text': text, 'speaker': speaker, 'start': start, 'end': end}


def delayed():
    rows = [row('Q', 'Como foi a crise da Varig?', 'ASKER', 0., 2.)]
    rows += [row(f'I{i}', 'Um comentário lateral sem relação demonstrada.', 'OTHER', 2.+i*2, 4.+i*2) for i in range(12)]
    rows += [row('A', 'Respondendo à sua pergunta sobre a crise da Varig, a empresa encerrou as operações.', 'RESPONDER', 26., 31.)]
    topics = [{'topic_id': 'T1', 'evidence_segment_ids': ['Q']}, {'topic_id': 'T2', 'evidence_segment_ids': ['A']}]
    sections = [{'section_id': 'SEC1', 'topic_ids': ['T1']}, {'section_id': 'SEC2', 'topic_ids': ['T2']}]
    return rows, topics, sections


def linked(links):
    return [link for link in links if link['answer_segment_ids']]


def test_delayed_cross_section_answer_is_proposed_with_real_references_and_no_canonical_mutation():
    rows, topics, sections = delayed()
    questions = questions_answers(rows)
    before = deepcopy((rows, questions, topics, sections))
    assert questions[0]['answer_status'] == 'unresolved'
    links = linked(build_question_answer_links(rows, questions, topics, sections))
    assert len(links) == 1
    link = links[0]
    assert link['question_id'] == questions[0]['question_id']
    assert link['question_segment_ids'] == ['Q'] and link['answer_segment_ids'] == ['A']
    assert link['question_interval'] == {'start': 0., 'end': 2.}
    assert link['answer_interval'] == {'start': 26., 'end': 31.}
    assert link['association_type'] == 'cross_section_response'
    assert link['question_section_ids'] == ['SEC1'] and link['answer_section_ids'] == ['SEC2']
    assert link['rationale']['segment_distance'] == 13
    assert link['requires_review'] and not link['confirmed'] and not link['causality_confirmed']
    assert link['question_answer_complete'] is None and link['audio_verified_complete'] is None
    assert not link['changes_canonical_qa'] and (rows, questions, topics, sections) == before
    assert links == linked(build_question_answer_links(rows, questions, topics, sections))


@pytest.mark.parametrize('change', ['lexical_only', 'unrelated_reference', 'unknown_answer', 'overlap', 'bound', 'tampered_question'])
def test_unproven_late_answer_stays_unresolved(change):
    rows, topics, sections = delayed()
    if change == 'lexical_only': rows[-1]['text'] = 'A crise da Varig ocorreu durante um período difícil.'
    elif change == 'unrelated_reference': rows[-1]['text'] = 'Respondendo à sua pergunta, o campeonato terminou domingo.'
    elif change == 'unknown_answer': rows[-1]['speaker'] = None
    elif change == 'overlap': rows[-2]['end'] = 28.
    questions = questions_answers(rows)
    if change == 'tampered_question': questions[0]['question'] = 'Uma pergunta que não foi observada.'
    cfg = {'max_search_segments': 10} if change == 'bound' else None
    assert not linked(build_question_answer_links(rows, questions, topics, sections, cfg=cfg))


def test_same_segment_self_answer_uses_literal_text_offsets_and_source_times():
    rows = [row('S', 'Por que a companhia caiu? Porque a dívida aumentou.', 'NARRATOR', 0., 7.)]
    questions = questions_answers(rows)
    links = linked(build_question_answer_links(rows, questions))
    assert len(links) == 1 and links[0]['association_type'] == 'same_segment_self_answer'
    link = links[0]
    spans = link['rationale']['source_text_spans']
    assert rows[0]['text'][spans['question']['start']:spans['question']['end']] == 'Por que a companhia caiu?'
    assert rows[0]['text'][spans['answer']['start']:spans['answer']['end']] == 'Porque a dívida aumentou.'
    assert link['question_interval'] == link['answer_interval'] == {'start': 0., 'end': 7.}
    assert 'same_segment_word_times_unresolved' in link['uncertainties']


def numeric_narration():
    return [row('C', 'Por exemplo, considere o número 0270.', 'NARRATOR', 0., 3.),
            row('Q', 'Como a gente lê?', 'NARRATOR', 3.4, 4.4),
            row('A', '270.', 'NARRATOR', 4.5, 5.2)]


def test_literal_number_reading_self_answer_needs_real_context_and_keeps_qa_unchanged():
    rows = numeric_narration(); questions = questions_answers(rows); before = deepcopy(questions)
    assert questions[0]['answer_status'] == 'unresolved'
    links = linked(build_question_answer_links(rows, questions))
    assert len(links) == 1
    link = links[0]
    assert link['association_type'] == 'self_answer' and link['answer_segment_ids'] == ['A']
    assert link['rationale']['response_cue'] == 'numeric_reading_self_response'
    assert link['rationale']['referenced_numeric_literal'] == '0270'
    assert link['rationale']['response_numeric_literal'] == '270'
    assert link['evidence_segment_ids'] == ['C', 'Q', 'A']
    assert not link['confirmed'] and link['question_answer_complete'] is None and questions == before


@pytest.mark.parametrize('change', ['different_number', 'no_numeric_context', 'unknown_context_speaker',
                                  'different_responder', 'long_gap', 'not_reading_question', 'not_literal_number'])
def test_numeric_turn_is_not_a_self_answer_without_all_specific_reading_guards(change):
    rows = numeric_narration()
    if change == 'different_number': rows[0]['text'] = 'Considere o número 0271.'
    elif change == 'no_numeric_context': rows[0]['text'] = 'Agora uma explicação sobre leitura.'
    elif change == 'unknown_context_speaker': rows[0]['speaker'] = None
    elif change == 'different_responder': rows[-1]['speaker'] = 'OTHER'
    elif change == 'long_gap': rows[-1]['start'], rows[-1]['end'] = 7., 8.
    elif change == 'not_reading_question': rows[1]['text'] = 'Quanto custava naquela época?'
    elif change == 'not_literal_number': rows[-1]['text'] = '270 pessoas participaram.'
    assert not linked(build_question_answer_links(rows, questions_answers(rows)))


def test_discourse_prefixed_polar_self_answer_is_provisional_without_reclassifying_question():
    rows = [row('Q', 'Ué, a gente já não contou a história desse voo?', 'NARRATOR', 0., 4.),
            row('A', 'Sim, a gente contou a história desse voo.', 'NARRATOR', 4.2, 8.)]
    questions = questions_answers(rows); before = deepcopy(questions)
    assert questions[0]['question_type'] == 'direct_question' and questions[0]['answer_status'] == 'unresolved'
    link = linked(build_question_answer_links(rows, questions))[0]
    assert link['association_type'] == 'self_answer'
    assert link['rationale']['response_cue'] == 'polar_narration_self_response'
    assert len(link['rationale']['shared_terms']) >= 2 and not link['confirmed']
    assert questions == before
    rows[0]['text'] = 'Ué, como a gente contou a história desse voo?'
    assert not linked(build_question_answer_links(rows, questions_answers(rows)))


@pytest.mark.parametrize('wh', ['quantos', 'quantas', 'quanta', 'que tipo de'])
def test_quantity_and_type_questions_do_not_become_polar_self_answers(wh):
    rows = [row('Q', f'A gente contou {wh} histórias desse voo?', 'NARRATOR', 0., 4.),
            row('A', 'Sim, a gente contou histórias desse voo.', 'NARRATOR', 4.2, 8.)]
    assert not linked(build_question_answer_links(rows, questions_answers(rows)))
    rows[0]['text'] = 'Ué, a gente já não contou a história desse voo?'
    rows[-1]['text'] = 'Sim!'
    assert not linked(build_question_answer_links(rows, questions_answers(rows)))


def test_rhetorical_followup_is_context_not_an_expected_or_confirmed_answer():
    rows = [row('Q', 'Quem nunca passou por uma crise aérea?', 'NARRATOR', 0., 2.),
            row('A', 'Na verdade, a crise aérea deixa muitas lições.', 'NARRATOR', 2., 5.)]
    questions = questions_answers(rows)
    assert questions[0]['question_type'] == 'rhetorical_question' and not questions[0]['answer_expected']
    links = linked(build_question_answer_links(rows, questions))
    assert len(links) == 1 and links[0]['association_type'] == 'rhetorical_followup'
    assert 'rhetorical_followup_is_not_expected_answer' in links[0]['uncertainties']
    assert not questions[0]['answer_expected'] and not questions[0]['answer_segment_ids']


def test_two_questions_keep_shared_response_ambiguous_instead_of_selecting_one():
    rows = [row('Q1', 'Foi a crise da Varig?', 'ASKER', 0., 2.),
            row('Q2', 'Foi o fechamento da empresa?', 'ASKER', 2., 4.),
            row('A', 'Sim, foi naquele período.', 'RESPONDER', 4., 6.)]
    questions = questions_answers(rows)
    links = linked(build_question_answer_links(rows, questions))
    assert {tuple(link['question_segment_ids']) for link in links} == {('Q1',), ('Q2',)}
    assert all('multiple_questions_match_response' in link['uncertainties'] and link['alternatives'] for link in links)
    assert all(not link['confirmed'] for link in links)


def test_polar_contradiction_is_preserved_as_uncertainty_with_alternatives():
    rows = [row('Q', 'Foi o fechamento da Varig?', 'ASKER', 0., 2.),
            row('A1', 'Sim, a empresa encerrou as operações.', 'R1', 2., 5.),
            row('A2', 'Não, a empresa continuou naquele período.', 'R2', 5., 8.)]
    links = linked(build_question_answer_links(rows, questions_answers(rows)))
    assert len(links) == 2
    assert all('conflicting_response_polarity' in link['uncertainties'] for link in links)
    assert all(link['alternatives'] and not link['confirmed'] for link in links)


def test_partial_answer_and_interruption_remain_visible_without_invented_completion():
    rows, topics, sections = delayed()
    rows[-1]['text'] = 'Respondendo à sua pergunta sobre a crise da Varig, a empresa estava...'
    rows[5]['speaker'] = None
    link = linked(build_question_answer_links(rows, questions_answers(rows), topics, sections))[0]
    assert 'partial_answer_observed' in link['uncertainties']
    assert 'intervening_speaker_ownership_unresolved' in link['uncertainties']
    assert len(link['rationale']['intervening_segment_ids']) == 12
    assert link['question_answer_complete'] is None


def test_causal_response_cue_after_interruption_is_textual_not_confirmed_causality():
    rows = [row('Q', 'Por que a companhia fechou?', 'ASKER', 0., 2.),
            row('C', 'A companhia enfrentou aquele período difícil.', 'ASKER', 2., 4.),
            row('A', 'Porque faltava caixa para a companhia.', 'RESPONDER', 4., 8.)]
    rows[-1]['uncertain_word_ids'] = ['W_SYNTHETIC']
    questions = questions_answers(rows)
    assert questions[0]['answer_status'] == 'unresolved'
    link = linked(build_question_answer_links(rows, questions))[0]
    assert link['answer_segment_ids'] == ['A'] and link['rationale']['response_cue'] == 'causal_response_cue'
    assert not link['causality_confirmed'] and not link['confirmed']
    assert link['source_transcript_needs_review'] and link['uncertain_segment_ids'] == ['A']
    assert questions[0]['answer_status'] == 'unresolved'


def test_proposal_limit_does_not_create_confidence_or_overwrite_existing_qa():
    rows = [row('Q', 'Foi o fechamento da Varig?', 'ASKER', 0., 2.),
            row('A1', 'Sim, a empresa encerrou as operações.', 'R1', 2., 5.),
            row('A2', 'Não, a empresa continuou naquele período.', 'R2', 5., 8.)]
    questions = questions_answers(rows)
    before = deepcopy(questions)
    links = build_question_answer_links(rows, questions, cfg={'max_proposals_per_question': 1})
    assert len(links) == 1 and links[0]['association_type'] == 'existing_qa_link'
    assert questions == before and not links[0]['confirmed']
    with pytest.raises(ValueError, match='invalid_relation_search_bound'):
        build_question_answer_links(rows, questions, cfg={'max_search_seconds': float('nan')})


def test_literal_topic_shift_requires_explicit_reference_before_proposing_old_answer():
    rows = [row('Q', 'Foi o fechamento da Varig?', 'ASKER', 0., 2.),
            row('SHIFT', 'Mudando de assunto, vamos falar de futebol.', 'OTHER', 2., 4.),
            row('A', 'Sim, foi naquele período.', 'RESPONDER', 4., 6.)]
    assert not linked(build_question_answer_links(rows, questions_answers(rows)))
    rows[-1]['text'] = 'Respondendo à sua pergunta sobre o fechamento da Varig, sim.'
    links = linked(build_question_answer_links(rows, questions_answers(rows)))
    assert len(links) == 1 and 'topic_shift_before_explicit_reference' in links[0]['uncertainties']


def test_omitted_temporal_blocker_inside_multipart_question_cannot_be_skipped():
    rows = [row('Q1', 'Por que a companhia fechou?', 'ASKER', 0., 2.),
            row('BLOCK', 'Uma fala simultânea longa.', 'OTHER', 2., 20.),
            row('Q2', 'E como começou a crise?', 'ASKER', 3., 4.),
            row('A', 'Porque a companhia ficou sem caixa.', 'RESPONDER', 5., 8.)]
    question = {'question_id': 'Q_SYNTHETIC', 'question_segment_ids': ['Q1', 'Q2'],
                'question': rows[0]['text']+' '+rows[2]['text'], 'question_speaker': 'ASKER',
                'question_start': 0., 'question_end': 4., 'answer_expected': True,
                'question_type': 'direct_question'}
    assert build_question_answer_links(rows, [question]) == []


def test_arc_source_span_does_not_skip_overlapping_omitted_evidence():
    rows = [row('S', 'Um dia fui trabalhar na empresa aérea.', 'NARRATOR', 0., 4.),
            row('BLOCK', 'Uma fala simultânea longa.', 'OTHER', 5., 20.),
            row('D', 'A empresa aérea tinha problemas.', 'NARRATOR', 10., 14.),
            row('R', 'Retomando a empresa aérea, houve mudanças.', 'NARRATOR', 15., 18.)]
    arcs = [{'story_arc_id': 'OLD', 'evidence_segment_ids': ['S', 'D']}]
    assert build_arc_context_links(rows, arcs) == []


def test_broad_arc_containing_previous_event_cannot_be_later_target():
    rows = [row('S', 'Um dia fui trabalhar na empresa aérea.', 'NARRATOR', 0., 4.),
            row('D', 'A empresa aérea tinha problemas.', 'NARRATOR', 4., 8.),
            row('R', 'Retomando a empresa aérea, houve mudanças.', 'NARRATOR', 120., 126.)]
    arcs = [{'story_arc_id': 'OLD', 'evidence_segment_ids': ['S', 'D']},
            {'story_arc_id': 'BROAD', 'evidence_segment_ids': ['S', 'D', 'R']}]
    links = build_arc_context_links(rows, arcs)
    assert len(links) == 1 and links[0]['target_arc_id'] is None
    assert links[0]['overlapping_target_arc_ids'] == ['BROAD']
    assert 'target_arc_overlaps_previous_event' in links[0]['uncertainties']


def test_unknown_question_owner_is_unresolved_and_duplicate_source_ids_never_guess():
    rows, _, _ = delayed(); rows[0]['speaker'] = None
    questions = questions_answers(rows)
    links = build_question_answer_links(rows, questions)
    assert len(links) == 1 and links[0]['answer_segment_ids'] == []
    assert links[0]['evidence_status'] == 'unresolved' and links[0]['answer_interval'] is None
    rows.append(deepcopy(rows[-1]))
    assert build_question_answer_links(rows, questions) == []


def test_tag_question_does_not_become_answered_by_a_new_relation():
    rows = [row('Q', 'Uma crise difícil, né?', 'ASKER', 0., 2.),
            row('A', 'Respondendo à sua pergunta sobre a crise difícil, sim.', 'OTHER', 2., 5.)]
    assert build_question_answer_links(rows, questions_answers(rows)) == []


def test_arc_resumption_references_previous_event_without_extending_or_supporting_story():
    rows = [row('S', 'Um dia fui trabalhar na empresa aérea.', 'NARRATOR', 0., 4.),
            row('D', 'A empresa aérea tinha problemas.', 'NARRATOR', 4., 8.),
            row('I', 'Outra conversa no programa.', 'OTHER', 30., 35.),
            row('R', 'Retomando a empresa aérea, houve uma mudança.', 'NARRATOR', 120., 126.)]
    arcs = [{'story_arc_id': 'OLD', 'evidence_segment_ids': ['S', 'D'], 'setup': {'segment_ids': ['S']},
             'narrative_supported': False}, {'story_arc_id': 'NEW', 'evidence_segment_ids': ['R'], 'narrative_supported': False}]
    before = deepcopy(arcs)
    links = build_arc_context_links(rows, arcs)
    assert len(links) == 1
    link = links[0]
    assert link['source_arc_id'] == 'OLD' and link['target_arc_id'] == 'NEW'
    assert link['evidence_segment_ids'] == ['S', 'D', 'R']
    assert link['relation'] == 'references_previous_event' and link['evidence_status'] == 'proposed_context_link'
    assert not link['promotes_narrative_support'] and not link['extends_canonical_arc']
    assert not link['confirmed'] and not link['causality_confirmed'] and arcs == before
    rows[-1]['text'] = 'A empresa aérea passou por mudanças.'
    assert build_arc_context_links(rows, arcs) == []


def test_partial_story_development_starts_after_setup_while_layout_remains_explicit():
    rows = [row('P0', 'Primeiro uma introdução do programa.', 'N', 0., 5.),
            row('P1', 'Mais um comentário introdutório.', 'N', 5., 10.),
            row('SETUP', 'Um dia eu fui trabalhar numa companhia.', 'N', 10., 15.),
            row('CONFLICT', 'Mas a companhia tinha um problema.', 'N', 15., 20.),
            row('END', 'Eu continuei trabalhando na companhia.', 'N', 20., 25.)]
    topic = {'topic_id': 'TOPIC', 'topic': 'Companhia', 'summary': 'Fixture sintética.', 'start': 0., 'end': 25.,
             'evidence_segment_ids': [r['segment_id'] for r in rows]}
    arcs = build_story_arcs({'segments': rows}, [topic])
    arc = next(a for a in arcs if a['story_arc_id'] == 'STORY_0000')
    assert arc['development']['segment_ids'] == ['CONFLICT', 'END']
    assert arc['narrative_structure']['development'] == ['CONFLICT', 'END']
    assert arc['section_layout']['development'] == ['P1', 'SETUP', 'CONFLICT']
    assert not arc['structure_contract']['section_layout_is_narrative_evidence']
    assert not arc['narrative_supported'] and arc['payoff'] is None
    validated, _ = _validate_story_arcs_contract([arc], rows)
    assert 'canonical_interval_conflict' not in validated[0]['support_diagnostics']['missing_support_reasons']


def test_discussion_layout_is_not_a_missing_narrative_development_component():
    rows = [row(f'S{i}', 'Um comentário informativo sobre tecnologia.', 'N', i*5., (i+1)*5.) for i in range(3)]
    topic = {'topic_id': 'T', 'topic': 'Tecnologia', 'summary': 'Fixture.', 'start': 0., 'end': 15.,
             'evidence_segment_ids': ['S0', 'S1', 'S2']}
    arc = build_story_arcs({'segments': rows}, [topic])[0]
    assert arc['development'] is None and arc['narrative_structure']['development'] == []
    assert arc['section_layout']['development'] == ['S1'] and not arc['narrative_supported']
