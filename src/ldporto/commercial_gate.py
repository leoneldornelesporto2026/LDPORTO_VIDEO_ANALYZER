"""Candidate-scoped sales evidence. Canonical ASR is never changed by OCR."""
from .editorial import rank_candidate


def refine_candidates(candidates, segments, visual_texts=None, cfg=None):
    rows = []
    for candidate in candidates:
        start = candidate.get('ideal_start', (candidate.get('core_moment') or candidate)['start'])
        end = candidate.get('ideal_end', (candidate.get('core_moment') or candidate)['end'])
        selected = [s for s in segments if s['end'] > start and s['start'] < end]
        visual = [r for r in visual_texts or [] if r.get('end', 0) >= start and r.get('start', 0) < end]
        row = {**candidate, 'text': ' '.join(s['text'] for s in selected),
               'evidence_segment_ids': [s['segment_id'] for s in selected], 'commercial_visual_evidence': visual}
        rows.append(rank_candidate(row, cfg))
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
