"""Offline synthetic dialogue only; assertions do not verify audio or correctness."""
from copy import deepcopy

import pytest

from ldporto.semantic import questions_answers, qa_contract
from ldporto.editorial import optimize_boundaries


def row(sid, text, speaker, start, end):
    return dict(segment_id=sid, text=text, speaker=speaker, start=start, end=end)


def dialogue(interruption='Sério?', resume='Depois finalizei o álbum com a banda.'):
    return [row('Q', 'Como gravou o álbum?', 'HOST', 0, 3),
            row('A1', 'Gravei o álbum no estúdio.', 'GUEST', 3, 8),
            row('I', interruption, 'HOST', 8, 12),
            row('A2', resume, 'GUEST', 12, 20)]


@pytest.mark.parametrize('interruption', ['Sério?', 'Muito bom!', 'Como assim?',
                                         'Quando você diz estúdio, o que significa?'])
def test_answer_resumes_with_literal_timestamps_and_independent_evidence(interruption):
    rows = dialogue(interruption)
    before = deepcopy(rows)
    qa = questions_answers(rows)[0]
    assert qa['answer_segment_ids'] == ['A1', 'A2']
    assert qa['answer_span'] == {'start': 3, 'end': 20}
    assert qa['answer_start'] == 3 and qa['answer_end'] == 20
    assert qa['answer'] == rows[1]['text'] + ' ' + rows[3]['text']
    assert qa['evidence_segment_ids'] == ['Q', 'A1', 'I', 'A2']
    assert qa['intervening_segment_ids'] == ['I']
    assert qa['association_evidence'][1] == dict(segment_id='A2', start=12, end=20,
        speaker='GUEST', speaker_matches_responder=True, shared_terms=['album'],
        response_cue='continuation_cue', pause_seconds=0, responder_pause_seconds=4,
        intervening_segment_ids=['I'])
    assert qa['intervention_evidence'][0]['segment_id'] == 'I'
    assert qa['confidence'] is None and qa['needs_review'] is True
    assert qa['question_answer_complete'] and qa['unresolved_reason'] is None
    assert rows == before


def test_clarification_before_answer_is_context_not_an_answer():
    rows = [row('Q', 'Como gravou o álbum?', 'HOST', 0, 3),
            row('C', 'Como assim?', 'GUEST', 3, 5),
            row('CTX', 'Falo da gravação do álbum no estúdio.', 'HOST', 5, 9),
            row('A', 'Gravei o álbum com a banda.', 'GUEST', 9, 15)]
    qa = questions_answers(rows)[0]
    assert qa['question_segment_ids'] == ['Q']
    assert qa['answer_segment_ids'] == ['A'] and qa['answer_start'] == 9
    assert qa['evidence_segment_ids'] == ['Q', 'C', 'CTX', 'A']
    assert [e['kind'] for e in qa['intervention_evidence']] == ['clarification_cue', 'clarification_context']


def test_new_question_after_request_for_clarification_remains_separate():
    rows = [row('Q', 'Como gravou o álbum?', 'HOST', 0, 3),
            row('C', 'Como assim?', 'GUEST', 3, 5),
            row('Q2', 'Quem gravou o álbum?', 'HOST', 5, 9),
            row('A', 'Meu amigo gravou o álbum.', 'GUEST', 9, 15)]
    first = questions_answers(rows)[0]
    assert first['answer'] is None and first['unresolved_reason'] == 'new_question_before_answer'
    assert first['question_segment_ids'] == ['Q']


def test_boundary_consumer_includes_question_intervention_and_full_resumed_answer():
    rows = dialogue('Como assim?')
    records = questions_answers(rows)
    boundary = optimize_boundaries({'start': 3, 'end': 8, 'evidence_segment_ids': ['A1'],
                                    'context_requirement': 'none'}, rows, qa_pairs=records)
    assert boundary['ideal_start'] == 0 and boundary['ideal_end'] == 20
    assert boundary['boundary_segment_ids'] == ['Q', 'A1', 'I', 'A2']
    assert boundary['qa_boundary_expansion_ids'] == ['Q_0000']


def test_two_independent_questions_do_not_share_the_last_answer():
    rows = [row('Q1', 'Como gravou o álbum?', 'HOST', 0, 3),
            row('Q2', 'Onde nasceu sua filha?', 'HOST', 3, 6),
            row('A', 'Minha filha nasceu em Santos.', 'GUEST', 6, 10)]
    first, second = questions_answers(rows)
    assert first['answer'] is None and first['answer_start'] is None
    assert first['unresolved_reason'] == 'new_question_before_answer'
    assert first['question_segment_ids'] == ['Q1']
    assert second['answer_segment_ids'] == ['A']
    assert qa_contract([first, second])['qa_metrics']['answered_question_count'] == 1


def test_connective_does_not_merge_questions_about_different_topics():
    rows = [row('Q1', 'Como gravou o álbum?', 'HOST', 0, 3),
            row('Q2', 'E onde nasceu sua filha?', 'HOST', 3, 6),
            row('A', 'Minha filha nasceu em Santos.', 'GUEST', 6, 10)]
    first, second = questions_answers(rows)
    assert first['answer'] is None and first['question_segment_ids'] == ['Q1']
    assert second['answer_segment_ids'] == ['A']


