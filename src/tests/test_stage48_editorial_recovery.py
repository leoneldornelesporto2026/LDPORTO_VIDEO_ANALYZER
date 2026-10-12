"""Synthetic offline evidence; real Clovis references carry no invented speech."""
import json
from copy import deepcopy
from pathlib import Path

import pytest

from ldporto.semantic import questions_answers, qa_contract
from ldporto.story_recovery import recover_story_arcs, editorial_recovery_report
from ldporto.understanding import build_story_arcs, build_main_moments
from ldporto.editorial import rank_candidate, optimize_boundaries
from ldporto.editorial_intelligence import select_editorial_shortlist
from ldporto.second_curation import build_second_curation_package


def row(sid, text, speaker, start, end):
    return dict(segment_id=sid, text=text, speaker=speaker, start=start, end=end)


def dialogue():
    return [row('Q', 'Como gravou o album?', 'H', 100, 103),
            row('A', 'Gravei o album no estudio.', 'G', 103, 110)]


def test_stable_identity_survives_unrelated_question_insertion_and_reordering():
    source = dialogue()
    first = questions_answers(source)[0]
    prefix = [row('EARLY', 'Onde nasceu?', 'H', 0, 3)]
    later = questions_answers(list(reversed(source + prefix)))[1]
    assert first['stable_question_id'] == later['stable_question_id']
    assert first['question_id'] != later['question_id']  # Legacy aliases stay compatible.


def test_explicit_handoff_links_literal_multi_speaker_answer():
    source = dialogue() + [row('B', 'Retomando a gravacao do album, gravamos em casa.', 'B', 110, 118)]
    saved = deepcopy(source)
    qa = questions_answers(source)[0]
    assert qa['answer_segment_ids'] == ['A', 'B'] and qa['answer_speakers'] == ['G', 'B']
    assert qa['association_evidence'][-1]['response_cue'] == 'explicit_speaker_handoff'
    assert qa['question_answer_complete'] is True
    assert source == saved and qa['answer_end'] == 118
    assert qa_contract([qa])['qa_metrics']['verified_complete_qa_count'] is None


def test_grounded_third_speaker_clarification_allows_original_responder_resume():
    source = dialogue() + [row('I', 'Quando voce diz estudio, o que significa?', 'B', 110, 114),
                           row('A2', 'O estudio do album ficava em casa.', 'G', 114, 121)]
    qa = questions_answers(source)[0]
    assert qa['answer_segment_ids'] == ['A', 'A2']
    assert qa['intervening_segment_ids'] == ['I'] and qa['question_answer_complete']
    assert 'Quando voce' not in qa['answer']


@pytest.mark.parametrize('speech', ['Retomando, a cozinha recebeu panelas novas.',
                                  'O album custou muito dinheiro.'])
def test_third_speaker_without_handoff_and_continuity_stays_unresolved(speech):
    qa = questions_answers(dialogue() + [row('B', speech, 'B', 110, 118)])[0]
    assert qa['answer_segment_ids'] == ['A'] and not qa['question_answer_complete']
    assert qa['unresolved_reason'] == 'third_speaker_intervention_unresolved'


def test_indirect_causal_response_has_observed_evidence_not_word_rewrite():
    source = [row('Q', 'Por que desistiu?', 'H', 0, 3),
              row('A', 'Porque faltava dinheiro para pagar os musicos.', 'G', 3, 12)]
    qa = questions_answers(source)[0]
    assert qa['answer'] == source[-1]['text']
    assert qa['association_evidence'][0]['response_cue'] == 'causal_response_cue'
    assert qa['question_answer_complete']


@pytest.mark.parametrize('outcome', ['Consegui cozinhar o jantar.', 'Quando terminou, consegui cozinhar o jantar.'])
def test_unrelated_outcome_inside_same_topic_cannot_complete_story(outcome):
    from test_stage09_story_arcs import fixture
    source, _ = fixture()
    source[-1]['text'] = outcome
    topic = dict(topic_id='T', start=0, end=40, evidence_segment_ids=[r['segment_id'] for r in source])
    for arcs in (recover_story_arcs(source, [topic]), build_story_arcs({'segments': source}, [topic])):
        assert not any(a['kind'] == 'complete_story' for a in arcs)
        assert all(a['payoff'] is None for a in arcs)


