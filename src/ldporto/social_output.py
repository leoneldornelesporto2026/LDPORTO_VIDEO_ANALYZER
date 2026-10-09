"""Social-output planning for Curator: story sets, aspect ratios, captions and titles.

This module never renders final social videos. It prepares grounded, cache-cheap plans that
can be consumed by the Curator without re-running perception/ASR/semantic stages.
"""
from __future__ import annotations

from collections import Counter
import math
import re

from .core import overlap
from .subtitle_review import clip_karaoke_gate
from .subtitle_style import style_rules
from .safe_area import plan_safe_area

ASPECT_RATIOS = {
    "9:16": {"width": 1080, "height": 1920, "use": "stories_reels_shorts"},
    "4:5": {"width": 1080, "height": 1350, "use": "feed_portrait"},
    "1:1": {"width": 1080, "height": 1080, "use": "square_feed"},
    "16:9": {"width": 1920, "height": 1080, "use": "youtube_landscape"},
}

CAPTION_PRESETS = {
    "no_caption": {"label": "No Caption", "font_family": "Arial", "weight": "bold", "highlight": False, "background": "none", "motion": "none"},
    "simple": {"label": "Simple", "font_family": "Arial", "weight": "bold", "highlight": False, "background": "none", "motion": "none"},
    "karaoke": {"label": "Karaoke", "font_family": "Arial", "weight": "black", "highlight": True, "background": "none", "motion": "word_highlight"},
    "popline": {"label": "Popline", "font_family": "Arial", "weight": "black", "highlight": True, "background": "none", "motion": "gentle_pop"},
    "deep_diver": {"label": "Deep Diver", "font_family": "Arial", "weight": "bold", "highlight": False, "background": "soft_box", "motion": "fade"},
    "think_media": {"label": "Think Media", "font_family": "Arial", "weight": "black", "highlight": True, "background": "none", "motion": "keyword_pop"},
    "pod_p": {"label": "Pod P", "font_family": "Arial", "weight": "bold", "highlight": True, "background": "none", "motion": "word_highlight"},
    "news": {"label": "News", "font_family": "Arial", "weight": "bold", "highlight": False, "background": "soft_box", "motion": "fade"},
    "show_highlight": {"label": "Show Highlight", "font_family": "Arial", "weight": "black", "highlight": True, "background": "none", "motion": "gentle_pop"},
    "clean_bold": {"label": "Clean Bold", "font_family": "Arial", "weight": "black", "highlight": True, "background": "none", "motion": "gentle_pop"},
    "high_contrast": {"label": "High Contrast", "font_family": "Arial", "weight": "black", "highlight": True, "background": "dark_box", "motion": "none"},
    "soft_subtitle": {"label": "Soft Subtitle", "font_family": "Arial", "weight": "semibold", "highlight": False, "background": "soft_box", "motion": "fade"},
    "creator_style": {"label": "Creator Style", "font_family": "Arial", "weight": "black", "highlight": True, "background": "none", "motion": "keyword_pop"},
}

from .editorial import COMMERCIAL_TYPES
from .editorial_intelligence import absolute_selection_blockers, diversity_next, diversity_features, selection_disposition


def _score(value, default=0.0):
    try:
        result = float(value)
        return result if math.isfinite(result) else default
    except (TypeError, ValueError):
        return default


def _words(text):
    return re.findall(r"[\wÀ-ÿ]+", text or "", flags=re.UNICODE)