def test_explicit_question_reformulation_preserves_source_ids():
    rows = [row('Q1', 'Como gravou o álbum?', 'HOST', 0, 3),
            row('Q2', 'Ou melhor, como foi a gravação?', 'HOST', 3, 6),
            row('A', 'Gravei o álbum em casa.', 'GUEST', 6, 10)]
    qa = questions_answers(rows)[0]
    assert qa['question_segment_ids'] == ['Q1', 'Q2']
    assert qa['question_end'] == 6 and qa['answer_end'] == 10


@pytest.mark.parametrize('question', ['Onde nasceu sua filha?', 'Onde?', 'Qual disco lançou?'])
def test_short_new_question_is_never_a_reaction(question):
    qa = questions_answers(dialogue(question, 'Minha filha nasceu em Santos.'))[0]
    assert qa['answer_segment_ids'] == ['A1'] and qa['answer_end'] == 8
    assert qa['unresolved_reason'] == 'new_question_during_answer'
    assert not qa['question_answer_complete'] and qa['answer_completeness'] == 'partial'
    assert qa['intervening_segment_ids'] == []


@pytest.mark.parametrize('text', ['A temperatura tropical trouxe ventos fortes na costa distante.',
                                'Foi uma viagem maravilhosa até a costa distante.',
                                'Sim, minha filha nasceu em Santos.'])
def test_next_speaker_and_long_speech_do_not_prove_relevance(text):
    qa = questions_answers([row('Q', 'Qual disco lançou?', 'HOST', 0, 3),
                            row('A', text, 'GUEST', 3, 10)])[0]
    assert qa['answer'] is None and qa['answer_span'] is None
    assert qa['answer_speaker'] is None and qa['answer_relevance'] is None
    assert qa['unresolved_reason'] == 'answer_relevance_unresolved'


@pytest.mark.parametrize('resume,reason', [
    ('A temperatura tropical trouxe ventos fortes na costa distante.', 'answer_continuation_unresolved'),
    ('Depois fiz uma viagem até a costa distante.', 'answer_continuation_unresolved'),
    ('Mudando de assunto, o álbum é caro.', 'topic_change_observed'),
    ('Qual álbum você prefere?', 'new_question_during_answer'),
])
def test_same_responder_cannot_append_a_different_subject(resume, reason):
    qa = questions_answers(dialogue(resume=resume))[0]
    assert qa['answer_segment_ids'] == ['A1'] and qa['answer_end'] == 8
    assert qa['unresolved_reason'] == reason and not qa['question_answer_complete']
    assert [e['segment_id'] for e in qa['association_evidence']] == ['A1']


def test_pause_extended_only_with_lexical_continuity():
    rows = dialogue()
    rows[3].update(start=25, end=30)
    qa = questions_answers(rows)[0]
    assert qa['answer_end'] == 30 and qa['answer_segment_ids'] == ['A1', 'A2']
    assert qa['association_evidence'][1]['pause_seconds'] == 13
    rows[3]['text'] = 'Depois uma viagem mudou nossa vida.'
    qa = questions_answers(rows)[0]
    assert qa['answer_end'] == 8 and qa['unresolved_reason'] == 'answer_continuation_unresolved'


def test_pause_outside_window_remains_pending():
    rows = dialogue()
    rows[3].update(start=40, end=45)
    qa = questions_answers(rows)[0]
    assert qa['answer_end'] == 8 and qa['unresolved_reason'] == 'pause_exceeds_search_window'
    assert not qa['question_answer_complete']


@pytest.mark.parametrize('speaker,reason', [(None, 'missing_speaker_evidence'),
                                          ('THIRD', 'third_speaker_intervention_unresolved')])
def test_unknown_or_third_speaker_does_not_authorize_resume(speaker, reason):
    rows = dialogue()
    rows[2]['speaker'] = speaker
    qa = questions_answers(rows)[0]
    assert qa['answer_segment_ids'] == ['A1'] and qa['unresolved_reason'] == reason


def test_asr_fragment_keeps_full_response_without_interviewer_text():
    rows = [row('Q', 'Como gravou o álbum?', 'HOST', 0, 3),
            row('A1', 'Gravei o álbum', 'GUEST', 3, 5),
            row('I', 'Entendi.', 'HOST', 5, 6),
            row('A2', 'em uma sala pequena.', 'GUEST', 6, 9)]
    qa = questions_answers(rows)[0]
    assert qa['answer'] == 'Gravei o álbum em uma sala pequena.'
    assert qa['answer_end'] == 9
    assert qa['association_evidence'][1]['response_cue'] == 'asr_fragment_cue'


def test_clarification_without_resumed_answer_cannot_be_complete():
    qa = questions_answers(dialogue('Como assim?')[:-1])[0]
    assert qa['unresolved_reason'] == 'answer_resume_not_observed'
    assert not qa['question_answer_complete']


def test_search_limit_cannot_claim_full_response():
    rows = [row('Q', 'Como gravou o álbum?', 'HOST', 0, 1)]
    rows += [row(f'A{i}', 'Gravei o álbum.', 'GUEST', i + 1, i + 2) for i in range(34)]
    qa = questions_answers(rows)[0]
    assert len(qa['answer_segment_ids']) == 32
    assert qa['unresolved_reason'] == 'answer_segment_search_limit'
    assert not qa['question_answer_complete']
