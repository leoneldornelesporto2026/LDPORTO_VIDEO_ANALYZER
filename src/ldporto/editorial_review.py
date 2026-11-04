"""Qualitative human triage and source-bound proposals; never ranking or approval."""
import math
import re


_CTA = {
    'subscription_request': r'\b(?:se\s+inscrev[ae]|inscrev[ae]-se)\b',
    'comment_request': r'\bcoment[ae](?:m)?\b',
    'like_request': r'\b(?:deix[ae]\s+(?:o\s+seu\s+)?like|curt[ae]\s+(?:o\s+)?v[ií]deo)\b',
    'share_request': r'\bcompartilh[ae](?:m)?\b',
}
_INTEREST = {
    'story_cue': r'\b(?:tem\s+uma\s+hist[oó]ria|um\s+dia|uma\s+vez|lembro|lembra|tentei|aconteceu)\b',
    'contrast_or_surprise_cue': r'\b(?:achei\s+que\s+era|pensei\s+que|mas\s+na\s+verdade|n[aã]o\s+era\s+isso)\b',
    'experience_cue': r'\b(?:fico\s+nervos[ao]|fiquei\s+nervos[ao]|me\s+sinto|pela\s+primeira\s+vez|primeiro\s+v[ií]deo)\b',
}
_HOUSEKEEPING = re.compile(r'\b(?:at[eé]\s+o\s+pr[oó]ximo\s+epis[oó]dio|beijo[, ]+tchau|obrigad[ao]|despedida)\b', re.I)


def editorial_potential(candidate):
    """Separate literal requests from editorial hypotheses without adding a score."""
    from .export_privacy import sanitize_export
    # Character offsets must remain reproducible after the existing export redaction.
    text = sanitize_export(candidate.get('transcript_literal') or '')
    cues, direct = [], []
    for kind, pattern in {**_CTA, **_INTEREST}.items():
        for match in re.finditer(pattern, text, re.I):
            prefix = text[max(0, match.start() - 100):match.start()]
            reported = bool(re.search(r'\b(?:disse|falou|falava|pediu|pedia|frase|exemplo)\b[^.!?]*$', prefix, re.I))
            negated = bool(re.search(r'\b(?:n[aã]o|nunca)\s*$', prefix, re.I))
            row = {'kind': kind, 'literal': match.group(), 'start_char': match.start(),
                   'end_char': match.end(), 'source': 'candidate.transcript_literal',
                   'reported_or_negated_context': reported or negated}
            cues.append(row)
            if kind in _CTA and not reported and not negated:
                direct.append(row)
    interest = [row for row in cues if row['kind'] in _INTEREST]
    context = sanitize_export(' '.join(row.get('text', '') for row in candidate.get('context_after') or []
                                       if isinstance(row, dict)))
    closing = _HOUSEKEEPING.search(text) or _HOUSEKEEPING.search(context)
    housekeeping = len({row['kind'] for row in direct}) >= 2 or bool(direct and closing)
    classification = ('MIXED_CTA_CONTENT' if housekeeping and interest else
                      'CTA_HOUSEKEEPING' if housekeeping else
                      'CONTENT_REVIEW' if interest else 'UNRESOLVED')
    return {'schema_version': '1.0', 'classification': classification,
            'cue_offset_scope': 'privacy_sanitized_export_transcript',
            'recorded_categories': list(candidate.get('categories') or []),
            'literal_cues': cues, 'closing_context_cue': closing.group() if closing else None,
            'interpretation': 'literal_cues_and_recorded_categories_are_review_hypotheses',
            'story_supported': None, 'humor_confirmed': None, 'surprise_verified': None,
            'human_quality_verified': None, 'new_score_created': False,
            'source_score_changed': False, 'requires_human_review': True}


def review_milestones(candidate):
    """Independent dimensions; an interest cue grants no eligibility or approval."""
    classification = editorial_potential(candidate)['classification']
    return {'interest_state': 'INTERESTING_CANDIDATE' if classification in
                {'CONTENT_REVIEW', 'MIXED_CTA_CONTENT'} else 'INTEREST_UNRESOLVED' if
                classification == 'UNRESOLVED' else 'HOUSEKEEPING_REVIEW',
            'interest_is_hypothesis': True,
            'eligibility_state': 'ELIGIBLE_FOR_REVIEW' if candidate.get('eligible_for_human_review') is True
                else 'NOT_ELIGIBLE_FOR_REVIEW',
            'human_review_state': 'HUMAN_REVIEW_PENDING',
            'human_review_completed': False, 'preview_approved': False, 'publish_ready': False,
            'narrative_quality_verified': None, 'acoustic_quality_verified': None,
            'visual_quality_verified': None, 'speaker_identity_verified': None, 'crop_approved': False}


