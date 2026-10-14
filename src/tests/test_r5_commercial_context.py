"""R5 literal commercial diagnostics; historical excerpts are not new ASR."""
from copy import deepcopy

import pytest

from ldporto.commercial_context import contextual_commercial_review, CLASSIFICATIONS
from ldporto.editorial import classify_content


@pytest.mark.parametrize('text,excluded_signal,segment_id', [
    ('O avião continuou rumando para o oeste a 20 mil pés.', 'price', 'SEG_00225'),
    ("de 9 G's que é 9 vezes a força da gravidade hoje eles aguentam até 30 G's", 'installment', 'SEG_00375'),
])
def test_varig_historical_physical_quantity_is_not_payment_evidence(text, excluded_signal, segment_id):
    result = classify_content(text, [segment_id])
    assert excluded_signal not in result['signals']
    assert result['content_type'] == 'editorial_content'
    review = contextual_commercial_review({'transcript_literal': text, 'segment_ids': [segment_id]})
    assert review['classification'] == 'uncertain'
    assert 'physical_quantity_is_not_a_price_or_payment_plan' in review['context_flags']
    assert review['evidence'][0]['text'] in text
    assert review['evidence'][0]['segment_ids'] == [segment_id]


@pytest.mark.parametrize('text', [
    'Compre o produto por R$ 20 mil, em 9 vezes sem juros.',
    'Compre agora por 20 mil reais, em 9 vezes de R$ 100.',
    'Compre o produto por 20 mil. Oferta imperdível em 9 vezes.',
    'Compre agora por R$ 99 o equipamento que resiste a 9 vezes a força da gravidade.',
    'Compre 20 mil pés de cabo na loja por R$ 99.',
])
def test_real_offer_cues_survive_physical_exclusions(text):
    result = classify_content(text, ['AD'])
    assert result['eligibility'] == 'excluded'
    assert 'price' in result['signals']
    assert result['commercial_score'] >= .6


def test_suppressed_physical_matches_do_not_hide_later_real_price():
    text = '20 mil pés, 30 mil pés, 40 mil pés. Compre agora por R$ 79.'
    result = classify_content(text)
    assert result['eligibility'] == 'excluded'
    assert [span['text'].rstrip('.') for span in result['evidence_spans'] if span['signal'] == 'price'] == ['R$ 79']


@pytest.mark.parametrize('text,expected', [
    ('Na reportagem discutimos o preço de R$ 79 do produto.', 'factual_price_mention'),
    ('A documentação está em exemplo.org para consulta.', 'contextual_website_reference'),
    ('Discutimos estudos sobre magnésio e seus efeitos colaterais.', 'product_discussion'),
    ('Compre agora o produto por R$ 79.', 'advertisement'),
    ('Nosso patrocinador é a marca Exemplo.', 'sponsorship'),
    ('Compre o produto.', 'call_to_purchase'),
    ('Este é o link de afiliado, recebo uma comissão.', 'affiliate'),
    ('Uma explicação sobre navegação aérea.', 'uncertain'),
])
def test_context_categories_are_diagnostic_only(text, expected):
    candidate = dict(moment_id='M1', transcript_literal=text, segment_ids=['S1'],
                     editorial_score_final=.4, final_gate={'publish_ready': False})
    before = deepcopy(candidate)
    result = contextual_commercial_review(candidate)
    assert result['classification'] == expected and expected in CLASSIFICATIONS
    assert result['rights_status'] == 'unknown'
    assert result['payment_confirmed'] is None and result['human_review_required'] is True
    assert result['publication_effect'] == 'diagnostic_only' and result['changes_scores_or_gates'] is False
    assert 'score' not in result and 'eligibility' not in result and 'publish_ready' not in result
    assert candidate == before
    assert all(text[span['start_char']:span['end_char']] == span['text'] for span in result['evidence'])


def test_reported_ad_does_not_identify_current_speaker_as_seller():
    result = contextual_commercial_review({'text': 'A propaganda dizia: compre agora por R$ 79.'})
    assert result['classification'] == 'uncertain'
    assert 'reported_offer_not_proof_of_current_solicitation' in result['context_flags']


def test_negated_affiliate_and_purchase_are_not_positive_disclosures():
    result = contextual_commercial_review({'text': 'Não usamos link de afiliado. Não compre por impulso.'})
    assert result['classification'] == 'uncertain'
    assert any(row['signal'] == 'affiliate' and row['negated'] for row in result['evidence'])
    assert 'negated_mention_is_not_affirmative_disclosure' in result['context_flags']


def test_references_select_only_candidate_segments_and_preserve_literals():
    segments = [dict(segment_id='OTHER', text='Compre agora por R$ 99.'),
                dict(segment_id='S2', text='Foi mencionado exemplo.org.'),
                dict(segment_id='S1', text='Uma fonte de consulta.')]
    original = deepcopy(segments)
    result = contextual_commercial_review({'segment_ids': ['S1', 'S2']}, segments)
    assert result['classification'] == 'contextual_website_reference'
    assert result['classification_scope'] == 'referenced_transcript_segments'
    assert result['evidence'][0]['segment_ids'] == ['S2']
    assert result['evidence'][0]['segment_attribution'] == 'literal_containment_not_alignment'
    assert result['unresolved_segment_ids'] == []
    assert segments == original


def test_unavailable_text_and_ids_do_not_prove_no_commercial_risk():
    result = contextual_commercial_review({'moment_id': 'M', 'segment_ids': ['MISSING']}, [])
    assert result['classification'] == 'uncertain'
    assert result['unresolved_segment_ids'] == ['MISSING'] and result['evidence'] == []
    assert result['human_review_required']
    assert 'absence_of_textual_cues_does_not_clear_visual_commercial_risk' in result['visual_scope']


@pytest.mark.parametrize('candidate', [None, {}, {'core_moment': 'invalid'}, {'segment_ids': 'NOT_A_LIST'}])
def test_sparse_input_is_conservatively_unresolved(candidate):
    assert contextual_commercial_review(candidate)['classification'] == 'uncertain'
