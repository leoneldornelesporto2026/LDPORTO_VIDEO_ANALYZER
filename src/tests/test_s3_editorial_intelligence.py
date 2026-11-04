"""Session 3: synthetic evidence-based regression, not real-video accuracy claims."""

from ldporto.editorial import rank_candidate, optimize_boundaries
from ldporto.editorial_intelligence import (narrative_integrity, humor_integrity,
                                           select_editorial_shortlist)
from ldporto.semantic import questions_answers, qa_contract
from ldporto.understanding import build_story_arcs, build_main_moments


def segment(sid, start, end, speaker, text):
    return {'segment_id': sid, 'start': start, 'end': end,
            'speaker': speaker, 'text': text}


def candidate(cid, topic, score=.85, *, text=None, arc=None, eligible=True):
    return {'moment_id': cid, 'topic_id': topic, 'story_arc_id': arc,
            'ideal_start': float(int(cid[1:]) * 100),
            'editorial_score_final': score, 'default_shortlist_eligible': eligible,
            'core_moment': {'text': text or 'Uma historia diferente ' + cid}}


def test_story_structure_is_ordered_and_ending_required():
    segments = [segment('I', 0, 8, 'A', 'Um dia aconteceu uma coisa muito estranha.'),
                segment('D', 8, 18, 'A', 'Mas veio um problema que mudou tudo.'),
                segment('P', 18, 29, 'A', 'No final consegui resolver e deu certo.'),
                segment('E', 29, 34, 'A', 'E esse foi o resultado.')]
    topic = {'topic_id': 'T', 'topic': 'O problema e sua resolucao', 'start': 0,
             'end': 34, 'evidence_segment_ids': [s['segment_id'] for s in segments]}
    arc = build_story_arcs({'segments': segments}, [topic])[0]
    assert arc['kind'] == 'complete_story'
    assert arc['narrative_structure']['introduction'] == ['I']
    assert arc['narrative_structure']['climax'] == ['D']
    assert arc['narrative_structure']['resolution'] == ['P']
    assert arc['narrative_structure']['ending'] == ['E']
    assert narrative_integrity(arc, ['I', 'D', 'P', 'E'])['status'] == 'complete_candidate'
    truncated = narrative_integrity(arc, ['I', 'D', 'P'])
    assert truncated['status'] == 'incomplete'
    assert 'missing_story_ending' in truncated['blockers']
    assert 'missing_story_setup' in narrative_integrity(arc, ['D', 'P', 'E'])['blockers']


def test_unresolved_story_does_not_get_invented_payoff():
    arc = {'kind': 'partial_story', 'evidence_segment_ids': ['S1', 'S2'],
           'setup': {'segment_ids': ['S1']}, 'development': {'segment_ids': ['S2']},
           'payoff': None}
    assessment = narrative_integrity(arc, ['S1', 'S2'])
    assert assessment['status'] == 'incomplete'
    assert 'story_payoff_not_grounded' in assessment['blockers']


def test_qa_multiturn_question_requires_continuity_after_reaction():
    rows = [segment('Q1', 0, 4, 'HOST', 'O que aconteceu na sua carreira?'),
            segment('Q2', 4, 6, 'HOST', 'E como resolveu?'),
            segment('A1', 6, 14, 'GUEST', 'Eu estava completamente perdido naquela época.'),
            segment('INT', 14, 16, 'HOST', 'Sério?'),
            segment('A2', 16, 27, 'GUEST', 'A gente mudou de cidade e tudo acabou bem.')]
    qa = questions_answers(rows)[0]
    assert qa['question_segment_ids'] == ['Q1', 'Q2']
    assert qa['answer_segment_ids'] == ['A1']
    assert qa['intervening_segment_ids'] == ['INT']
    assert not qa['question_answer_complete']
    assert qa['unresolved_reason'] == 'answer_continuation_unresolved'
    assert qa['needs_review'] is True
    assert qa_contract([qa])['qa_metrics']['complete_qa_count'] == 0


def test_qa_missing_speaker_remains_unresolved():
    rows = [segment('Q', 0, 3, None, 'Como aconteceu?'),
            segment('A', 3, 10, 'GUEST', 'Foi um acontecimento importante.')]
    qa = questions_answers(rows)[0]
    assert qa['answer_segment_ids'] == []
    assert qa['unresolved_reason'] == 'missing_speaker_evidence'


