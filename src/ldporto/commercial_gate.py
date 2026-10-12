"""S8: Evidence-bound commercial gate. OCR never rewrites speech or proves an ad alone.

Blocks are defined from observed transcript intervals, not a blind +/- N seconds
around every price or brand. Uncertain sales/review clips fail closed for Stories.
"""
from collections import Counter
import math
import re
import hashlib
from pathlib import Path
import shutil

from .core import file_hash

from .editorial import classify_content, rank_candidate, fold_text
from .ocr import validate_observations, normalize_commercial_observation
from .integrity_contracts import capability_contract


def commercial_evidence_state(analysis, candidate_id=None):
    contract = capability_contract(analysis)
    capability = contract['stages'].get('17c_commercial_visual')
    if capability is None:
        return None  # Legacy imports have no visual measurement contract.
    state = capability['state']
    visual = analysis.get('commercial_visual_s8') or {}
    inspected = visual.get('inspected_candidate_ids')
    if state in {'measured_ok', 'measured_partial'} and candidate_id and inspected is not None and candidate_id not in inspected:
        return 'unavailable_dependency'
    return state


def require_commercial_review(classification, state):
    """Confirmed exclusions dominate; missing visual evidence never clears risk."""
    if classification.get('eligibility') == 'excluded' or state in (None, 'measured_ok'):
        return classification
    return {**classification, 'eligibility': 'review', 'needs_review': True,
            'review_reason': classification.get('review_reason') or 'commercial_visual_' + state,
            'visual_capability_state': state}


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


def _institutional_promo(text):
    text = fold_text(text)
    # A station/competition mention alone is editorial, never a promotion.
    return bool(re.search(r'\bjovem pan\b', text) and re.search(r'\bcopa\b', text)
                and re.search(r'\b(?:acompanhe|assista|sintonize|nao perca|vem com a gente)\b', text)
                and not re.search(r'\b(?:nao|nunca)\s+(?:acompanhe|assista|sintonize)\b', text)
                and not re.search(r'\b(?:na reportagem|a vinheta dizia|o anuncio dizia|historico|historica|criticamos)\b', text))


def _speech_classification(text, ids=None):
    result = classify_content(text, ids)
    if _institutional_promo(text):
        return {**result, 'eligibility': 'excluded', 'needs_review': True,
                'content_type': 'commercial_promotion', 'commercial_kind': 'institutional_promotion',
                'commercial_score': None,
                'institutional_call_evidence': {'text': text, 'segment_ids': list(ids or [])},
                'review_reason': 'institutional_station_event_call',
                'signals': sorted(set(result['signals']) | {'institutional_call'})}
    return result


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
    classifications = [_speech_classification(row.get('text', ''), [row.get('segment_id')]) for row in ordered]
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
            combined = _speech_classification(' '.join(str(r.get('text') or '') for r in group))
            if combined['eligibility'] == 'excluded':
                marked = {k for k in range(index, cursor + 1) if _precursors(classifications[k]) or
                          combined.get('commercial_kind') == 'institutional_promotion'}
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
        classification = _speech_classification(row['text'], [x for x in row['segment_ids'] if x])
        if any(ordered[k].get('segment_id') in row['segment_ids'] for k in voice_conflicts):
            classification = {**classification, 'eligibility': 'review', 'needs_review': True,
                              'review_reason': 'split_offer_across_different_voices'}
        blocks.append({'block_id': f'COMMERCIAL_{n:04d}', 'start': row['start'], 'end': row['end'],
                       'segment_ids': [x for x in row['segment_ids'] if x],
                       'signals': row['signals'], 'classification': classification,
                       'voice_evidence': {'speaker_ids': voices,
                           'continuity': 'different_observed_voices' if len(voices) > 1 else
                               'same_observed_voice' if len(voices) == 1 and all(_voice(s) for s in source_rows) else None},
                       'origin': 'strong_canonical_transcript',
                       'observations': [{'source': 'asr', 'start': s['start'], 'end': s['end'],
                           'segment_id': s.get('segment_id'), 'text': s.get('text'),
                           'confidence': s.get('confidence')} for s in source_rows],
                       'visual_corroboration': [v for raw in (visual_texts or [])
                           if (v := normalize_commercial_observation(raw)) and v['measurement_state'] == 'measured'
                           and row['start'] <= v['start'] <= row['end']],
                       'needs_review': True})
    return blocks


