"""S8: Evidence-bound commercial gate. OCR never rewrites speech or proves an ad alone.

Blocks are defined from observed transcript intervals, not a blind +/- N seconds
around every price or brand. Uncertain sales/review clips fail closed for Stories.
"""
from collections import Counter
import math

from .editorial import classify_content, rank_candidate
from .ocr import validate_observations
from .integrity_contracts import capability_contract


def commercial_evidence_state(analysis, candidate_id=None):
    contract = capability_contract(analysis)
    capability = contract['stages'].get('17c_commercial_visual')
    if capability is None:
        return None  # Legacy imports have no visual measurement contract.
    state = capability['state']
    visual = analysis.get('commercial_visual_s8') or {}
    inspected = visual.get('inspected_candidate_ids')
    if candidate_id and inspected is not None and candidate_id not in inspected:
        return 'unavailable_dependency'
    return state


def require_commercial_review(classification, state):
    """Confirmed exclusions dominate; missing visual evidence never clears risk."""
    if classification.get('eligibility') == 'excluded' or state in (None, 'measured_ok'):
        return classification
    return {**classification, 'eligibility': 'review', 'needs_review': True,
            'review_reason': 'commercial_visual_' + state, 'visual_capability_state': state}


SALE_SIGNALS = {'price', 'installment', 'discount', 'store', 'product', 'sales_cta',
                'urgency', 'payment', 'sponsor', 'event', 'domain', 'contact',
                'recommendation', 'health_claim', 'benefit_claim', 'guest_invitation'}


def _interval(candidate):
    core = candidate.get('core_moment') or candidate
    return (float(candidate.get('ideal_start', core.get('start', 0))),
            float(candidate.get('ideal_end', core.get('end', core.get('start', 0)))))


def _as_range(row):
    try:
        start, end = float(row['start']), float(row['end'])
        if not (math.isfinite(start) and math.isfinite(end) and end >= start >= 0):
            return None
        return start, end
    except (TypeError, KeyError, ValueError):
        return None


def _overlap(a, b):
    return max(0., min(a[1], b[1]) - max(a[0], b[0]))


def _precursors(classification):
    return set((classification or {}).get('signals') or []) & SALE_SIGNALS


def _voice(row):
    value = row.get('speaker_id') or row.get('speaker')
    return value if isinstance(value, str) and value.strip().upper() not in {'', 'UNKNOWN', 'UNASSIGNED'} else None


