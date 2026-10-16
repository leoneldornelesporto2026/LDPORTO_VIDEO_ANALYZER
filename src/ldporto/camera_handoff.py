"""Shared, source-bound camera recommendations for Reels and Stories.

This adapts the existing Director timeline; it never creates another camera
planner, infers a performer role, or authorizes a final crop/render.
"""
from copy import deepcopy
import math

from .core import digest
from .zoom_delivery import timeline_zoom_span


COMPOSITION_MODES = ('FOCUS_PERSON_9X16', 'SOURCE_FIT_BLUR', 'DUO_STAGE',
                     'INSTRUMENT_FOCUS', 'AUDIENCE_REACTION', 'SOURCE_PRESERVE')


def _number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _rect_valid(rect):
    return bool(isinstance(rect, dict) and all(_number(rect.get(k)) for k in ('x', 'y', 'width', 'height'))
                and min(rect['x'], rect['y']) >= 0 and min(rect['width'], rect['height']) > 0
                and rect['x'] + rect['width'] <= 1.000001 and rect['y'] + rect['height'] <= 1.000001)


def build_camera_handoff(analysis, start=None, end=None, *, intervals=None):
    """Retain absolute source times, including separate non-contiguous intervals."""
    timeline = analysis.get('camera_director_timeline') or analysis.get('camera/camera_director_timeline.json') or []
    if intervals is None:
        duration = (analysis.get('metadata') or analysis.get('source/metadata.json') or {}).get('duration')
        intervals = [{'start': 0. if start is None else start,
                      'end': duration if end is None else end}]
    selected = [dict(r) for r in intervals if _number(r.get('start')) and _number(r.get('end'))
                and 0 <= r['start'] < r['end']]
    segments = []
    for interval_index, interval in enumerate(selected):
        for row in timeline:
            if not (_number(row.get('start')) and _number(row.get('end'))):
                continue
            a, b = max(interval['start'], row['start']), min(interval['end'], row['end'])
            if a >= b:
                continue
            crop, camera = row.get('crop') or {}, row.get('camera') or {}
            safe = crop.get('safe') is True and _rect_valid(crop.get('rect_end'))
            focus = row.get('focus_person')
            pair = (row.get('split') or {})
            people = ([focus] if focus else list(dict.fromkeys(p for p in
                      (pair.get('left_person'), pair.get('right_person')) if p)))
            if row.get('layout') == 'single_person' and focus and safe:
                mode = 'FOCUS_PERSON_9X16'
            elif row.get('layout') == 'two_shot' and safe:
                mode = 'DUO_STAGE'
                people = list(row.get('visible_people') or [])
            else:
                mode = 'SOURCE_FIT_BLUR'
            requested = row.get('composition_intent')
            if requested not in COMPOSITION_MODES:
                requested = mode
            # Instrument/audience intents need their own spatial observations.
            # A face-only safe crop does not verify hands, instruments or a crowd.
            evidence_missing = []
            if requested in ('INSTRUMENT_FOCUS', 'AUDIENCE_REACTION'):
                evidence_missing.append('role_and_required_subject_geometry_review_required')
                mode = 'SOURCE_FIT_BLUR'
            if row.get('layout') == 'split_candidate':
                evidence_missing.append('split_requires_distinct_panel_geometry_and_curator_review')
            motion = bool(safe and timeline_zoom_span(row, a, b) > .001)
            segments.append({'source_interval_index': interval_index, 'start': a, 'end': b,
                'director_id': row.get('director_id'), 'source_shot_id': row.get('source_shot_id'),
                'composition_intent': requested, 'recommended_composition': mode,
                'fallback_composition': 'SOURCE_FIT_BLUR', 'terminal_fallback': 'SOURCE_PRESERVE',
                'target_person_ids': people, 'camera_mode': row.get('camera_mode'),
                'layout': row.get('layout'), 'crop': deepcopy(crop), 'camera': deepcopy(camera),
                'split': deepcopy(row.get('split')), 'keyframe_time_basis': 'absolute_source_seconds',
                'keyframes_may_extend_beyond_selected_interval': True,
                'evidence': {'visual_sample_at_start': row.get('visual_observed_at_start'),
                    'visual_sample_at_end': row.get('visual_observed_at_end'),
                    'focus_proposed': bool(focus),
                    'speaker_identity_confirmed': row.get('speaker_identity_confirmed') is True,
                    'crop_geometrically_valid': safe,
                    'motion_preflight_supported': safe and (crop.get('preflight_sample_count') or 0) >= 2,
                    'movement_present_in_timeline': motion,
                    'movement_rendered': None, 'movement_confirmed_in_final_frames': None,
                    'instrument_preservation_verified': None, 'final_safe_area_verified': None},
                'reason_codes': list((row.get('decision') or {}).get('reasons') or []),
                'review_reasons': evidence_missing, 'review_required': True})
    return {'schema_version': '1.0', 'producer': 'ldporto.camera_handoff',
        'camera_engine': 'ldporto.camera_director', 'geometry_contract': 'normalized_source_coordinates',
        'renderer_owner': 'VIDEO_CURATOR', 'applies_to': ['REEL', 'STORY'],
        'available_composition_intents': list(COMPOSITION_MODES),
        'source_intervals': selected, 'segments': segments, 'timeline_sha256': digest(timeline),
        'fallback': {'composition': 'SOURCE_FIT_BLUR', 'preserve_entire_source': True,
            'foreground_fit': 'contain', 'background_fit': 'cover_blur', 'distort_source': False,
            'terminal_fallback': 'SOURCE_PRESERVE'},
        'technical_preview_policy': 'existing_preview_renderer_uses_fit_with_padding',
        'execution_scope': 'recommendation_not_render_or_approval',
        'review_required': True, 'preview_approved': False, 'publish_ready': False}
