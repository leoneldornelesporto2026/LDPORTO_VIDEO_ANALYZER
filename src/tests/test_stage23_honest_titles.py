from copy import deepcopy

import pytest

from ldporto.config import DEFAULTS
from ldporto.social_output import build_social_output, select_story_set, title_plan
from ldporto.second_curation_export import _reconcile_social_output
from test_v44_social_output import candidate


@pytest.mark.parametrize('fake', [
    'Eu ganhei um milh\u00e3o de reais.',
    'Eu ganhei um milh\u00e3o de reais ontem.',
    'Um milh\u00e3o de reais eu ganhei.',
    'Eu nunca perdi um milh\u00e3o de reais.',
    'Eu perdi dois milh\u00f5es de reais.',
])
def test_false_hooks_rejected_even_with_same_words(fake):
    row = candidate('A', 0)
    row.update(transcript_literal='Eu n\u00e3o ganhei um milh\u00e3o de reais. Eu perdi dinheiro.',
               generated_copy={'hook_idea': fake})
    plan = title_plan(row)
    rejected = next(r for r in plan['title_rejections'] if r['text'] == fake)
    assert rejected['review_status'] == 'REJECTED'
    assert rejected['evidence_excerpt'] is None
    assert plan['title'] == 'Eu n\u00e3o ganhei um milh\u00e3o de reais.'
    assert plan['title_human_approved'] is False


def test_strong_question_has_exact_evidence_and_review():
    row = candidate('A', 0)
    row.update(transcript_literal='Por que eu larguei tudo? Eu queria tocar m\u00fasica.',
               generated_copy={'hook_idea': 'Por que eu larguei tudo?'})
    plan = title_plan(row)
    assert plan['title'] == 'Por que eu larguei tudo?'
    principal = plan['title_principal']
    assert principal['evidence_excerpt'] == plan['title']
    assert principal['source_evidence']['candidate_id'] == 'A'
    assert principal['requires_review'] is True
    assert principal['fact_verified'] is None
    assert plan['title_alternatives'][0]['text'] == 'Eu queria tocar m\u00fasica.'


@pytest.mark.parametrize('signal', ['word', 'technical', 'subtitle', 'marker'])
def test_uncertain_asr_never_becomes_factual_principal(signal):
    row = candidate('A', 0)
    row['transcript_literal'] = 'Eu larguei tudo para tocar m\u00fasica.'
    analysis = {}
    if signal == 'word':
        analysis['words'] = [{'word': 'larguei', 'start': 1, 'end': 2, 'needs_review': True, 'confidence': .9}]
    if signal == 'technical':
        row['technical_quality'] = {'asr_low_confidence_fraction': .1}
    if signal == 'subtitle':
        analysis['subtitle_review_s7'] = {'candidates': {'A': {'issue_counts': {'alternate_asr_requires_listening': 1}}}}
    if signal == 'marker':
        row['transcript_literal'] += ' [inaud\u00edvel]'
    result = build_social_output(analysis, deepcopy(DEFAULTS), {'candidates': [row]})
    story = result['stories'][0]
    assert story['title'] is None
    assert story['title_principal'] is None
    assert story['title_status'] == 'TITLE_REVIEW_REQUIRED'
    assert story['title_variants'][0]['review_status'] == 'LISTEN_AND_REVIEW'
    assert story['publication_ready'] is False


@pytest.mark.parametrize('text', ['', 'Eu ganhei tudo mas depois perdi',
    'Eu ganhei tudo na primeira rodada do campeonato por\u00e9m na segunda rodada perdi absolutamente tudo novamente.'])
def test_missing_or_long_sentence_is_not_truncated_into_claim(text):
    row = candidate('A', 0)
    row['transcript_literal'] = text
    plan = title_plan(row)
    assert plan['title'] is None
    assert plan['title_status'] == 'TITLE_REVIEW_REQUIRED'
    assert plan['title_source_evidence']['text'] == (text or None)


def test_temporal_and_category_balance_without_filling_with_ads_or_weak_clips():
    rows = [candidate('A', 0, 'humor', 'T1', score=.9),
            candidate('B', 90, 'humor', 'T2', score=.9),
            candidate('C', 650, 'emocao', 'T3', score=.88),
            candidate('AD', 1250, commercial=True, score=.99),
            candidate('WEAK', 1800, score=.01)]
    rows[-1].update(hook_strength=0, ranking_confidence=0, score_components={})
    selected, metrics = select_story_set(rows, {'max_stories': 2})
    assert {r['candidate_id'] for r in selected} == {'A', 'C'}
    assert len(metrics['window_counts']) == 2
    selected, metrics = select_story_set(rows, {'max_stories': 12})
    assert len(selected) == 3
    assert metrics['unfilled_slots_are_intentional'] is True


def test_export_rechecks_stale_title_and_syncs_suggestions():
    row = candidate('A', 0)
    row.update(publication_eligible=True, transcript_literal='Eu n\u00e3o ganhei dinheiro.')
    social = {'stories': [{'story_id': 'STORY_001', 'candidate_id': 'A', 'title': 'Eu ganhei dinheiro.'}],
              'title_suggestions': [{'story_id': 'STORY_001', 'title': 'Eu ganhei dinheiro.'}]}
    output = _reconcile_social_output(social, [row], True)
    story = output['stories'][0]
    assert story['title'] == 'Eu n\u00e3o ganhei dinheiro.'
    assert story['title_rejections'][0]['text'] == 'Eu ganhei dinheiro.'
    assert output['title_suggestions'][0]['title'] == story['title']
    assert output['publication_ready'] is False
    assert social['stories'][0]['title'] == 'Eu ganhei dinheiro.'


def test_export_rechecks_uncertainty_from_current_analysis():
    row = candidate('A', 0)
    row.update(publication_eligible=True, transcript_literal='Eu ganhei dinheiro.')
    social = {'stories': [{'story_id': 'STORY_001', 'candidate_id': 'A', 'title': row['transcript_literal']}]}
    analysis = {'words': [{'word': 'ganhei', 'start': 1, 'end': 2, 'confidence': .2}]}
    output = _reconcile_social_output(social, [row], True, analysis)
    assert output['stories'][0]['title'] is None
    assert output['title_suggestions'][0]['status'] == 'TITLE_REVIEW_REQUIRED'


def test_category_balance_does_not_override_quality_band():
    rows = [candidate('A', 0, 'humor', 'T1', score=.99),
            candidate('B', 90, 'humor', 'T2', score=.99),
            candidate('C', 650, 'emocao', 'T3', score=.5)]
    selected, _ = select_story_set(rows, {'max_stories': 2})
    assert {r['candidate_id'] for r in selected} == {'A', 'B'}