def build_commercial_blocks(segments, visual_texts=None, *, merge_gap_seconds=2.0):
    """Strong ASR commercial spans, merged only across genuine time adjacency.

    Visual-only cues can require a separate review; they do not establish a
    commercial block from an OCR observation whose duration is unknown.
    """
    ordered = sorted((dict(s) for s in segments if isinstance(s, dict) and _as_range(s)),
                     key=lambda r: (r['start'], r['end']))
    # Commercial intent is frequently split by ASR boundaries: product/CTA in
    # one segment, price/payment in the next. Independently marked commercial
    # windows must be adjacent and every marked row needs lexical sales evidence.
    classifications = [classify_content(row.get('text', ''), [row.get('segment_id')]) for row in ordered]
    seed_indices = {i for i, c in enumerate(classifications) if c['eligibility'] == 'excluded'}
    voice_conflicts = set()
    for index in range(len(ordered)):
        group = []
        for cursor in range(index, min(len(ordered), index + 4)):
            if group and ordered[cursor]['start'] - ordered[cursor-1]['end'] > 1.5:
                break
            group.append(ordered[cursor])
            if len(group) < 2:
                continue
            combined = classify_content(' '.join(str(r.get('text') or '') for r in group))
            if combined['eligibility'] == 'excluded':
                marked = {k for k in range(index, cursor + 1) if _precursors(classifications[k])}
                voices = {_voice(r) for r in group if _voice(r) is not None}
                if len(voices) > 1 and not any(classifications[k]['eligibility'] == 'excluded' for k in marked):
                    voice_conflicts.update(marked)
                seed_indices.update(marked)
                break
    runs, current, last_index = [], None, None
    for index, row in enumerate(ordered):
        if index not in seed_indices:
            current = None; last_index = None; continue
        r = _as_range(row)
        item = {'start': r[0], 'end': r[1], 'segment_ids': [row.get('segment_id')],
                'text': str(row.get('text') or ''), 'signals': list(classifications[index]['signals'])}
        if current and last_index == index - 1 and r[0] <= current['end'] + merge_gap_seconds:
            current['end'] = max(current['end'], r[1])
            current['segment_ids'].extend(item['segment_ids'])
            current['signals'] = sorted(set(current['signals'] + item['signals']))
            current['text'] += ' ' + item['text']
        else:
            current = item
            runs.append(item)
        last_index = index
    # Limited backward propagation: a continuous offer's factual preamble may
    # itself contain price/product/stock but no imperative CTA yet.  This is
    # *not* a blanket 25-second context exclusion.
    for run in runs:
        preceding = [s for s in ordered if s['end'] <= run['start'] and
                     0 <= run['start'] - s['end'] <= 1.0]
        if preceding:
            precursor = preceding[-1]
            evidence = classify_content(precursor.get('text', ''), [precursor.get('segment_id')])
            run_voices = {_voice(s) for s in ordered if s.get('segment_id') in run['segment_ids'] and _voice(s)}
            different_voice = _voice(precursor) is not None and run_voices and _voice(precursor) not in run_voices
            if (len(_precursors(evidence)) >= 2 and evidence['eligibility'] != 'excluded' and
                    not evidence.get('reported_commercial_context') and not different_voice):
                run['start'] = float(precursor['start'])
                run['segment_ids'].insert(0, precursor.get('segment_id'))
                run['signals'] = sorted(set(run['signals']) | _precursors(evidence))
                run['text'] = str(precursor.get('text') or '') + ' ' + run['text']
    blocks = []
    for n, row in enumerate(runs, 1):
        source_rows = [s for s in ordered if s.get('segment_id') in row['segment_ids']]
        voices = sorted({_voice(s) for s in source_rows if _voice(s) is not None})
        classification = classify_content(row['text'], [x for x in row['segment_ids'] if x])
        if any(ordered[k].get('segment_id') in row['segment_ids'] for k in voice_conflicts):
            classification = {**classification, 'eligibility': 'review', 'needs_review': True,
                              'review_reason': 'split_offer_across_different_voices'}
        blocks.append({'block_id': f'COMMERCIAL_{n:04d}', 'start': row['start'], 'end': row['end'],
                       'segment_ids': [x for x in row['segment_ids'] if x],
                       'signals': row['signals'], 'classification': classification,
                       'voice_evidence': {'speaker_ids': voices,
                           'continuity': 'different_observed_voices' if len(voices) > 1 else
                               'same_observed_voice' if len(voices) == 1 and all(_voice(s) for s in source_rows) else None},
                       'origin': 'strong_canonical_transcript', 'visual_corroboration': [v for v in (visual_texts or [])
                           if isinstance(v, dict) and _as_range(v) and row['start'] <= float(v['start']) <= row['end']],
                       'needs_review': True})
    return blocks