def title_plan(candidate, review=None, words=None):
    """Conservative text support, never a factual/audio or publication approval.

    Only complete source sentences qualify automatically. Paraphrases require
    human review outside this gate: bag-of-words overlap cannot check negation,
    attribution, reordered events or numbers. Never truncate a source sentence.
    """
    transcript = ' '.join(str(candidate.get('transcript_literal') or '').split())
    sentences = re.findall(r'[^.!?]+[.!?](?:["”\'](?=\s|$))?', transcript)
    sentences = [s.strip() for s in sentences if s.strip()]
    review = review or {}
    issues = set(review.get('issue_counts') or {})
    issues.update(code for cap in review.get('captions') or [] for code in cap.get('issue_codes') or [])
    uncertain = bool(issues & {'asr_text_uncertain', 'suspected_hallucination',
        'alternate_asr_requires_listening', 'interrupted_or_incomplete_word',
        'overlapping_speech', 'multiple_voices_overlap', 'cut_splits_word',
        'phrase_boundary_requires_listening'})
    uncertain = uncertain or _score((candidate.get('technical_quality') or {}).get('asr_low_confidence_fraction')) > 0
    for word in (words or candidate.get('words') or []):
        confidence = word.get('confidence')
        if (word.get('needs_review') or word.get('suspected_hallucination') or word.get('speech_overlap')
                or word.get('truncated') or word.get('truncation') or word.get('non_word')
                or confidence is None or _score(confidence, -1) < .6 or _score(confidence, -1) > 1):
            uncertain = True
    uncertain = uncertain or bool(re.search(r'\[[^]]+\]|\u2026', transcript))
    evidence = {'candidate_id': candidate.get('candidate_id'), 'start': candidate.get('start'),
                'end': candidate.get('end'), 'segment_ids': list(candidate.get('segment_ids') or []),
                'text': transcript or None, 'audio_verified': None}
    variants, rejected, seen = [], [], set()
    def add(mode, value):
        text = ' '.join(str(value or '').split())
        if not text or text in seen:
            return
        seen.add(text)
        supported = text in sentences
        reason = ('asr_uncertain_requires_listening' if uncertain and supported else
                  'complete_literal_sentence_requires_context_review' if supported else
                  'not_complete_literal_sentence_semantic_support_unverified')
        row = {'mode': mode, 'text': text, 'requires_review': True,
               'review_status': 'LISTEN_AND_REVIEW' if uncertain and supported else 'REVIEW_REQUIRED' if supported else 'REJECTED',
               'evidence_status': 'asr_uncertain' if uncertain and supported else 'literal_transcript' if supported else 'unsupported',
               'evidence_reason': reason, 'evidence_excerpt': text if supported else None,
               'source_evidence': dict(evidence), 'support_validated': supported and not uncertain,
               'fact_verified': None}
        if supported and len(text) <= 100 and len(_words(text)) <= 14:
            variants.append(row)
        else:
            if supported:
                row.update(review_status='REJECTED', evidence_reason='complete_sentence_exceeds_title_budget')
            rejected.append(row)
    generated = candidate.get('generated_copy') or {}
    for mode, value in [('semantic_hook', generated.get('hook_idea')),
                        ('semantic_editorial', generated.get('title_idea')),
                        ('topic', candidate.get('topic') or candidate.get('topic_summary'))]:
        add(mode, value)
    for sentence in sorted(sentences, key=lambda s: not s.endswith('?')):
        add('literal_question' if sentence.endswith('?') else 'literal_sentence', sentence)
    variants = variants[:4]
    principal = next((r for r in variants if r['support_validated']), None)
    return {'title': principal['text'] if principal else None, 'title_principal': principal,
            'title_variants': variants, 'title_alternatives': [r for r in variants if r is not principal],
            'title_rejections': rejected, 'title_status': 'SUPPORTED_REVIEW_REQUIRED' if principal else 'TITLE_REVIEW_REQUIRED',
            'title_review_reasons': [principal['evidence_reason'] if principal else
                'asr_uncertain_requires_listening' if uncertain else 'no_supported_complete_title'],
            'title_source_evidence': evidence, 'title_validated': bool(principal),
            'title_human_approved': False}


def _title_variants(candidate):
    return title_plan(candidate)['title_variants']