def candidate_visual_coverage(candidate, visual, observations, graphics=None):
    """Frame sampling coverage is never a fraction of continuous screen time."""
    start, end = _interval(candidate)
    cid = candidate.get('moment_id', candidate.get('candidate_id'))
    receipt = (visual or {}).get('candidate_coverage', {}).get(cid, {})
    measured = [o for o in observations if o.get('source') == 'ocr' and
                o.get('measurement_state') == 'measured']
    times = sorted({o['observed_at'] for o in measured})
    successful = receipt.get('measured_frames', len(times) if times else None)
    failed = receipt.get('failed_frames_or_ocr')
    expected = receipt.get('requested_frames')
    state = ('partially_failed' if failed and successful else 'sampled' if successful else 'not_measured')
    gc_windows = [g for g in (graphics or {}).get('intervals', []) if _as_range(g) and
                  _overlap((start, end), _as_range(g)) > 0 and g.get('moment_id') in (None, cid) and
                  (g.get('status') in {'measured', 'measured_temporal_intervals'} or g.get('regions'))]
    return {'scope': 'candidate_window', 'state': state, 'start': start, 'end': end,
            'requested_frames': expected, 'measured_frames': successful,
            'failed_frames_or_ocr': failed, 'observed_at': times,
            'sampling_coverage': successful / expected if expected and successful is not None else None,
            'continuous_visual_coverage': None, 'continuity_established': False,
            'modality_scopes': {
                'ocr': state,
                'asr': 'transcribed' if any(o.get('source') == 'asr' for o in observations) else 'not_measured',
                'broadcast_gc': 'sampled' if gc_windows else 'not_measured'},
            'gc_sampled_window_count': len(gc_windows)}


def commercial_risk(classification, observations, coverage):
    """Fuse independently observed modalities without calibrating a probability."""
    ocr = [o for o in observations if o.get('source') == 'ocr' and
           o.get('measurement_state') == 'measured' and o.get('text')]
    gc = [o for o in observations if o.get('source') == 'gc']
    asr = [o for o in observations if o.get('source') == 'asr']
    visual_signals = set()
    for o in ocr:
        visual_signals.update(classify_content(o['text'])['signals'])
        if re.search(r'\b\d+\s*%\s*(?:off|de desconto)', fold_text(o['text'])):
            visual_signals.add('discount')
        if re.search(r'\bqr\s*code\b', fold_text(o['text'])):
            visual_signals.add('qr')
    graphic_promotion = any(o.get('kind') in {'qr', 'qr_code', 'sponsor', 'vinheta', 'institutional_promo'} for o in gc)
    persistent = any(o.get('temporal_validated') and o.get('spatial_validated') and
                     not o.get('uncertain') for o in ocr)
    audio_signals = set().union(*(set(o.get('signals') or []) for o in asr))
    promotion = visual_signals & {'discount', 'price', 'sales_cta', 'sponsor', 'qr', 'installment'}
    reasons = ['ocr_' + s for s in sorted(promotion)]
    reasons += ['asr_' + s for s in sorted(audio_signals & SALE_SIGNALS)]
    if gc:
        reasons.append('gc_observed_not_text_recognition')
    if persistent:
        reasons.append('repeated_ocr_samples_not_continuous_display')
    if classification.get('review_reason'):
        reasons.append(classification['review_reason'])
    grounded_speech = _speech_classification(' '.join(str(o.get('text') or '') for o in asr))
    if classification.get('eligibility') == 'excluded' and grounded_speech['eligibility'] == 'excluded':
        state = 'confirmed_ad'
        reasons.append('grounded_commercial_exclusion')
    elif classification.get('eligibility') == 'excluded':
        state = 'requires_review'
        reasons.append('upstream_exclusion_preserved_confirmation_unavailable')
    elif (persistent and len(promotion) >= 2 and gc and
          audio_signals & {'sales_cta', 'sponsor', 'discount'} and
          not classification.get('reported_commercial_context')):
        state = 'probable_ad'
        reasons.append('multimodal_promotion_requires_human')
    elif classification.get('eligibility') == 'review' or promotion or graphic_promotion:
        state = 'requires_review'
    elif coverage['state'] == 'partially_failed':
        state = 'requires_review'
        reasons.append('ocr_partial_failure')
    elif coverage['state'] == 'sampled':
        state = 'measured_no_ad_evidence'
        reasons.append('no_ad_evidence_in_samples')
    else:
        state = 'not_measured'
        reasons.append('visual_not_measured')
    return {'state': state, 'reason_codes': sorted(set(reasons)),
            'coverage_state': coverage['state'],
            'evidence_scope': 'confirmed' if state == 'confirmed_ad' else coverage['state'],
            'probability': None, 'confidence_is_calibrated': False,
            'continuous_display_confirmed': False}


