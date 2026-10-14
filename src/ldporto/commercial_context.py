"""Textual commercial context for human review; never a publication decision."""
import re
import unicodedata

from .editorial import classify_content, fold_text, COMMERCIAL_TYPES


CLASSIFICATIONS = ('factual_price_mention', 'contextual_website_reference', 'product_discussion',
                   'advertisement', 'sponsorship', 'call_to_purchase', 'affiliate', 'uncertain')


def _source(candidate, segments):
    declared = candidate.get('evidence_segment_ids') or candidate.get('segment_ids') or []
    ids = list(dict.fromkeys(value for value in (declared if isinstance(declared, (list, tuple)) else [])
        if isinstance(value, str) and value))
    rows = segments.get('segments', []) if isinstance(segments, dict) else segments or []
    selected = [row for row in rows if isinstance(row, dict) and row.get('segment_id') in ids
                and isinstance(row.get('text'), str)]
    by_id = {row['segment_id']: row for row in selected}
    selected = [by_id[value] for value in ids if value in by_id]
    literal = candidate.get('transcript_literal')
    if isinstance(literal, str) and literal.strip():
        return literal, ids, selected, 'candidate_transcript_literal'
    if selected:
        return ' '.join(row['text'] for row in selected), ids, selected, 'referenced_transcript_segments'
    literal = candidate.get('text')
    if not isinstance(literal, str):
        core = candidate.get('core_moment')
        literal = core.get('text') if isinstance(core, dict) else None
    return (literal if isinstance(literal, str) else ''), ids, selected, 'candidate_text_unverified'


def _extra_spans(literal, ids):
    normalized = fold_text(literal)
    offsets = [index for index, character in enumerate(literal) for _ in fold_text(character)]
    patterns = {
        'affiliate': r'\b(?:links? de afiliad[oa]s?|sou afiliad[oa]|somos afiliad[oa]s|'
                     r'(?:ganho|ganhamos|recebo|recebemos) (?:uma )?comissao)\b',
        'physical_measurement': r'\b\d[\d.,]*\s+mil\s+pes\b|'
                                r'\b\d{1,3}\s+vezes\s+a\s+forca\s+da\s+gravidade\b',
    }
    for signal, pattern in patterns.items():
        for match in re.finditer(pattern, normalized):
            start, end = offsets[match.start()], offsets[match.end()-1] + 1
            while end < len(literal) and unicodedata.category(literal[end]) == 'Mn':
                end += 1
            prefix = normalized[max(0, match.start()-48):match.start()]
            negated = bool(re.search(r'\b(?:nao|nunca|sem|nenhum|nenhuma)\s+(?:\w+\s+){0,4}$', prefix))
            yield dict(signal=signal, text=literal[start:end], start_char=start, end_char=end,
                       segment_ids=list(ids), negated=negated)


def contextual_commercial_review(candidate, segments=None):
    """Describe cues in candidate text, without changing scores, gates or rights.

    Optional segments are used only through the candidate's explicit references.
    Segment attribution is literal containment, not word-level alignment or proof
    of a paid relationship. ``factual_price_mention`` names a linguistic mention;
    the monetary claim itself is not fact-checked here.
    """
    candidate = candidate if isinstance(candidate, dict) else {}
    literal, ids, selected, scope = _source(candidate, segments)
    observed = classify_content(literal, ids)
    evidence = [dict(span, negated=False) for span in observed['evidence_spans']]
    evidence.extend(_extra_spans(literal, ids))
    for span in evidence:
        matching = [row['segment_id'] for row in selected if span['text'] in row['text']]
        if matching:
            span['segment_ids'] = matching
            span['segment_attribution'] = 'literal_containment_not_alignment'
        else:
            span['segment_attribution'] = 'candidate_declared_references_not_alignment'
    cues = set(observed['signals'])
    affiliate = any(span['signal'] == 'affiliate' and not span['negated'] for span in evidence)
    reported = (observed['reported_commercial_context'] and
                (observed['commercial_kind'] == 'reported_offer' or 'sales_cta' in cues or affiliate))
    flags = []
    if any(span['signal'] == 'physical_measurement' for span in evidence):
        flags.append('physical_quantity_is_not_a_price_or_payment_plan')
    if reported:
        flags.append('reported_offer_not_proof_of_current_solicitation')
    if any(span.get('negated') for span in evidence):
        flags.append('negated_mention_is_not_affirmative_disclosure')
    if not literal.strip():
        classification = 'uncertain'
        flags.append('literal_text_unavailable')
    elif reported:
        classification = 'uncertain'
    elif affiliate:
        classification = 'affiliate'
    elif 'sponsor' in cues:
        classification = 'sponsorship'
    elif observed['content_type'] in COMMERCIAL_TYPES:
        classification = 'advertisement'
    elif 'sales_cta' in cues:
        classification = 'call_to_purchase'
    elif 'price' in cues:
        classification = 'factual_price_mention'
    elif 'domain' in cues:
        classification = 'contextual_website_reference'
    elif 'product' in cues:
        classification = 'product_discussion'
    else:
        classification = 'uncertain'
        flags.append('no_affirmative_commercial_cue_in_available_text')
    return {
        'schema_version': '1.0',
        'method': 'literal_commercial_context_r5',
        'candidate_id': candidate.get('moment_id') or candidate.get('candidate_id'),
        'classification': classification,
        'classification_scope': scope,
        'claim_scope': 'linguistic_context_only_not_fact_check_or_paid_relationship_verification',
        'context_flags': flags,
        'evidence': evidence,
        'evidence_segment_ids': ids,
        'unresolved_segment_ids': [value for value in ids if value not in {row['segment_id'] for row in selected}],
        'rights_status': 'unknown',
        'payment_confirmed': None,
        'human_review_required': True,
        'publication_effect': 'diagnostic_only',
        'changes_scores_or_gates': False,
        'visual_scope': 'not_evaluated; absence_of_textual_cues_does_not_clear_visual_commercial_risk',
    }