def test_qa_expands_to_source_question_and_full_answer_without_inventing_times():
    rows = [segment('Q', 0, 5, 'HOST', 'Como conseguiu realizar a gravacao?'),
            segment('A1', 5, 12, 'GUEST', 'Eu gravei tudo em uma sala pequena.'),
            segment('A2', 12, 22, 'GUEST', 'Depois um amigo ajudou a finalizar a gravação.')]
    linked = questions_answers(rows)
    boundary = optimize_boundaries({'start': 5, 'end': 12, 'evidence_segment_ids': ['A1'],
                                    'context_requirement': 'none'}, rows, qa_pairs=linked)
    assert boundary['ideal_start'] == 0 and boundary['ideal_end'] == 22
    assert boundary['boundary_segment_ids'] == ['Q', 'A1', 'A2']
    assert boundary['qa_boundary_expansion_ids'] == ['Q_0000']


def test_humor_after_clip_is_blocked_and_laugh_inside_is_literal_cue():
    rows = [segment('S1', 0, 11, 'A', 'Eu comecei a contar uma piada.'),
            segment('S2', 11, 19, 'A', 'Mas ai ele disse a coisa mais absurda.'),
            segment('S3', 19, 24, 'B', '[risos]')]
    unfinished = humor_integrity(rows, 0, 19, hinted=True)
    assert 'reaction_after_clip' in unfinished['blockers']
    complete = humor_integrity(rows, 0, 24, hinted=True)
    assert complete['laughter_segment_ids'] == ['S3']
    assert complete['blockers'] == []
    assert complete['requires_review']


def test_story_and_humor_blocked_even_when_rank_high():
    raw = {'moment_id': 'M', 'text': 'Uma piada incompleta.', 'ideal_start': 0,
           'ideal_end': 45, 'clean_opening': True, 'clean_ending': True,
           'hook_score': .98, 'standalone_score': .99,
           'context_requirement': 'none', 'editorial_blockers': ['reaction_after_clip']}
    ranked = rank_candidate(raw)
    assert not ranked['default_shortlist_eligible']
    assert ranked['penalties']['editorial_incomplete'] > 0


def test_shortlist_has_no_quota_and_increases_topic_diversity():
    data = [candidate('M1', 'SAME', .93), candidate('M2', 'SAME', .88),
            candidate('M3', 'SAME', .84), candidate('M4', 'OTHER', .78),
            candidate('M5', 'LOW', .30), candidate('M6', 'FAIL', .99, eligible=False)]
    result, report = select_editorial_shortlist(data, max_items=12, min_score=.5, max_per_topic=2)
    assert [row['moment_id'] for row in result] == ['M1', 'M2', 'M4']
    assert report['shortlist_count'] == 3
    assert report['fixed_quota'] is False
    assert any(r['reasons'] == ['topic_diversity_limit'] for r in report['rejected'])


def test_shortlist_blocks_distant_lexical_repetition_without_erasing_distinct_topics():
    text = 'O antigo show da banda e a viagem para Porto Alegre'
    data = [candidate('M1', 'A', .9, text=text),
            candidate('M2', 'B', .8, text=text + ' ontem'),
            candidate('M3', 'C', .7, text='O motor de uma aeronave e a torre')]
    chosen, report = select_editorial_shortlist(data)
    assert [row['moment_id'] for row in chosen] == ['M1', 'M3']
    assert any('semantic_repetition' in r['reasons'] for r in report['rejected'])


def test_main_moments_cannot_shortlist_a_story_cut_before_ending():
    segments = [segment('I', 0, 10, 'A', 'Um dia aconteceu comigo.'),
                segment('D', 10, 20, 'A', 'Mas tive um problema.'),
                segment('P', 20, 30, 'A', 'No final consegui resolver tudo.'),
                segment('E', 30, 40, 'A', 'E assim tudo terminou.')]
    arc = build_story_arcs({'segments': segments}, [{'topic_id': 'T', 'topic': 'Historia',
        'start': 0, 'end': 40, 'evidence_segment_ids': ['I', 'D', 'P', 'E']}])[0]
    # A full arc is in the source and is expanded, so it cannot end at D.
    moments = [{'moment_id': 'M', 'start': 10, 'end': 20, 'text': 'Mas tive um problema.',
                'evidence_segment_ids': ['D'], 'categories': ['storytelling'],
                'standalone_class': 'good', 'context_required': 'none'}]
    ranked = build_main_moments({'segments': segments}, [], moments, [], [arc], [])
    assert ranked[0]['ideal_end'] >= 30
    assert ranked[0]['narrative_integrity']['status'] == 'complete_candidate'
