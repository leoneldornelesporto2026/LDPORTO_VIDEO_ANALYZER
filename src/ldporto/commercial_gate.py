"""Candidate-scoped sales evidence. Canonical ASR is never changed by OCR."""
from .editorial import rank_candidate, classify_content


def _interval(candidate):
    core = candidate.get('core_moment') or candidate
    return (float(candidate.get('ideal_start', core.get('start', 0))),
            float(candidate.get('ideal_end', core.get('end', core.get('start', 0)))))


def _commercial_precursor_signals(classification):
    signals = set((classification or {}).get('signals') or [])
    return signals & {'price', 'installment', 'discount', 'store', 'product', 'sales_cta',
                      'urgency', 'payment', 'sponsor', 'event', 'domain', 'contact',
                      'recommendation', 'health_claim', 'benefit_claim'}


def _block_context(segments, start, end, before=25.0, after=25.0):
    lo, hi = max(0.0, start - before), end + after
    selected = [s for s in segments if isinstance(s, dict) and s.get('end', 0) > lo and s.get('start', 0) < hi]
    return selected, ' '.join(str(s.get('text') or '') for s in selected).strip()


def refine_candidates(candidates, segments, visual_texts=None, cfg=None):
    """Re-rank candidates with literal evidence and bounded commercial-block context."""
    cfg = cfg or {}
    rows = []
    block_before = float(cfg.get('commercial_block_context_before_seconds', 25.0))
    block_after = float(cfg.get('commercial_block_context_after_seconds', 25.0))
    min_precursors = int(cfg.get('commercial_block_min_precursor_signals', 2))
    clean_segments = [s for s in segments if isinstance(s, dict)]
    for candidate in candidates:
        start, end = _interval(candidate)
        selected = [s for s in clean_segments if s.get('end', 0) > start and s.get('start', 0) < end]
        visual = [r for r in visual_texts or [] if isinstance(r, dict) and r.get('end', 0) >= start and r.get('start', 0) < end]
        literal = ' '.join(str(s.get('text') or '') for s in selected).strip()
        row = {**candidate, 'text': literal,
               'evidence_segment_ids': [s.get('segment_id') for s in selected if s.get('segment_id')],
               'commercial_visual_evidence': visual}
        ranked = rank_candidate(row, cfg)
        local = ranked.get('commercial_classification') or {}
        if local.get('eligibility') != 'excluded':
            precursor = _commercial_precursor_signals(local)
            if len(precursor) >= min_precursors:
                context_rows, context_text = _block_context(clean_segments, start, end, block_before, block_after)
                context_ids = [s.get('segment_id') for s in context_rows if s.get('segment_id')]
                block = classify_content(context_text, context_ids, visual)
                if block.get('eligibility') == 'excluded':
                    propagated = {**block,
                        'classifier_method': 'pt_br_grounded_commercial_gate_v3_block_propagation',
                        'block_propagated': True,
                        'block_interval': {'start': max(0.0, start - block_before), 'end': end + block_after},
                        'candidate_precursor_signals': sorted(precursor),
                        'needs_review': True,
                    }
                    ranked = rank_candidate({**ranked, 'text': literal}, cfg)
                    ranked = {**ranked, 'commercial_classification': propagated,
                              'content_type': propagated['content_type'],
                              'commercial_score': propagated['commercial_score'],
                              'default_shortlist_eligible': False}
        if (ranked.get('commercial_classification') or {}).get('eligibility') == 'excluded':
            ranked['default_shortlist_eligible'] = False
        rows.append(ranked)
    return sorted(rows, key=lambda r: r.get('editorial_score_final') or 0, reverse=True)


def apply_commercial_refinement(understanding, segments, visual_texts, cfg):
    rows = refine_candidates(understanding.get('main_moments', []), segments, visual_texts, cfg)
    eligible = [row for row in rows if row.get('default_shortlist_eligible', True)]
    shortlist = [row['moment_id'] for row in eligible[:cfg.get('max_moments', 12)]]
    metrics = {**understanding.get('candidate_metrics', {}),
               'excluded_commercial_count': sum(row['commercial_classification']['eligibility'] == 'excluded' for row in rows),
               'excluded_eligibility_count': len(rows) - len(eligible), 'final_shortlist_count': len(shortlist)}
    return {**understanding, 'main_moments': rows, 'editorial_shortlist': shortlist, 'candidate_metrics': metrics}


def targeted_ocr(video, candidates, cfg, limit=16):
    if not cfg.get('enabled'):
        return {'status': 'skipped', 'texts': [], 'scope': 'selected_candidates'}
    import cv2
    try:
        import pytesseract
        if cfg.get('tesseract_cmd'):
            pytesseract.pytesseract.tesseract_cmd = cfg['tesseract_cmd']
        pytesseract.get_tesseract_version()
    except (ImportError, OSError):
        return {'status': 'unavailable', 'texts': [], 'reason': 'optional_tesseract_missing'}
    cap = cv2.VideoCapture(str(video))
    texts = []
    try:
        for row in candidates[:limit]:
            core = row.get('core_moment') or row
            start, end = row.get('ideal_start', core['start']), row.get('ideal_end', core['end'])
            for time in (start, (start + end) / 2):
                cap.set(cv2.CAP_PROP_POS_MSEC, time * 1000)
                ok, frame = cap.read()
                if not ok:
                    continue
                try:
                    text = pytesseract.image_to_string(frame, lang=cfg.get('languages', 'por+eng'), timeout=5).strip()
                except (RuntimeError, pytesseract.TesseractError):
                    continue
                if text:
                    texts.append({'text': text, 'start': time, 'end': time, 'source': 'ocr',
                                  'moment_id': row.get('moment_id'), 'duration_unknown': True})
    finally:
        cap.release()
    return {'status': 'measured', 'texts': texts, 'scope': 'selected_candidates', 'max_frames': 2 * limit}
