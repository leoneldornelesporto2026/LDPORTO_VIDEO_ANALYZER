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

from .editorial import COMMERCIAL_TYPES


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
    generated = candidate.get("generated_copy") or {}
    transcript = (candidate.get("transcript_literal") or "").strip()
    topic = (candidate.get("topic") or candidate.get("topic_summary") or "").strip()
    variants = []
    for mode, value in (
        ("semantic_editorial", generated.get("title_idea")),
        ("semantic_hook", generated.get("hook_idea")),
        ("topic", topic),
    ):
        if value and value not in [row["text"] for row in variants]:
            variants.append({"mode": mode, "text": str(value).strip(), "requires_review": True})
    if "?" in transcript:
        question = transcript.split("?", 1)[0].strip() + "?"
        if 3 <= len(_words(question)) <= 14:
            variants.append({"mode": "literal_question", "text": question, "requires_review": False})
    literal = _short_title(transcript)
    if literal and literal not in [row["text"] for row in variants]:
        variants.append({"mode": "literal_excerpt", "text": literal, "requires_review": True})
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
        or row.get("eligibility") == "excluded"
        or _score(score) >= .7
        or candidate.get("default_shortlist_eligible") is False and row.get("eligibility") == "excluded"
    )


def _critical_editorial_stage_ready(analysis):
    stage = (analysis.get("stage_status") or {}).get("16_understanding", {})
    status = stage.get("status")
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
    """Select multiple independent story moments with temporal/topic/category diversity."""
    minimum = float(cfg.get("min_seconds", 15))
    maximum = float(cfg.get("max_seconds", 60))
    limit = int(cfg.get("max_stories", 12))
    spacing = float(cfg.get("min_spacing_seconds", 45))
    per_topic = int(cfg.get("max_per_topic", 2))
    distribution_window = float(cfg.get("distribution_window_seconds", 600))
    max_per_window = int(cfg.get("max_per_window", 3))
    eligible = []
    for candidate in candidates:
        duration = _score(candidate.get("duration"), _score(candidate.get("end")) - _score(candidate.get("start")))
        if not minimum <= duration <= maximum:
            continue
        if _commercial(candidate) or candidate.get("default_shortlist_eligible") is False:
            continue
        row = dict(candidate)
        row["story_score"] = _story_score(candidate)
        row["story_category"] = _category(candidate)
        eligible.append(row)
    eligible.sort(key=lambda row: (-row["story_score"], row.get("start", 0)))
    selected, topic_counts, category_counts, window_counts = [], Counter(), Counter(), Counter()
    for row in eligible:
        topic = row.get("primary_topic_id") or row.get("topic") or "unknown"
        window_id = int(float(row.get("start", 0)) // max(distribution_window, 1.0))
        if topic_counts[topic] >= per_topic or window_counts[window_id] >= max_per_window:
            continue
        too_close = False
        for prior in selected:
            distance = min(abs(row["start"] - prior["start"]), abs(row["end"] - prior["end"]))
            if distance < spacing and row["story_category"] == prior["story_category"]:
                too_close = True
                break
        if too_close:
            continue
        selected.append(row)
        topic_counts[topic] += 1
        window_counts[window_id] += 1
        category_counts[row["story_category"]] += 1
        if len(selected) >= limit:
            break
    # Fill remaining slots only after diversity pass, still without exact duplicates/commercials.
    ids = {row["candidate_id"] for row in selected}
    for row in eligible:
        if len(selected) >= limit:
            break
        if row["candidate_id"] in ids:
            continue
        topic = row.get("primary_topic_id") or row.get("topic") or "unknown"
        window_id = int(float(row.get("start", 0)) // max(distribution_window, 1.0))
        if topic_counts[topic] >= per_topic or window_counts[window_id] >= max_per_window:
            continue
        selected.append(row); ids.add(row["candidate_id"]); topic_counts[topic] += 1; window_counts[window_id] += 1; category_counts[row["story_category"]] += 1
    return selected, {"eligible_count": len(eligible), "selected_count": len(selected),
                      "category_counts": dict(category_counts), "topic_counts": dict(topic_counts),
                      "distribution_window_seconds": distribution_window, "window_counts": dict(window_counts)}


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
    stories, title_rows, caption_rows = [], [], []
    for rank, candidate in enumerate(selected, 1):
        preset = _preset_for(candidate, content_mode, preset_cfg)
        titles = _title_variants(candidate)
        title = titles[0]["text"] if titles else f"Momento {rank}"
        caption_plan = _caption_plan(candidate, graphics, preset)
        caption_plan["font_family"] = social.get("caption_font", "Arial")
        caption_plan["size_scale"] = social.get("caption_size_scale", 1.0)
        caption_plan["primary_color"] = social.get("caption_primary_color", "#FFFFFF")
        caption_plan["highlight_color"] = social.get("caption_highlight_color", "#F4FF26")
        row = {
            "story_id": f"STORY_{rank:03d}", "rank": rank,
            "candidate_id": candidate["candidate_id"], "start": candidate["start"], "end": candidate["end"],
            "duration": candidate.get("duration") or candidate["end"] - candidate["start"],
            "category": candidate["story_category"], "score": candidate["story_score"],
            "title": title, "title_variants": titles, "title_status": "grounded_suggestion_requires_review",
            "caption_preset": preset, "caption_plan": caption_plan,
            "aspect_ratio": aspect, "render_profile": ASPECT_RATIOS[aspect],
            "camera_mode": candidate.get("camera_mode"), "layouts": candidate.get("layouts", []),
            "reason": "selected_from_full_video_with_editorial_temporal_and_category_diversity",
            "source_topic_id": candidate.get("primary_topic_id"),
            "source_story_arc_id": candidate.get("story_arc"),
            "commercial_review": candidate.get("commercial_classification"),
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