def refine_candidates(candidates, segments, visual_texts=None, cfg=None, *, commercial_blocks=None):
    cfg = cfg or {}
    clean_segments = [s for s in segments if isinstance(s, dict) and _as_range(s)]
    blocks = commercial_blocks if commercial_blocks is not None else build_commercial_blocks(clean_segments, visual_texts)
    rows = []
    for candidate in candidates:
        window = _interval(candidate)
        if not window[1] > window[0]:
            rows.append({**candidate, 'default_shortlist_eligible': False,
                         'commercial_gate_reason': 'invalid_candidate_interval'})
            continue
        selected = [s for s in clean_segments if _overlap(window, _as_range(s)) > 0]
        literal = ' '.join(str(s.get('text') or '') for s in selected).strip()
        # One OCR frame is NOT evidence of on-screen duration. Scoped OCR frames
        # must belong to the candidate; global keyframes use observed instant.
        visual = [v for v in (visual_texts or []) if isinstance(v, dict) and v.get('text')
                  and (_as_range(v) is not None) and window[0] <= float(v['start']) < window[1]
                  and (v.get('moment_id') is None or v.get('moment_id') == candidate.get('moment_id'))]
        evidence_ids = [s.get('segment_id') for s in selected if s.get('segment_id')]
        ranked = rank_candidate({**candidate, 'text': literal, 'evidence_segment_ids': evidence_ids,
                                 'commercial_visual_evidence': visual}, cfg)
        local = ranked.get('commercial_classification') or {}
        audio_only = classify_content(literal, evidence_ids)
        prior = candidate.get('commercial_classification') or {}
        if prior.get('eligibility') == 'excluded' and local.get('eligibility') != 'excluded':
            ranked['commercial_classification'] = {**prior,
                'eligibility': 'excluded', 'upstream_exclusion_preserved': True}
            ranked['default_shortlist_eligible'] = False
            local = ranked['commercial_classification']
        elif prior.get('eligibility') == 'review' and local.get('eligibility') == 'eligible':
            ranked['commercial_classification'] = {**prior,
                'eligibility': 'review', 'upstream_review_preserved': True}
            ranked['default_shortlist_eligible'] = False
            local = ranked['commercial_classification']
        # OCR-only offers are a REVIEW, not confirmed spoken advertisements.
        if prior.get('eligibility') != 'excluded' and ((local.get('eligibility') == 'excluded' or
                (local.get('eligibility') == 'review' and visual and
                 classify_content(' '.join(v['text'] for v in visual))['eligibility'] == 'excluded')) and audio_only.get('eligibility') != 'excluded'):
            local = {**local, 'eligibility': 'review', 'needs_review': True,
                     'classifier_method': 's8_ocr_unconfirmed',
                     'visual_only_sale_unconfirmed': True,
                     'review_reason': 'ocr_sales_evidence_without_transcript_confirmation'}
            ranked.update(commercial_classification=local, default_shortlist_eligible=False)
        # A strong commercial block that overlaps the selected candidate cannot
        # be erased by candidate-local re-ranking. Reject partial excerpts too.
        intersecting = [block for block in blocks if _overlap(window, (block['start'], block['end'])) > 0]
        if intersecting:
            strongest = max(intersecting, key=lambda b: (
                b['classification'].get('eligibility') == 'excluded', _overlap(window, (b['start'], b['end']))))
            prior = ranked['commercial_classification']
            if strongest['classification'].get('eligibility') == 'excluded':
                ranked['commercial_classification'] = {**strongest['classification'],
                    'eligibility': 'excluded', 'needs_review': True,
                    'classifier_method': 's8_grounded_block_overlap',
                    'block_id': strongest['block_id'], 'block_propagated': True,
                    'block_interval': {'start': strongest['start'], 'end': strongest['end']},
                    'evidence_segment_ids': strongest['segment_ids']}
                ranked['default_shortlist_eligible'] = False
            elif prior.get('eligibility') != 'excluded':
                ranked['commercial_classification'] = {**prior, 'eligibility': 'review',
                    'needs_review': True, 'review_reason': 'near_commercial_block', 'block_id': strongest['block_id']}
                ranked['default_shortlist_eligible'] = False
        status = (ranked.get('commercial_classification') or {}).get('eligibility')
        # Unverified promotion must never be silently published as Story.
        if status != 'eligible':
            ranked['default_shortlist_eligible'] = False
        ranked['commercial_gate_reason'] = ranked.get('commercial_gate_reason') or (
            'confirmed_commercial' if status == 'excluded' else 'needs_manual_commercial_review' if status == 'review' else 'eligible')
        ranked['commercial_block_refs'] = [block['block_id'] for block in intersecting]
        ranked['excluded_commercial_interval_ids'] = sorted(set(
            candidate.get('excluded_commercial_interval_ids') or []) | {
            block['block_id'] for block in intersecting if block['classification'].get('eligibility') == 'excluded'})
        ranked['content_type'] = ranked['commercial_classification']['content_type']
        ranked['commercial_score'] = ranked['commercial_classification']['commercial_score']
        rows.append(ranked)
    return sorted(rows, key=lambda r: r.get('editorial_score_final') or 0, reverse=True)


def apply_commercial_refinement(understanding, segments, visual_texts, cfg, *, commercial_visual=None):
    blocks = build_commercial_blocks(segments, visual_texts)
    rows = refine_candidates(understanding.get('main_moments', []), segments, visual_texts, cfg,
                             commercial_blocks=blocks)
    if commercial_visual is not None:
        evidence = {'commercial_visual_s8': commercial_visual}
        for row in rows:
            row['commercial_classification'] = require_commercial_review(
                row['commercial_classification'], commercial_evidence_state(evidence, row.get('moment_id')))
            if row['commercial_classification']['eligibility'] != 'eligible':
                row['default_shortlist_eligible'] = False
                row['commercial_gate_reason'] = row['commercial_classification'].get('review_reason', 'confirmed_commercial')
    eligible = [row for row in rows if row.get('default_shortlist_eligible', True) and
                (row.get('commercial_classification') or {}).get('eligibility') == 'eligible']
    max_moments = max(0, int(cfg.get('max_moments', 12)))
    shortlist = [row.get('moment_id') for row in eligible[:max_moments] if row.get('moment_id')]
    reasons = Counter(row.get('commercial_gate_reason') for row in rows)
    metrics = {**understanding.get('candidate_metrics', {}),
               'excluded_commercial_count': sum((r.get('commercial_classification') or {}).get('eligibility') == 'excluded' for r in rows),
               'commercial_review_count': sum((r.get('commercial_classification') or {}).get('eligibility') == 'review' for r in rows),
               'commercial_block_count': len(blocks), 'commercial_gate_reasons': dict(reasons),
               'excluded_eligibility_count': len(rows) - len(eligible), 'final_shortlist_count': len(shortlist)}
    return {**understanding, 'main_moments': rows, 'editorial_shortlist': shortlist,
            'commercial_blocks': blocks, 'candidate_metrics': metrics}


