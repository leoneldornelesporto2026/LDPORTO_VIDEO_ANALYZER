"""Explain an editorial result without changing selection, scores or review gates."""
from collections import Counter

from .editorial import duration_contract, finite_score
from .ollama_local import measured_number


MESSAGES = {
    'selected': 'Candidatos selecionados para revisao humana.',
    'no_eligible_cuts': 'Nenhum corte elegivel passou pelos criterios registrados.',
    'insufficient_evidence': 'Evidencia insuficiente para aprovar uma shortlist.',
    'video_too_short': 'Video curto demais para a duracao alvo da shortlist configurada.',
    'technical_error': 'Erro tecnico impede concluir a avaliacao editorial.',
    'low_quality_candidates': 'Candidatos avaliados ficaram abaixo do piso de qualidade editorial.',
}


def full_source_review(analysis, contract=None):
    """A short source is reviewable as evidence, never an automatically eligible clip."""
    contract = contract or duration_contract()
    duration = measured_number((analysis.get('metadata') or {}).get('duration'))
    segments = analysis.get('transcript_segments') or []
    if duration is None or duration <= 0 or duration >= contract['target_min_seconds'] or not any(row.get('text', '').strip() for row in segments):
        return None
    return {'schema_version': '1.0', 'mode': 'full_source_review', 'state': 'DIAGNOSTIC_ONLY',
            'reason_codes': ['source_below_configured_target_minimum'],
            'source_interval': {'start': 0., 'end': duration},
            'segment_ids': [row['segment_id'] for row in segments if row.get('segment_id')],
            'word_ids': [row['word_id'] for row in analysis.get('words') or [] if row.get('word_id')],
            'duration_contract': dict(contract), 'editorial_score': None,
            'requires_human_review': True, 'eligible_for_shortlist': False,
            'preview_approved': False, 'publication_ready': False,
            'source_media_included': False, 'review_scope': 'original_source_evidence_only'}


def classify_editorial_outcome(analysis, cfg=None):
    cfg = cfg or {}
    cfg = cfg.get('understanding', cfg)
    previous = analysis.get('editorial_result') or {}
    candidates = analysis.get('main_moments') or []
    recorded_contract = next((row.get('duration_contract') for row in candidates if row.get('duration_contract')), {})
    contract = duration_contract({**(previous.get('duration_contract') or recorded_contract), **cfg})
    floor = cfg.get('min_editorial_score', previous.get('quality_floor', .50))
    shortlist = analysis.get('editorial_shortlist') or []
    segments = analysis.get('transcript_segments') or []
    source_ids = {row.get('segment_id') for row in segments if row.get('segment_id')}
    uncertain_source_ids = {row.get('segment_id') for row in segments if row.get('needs_review') or
                            row.get('uncertain_word_ids') or row.get('review_reasons')}
    failures = sorted(stage for stage in ('04_transcription', '15_semantic', '16_understanding')
                      if (analysis.get('stage_status', {}).get(stage) or {}).get('status') in
                      {'failed', 'blocked', 'unavailable', 'cancelled'})
    duration = measured_number((analysis.get('metadata') or {}).get('duration'))
    scores = [finite_score(row.get('editorial_score_final')) for row in candidates]
    missing_evidence = []
    for row, score in zip(candidates, scores):
        references = row.get('evidence_segment_ids', row.get('segment_ids')) or []
        missing_components = (row.get('ranking_uncertainty') or {}).get('missing_required_components') or []
        if (not references or not set(references) <= source_ids or score is None or missing_components
                or row.get('source_transcript_needs_review') or row.get('uncertain_segment_ids')
                or set(references) & uncertain_source_ids):
            missing_evidence.append(row.get('moment_id', row.get('candidate_id')))
    reasons = []
    if failures:
        reasons.append('required_editorial_stage_failed')
    if not any(row.get('text', '').strip() for row in segments):
        reasons.append('original_transcript_missing')
    if missing_evidence:
        reasons.append('candidate_evidence_or_score_unresolved')
    if duration is not None and duration < contract['target_min_seconds']:
        reasons.append('source_below_configured_target_minimum')
    if candidates and all(score is not None and score < floor for score in scores):
        reasons.append('all_recorded_scores_below_quality_floor')
    if failures:
        state = 'technical_error'
    elif shortlist:
        state = 'selected'
    elif 'original_transcript_missing' in reasons:
        state = 'insufficient_evidence'
    elif 'source_below_configured_target_minimum' in reasons:
        state = 'video_too_short'
    elif missing_evidence:
        state = 'insufficient_evidence'
    elif 'all_recorded_scores_below_quality_floor' in reasons:
        state = 'low_quality_candidates'
    else:
        state = 'no_eligible_cuts'
        reasons.append('no_candidate_passed_recorded_selection_gates')
    rejected = ((analysis.get('candidate_metrics') or {}).get('selection_report') or {}).get('rejected') or []
    reason_counts = Counter(reason for row in rejected for reason in set(row.get('reasons') or []))
    from .second_curation import human_review_summary
    review_candidates = (analysis.get('second_curation_package') or {}).get('candidates') or []
    if not review_candidates:
        by_id = {row.get('segment_id'): row for row in segments if row.get('segment_id')}
        for rank, row in enumerate(candidates, 1):
            references = row.get('evidence_segment_ids', row.get('segment_ids')) or []
            original_rows = [by_id[reference] for reference in references if reference in by_id]
            classification = row.get('commercial_classification') or {}
            literal = ' '.join(source.get('text', '') for source in original_rows).strip()
            eligible = (bool(references) and set(references) <= source_ids and bool(literal) and
                        '04_transcription' not in failures and classification.get('eligibility') != 'excluded' and
                        not row.get('excluded_commercial_interval_ids'))
            review_candidates.append({**row, 'candidate_id': row.get('moment_id') or row.get('candidate_id'),
                'rank': row.get('rank', rank), 'start': row.get('ideal_start', row.get('start')),
                'end': row.get('ideal_end', row.get('end')), 'segment_ids': references,
                'transcript_literal': literal, 'eligible_for_human_review': eligible,
                'editorial_verified': True if not failures else None})
    review_summary = human_review_summary(review_candidates)
    return {'schema_version': '1.1', 'state': state, 'message': MESSAGES[state],
            'reason_codes': reasons, 'candidate_count': len(candidates), 'shortlist_count': len(shortlist),
            'duration_seconds': duration, 'duration_contract': contract, 'quality_floor': floor,
            'technical_failure_stages': failures, 'unresolved_candidate_ids': missing_evidence,
            'recorded_rejection_counts': dict(sorted(reason_counts.items())),
            'diagnostic_only': True, 'selection_policy_changed': False,
            'human_review_summary': review_summary,
            'human_review_available': review_summary['human_review_queue_count'] > 0,
            'full_source_review': full_source_review(analysis, contract),
            'publication_ready': False}