def commercial_benchmark_metrics(candidates, annotations=None):
    """Counts only explicitly annotated IDs; no precision inferred from fixtures."""
    if not annotations:
        return {'commercial_false_negative_candidates': None, 'benchmark_scope': 'not_measured',
                'precision': None, 'recall': None}
    by_id = {r.get('moment_id', r.get('candidate_id')): r for r in candidates}
    labels = annotations.get('labels') or []
    if annotations.get('annotation_kind') not in {'synthetic_fixture', 'verified_human'} or not labels:
        return commercial_benchmark_metrics(candidates)
    positives = [r['candidate_id'] for r in labels if r.get('expected_ad') is True]
    missing = [cid for cid in positives if cid not in by_id]
    false_negative = [cid for cid in positives if cid in by_id and
        (by_id[cid].get('commercial_risk') or {}).get('state') not in
        {'confirmed_ad', 'probable_ad', 'requires_review'}]
    return {'commercial_false_negative_candidates': false_negative if not missing else None,
            'unmeasured_benchmark_candidate_ids': missing,
            'benchmark_scope': annotations['annotation_kind'],
            'precision': None, 'recall': None}


def refine_candidates(candidates, segments, visual_texts=None, cfg=None, *, commercial_blocks=None, graphics=None, commercial_visual=None):
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
        scoped = [v for v in (visual_texts or []) if isinstance(v, dict)
                  and (_as_range(v) is not None) and window[0] <= float(v['start']) < window[1]
                  and (v.get('moment_id') is None or v.get('moment_id') == candidate.get('moment_id'))]
        normalized = [normalize_commercial_observation(v) for v in scoped]
        visual = [v for v in normalized if v and v['measurement_state'] == 'measured' and v['text']]
        observations = [{'source': 'asr', 'start': s['start'], 'end': s['end'],
                         'segment_id': s.get('segment_id'), 'text': s.get('text'),
                         'confidence': s.get('confidence'), 'measurement_state': 'transcribed',
                         'signals': _speech_classification(s.get('text', ''))['signals']} for s in selected]
        observations.extend(v for v in normalized if v)
        graphic_rows = [g for g in (graphics or {}).get('intervals', []) if _as_range(g)
                        and _overlap(window, _as_range(g)) > 0
                        and g.get('moment_id') in (None, candidate.get('moment_id'))]
        for g in graphic_rows:
            for region in g.get('regions', []):
                observations.append({'source': 'gc', 'start': g['start'], 'end': g['end'],
                    'kind': region.get('kind'), 'confidence': region.get('confidence'),
                    'observed_at': region.get('observed_at', g.get('observed_at')),
                    'source_frame_hash': region.get('source_frame_hash'), 'bbox': region.get('bbox'),
                    'evidence': region.get('evidence'), 'text': None,
                    'limitation': 'graphic_candidate_not_text_recognition', 'commercial_confirmed': None})
        unmeasured_suspect = (candidate.get('commercial_visual_suspected') is True or
            any(v and v['measurement_state'] == 'not_measured' and
                (classify_content(raw.get('text', ''))['eligibility'] != 'eligible' or
                 re.search(r'\b\d+\s*%\s*(?:off|de desconto)|\bqr\s*code\b', fold_text(raw.get('text', ''))))
                for raw, v in zip(scoped, normalized)))
        graphic_suspect = any(o.get('kind') in {'qr', 'qr_code', 'sponsor', 'vinheta', 'institutional_promo'}
                              for o in observations if o['source'] == 'gc')
        visual_suspect = any(re.search(r'\b\d+\s*%\s*(?:off|de desconto)|\bqr\s*code\b',
                                     v['normalized_text']) for v in visual)
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
            for block in intersecting:
                observations.extend({**o, 'block_id': block['block_id']} for o in block.get('observations', [])
                                    if o.get('segment_id') not in evidence_ids)
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
        if status != 'excluded' and (unmeasured_suspect or graphic_suspect or visual_suspect):
            reason = 'commercial_visual_unmeasured' if unmeasured_suspect else 'commercial_visual_promotion_unconfirmed'
            ranked['commercial_classification'] = {**ranked['commercial_classification'],
                'eligibility': 'review', 'needs_review': True, 'review_reason': reason,
                'visual_only_sale_unconfirmed': True}
            ranked['commercial_gate_reason'] = reason
            status = 'review'
        ranked['commercial_observations'] = observations
        ranked['commercial_classification']['observations'] = observations
        ranked['commercial_classification']['confidence_is_calibrated'] = False
        coverage = candidate_visual_coverage(candidate, commercial_visual, observations, graphics)
        risk = commercial_risk(ranked['commercial_classification'], observations, coverage)
        ranked['commercial_coverage'] = coverage
        ranked['commercial_risk'] = risk
        ranked['commercial_classification'].update(commercial_risk_state=risk['state'], reason_codes=risk['reason_codes'])
        if risk['state'] in {'probable_ad', 'requires_review'} and status != 'excluded':
            ranked['commercial_classification'].update(eligibility='review', needs_review=True)
            status = 'review'
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


