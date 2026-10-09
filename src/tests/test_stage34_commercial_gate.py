"""Offline synthetic evidence only; no ASR, OCR engine or media pipeline."""
from copy import deepcopy

from ldporto.commercial_gate import apply_commercial_refinement, build_commercial_blocks, targeted_ocr
from ldporto.editorial import classify_content, rank_candidate
from ldporto.second_curation import build_second_curation_package
from ldporto.second_curation_export import _final_commercial_classification
from ldporto.social_output import build_social_output, select_story_set
from ldporto.config import DEFAULTS
from test_s8_commercial_graphics_stories import _moment, _candidate


def offer(voice='SP1'):
    return [dict(segment_id='PRICE', start=0, end=10, text='O curso custa R$ 79.', speaker=voice),
            dict(segment_id='CTA', start=10, end=20, text='Compre agora.', speaker=voice)]


def test_split_offer_voice_ocr_and_ids_reach_curator_and_ranking():
    segments = offer()
    visual = [dict(source='ocr', text='R$ 79', start=5, end=5, uncertain=True)]
    result = apply_commercial_refinement({'main_moments': [_moment('PRICE_ONLY', 0, 10)]}, segments, visual, {})
    block = result['commercial_blocks'][0]
    assert block['voice_evidence'] == {'speaker_ids': ['SP1'], 'continuity': 'same_observed_voice'}
    assert block['visual_corroboration'] == visual
    assert block['segment_ids'] == ['PRICE', 'CTA']
    moment = result['main_moments'][0]
    assert moment['excluded_commercial_interval_ids'] == [block['block_id']]
    assert moment['commercial_classification']['eligibility'] == 'excluded'
    assert not result['editorial_shortlist']

    ranked = rank_candidate(moment)
    assert ranked['commercial_classification']['eligibility'] == 'excluded'
    assert ranked['excluded_commercial_interval_ids'] == moment['excluded_commercial_interval_ids']
    package = build_second_curation_package({**result, 'transcript_segments': segments})
    candidate = package['candidates'][0]
    assert candidate['commercial_block_refs'] == [block['block_id']]
    assert candidate['excluded_commercial_interval_ids'] == [block['block_id']]
    assert not candidate['default_shortlist_eligible']
    assert _final_commercial_classification(candidate)['eligibility'] == 'excluded'


def test_different_voices_cannot_prove_split_offer():
    segments = offer()
    segments[1]['speaker'] = 'SP2'
    result = apply_commercial_refinement({'main_moments': [_moment('M', 0, 10)]}, segments, [], {})
    block = result['commercial_blocks'][0]
    assert block['classification']['eligibility'] == 'review'
    assert block['voice_evidence']['continuity'] == 'different_observed_voices'
    assert result['main_moments'][0]['commercial_classification']['eligibility'] == 'review'
    assert not result['editorial_shortlist']
    package = build_second_curation_package({**result, 'transcript_segments': segments})
    assert _final_commercial_classification(package['candidates'][0])['eligibility'] == 'review'


def test_missing_voice_remains_null_not_an_identity():
    segments = offer(None)
    assert build_commercial_blocks(segments)[0]['voice_evidence']['continuity'] is None


def test_time_gap_does_not_combine_price_and_cta():
    segments = offer()
    segments[1].update(start=40, end=50)
    assert not build_commercial_blocks(segments)


def test_even_short_overlap_with_excluded_interval_blocks_selection():
    segments = [dict(segment_id='AD', start=20, end=40, text='Compre agora por R$ 79.')]
    result = apply_commercial_refinement({'main_moments': [_moment('EDGE', 0, 20.1)]}, segments, [], {})
    assert result['main_moments'][0]['commercial_classification']['eligibility'] == 'excluded'
    assert not result['editorial_shortlist']


def test_neutral_brand_reporting_is_eligible_and_reported_offer_needs_review():
    neutral = 'Na reportagem discutimos a Apple e o preço de R$ 79 do produto.'
    assert classify_content(neutral)['eligibility'] == 'eligible'
    reported = 'A propaganda dizia: compre agora o produto por R$ 79.'
    assert classify_content(reported)['eligibility'] == 'review'
    assert classify_content(reported)['commercial_kind'] == 'reported_offer'
    assert not build_commercial_blocks([dict(segment_id='N', start=0, end=20, text=reported)])


def test_invitation_and_offer_are_separate_without_inventing_payment():
    invitation = classify_content('Venham ao meu show neste sábado.')
    assert invitation['eligibility'] == 'excluded'
    assert invitation['commercial_kind'] == 'guest_promotional_invitation'
    assert any(span['signal'] == 'guest_invitation' and span['text'] == 'Venham ao meu show'
               for span in invitation['evidence_spans'])
    paid = classify_content('Nosso patrocinador: compre agora por R$ 79.')
    assert paid['commercial_kind'] == 'paid_ad_or_sales_offer'
    assert paid['payment_confirmed'] is None


def test_adjacent_journalistic_price_preamble_not_absorbed_by_ad():
    segments = [dict(segment_id='NEWS', start=0, end=10,
                     text='Na reportagem discutimos o produto e o preço de R$ 79.'),
                dict(segment_id='AD', start=10, end=30, text='Compre agora por R$ 79.')]
    result = apply_commercial_refinement({'main_moments': [_moment('NEWS', 0, 10)]}, segments, [], {})
    assert result['commercial_blocks'][0]['segment_ids'] == ['AD']
    assert result['main_moments'][0]['commercial_classification']['eligibility'] == 'eligible'


def test_interval_ids_alone_fail_closed_for_export_stories_and_ranking():
    candidate = _candidate('AD', 0)
    candidate['excluded_commercial_interval_ids'] = ['COMMERCIAL_0001']
    selected, metrics = select_story_set([candidate], {'max_stories': 12})
    assert not selected
    assert _final_commercial_classification(candidate)['eligibility'] == 'excluded'
    moment = {**_moment('AD', 0, 35), 'excluded_commercial_interval_ids': ['COMMERCIAL_0001']}
    assert rank_candidate(moment)['default_shortlist_eligible'] is False
    assert metrics['candidate_decisions'][0]['excluded_commercial_interval_ids'] == ['COMMERCIAL_0001']


def test_neutral_story_keeps_block_references_and_no_publication_authority():
    candidate = _candidate('NEUTRAL', 0)
    candidate['commercial_block_refs'] = []
    result = build_social_output({}, deepcopy(DEFAULTS), {'candidates': [candidate]})
    assert result['stories'][0]['commercial_block_refs'] == []
    assert result['stories'][0]['excluded_commercial_interval_ids'] == []
    assert result['stories'][0]['publication_ready'] is False
    assert targeted_ocr('not-opened.mp4', [], {'enabled': False})['commercial_present'] is None


def test_ocr_cannot_downgrade_prior_exclusion():
    candidate = _moment('M', 0, 20)
    candidate['commercial_classification'] = classify_content('Compre agora por R$ 79.')
    segments = [dict(segment_id='N', start=0, end=20, text='Uma história da infância.')]
    visual = [dict(source='ocr', text='Compre por R$ 79', start=10, end=10, uncertain=True)]
    result = apply_commercial_refinement({'main_moments': [candidate]}, segments, visual, {})
    assert result['main_moments'][0]['commercial_classification']['eligibility'] == 'excluded'