def targeted_ocr(video, candidates, cfg, limit=16):
    """Optional Tesseract, three bounded, observed frames per selected interval.

    Returns normalized coordinates, OCR confidences and text type hints. The
    first/last observation does NOT establish continuous display duration.
    """
    if not cfg.get('enabled'):
        return {'status': 'skipped', 'texts': [], 'scope': 'selected_candidates', 'reason': 'ocr_disabled',
                'capability_state': 'not_measured_disabled',
                'measurement_state': 'not_measured', 'commercial_present': None}
    try:
        import cv2
        import pytesseract
        if cfg.get('tesseract_cmd'):
            pytesseract.pytesseract.tesseract_cmd = cfg['tesseract_cmd']
        pytesseract.get_tesseract_version()
    except (ImportError, OSError, RuntimeError) as exc:
        return {'status': 'unavailable', 'texts': [], 'reason': 'optional_tesseract_missing',
                'capability_state': 'unavailable_dependency',
                'measurement_state': 'not_measured', 'commercial_present': None,
                'detail': type(exc).__name__}
    cap = cv2.VideoCapture(str(video))
    if not cap.isOpened():
        cap.release()
        return {'status': 'unavailable', 'texts': [], 'reason': 'video_decode_unavailable',
                'capability_state': 'unavailable_dependency',
                'measurement_state': 'not_measured', 'commercial_present': None}
    texts, sampled, measured, errors, inspected_ids = [], 0, 0, 0, []
    try:
        for row in candidates[:max(0, int(limit))]:
            start, end = _interval(row)
            if end <= start:
                continue
            inspected_ids.append(row.get('moment_id'))
            samples = [start + (end-start)*part for part in (.12, .5, .88)]
            for when in samples:
                cap.set(cv2.CAP_PROP_POS_MSEC, when * 1000)
                decoded, frame = cap.read()
                if not decoded:
                    errors += 1
                    continue
                sampled += 1
                h, w = frame.shape[:2]
                try:
                    data = pytesseract.image_to_data(frame, lang=cfg.get('languages', 'por+eng'),
                        config='--psm 11', output_type=pytesseract.Output.DICT, timeout=5)
                except (RuntimeError, pytesseract.TesseractError):
                    errors += 1
                    continue
                measured += 1
                groups = {}
                for i, token in enumerate(data['text']):
                    try:
                        conf = float(data['conf'][i])
                    except (TypeError, ValueError):
                        continue
                    if str(token).strip() and conf >= 45:
                        key = (data['block_num'][i], data['par_num'][i], data['line_num'][i])
                        groups.setdefault(key, []).append(i)
                for ids in groups.values():
                    text = ' '.join(data['text'][i] for i in ids).strip()
                    left = min(data['left'][i] for i in ids)
                    top = min(data['top'][i] for i in ids)
                    right = max(data['left'][i]+data['width'][i] for i in ids)
                    bottom = max(data['top'][i]+data['height'][i] for i in ids)
                    box = {'x': left/w, 'y': top/h, 'width': (right-left)/w, 'height': (bottom-top)/h}
                    signals = classify_content(text).get('signals', [])
                    visual_type = ('offer_or_price' if set(signals) & {'price', 'discount', 'installment', 'payment'}
                                   else 'lower_third_gc' if box['y'] > .55
                                   else 'banner_or_logo_text' if box['y'] < .25 else 'unknown_text')
                    texts.append({'text': text, 'start': when, 'end': when, 'observed_at': when,
                                  'source': 'ocr', 'method': 'tesseract_candidate_frame_s8',
                                  'moment_id': row.get('moment_id'), 'bbox': box,
                                  'confidence': round(sum(float(data['conf'][i]) for i in ids)/len(ids)/100, 3),
                                  'signals': signals, 'visual_type_hint': visual_type,
                                  'duration_unknown': True, 'needs_review': True})
    finally:
        cap.release()
    return {'status': 'measured' if measured and not errors else 'partial', 'texts': validate_observations(texts),
            'capability_state': ('failed' if errors and not measured else
                                 'measured_partial' if errors or not measured else 'measured_ok'),
            'measurement_state': 'measured' if measured else 'not_measured', 'commercial_present': None,
            'measured_frames': measured,
            'sampled_frames': sampled, 'failed_frames_or_ocr': errors,
            'scope': 'selected_candidate_observations', 'max_frames': max(0, int(limit))*3,
            'continuity_established': False, 'requested_candidate_count': len(candidates),
            'inspected_candidate_ids': inspected_ids,
            'uninspected_candidate_count': max(0, len(candidates)-len(inspected_ids))}