def apply_commercial_refinement(understanding, segments, visual_texts, cfg, *, commercial_visual=None, graphics=None, benchmark_annotations=None):
    blocks = build_commercial_blocks(segments, visual_texts)
    rows = refine_candidates(understanding.get('main_moments', []), segments, visual_texts, cfg,
                             commercial_blocks=blocks, graphics=graphics, commercial_visual=commercial_visual)
    if commercial_visual is not None:
        evidence = {'commercial_visual_s8': commercial_visual}
        for row in rows:
            row['commercial_classification'] = require_commercial_review(
                row['commercial_classification'], commercial_evidence_state(evidence, row.get('moment_id')))
            if row['commercial_classification']['eligibility'] != 'eligible':
                row['default_shortlist_eligible'] = False
                row['commercial_gate_reason'] = row['commercial_classification'].get('review_reason', 'confirmed_commercial')
            if row['commercial_classification']['eligibility'] == 'review' and row['commercial_risk']['state'] == 'measured_no_ad_evidence':
                row['commercial_risk']['state'] = 'requires_review'
                row['commercial_risk']['reason_codes'].append('visual_capability_requires_review')
                row['commercial_classification'].update(commercial_risk_state='requires_review',
                    reason_codes=row['commercial_risk']['reason_codes'])
    eligible = [row for row in rows if row.get('default_shortlist_eligible', True) and
                (row.get('commercial_classification') or {}).get('eligibility') == 'eligible']
    max_moments = max(0, int(cfg.get('max_moments', 12)))
    shortlist = [row.get('moment_id') for row in eligible[:max_moments] if row.get('moment_id')]
    reasons = Counter(row.get('commercial_gate_reason') for row in rows)
    metrics = {**understanding.get('candidate_metrics', {}),
               'excluded_commercial_count': sum((r.get('commercial_classification') or {}).get('eligibility') == 'excluded' for r in rows),
               'commercial_review_count': sum((r.get('commercial_classification') or {}).get('eligibility') == 'review' for r in rows),
               'commercial_block_count': len(blocks), 'commercial_gate_reasons': dict(reasons),
               'commercial_risk_states': dict(Counter(r['commercial_risk']['state'] for r in rows if r.get('commercial_risk'))),
               'commercial_visual_coverage_by_candidate': {r['moment_id']: r.get('commercial_coverage') for r in rows if r.get('moment_id')},
               'commercial_false_negative_candidates': None,
               'commercial_suspects_requiring_human': [r.get('moment_id') for r in rows if
                   (r.get('commercial_risk') or {}).get('state') in {'probable_ad', 'requires_review'}],
               'excluded_eligibility_count': len(rows) - len(eligible), 'final_shortlist_count': len(shortlist)}
    metrics.update(commercial_benchmark_metrics(rows, benchmark_annotations))
    return {**understanding, 'main_moments': rows, 'editorial_shortlist': shortlist,
            'commercial_blocks': blocks, 'candidate_metrics': metrics}


