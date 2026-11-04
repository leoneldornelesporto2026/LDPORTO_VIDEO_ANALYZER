import json
from pathlib import Path
import pytest
from ldporto.editorial import classify_content


@pytest.mark.parametrize('row', json.loads((Path(__file__).parent / 'fixtures/v44/commercial_false_negatives.json').read_text(encoding='utf-8'))['candidates'])
def test_real_v43_false_negatives_are_excluded_with_literal_evidence(row):
    result = classify_content(row['text'], row['evidence_segment_ids'])
    assert result['eligibility'] == 'excluded', row['moment_id']
    assert result['commercial_score'] >= .7
    assert all(span['text'] == row['text'][span['start_char']:span['end_char']] for span in result['evidence_spans'])


@pytest.mark.parametrize('text', [
    'A Havan é assunto de uma investigação. Não compre por impulso.',
    'Na Openbox eu trabalhei. As lojas perderam vendas durante a crise.',
    'Pagamos 69,99 naquele dia e discutimos o impacto da inflação.',
    'Não aproveite promoções sem comparar os preços.',
])
def test_brand_price_or_negated_sales_are_not_enough(text):
    assert classify_content(text)['eligibility'] != 'excluded'


def test_visual_price_and_discount_corrobate_sales_but_logo_alone_does_not():
    visual = [{'text': 'R$ 69,99 promoção 50% de desconto', 'start': 2, 'end': 4, 'source': 'ocr'}]
    result = classify_content('Passa na loja e aproveita.', ['S1'], visual_evidence=visual)
    assert result['eligibility'] == 'excluded'
    assert any(span.get('modality') == 'visual_text' for span in result['evidence_spans'])
    assert classify_content('Discussão sobre a empresa.', visual_evidence=[{'text': 'HAVAN', 'source': 'ocr'}])['eligibility'] == 'eligible'


def test_post_visual_gate_shortlist_and_metrics_match_delivered_candidates():
    from ldporto.commercial_gate import apply_commercial_refinement
    ad = json.loads((Path(__file__).parent / 'fixtures/v44/commercial_false_negatives.json').read_text(encoding='utf-8'))['candidates'][0]
    start,end=ad['start'],ad['end']
    candidate={**ad,'default_shortlist_eligible':True,'editorial_score_final':.9}
    data={'main_moments':[candidate],'editorial_shortlist':[candidate['moment_id']],
          'candidate_metrics':{'final_shortlist_count':1}}
    segments=[{'segment_id':ad['evidence_segment_ids'][0], 'start':start,'end':end,'text':ad['text']}]
    final=apply_commercial_refinement(data,segments,[],{'max_moments':12})
    assert final['editorial_shortlist'] == []
    assert final['candidate_metrics']['final_shortlist_count'] == 0
    assert final['candidate_metrics']['excluded_commercial_count'] == 1
    assert data['editorial_shortlist'] == [candidate['moment_id']]


def test_commercial_block_propagation_excludes_precursor_candidate_next_to_strong_ad():
    from ldporto.commercial_gate import apply_commercial_refinement
    precursor = {'moment_id': 'PRE', 'ideal_start': 0.0, 'ideal_end': 20.0,
        'core_moment': {'start': 0.0, 'end': 20.0, 'text': 'produto'},
        'text': 'Poltrona eletrica com preco especial, estoque limitado e parcelas.',
        'evidence_segment_ids': ['S0'], 'context_requirement': 'none',
        'standalone_score': .9, 'hook_score': .8, 'clean_opening': True, 'clean_ending': True,
        'duration_suitability_score': .8}
    strong = {'moment_id': 'AD', 'ideal_start': 20.0, 'ideal_end': 45.0,
        'core_moment': {'start': 20.0, 'end': 45.0, 'text': 'promo'},
        'text': 'Aproveite 60% de desconto, pague no Pix e corra para a loja agora.',
        'evidence_segment_ids': ['S1'], 'context_requirement': 'none',
        'standalone_score': .9, 'hook_score': .8, 'clean_opening': True, 'clean_ending': True,
        'duration_suitability_score': .8}
    segments = [
        {'segment_id': 'S0', 'start': 0.0, 'end': 20.0, 'text': precursor['text']},
        {'segment_id': 'S1', 'start': 20.0, 'end': 45.0, 'text': strong['text']}]
    result = apply_commercial_refinement({'main_moments': [precursor, strong], 'candidate_metrics': {}}, segments, [],
                                         {'max_moments': 12, 'target_min_seconds': 15, 'target_max_seconds': 90,
                                          'hard_min_seconds': 8, 'hard_max_seconds': 180,
                                          'allow_story_exception': True, 'allow_commercial_candidates': False,
                                          'commercial_penalty': .5})
    by_id = {row['moment_id']: row for row in result['main_moments']}
    assert by_id['AD']['commercial_classification']['eligibility'] == 'excluded'
    assert by_id['PRE']['commercial_classification']['eligibility'] == 'excluded'
    assert by_id['PRE']['commercial_classification'].get('block_propagated') is True
    assert by_id['PRE']['default_shortlist_eligible'] is False


def test_commercial_block_propagation_does_not_exclude_neutral_brand_discussion_near_ad():
    from ldporto.commercial_gate import apply_commercial_refinement
    neutral = {'moment_id': 'N', 'ideal_start': 0.0, 'ideal_end': 20.0,
               'core_moment': {'start': 0.0, 'end': 20.0, 'text': 'historia'},
               'text': 'Na Openbox eu trabalhei e hoje conto como era a cultura da empresa.',
               'evidence_segment_ids': ['S0'], 'context_requirement': 'none',
               'standalone_score': .9, 'hook_score': .8, 'clean_opening': True, 'clean_ending': True,
               'duration_suitability_score': .8}
    ad = {'moment_id': 'AD', 'ideal_start': 25.0, 'ideal_end': 50.0,
          'core_moment': {'start': 25.0, 'end': 50.0, 'text': 'promo'},
          'text': 'Compre agora com 60% de desconto no Pix e aproveite na loja.',
          'evidence_segment_ids': ['S1'], 'context_requirement': 'none',
          'standalone_score': .9, 'hook_score': .8, 'clean_opening': True, 'clean_ending': True,
          'duration_suitability_score': .8}
    segments = [{'segment_id': 'S0', 'start': 0, 'end': 20, 'text': neutral['text']},
                {'segment_id': 'S1', 'start': 25, 'end': 50, 'text': ad['text']}]
    result = apply_commercial_refinement({'main_moments': [neutral, ad], 'candidate_metrics': {}}, segments, [],
                                         {'max_moments': 12, 'target_min_seconds': 15, 'target_max_seconds': 90,
                                          'hard_min_seconds': 8, 'hard_max_seconds': 180,
                                          'allow_story_exception': True, 'allow_commercial_candidates': False,
                                          'commercial_penalty': .5})
    by_id = {row['moment_id']: row for row in result['main_moments']}
    assert by_id['N']['commercial_classification']['eligibility'] != 'excluded'