def boundary_review_proposals(candidate, segments, topics=None):
    """Suggest canonical edges/adjacent context without applying or certifying them."""
    rows = [row for row in segments if isinstance(row, dict) and row.get('segment_id') and
            isinstance(row.get('text'), str) and row['text'].strip() and
            all(isinstance(row.get(key), (int, float)) and not isinstance(row[key], bool)
                and math.isfinite(row[key]) for key in ('start', 'end')) and 0 <= row['start'] < row['end']]
    rows.sort(key=lambda row: (row['start'], row['end']))
    if len({row['segment_id'] for row in rows}) != len(rows):
        return []
    positions = {row['segment_id']: index for index, row in enumerate(rows)}
    selected_ids = candidate.get('segment_ids') or []
    if not selected_ids or any(sid not in positions for sid in selected_ids):
        return []
    indices = sorted({positions[sid] for sid in selected_ids})
    if indices != list(range(indices[0], indices[-1] + 1)):
        return []
    start, end = candidate.get('start'), candidate.get('end')
    if not all(isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)
               for value in (start, end)) or not 0 <= start < end:
        return []
    source = rows[indices[0]:indices[-1] + 1]
    if any(row['end'] <= start or row['start'] >= end for row in source):
        return []
    if any(right['start'] < left['end'] - 1e-6 for left, right in zip(source, source[1:])):
        return []
    contract = candidate.get('duration_contract') or {}
    maximum = contract.get('hard_max_seconds')
    if not isinstance(maximum, (int, float)) or isinstance(maximum, bool) or not math.isfinite(maximum):
        return []
    topic_sets = {row['segment_id']: {topic.get('topic_id') for topic in topics or []
        if row['segment_id'] in (topic.get('evidence_segment_ids') or []) and topic.get('topic_id')}
        for row in rows}
    selected_topics = set().union(*(topic_sets[row['segment_id']] for row in source))
    proposals = []
    def propose(kind, observed, added=()):
        duration = observed[-1]['end'] - observed[0]['start']
        minimum = contract.get('hard_min_seconds', 0)
        if not isinstance(minimum, (int, float)) or isinstance(minimum, bool) or not math.isfinite(minimum):
            return
        if not minimum <= duration <= maximum:
            return
        if any(right['start'] < left['end'] - 1e-6 for left, right in zip(observed, observed[1:])):
            return
        proposals.append({'proposal_id': str(candidate.get('candidate_id')) + ':' + kind,
            'kind': kind, 'start': observed[0]['start'], 'end': observed[-1]['end'],
            'duration_seconds': duration, 'duration_contract': dict(contract),
            'segment_ids': [row['segment_id'] for row in observed],
            'added_context_segment_ids': [row['segment_id'] for row in added],
            'first_literal': observed[0]['text'], 'last_literal': observed[-1]['text'],
            'ending_punctuation_observed': bool(re.search(r'[.!?]$', observed[-1]['text'].rstrip()))
                and not observed[-1]['text'].rstrip().endswith(('...', '…')),
            'semantic_completion_verified': None, 'requires_human_review': True,
            'applied': False, 'source_preserve': True, 'publication_ready': False,
            'topic_scope': 'recorded_source_topics' if selected_topics else 'unmeasured'})
    propose('canonical_segment_edges', source)
    def adjacent_allowed(row, gap):
        known = topic_sets[row['segment_id']]
        return 0 <= gap <= 5 and bool(known and selected_topics and known <= selected_topics)
    first, last = indices[0], indices[-1]
    if first and (re.match(r'^(?:que|e|mas|porque|assim|ent[aã]o|a[ií]|inclusive)\b', source[0]['text'], re.I)
                  or candidate.get('clean_opening') is False):
        previous = rows[first - 1]
        if adjacent_allowed(previous, source[0]['start'] - previous['end']):
            propose('inspect_preceding_context', [previous, *source], [previous])
    if last + 1 < len(rows) and (candidate.get('clean_ending') is False or
                                not re.search(r'[.!?]$', source[-1]['text'].rstrip()) or
                                source[-1]['text'].rstrip().endswith(('...', '…'))):
        following = rows[last + 1]
        if adjacent_allowed(following, following['start'] - source[-1]['end']):
            propose('inspect_following_continuation', [*source, following], [following])
    return proposals