def ocr_runtime_fingerprint(cfg):
    """Probe only local OCR dependencies; never install or invoke inference."""
    result = {'enabled': bool(cfg.get('enabled')), 'available': False,
              'requested_languages': cfg.get('languages', 'por+eng'),
              'executable': None, 'executable_sha256': None, 'version': None,
              'available_languages': None, 'opencv_version': None,
              'language_model_sha256': None}
    if not result['enabled']:
        return {**result, 'reason': 'ocr_disabled'}
    try:
        import cv2
        import pytesseract
        executable = resolve_executable(cfg)
        result.update(executable=str(executable), executable_sha256=file_hash(executable),
                      version=str(ocr_call(cfg, 'get_tesseract_version')),
                      available_languages=sorted(ocr_call(cfg, 'get_languages', config='')),
                      opencv_version=cv2.__version__)
        # Recover local traineddata only; absent paths remain unknown, never download.
        import os
        roots = ([Path(os.environ['TESSDATA_PREFIX'])] if os.environ.get('TESSDATA_PREFIX') else [])
        roots += [executable.parent / 'tessdata', executable.parent.parent / 'share' / 'tessdata']
        models = {}
        for language in result['requested_languages'].split('+'):
            if not language or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-' for c in language):
                continue
            model = next((root / (language + '.traineddata') for root in roots
                          if (root / (language + '.traineddata')).is_file()), None)
            models[language] = file_hash(model) if model else None
        result['language_model_sha256'] = models
        missing = sorted(set(result['requested_languages'].split('+')) - set(result['available_languages']))
        if missing:
            return {**result, 'reason': 'tesseract_languages_missing', 'missing_languages': missing}
        return {**result, 'available': True, 'reason': None}
    except (ImportError, OSError, RuntimeError) as exc:
        return {**result, 'reason': 'optional_ocr_dependency_missing', 'detail': type(exc).__name__}


def commercial_visual_params(source_hash, candidates, cfg, limit, runtime, upstream_hashes):
    return {'contract': '46.1', 'source_sha256': source_hash, 'candidates': candidates,
            'ocr': cfg, 'limit': limit, 'runtime': runtime, 'upstream_hashes': upstream_hashes,
            'sampling': [.12, .5, .88], 'psm': 11, 'timeout': 5, 'min_confidence': 45}


from .ocr_execution import receipt
from .ocr_runtime import call as ocr_call, resolve_executable
from .ocr_diagnostics import diagnose_ocr


