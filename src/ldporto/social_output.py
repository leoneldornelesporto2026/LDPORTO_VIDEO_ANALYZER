"""Social-output planning for Curator: story sets, aspect ratios, captions and titles.

This module never renders final social videos. It prepares grounded, cache-cheap plans that
can be consumed by the Curator without re-running perception/ASR/semantic stages.
"""
from __future__ import annotations

from collections import Counter, defaultdict
import math
import re

from .core import overlap

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

from .editorial import COMMERCIAL_TYPES, fold_text, terms


def _score(value, default=0.0):
    try:
        result = float(value)
        return result if math.isfinite(result) else default
    except (TypeError, ValueError):
        return default


def _words(text):
    return re.findall(r"[\wÀ-ÿ]+", text or "", flags=re.UNICODE)


def _short_title(text, max_words=9):
    tokens = _words(text)
    if not tokens:
        return None
    title = " ".join(tokens[:max_words])
    return title[:1].upper() + title[1:]


def _title_variants(candidate):
    """Strong but evidence-bound titles: never select an unverified LLM promise."""
    generated = candidate.get('generated_copy') or {}
    transcript = (candidate.get('transcript_literal') or '').strip()
    topic = (candidate.get('topic') or candidate.get('topic_summary') or '').strip()
    variants, seen = [], set()
    def add(mode, title, *, verified=False, reason=None):
        title = ' '.join(str(title or '').split()).strip()[:100]
        if title and fold_text(title) not in seen:
            seen.add(fold_text(title))
            variants.append({'mode': mode, 'text': title, 'requires_review': not verified,
                             'evidence_status': 'literal_transcript' if verified else 'lexically_supported_suggestion',
                             'evidence_reason': reason})
    literal_terms = terms(transcript)
    if '?' in transcript:
        question = transcript.split('?', 1)[0].strip() + '?'
        if 3 <= len(_words(question)) <= 14:
            add('literal_question', question, verified=True)
    # Avoid fabricated secrets, revelations, absolute claims, quantities and
    # outcomes not anchored in the canonical transcript. Lexical containment is
    # intentionally strict; human editor may still propose a paraphrase.
    for mode, value in (('semantic_hook', generated.get('hook_idea')),
                        ('semantic_editorial', generated.get('title_idea')),
                        ('topic', topic)):
        if not isinstance(value, str) or not value.strip():
            continue
        proposed = terms(value)
        unsupported = proposed - literal_terms
        novelty = len(unsupported) / max(1, len(proposed))
        forbidden = {'segredo', 'revelacao', 'inacreditavel', 'chocante', 'exclusivo',
                     'bomba', 'prova', 'verdade', 'nunca', 'sempre', 'tudo', 'ninguem'}
        if (literal_terms and len(proposed) >= 2 and novelty <= .25
            and not (unsupported & forbidden)):
            add(mode, value, verified=False, reason='lexical_overlap_not_fact_check')
    literal = _short_title(transcript)
    if literal:
        add('literal_excerpt', literal, verified=True)
    return variants[:4]


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
    limit = int(cfg.get('max_stories', 12))
    spacing = float(cfg.get('min_spacing_seconds', 45))
    per_topic = int(cfg.get('max_per_topic', 2))
    distribution_window = max(1., float(cfg.get('distribution_window_seconds', 600)))
    max_per_window = int(cfg.get('max_per_window', 3))
    eligible, rejection = [], Counter()
    for candidate in candidates:
        duration = _score(candidate.get('duration'), _score(candidate.get('end')) - _score(candidate.get('start')))
        if not minimum <= duration <= maximum:
            rejection['duration'] += 1; continue
        if _commercial(candidate) or candidate.get('default_shortlist_eligible') is False:
            rejection['commercial_or_editorial_gate'] += 1; continue
        if (candidate.get('commercial_classification') or {}).get('eligibility') not in (None, 'eligible'):
            rejection['commercial_requires_review'] += 1; continue
        if candidate.get('editorial_blockers'):
            rejection['editorial_blocker'] += 1; continue
        row = dict(candidate)
        row['story_score'] = _story_score(candidate)
        row['story_category'] = _category(candidate)
        eligible.append(row)
    eligible.sort(key=lambda row: (-row['story_score'], row.get('start', 0)))
    if not eligible:
        return [], {'eligible_count': 0, 'selected_count': 0, 'rejection_reasons': dict(rejection),
                    'category_counts': {}, 'topic_counts': {}, 'distribution_window_seconds': distribution_window,
                    'window_counts': {}, 'phase_coverage': 0}
    earliest = min(_score(row.get('start')) for row in eligible)
    latest = max(_score(row.get('end')) for row in eligible)
    # Equal-duration temporal phases enable beginning/middle/end coverage even
    # when the video is shorter than 600 s. One top item per phase first.
    phases = min(max(1, limit), max(1, math.ceil((latest-earliest)/distribution_window)))
    phase_width = max(1., (latest-earliest)/phases)
    def phase(row):
        return min(phases-1, int((_score(row.get('start'))-earliest)/phase_width))
    grouped = defaultdict(list)
    for row in eligible:
        grouped[phase(row)].append(row)
    selected, ids, topic_counts, category_counts, window_counts, distinct_arcs = [], set(), Counter(), Counter(), Counter(), set()
    def accept(row):
        cid = row.get('candidate_id')
        topic = row.get('primary_topic_id') or row.get('topic') or 'unknown'
        window_id = int(_score(row.get('start')) // distribution_window)
        arc = row.get('story_arc') or row.get('source_story_arc_id')
        if not cid or cid in ids or topic_counts[topic] >= per_topic or window_counts[window_id] >= max_per_window:
            return False
        if arc and arc in distinct_arcs:
            return False
        for prior in selected:
            if max(row['start'], prior['start']) < min(row['end'], prior['end']):
                return False
            distance = min(abs(row['start']-prior['start']), abs(row['end']-prior['end']))
            if distance < spacing and row['story_category'] == prior['story_category']:
                return False
        selected.append(row); ids.add(cid); topic_counts[topic] += 1
        category_counts[row['story_category']] += 1; window_counts[window_id] += 1
        if arc: distinct_arcs.add(arc)
        return True
    # Phase-first, then best remaining material. No forced quantity.
    for key in sorted(grouped):
        for row in grouped[key]:
            if accept(row):
                break
        if len(selected) >= limit:
            break
    for row in eligible:
        if len(selected) >= limit: break
        accept(row)
    selected.sort(key=lambda row: (-row['story_score'], row.get('start', 0)))
    return selected, {'eligible_count': len(eligible), 'selected_count': len(selected),
        'category_counts': dict(category_counts), 'topic_counts': dict(topic_counts),
        'rejection_reasons': dict(rejection), 'distribution_window_seconds': distribution_window,
        'window_counts': dict(window_counts), 'temporal_phases': phases,
        'phase_coverage': len(set(phase(row) for row in selected)),
        'coverage_seconds': {'first_candidate_start': earliest, 'last_candidate_end': latest},
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
        titles = _title_variants(candidate)
        title = titles[0]["text"] if titles else f"Momento {rank}"
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
        clip_review = (analysis.get('subtitle_review_s7') or {}).get('candidates', {}).get(candidate['candidate_id'], {})
        caption_plan['subtitle_review_state'] = clip_review.get('approval_state', 'NOT_EVALUATED')
        caption_plan['word_highlight_enabled'] = bool(clip_review.get('karaoke_allowed'))
        caption_plan['effective_preset'] = ('simple' if preset in ('karaoke', 'pod_p')
                                             and not caption_plan['word_highlight_enabled'] else preset)
        caption_plan['requested_preset'] = preset
        caption_plan['preset'] = caption_plan['effective_preset']
        caption_plan['per_clip_review_required'] = True
        caption_plan["font_family"] = social.get("caption_font", "Arial")
        caption_plan["size_scale"] = social.get("caption_size_scale", 1.0)
        caption_plan["primary_color"] = social.get("caption_primary_color", "#FFFFFF")
        caption_plan["highlight_color"] = social.get("caption_highlight_color", "#F4FF26")
        row = {
            "story_id": f"STORY_{rank:03d}", "rank": rank,
            "candidate_id": candidate["candidate_id"], "start": candidate["start"], "end": candidate["end"],
            "duration": candidate.get("duration") or candidate["end"] - candidate["start"],
            "category": candidate["story_category"], "score": candidate["story_score"],
            "visual_plan": visual_plan,
            "audio_reaction_evidence": [{"start": r.get('start'), "end": r.get('end'),
                "label": r.get('label') or r.get('event') or r.get('type'),
                "confidence": r.get('confidence')} for r in observed_reactions[:8]],
            "title": title, "title_variants": titles,
            "title_status": ("literal_transcript_requires_editorial_review" if titles and
                titles[0].get('evidence_status') == 'literal_transcript' else 'grounded_suggestion_requires_review'),
            "caption_preset": caption_plan["effective_preset"], "requested_caption_preset": preset, "caption_plan": caption_plan,
            "aspect_ratio": aspect, "render_profile": ASPECT_RATIOS[aspect],
            "camera_mode": candidate.get("camera_mode"), "layouts": candidate.get("layouts", []),
            "reason": "selected_from_full_video_with_editorial_temporal_and_category_diversity",
            "source_topic_id": candidate.get("primary_topic_id"),
            "source_story_arc_id": candidate.get("story_arc"),
            "commercial_review": candidate.get("commercial_classification"),
            "publication_ready": False, "requires_curator_review": True,
        }
        stories.append(row)
        title_rows.append({"story_id": row["story_id"], "candidate_id": row["candidate_id"], "title": title,
                           "variants": titles, "status": row["title_status"]})
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