def test_conflicting_source_records_are_ambiguity_not_complete_qa():
    qa = questions_answers(dialogue())[0]
    conflicting = {**qa, 'answer': 'Uma fala diferente.'}
    report = editorial_recovery_report([qa], [], [], {'questions_answers': [qa], 'question_answer_pairs': [conflicting]})
    assert report['qa']['textually_complete_requires_review'] == 0
    assert report['qa']['conflicting_record_ids'] == 1
    assert report['qa']['verified_complete'] is None and not report['publish_ready']


def ranked(mid='M', **extra):
    return rank_candidate(dict(moment_id=mid, ideal_start=0, ideal_end=35,
                               clean_opening=True, clean_ending=True, hook_score=.9,
                               standalone_score=.9, context_requirement='none',
                               evidence_segment_ids=['S'], **extra))


def test_optional_punchline_unknown_preserves_ranking_and_alternative():
    candidate = ranked()
    assert candidate['score_components']['punchline'] is None
    assert candidate['score_evidence']['punchline']['status'] == 'unmeasured'
    assert candidate['default_shortlist_eligible']
    alternate = {**ranked('ALT'), 'ideal_start': 600, 'ideal_end': 635}
    selected, report = select_editorial_shortlist([candidate, alternate], max_items=1)
    assert len(selected) == 1
    assert next(d for d in report['candidate_diagnostics'] if d['moment_id'] == 'ALT')['selection_disposition'] == 'alternative'
    assert report['fixed_quota'] is False


def test_missing_required_hook_is_pending_and_cannot_prove_quality():
    candidate = ranked()
    candidate['hook_score'] = None
    candidate = rank_candidate(candidate)
    selected, report = select_editorial_shortlist([candidate])
    assert not selected
    assert report['candidate_diagnostics'][0]['selection_disposition'] == 'pending'
    assert candidate['score_evidence']['hook']['value'] is None


def test_conflicting_scenes_block_humor_context_and_preserve_literal_source():
    source = [row('S', 'Um dia eu fui ao mercado.', 'G', 0, 5),
              row('D', 'Mas ai eu falei uma frase porque', 'G', 5, 10),
              row('P', 'o mercado tinha fechado.', 'G', 10, 15)]
    saved = deepcopy(source)
    result = optimize_boundaries({'start': 5, 'end': 10, 'evidence_segment_ids': ['D'],
                                  'categories': ['humor'], 'context_requirement': 'none'}, source,
                                 shots=[{'start': 0, 'end': 8}, {'start': 8, 'end': 15}])
    assert result['humor_boundary_proposal']['expansion_unresolved']
    assert source == saved


def test_hook_cannot_borrow_words_outside_selected_clip():
    source = [row('S', 'Uma explicacao completa.', 'G', 0, 5),
              row('OUT', 'Nunca contei este segredo.', 'G', 5, 15)]
    moment = dict(moment_id='M', start=0, end=5, evidence_segment_ids=['S'], categories=[],
                  text=source[0]['text'], standalone_class='excellent', context_requirement='none')
    item = build_main_moments({'segments': source}, [], [moment], [], [], [])[0]
    assert item['hook_score'] is None and item['ending_strength'] == 1


def test_three_real_references_remain_unmeasured_without_original_evidence():
    fixture = json.loads((Path(__file__).parent / 'fixtures/stage48_clovis_review_refs.json').read_text(encoding='utf-8'))
    assert fixture['transcript_evidence_available'] is False
    assert len(fixture['candidates']) == 3
    for ref in fixture['candidates']:
        h, m, s = map(int, ref['reported_time'].split(':'))
        assert ref['reported_start'] == h * 3600 + m * 60 + s
        assert ref['transcript'] is None and ref['end'] is None
    package = build_second_curation_package({'main_moments': [], 'transcript_segments': [], 'story_arcs': []})
    assert package['editorial_recovery_report']['candidate_count'] == 0
    assert package['editorial_recovery_report']['narrative_groups'] == []
    assert not package['editorial_recovery_report']['publish_ready']