@receipt('commercial_17c')
def targeted_ocr(video, candidates, cfg, limit=16):
    """Optional Tesseract, three bounded, observed frames per selected interval.

    Returns normalized coordinates, OCR confidences and text type hints. The
    first/last observation does NOT establish continuous display duration.
    """
    if not cfg.get('enabled'):
        return {'status': 'skipped', 'texts': [], 'scope': 'selected_candidates', 'reason': 'ocr_disabled',
                'capability_state': 'not_measured_disabled',
                'measurement_state': 'not_measured', 'commercial_present': None}
    diagnostic = diagnose_ocr(cfg)
    if not diagnostic['ok']:
        return {'status': 'unavailable', 'texts': [], 'reason': diagnostic['reason'],
                'diagnostic': diagnostic, 'capability_state': 'unavailable_dependency',
                'measurement_state': 'not_measured', 'commercial_present': None}
    try:
        import cv2
        import pytesseract
    except Exception as exc:
        return {'status': 'unavailable', 'texts': [], 'reason': 'dependency_missing',
                'capability_state': 'unavailable_dependency',
                'measurement_state': 'not_measured', 'commercial_present': None,
                'detail': type(exc).__name__}
    cap = cv2.VideoCapture(str(video))
    if not cap.isOpened():
        cap.release()
        return {'status': 'unavailable', 'texts': [], 'reason': 'video_decode_unavailable',
                'capability_state': 'unavailable_dependency',
                'measurement_state': 'not_measured', 'commercial_present': None}
    source_sha256 = file_hash(video) if Path(video).is_file() else None
    frames = []
    texts, sampled, measured, errors, inspected_ids = [], 0, 0, 0, []
    coverage = {}
    try:
        for row in candidates[:max(0, int(limit))]:
            start, end = _interval(row)
            if end <= start:
                continue
            inspected_ids.append(row.get('moment_id'))
            counts = {'requested_frames': 3, 'measured_frames': 0, 'failed_frames_or_ocr': 0,
                      'start': start, 'end': end, 'scope': 'candidate_window'}
            coverage[row.get('moment_id')] = counts
            samples = [start + (end-start)*part for part in (.12, .5, .88)]
            for when in samples:
                cap.set(cv2.CAP_PROP_POS_MSEC, when * 1000)
                decoded, frame = cap.read()
                if not decoded:
                    errors += 1
                    counts['failed_frames_or_ocr'] += 1
                    continue
                sampled += 1
                h, w = frame.shape[:2]
                frame_sha256 = hashlib.sha256(frame.tobytes()).hexdigest()
                frames.append({'moment_id': row.get('moment_id'), 'requested_at': when,
                               'source_sha256': source_sha256, 'decoded_frame_sha256': frame_sha256,
                               'source_frame_hash': frame_sha256, 'observed_at': when,
                               'ocr_state': 'not_measured',
                               'shape': list(frame.shape), 'timestamp_basis': 'requested_seek_position',
                               'decoder_position_msec': cap.get(cv2.CAP_PROP_POS_MSEC) if hasattr(cap, 'get') else None})
                try:
                    data = ocr_call(cfg, 'image_to_data', frame,
                        config='--psm 11', output_type=pytesseract.Output.DICT, timeout=5)
                except (OSError, RuntimeError, pytesseract.TesseractError):
                    errors += 1
                    counts['failed_frames_or_ocr'] += 1
                    frames[-1]['ocr_state'] = 'failed'
                    continue
                measured += 1
                counts['measured_frames'] += 1
                frames[-1]['ocr_state'] = 'measured'
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
                                  'original_text': text, 'source_frame_hash': frame_sha256,
                                  'timestamp_basis': 'requested_seek_position',
                                  'source': 'ocr', 'method': 'tesseract_candidate_frame_s8',
                                  'source_sha256': source_sha256, 'decoded_frame_sha256': frame_sha256,
                                  'moment_id': row.get('moment_id'), 'bbox': box,
                                  'confidence': round(sum(float(data['conf'][i]) for i in ids)/len(ids)/100, 3),
                                  'signals': signals, 'visual_type_hint': visual_type,
                                  'duration_unknown': True, 'needs_review': True})
    finally:
        cap.release()
    return {'status': 'measured' if measured and not errors else 'partial', 'texts': validate_observations(texts),
            'capability_state': ('failed' if errors and not measured else
                                 'unavailable_dependency' if not measured else
                                 'measured_partial' if errors else 'measured_ok'),
            'reason': 'ocr_or_decode_errors' if errors else 'no_candidate_frames_measured' if not measured else None,
            'measurement_state': 'measured' if measured else 'not_measured', 'commercial_present': None,
            'source_sha256': source_sha256, 'frame_resources': frames,
            'candidate_coverage': coverage,
            'measured_frames': measured,
            'sampled_frames': sampled, 'failed_frames_or_ocr': errors,
            'scope': 'selected_candidate_observations', 'max_frames': max(0, int(limit))*3,
            'continuity_established': False, 'requested_candidate_count': len(candidates),
            'inspected_candidate_ids': inspected_ids,
            'uninspected_candidate_count': max(0, len(candidates)-len(inspected_ids))}