def _story_diversity_next(rows, selected, window_seconds):
    # Add category to the existing quality-band policy without changing shortlist.
    best = max(r['story_score'] for r in rows)
    close = [r for r in rows if r['story_score'] >= best - .08]
    def novelty(row):
        return (int(not any(r['story_category'] == row['story_category'] for r in selected)) +
                int(not any(int(r['start'] // window_seconds) == int(row['start'] // window_seconds) for r in selected)))
    if selected:
        most = max(novelty(r) for r in close)
        close = [r for r in close if novelty(r) == most]
    return diversity_next(close, selected, 'story_score', window_seconds)


def _category(candidate):
    components = candidate.get("score_components") or {}
    options = {
        "humor": _score(components.get("humor")),
        "emocao": _score(components.get("emotion")),
        "curiosidade": _score(components.get("curiosity")),
        "impacto": max(_score(components.get("surprise")), _score(components.get("controversy")), _score(candidate.get("hook_strength"))),
        "pergunta_resposta": 1.0 if candidate.get("question_answer_linkage") else _score(components.get("qa_completeness")),
        "historia": _score(components.get("story_completeness")),
        "informativo": _score(components.get("information_density")),
        "visual": _score(components.get("visual_viability")),
    }
    category, value = max(options.items(), key=lambda pair: pair[1])
    return category if value > 0 else "momento_forte"


def _commercial(candidate):
    row = candidate.get("commercial_classification") or {}
    score = row.get("commercial_score", row.get("score", candidate.get("commercial_score")))
    return bool(
        candidate.get("content_type") in COMMERCIAL_TYPES
        or row.get("content_type") in COMMERCIAL_TYPES
        or row.get("eligibility") in {"excluded", "review"}
        or _score(score) >= .7
        or candidate.get("default_shortlist_eligible") is False and row.get("eligibility") == "excluded"
    )


def _critical_editorial_stage_ready(analysis):
    stage = (analysis.get("stage_status") or {}).get("16_understanding", {})
    status = stage.get("status")
    if status is None and (analysis.get("run_manifest") or {}).get("root_cause_stage") == "16_understanding":
        return False, 'understanding_failed_or_unavailable_in_run_manifest'
    if status is None:
        return True, None
    if status in {"ok", "partial"}:
        return True, None
    return False, f"understanding_{status}"


def _story_score(candidate):
    components = candidate.get("score_components") or {}
    editorial = _score(candidate.get("editorial_quality_score"), _score(candidate.get("editorial_score_final"), _score(candidate.get("editorial_score_raw"))))
    bonus = max(
        _score(candidate.get("hook_strength")),
        _score(components.get("emotion")),
        _score(components.get("humor")),
        _score(components.get("curiosity")),
        _score(components.get("surprise")),
        _score(components.get("story_completeness")),
        _score(components.get("qa_completeness")),
    )
    visual = _score(candidate.get("visual_viability"))
    standalone = _score(components.get("standalone_clarity"))
    confidence = _score(candidate.get("ranking_confidence"), .5)
    return round(.45 * editorial + .22 * bonus + .12 * visual + .11 * standalone + .10 * confidence, 6)


def _graphics_for_interval(graphics, start, end):
    rows = []
    for interval in (graphics or {}).get("intervals", []):
        if overlap(start, end, interval.get("start", 0), interval.get("end", 0)) <= 0:
            continue
        rows.extend([region for region in interval.get("regions", []) if isinstance(region, dict)])
    return rows


def _normalized_rect_overlap(first, second):
    """2D overlap area of normalized bounding boxes; zero on missing geometry."""
    try:
        a = (_score(first['x']), _score(first['y']), _score(first['width']), _score(first['height']))
        b = (_score(second['x']), _score(second['y']), _score(second['width']), _score(second['height']))
        if not (0 <= a[0] <= 1 and 0 <= a[1] <= 1 and 0 < a[2] <= 1 and 0 < a[3] <= 1 and
                0 <= b[0] <= 1 and 0 <= b[1] <= 1 and 0 < b[2] <= 1 and 0 < b[3] <= 1):
            return 0.
        return max(0., min(a[0]+a[2], b[0]+b[2])-max(a[0],b[0])) * max(0.,min(a[1]+a[3],b[1]+b[3])-max(a[1],b[1]))
    except (TypeError, KeyError):
        return 0.


def _caption_plan(candidate, graphics, preset):
    regions = _graphics_for_interval(graphics, candidate["start"], candidate["end"])
    lower = any(row.get("persistent") and row.get("kind") in {"lower_third", "ticker"} and _score(row.get("y_start")) > .4 for row in regions)
    top = any(row.get("persistent") and row.get("kind") == "banner" and _score(row.get("y_end")) < .35 for row in regions)
    if lower and not top:
        preferred = "upper_middle"
    elif top and not lower:
        preferred = "lower_middle"
    elif lower and top:
        preferred = "dynamic_safe_zone"
    else:
        preferred = "lower_middle"
    return {
        "preset": preset,
        "preferred_position": preferred,
        "avoid_faces": True,
        "avoid_mouth": True,
        "avoid_broadcast_graphics": True,
        "dynamic_reposition_required": bool(candidate.get("person_ids") or regions),
        "broadcast_regions": regions,
        "fallback_positions": ["upper_middle", "lower_middle", "center_low", "top"],
        "max_lines": 2,
        "line_break_policy": "phrase_boundary_first",
        "safe_area_policy": "recompute_after_crop_and_aspect_ratio",
        "broadcast_evidence_status": "interval_observed" if regions else "no_observed_region_in_interval_not_proof_of_absence",
        "final_safe_area_verified": False,
        "subtitle_text_review_required": True,
        "candidate_safe_rects_normalized": [
            {"position": "upper_middle", "x": .10, "y": .18, "width": .80, "height": .22,
             "requires_post_crop_validation": True},
            {"position": "lower_middle", "x": .10, "y": .62, "width": .80, "height": .20,
             "requires_post_crop_validation": True}],
        "observed_graphics_count": len(regions),
        "coordinate_system": "normalized_post_crop_placeholder",
        "position_verification": "pending_frame_and_final_render",
    }


def _preset_for(candidate, content_mode, configured):
    if configured != "auto":
        return configured
    category = _category(candidate)
    if content_mode == "show":
        return "show_highlight"
    if content_mode in {"programa_tv", "noticias"}:
        return "news"
    if category in {"humor", "impacto", "emocao"}:
        return "creator_style"
    if category == "pergunta_resposta":
        return "clean_bold"
    return "karaoke"


def select_story_set(candidates, cfg):
    """Select across the complete programme; never fill slots by repetition."""
    minimum = float(cfg.get('min_seconds', 15))
    maximum = float(cfg.get('max_seconds', 60))
    limit = max(0, int(cfg.get('max_stories', 12)))
    spacing = float(cfg.get('min_spacing_seconds', 45))
    per_topic = int(cfg.get('max_per_topic', 2))
    distribution_window = max(1., float(cfg.get('distribution_window_seconds', 600)))
    max_per_window = int(cfg.get('max_per_window', 3))
    eligible, rejection, rejected_candidates = [], Counter(), {}
    def reject(candidate, reason):
        rejection[reason] += 1
        rejected_candidates[candidate.get("candidate_id")] = [reason] + absolute_selection_blockers(candidate)
    def decisions(ids):
        return [{"candidate_id": r.get("candidate_id"),
                 "disposition": selection_disposition(r, rejected_candidates.get(r.get("candidate_id"), []), r.get("candidate_id") in ids),
                 "reasons": rejected_candidates.get(r.get("candidate_id"), ["passed_recorded_selection_gates"]),
                 "commercial_block_refs": r.get('commercial_block_refs', []),
                 "excluded_commercial_interval_ids": r.get('excluded_commercial_interval_ids', []),
                 "diversity_features": diversity_features(r, distribution_window)} for r in candidates]
    for candidate in candidates:
        duration = _score(candidate.get('duration'), _score(candidate.get('end')) - _score(candidate.get('start')))
        if not minimum <= duration <= maximum:
            reject(candidate, 'duration'); continue
        if candidate.get('excluded_commercial_interval_ids') or _commercial(candidate) or candidate.get('default_shortlist_eligible') is False:
            reject(candidate, 'commercial_or_editorial_gate'); continue
        if (candidate.get('commercial_classification') or {}).get('eligibility') not in (None, 'eligible'):
            reject(candidate, 'commercial_requires_review'); continue
        if absolute_selection_blockers(candidate):
            reject(candidate, 'editorial_blocker'); continue
        row = dict(candidate)
        row['story_score'] = _story_score(candidate)
        row['story_category'] = _category(candidate)
        if row['story_score'] < float(cfg.get('min_story_score', .50)):
            reject(candidate, 'below_story_quality_floor'); continue
        eligible.append(row)
    eligible.sort(key=lambda row: (-row['story_score'], row.get('start', 0)))
    if not eligible:
        return [], {'eligible_count': 0, 'selected_count': 0, 'rejection_reasons': dict(rejection),
                    'category_counts': {}, 'topic_counts': {}, 'distribution_window_seconds': distribution_window,
                    'window_counts': {}, 'phase_coverage': 0, 'fixed_quota': False,
                    'unfilled_slots_are_intentional': limit > 0, 'candidate_decisions': decisions(set())}
    earliest = min(_score(row.get('start')) for row in eligible)
    latest = max(_score(row.get('end')) for row in eligible)
    # Phase coverage is diagnostic; it does not reserve or force any slots.
    phases = min(max(1, limit), max(1, math.ceil((latest-earliest)/distribution_window)))
    phase_width = max(1., (latest-earliest)/phases)
    def phase(row):
        return min(phases-1, int((_score(row.get('start'))-earliest)/phase_width))
    selected, ids, topic_counts, category_counts, window_counts, distinct_arcs = [], set(), Counter(), Counter(), Counter(), set()
    def accept(row):
        cid = row.get('candidate_id')
        topic = row.get('primary_topic_id') or row.get('topic')
        window_id = int(_score(row.get('start')) // distribution_window)
        arc = row.get('story_arc') or row.get('source_story_arc_id') or row.get('story_arc_id')
        if not cid or cid in ids or (topic and topic_counts[topic] >= per_topic) or window_counts[window_id] >= max_per_window:
            return False
        if arc and arc in distinct_arcs:
            return False
        for prior in selected:
            if row.get('duplicate_group_id') and row['duplicate_group_id'] == prior.get('duplicate_group_id'):
                return False
            if max(row['start'], prior['start']) < min(row['end'], prior['end']):
                return False
            distance = min(abs(row['start']-prior['start']), abs(row['end']-prior['end']))
            if distance < spacing and row['story_category'] == prior['story_category']:
                return False
        selected.append(row); ids.add(cid)
        if topic: topic_counts[topic] += 1
        category_counts[row['story_category']] += 1; window_counts[window_id] += 1
        if arc: distinct_arcs.add(arc)
        return True
    remaining = list(eligible)
    while remaining and len(selected) < limit:
        row = _story_diversity_next(remaining, selected, distribution_window)
        remaining.remove(row)
        if not accept(row):
            rejected_candidates[row.get('candidate_id')] = ['diversity_or_repetition_limit']
    for row in remaining:
        rejected_candidates[row.get('candidate_id')] = ['shortlist_capacity']
    selected.sort(key=lambda row: (-row['story_score'], row.get('start', 0)))
    return selected, {'eligible_count': len(eligible), 'selected_count': len(selected),
        'category_counts': dict(category_counts), 'topic_counts': dict(topic_counts),
        'rejection_reasons': dict(rejection), 'distribution_window_seconds': distribution_window,
        'window_counts': dict(window_counts), 'temporal_phases': phases,
        'phase_coverage': len(set(phase(row) for row in selected)),
        'coverage_seconds': {'first_candidate_start': earliest, 'last_candidate_end': latest},
        'fixed_quota': False, 'diversity_policy_version': '23.1',
        'candidate_decisions': decisions(ids),
        'unfilled_slots_are_intentional': len(selected) < limit}


def build_social_output(analysis, cfg, package=None):
    social = cfg.get("social_output") or {}
    stories_cfg = social.get("stories") or {}
    candidates = (package or analysis.get("second_curation_package") or {}).get("candidates", [])
    editorial_ready, blocked_reason = _critical_editorial_stage_ready(analysis)
    if editorial_ready:
        selected, metrics = select_story_set(candidates, stories_cfg)
    else:
        selected = []
        metrics = {
            "eligible_count": 0, "selected_count": 0, "category_counts": {}, "topic_counts": {},
            "distribution_window_seconds": float(stories_cfg.get("distribution_window_seconds", 600)),
            "window_counts": {}, "blocked_reason": blocked_reason,
            "provisional_candidate_count": len(candidates),
        }
    content_mode = social.get("content_mode", "auto")
    preset_cfg = social.get("caption_preset", "auto")
    aspect = social.get("aspect_ratio", "9:16")
    graphics = analysis.get("broadcast_graphics") or {}
    ocr_rows = (analysis.get('commercial_visual_s8') or {}).get('texts') or []
    events = analysis.get('audio_events') or []
    stories, title_rows, caption_rows = [], [], []
    for rank, candidate in enumerate(selected, 1):
        preset = _preset_for(candidate, content_mode, preset_cfg)
        clip_review = (analysis.get('subtitle_review_s7') or {}).get('candidates', {}).get(candidate['candidate_id'], {})
        source_words = [w for w in analysis.get('words') or []
                        if w.get('word_id') in (candidate.get('word_ids') or []) or
                        candidate['start'] < _score(w.get('end'), -1) and _score(w.get('start'), -1) < candidate['end']]
        copy_plan = title_plan(candidate, clip_review, source_words)
        title = copy_plan['title']
        caption_plan = _caption_plan(candidate, graphics, preset)
        evidence_ocr = [r for r in ocr_rows if isinstance(r, dict) and r.get('bbox')
                        and candidate['start'] <= _score(r.get('observed_at'), -1) < candidate['end']
                        and (not r.get('moment_id') or r.get('moment_id') == candidate['candidate_id'])]
        caption_plan['observed_ocr_boxes'] = [{'observed_at': r.get('observed_at'),
            'bbox': r['bbox'], 'visual_type_hint': r.get('visual_type_hint'),
            'persistence': 'unknown', 'source': 'ocr'} for r in evidence_ocr]
        caption_plan['requires_reposition_after_crop'] = bool(evidence_ocr or caption_plan['broadcast_regions'])
        obstacles = [r['bbox'] for r in evidence_ocr]
        for region in caption_plan['broadcast_regions']:
            if not all(k in region for k in ('x_start','x_end','y_start','y_end')):
                continue
            obstacles.append({'x':region['x_start'], 'y':region['y_start'],
                'width': _score(region['x_end'])-_score(region['x_start']),
                'height': _score(region['y_end'])-_score(region['y_start'])})
        for rect in caption_plan['candidate_safe_rects_normalized']:
            hits = sum(_normalized_rect_overlap(rect, obstacle) > .001 for obstacle in obstacles)
            rect['observed_overlay_conflicts'] = hits
            rect['evidence_status'] = 'observed_overlay_conflict_requires_relayout' if hits else 'provisional_no_overlay_overlap_not_face_verified'
        preferred_rect = next((r for r in caption_plan['candidate_safe_rects_normalized']
            if r['position'] == caption_plan['preferred_position']), None)
        if preferred_rect and preferred_rect['observed_overlay_conflicts']:
            alternatives = [r for r in caption_plan['candidate_safe_rects_normalized']
                if not r['observed_overlay_conflicts']]
            caption_plan['preferred_position'] = alternatives[0]['position'] if alternatives else 'dynamic_safe_zone'
            caption_plan['position_verification'] = 'overlay_conflict_requires_reposition_and_final_frame_verification'
        observed_reactions = [r for r in events if isinstance(r, dict)
            and _score(r.get('start'), -1) >= candidate['start'] and _score(r.get('start'), -1) < candidate['end']
            and any(word in str(r.get('label') or r.get('event') or r.get('type') or '').lower()
                    for word in ('laughter', 'laugh', 'risada', 'applause', 'aplauso'))]
        # These events are only optional signals; they cannot infer speech or
        # automatically assert an authentic joke.
        visual_mode = ('reaction_split_review' if len(candidate.get('person_ids') or []) >= 2
                       and any('split' in str(l).lower() for l in candidate.get('layouts') or [])
                       and observed_reactions else 'source_preserve')
        style_by_category = {
            'humor': 'humor_reaction_conservative',
            'pergunta_resposta': 'qa_clean_question_hook',
            'historia': 'story_arc_context_first',
            'curiosidade': 'curiosity_factual',
            'emocao': 'emotional_minimal',
            'impacto': 'impact_emphasis',
            'informativo': 'information_clear',
            'visual': 'source_visual_preserve',
        }
        # Screen geometry must be recomputed after the final crop. Suggested
        # rectangles are *not* certified free of faces/TV graphics.
        gc_top = any(r.get('kind') == 'banner' and _score(r.get('y_end')) < .35
                     for r in caption_plan['broadcast_regions'])
        gc_lower = any(r.get('kind') in ('lower_third','ticker') and _score(r.get('y_start')) > .4
                       for r in caption_plan['broadcast_regions'])
        title_rect = ({'x':.1, 'y':.33, 'width':.8, 'height':.13} if gc_top
                      else {'x':.1, 'y':.08, 'width':.8, 'height':.12})
        if gc_top and gc_lower:
            title_review_reason = 'top_and_lower_third_both_occupied_manual_layout_required'
        elif gc_top:
            title_review_reason = 'top_banner_detected_use_mid_candidate'
        elif gc_lower:
            title_review_reason = 'lower_third_detected_keep_title_top'
        else:
            title_review_reason = 'no_broadcast_graphics_observed_not_proof_of_empty_space'
        ocr_run = analysis.get('commercial_visual_s8') or {}
        graphics_run = analysis.get('broadcast_graphics') or {}
        visual_plan = {'preset': style_by_category.get(candidate['story_category'], 'source_preserve'),
            'commercial_ocr_scope': ('sampled' if candidate['candidate_id'] in (ocr_run.get('inspected_candidate_ids') or [])
                                     and ocr_run.get('status') == 'measured' else
                                     'uninspected_or_backend_unavailable'),
            'broadcast_graphics_scope': ('sampled' if candidate['candidate_id'] in (graphics_run.get('inspected_candidate_ids') or [])
                                         and graphics_run.get('status') == 'measured' else
                                         'uninspected_or_backend_unavailable'),
            'layout_mode': visual_mode, 'caption_style': preset,
            'overlay_safety': caption_plan['position_verification'],
            'title_position': 'center_upper' if gc_top else 'safe_top',
            'title_candidate_rect_normalized': title_rect,
            'title_review_reason': title_review_reason,
            'safe_area_verified': False, 'split_requires_visual_confirmation': visual_mode != 'source_preserve',
            'broadcast_region_count': len(caption_plan['broadcast_regions']),
            'ocr_observations': len(evidence_ocr), 'audio_reaction_evidence_count': len(observed_reactions),
            'needs_preview_and_human_review': True,
            'zoom_policy': 'camera_director_evidence_required_no_decorative_zoom',
            'editorial_copy_must_be_supported_by_transcript': True}
        safe_plan = plan_safe_area(analysis, candidate, ASPECT_RATIOS[aspect],
                                  caption_plan['preferred_position'], title_rect)
        visual_plan['safe_area_plan'] = safe_plan
        visual_plan['safe_area_approved'] = None
        visual_plan['post_render_validation_required'] = True
        visual_plan['reposition_required'] = safe_plan['reposition_required']
        visual_plan['reposition_reasons'] = safe_plan['reposition_reasons']
        caption_plan['safe_area_segments'] = safe_plan['segments']
        caption_plan['safe_area_confidence'] = safe_plan['confidence']
        caption_plan['safe_area_approved'] = None
        caption_plan['post_render_validation_required'] = True
        caption_plan['reposition_required'] = safe_plan['reposition_required']
        caption_plan['reposition_reasons'] = safe_plan['reposition_reasons']
        caption_plan['dynamic_reposition_required'] = (caption_plan['dynamic_reposition_required']
                                                       or safe_plan['reposition_required'])
        caption_plan['requires_reposition_after_crop'] = (caption_plan['requires_reposition_after_crop']
                                                         or safe_plan['reposition_required'])
        caption_plan['transition_policy'] = safe_plan['transition_policy']
        # Legacy positions remain a fallback when no usable output geometry exists.
        first_safe = next((s for s in safe_plan['segments'] if s['obstacles']), None)
        if first_safe and first_safe['title_rect'] and first_safe['caption_rect']:
            visual_plan['title_position'] = first_safe['title_position']
            visual_plan['title_candidate_rect_normalized'] = first_safe['title_rect']
            visual_plan['title_review_reason'] = 'joint_sampled_geometry_plan_requires_final_render_review'
            caption_plan['preferred_position'] = first_safe['caption_position']
            caption_plan['proposed_rect_normalized'] = first_safe['caption_rect']
        elif first_safe:
            visual_plan['title_position'] = 'manual_layout_required'
            visual_plan['title_candidate_rect_normalized'] = None
            visual_plan['title_review_reason'] = 'no_joint_title_caption_zone_manual_layout_required'
            caption_plan['preferred_position'] = 'dynamic_safe_zone'
            caption_plan['proposed_rect_normalized'] = None
        caption_plan['position_verification'] = 'pending_final_social_render_inspection'
        visual_plan['overlay_safety'] = caption_plan['position_verification']
        clip_review = (analysis.get('subtitle_review_s7') or {}).get('candidates', {}).get(candidate['candidate_id'], {})
        caption_plan['subtitle_review_state'] = clip_review.get('approval_state', 'NOT_EVALUATED')
        caption_plan['word_highlight_enabled'] = clip_karaoke_gate(clip_review, candidate)
        caption_plan['effective_caption_mode'] = ('word_karaoke' if caption_plan['word_highlight_enabled'] else 'phrase_subtitles')
        caption_plan['karaoke_fallback_reason'] = (None if caption_plan['word_highlight_enabled'] else 'current_cut_alignment_and_audio_evidence_not_verified')
        caption_plan['effective_preset'] = ('simple' if preset in ('karaoke', 'pod_p')
                                             and not caption_plan['word_highlight_enabled'] else preset)
        caption_plan['requested_preset'] = preset
        caption_plan['preset'] = caption_plan['effective_preset']
        caption_plan['per_clip_review_required'] = True
        caption_plan["font_family"] = social.get("caption_font", "Arial")
        caption_plan["size_scale"] = social.get("caption_size_scale", 1.0)
        caption_plan["primary_color"] = social.get("caption_primary_color", "#FFFFFF")
        caption_plan["highlight_color"] = social.get("caption_highlight_color", "#F4FF26")
        caption_plan['legibility_rules'] = style_rules(**{k: ASPECT_RATIOS[aspect][k] for k in ('width', 'height')},
            font=caption_plan['font_family'], scale=caption_plan['size_scale'],
            primary=caption_plan['primary_color'], highlight=caption_plan['highlight_color'])
        caption_plan['title_legibility_review_required'] = True
        row = {
            "story_id": f"STORY_{rank:03d}", "rank": rank,
            "candidate_id": candidate["candidate_id"], "start": candidate["start"], "end": candidate["end"],
            "duration": candidate.get("duration") or candidate["end"] - candidate["start"],
            "category": candidate["story_category"], "score": candidate["story_score"],
            "visual_plan": visual_plan,
            "audio_reaction_evidence": [{"start": r.get('start'), "end": r.get('end'),
                "label": r.get('label') or r.get('event') or r.get('type'),
                "confidence": r.get('confidence')} for r in observed_reactions[:8]],
            **copy_plan,
            "caption_preset": caption_plan["effective_preset"], "requested_caption_preset": preset, "caption_plan": caption_plan,
            "aspect_ratio": aspect, "render_profile": ASPECT_RATIOS[aspect],
            "camera_mode": candidate.get("camera_mode"), "layouts": candidate.get("layouts", []),
            "reason": "selected_from_full_video_with_editorial_temporal_and_category_diversity",
            "source_topic_id": candidate.get("primary_topic_id"),
            "source_story_arc_id": candidate.get("story_arc"),
            "commercial_review": candidate.get("commercial_classification"),
            "commercial_block_refs": candidate.get('commercial_block_refs', []),
            "excluded_commercial_interval_ids": candidate.get('excluded_commercial_interval_ids', []),
            "publication_ready": False, "requires_curator_review": True,
        }
        stories.append(row)
        title_rows.append({"story_id": row["story_id"], "candidate_id": row["candidate_id"],
                           **copy_plan, "variants": copy_plan['title_variants'], "status": row['title_status']})
        caption_rows.append({"story_id": row["story_id"], "candidate_id": row["candidate_id"], **caption_plan})
    profiles = {key: {**value, "safe_area_recomputed_per_ratio": True} for key, value in ASPECT_RATIOS.items()}
    return {
        "schema_version": "1.1", "mode": "multiple_independent_stories", "enabled": bool(stories_cfg.get("enabled", True)),
        "story_readiness": "READY" if editorial_ready else "BLOCKED",
        "story_readiness_reason": blocked_reason,
        "readiness_scope": "editorial_planning_only_not_final_render",
        "publication_ready": False, "requires_curator_review": True,
        "provisional_candidates_available": bool(candidates) and not editorial_ready,
        "selected_aspect_ratio": aspect, "available_aspect_ratios": profiles,
        "selected_caption_preset": preset_cfg, "available_caption_presets": CAPTION_PRESETS,
        "content_mode": content_mode, "caption_font": social.get("caption_font", "Arial"),
        "caption_size_scale": social.get("caption_size_scale", 1.0),
        "caption_primary_color": social.get("caption_primary_color", "#FFFFFF"),
        "caption_highlight_color": social.get("caption_highlight_color", "#F4FF26"),
        "stories": stories, "stories_metrics": metrics,
        "story_compilation": {"enabled": False, "note": "Optional future mode; independent stories are the default."},
        "title_suggestions": title_rows, "caption_style_recommendations": caption_rows,
        "render_contract": {"final_render_owner": "LDPORTO_VIDEO_CURATOR", "analyzer_renders_final_social_video": False,
                            "recompute_caption_and_title_safe_area_after_camera_crop": True},
    }
