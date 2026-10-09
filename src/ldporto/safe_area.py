"""Provisional overlay geometry. Never certifies an uninspected social render."""
import math
from .preview_renderer import _interpolate_keyframes


def rect(value):
    try:
        result = {k: float(value[k]) for k in ('x', 'y', 'width', 'height')}
    except (TypeError, KeyError, ValueError, OverflowError):
        return None
    if not all(math.isfinite(v) for v in result.values()):
        return None
    if (result['x'] < 0 or result['y'] < 0 or result['width'] <= 0 or result['height'] <= 0
            or result['x'] + result['width'] > 1.000001
            or result['y'] + result['height'] > 1.000001):
        return None
    return result


def intersects(a, b, margin=.012):
    return (a['x'] < b['x'] + b['width'] + margin
            and b['x'] < a['x'] + a['width'] + margin
            and a['y'] < b['y'] + b['height'] + margin
            and b['y'] < a['y'] + a['height'] + margin)


def _project(box, crop):
    left, top = max(box['x'], crop['x']), max(box['y'], crop['y'])
    right = min(box['x'] + box['width'], crop['x'] + crop['width'])
    bottom = min(box['y'] + box['height'], crop['y'] + crop['height'])
    if right <= left or bottom <= top:
        return None
    return dict(x=(left-crop['x'])/crop['width'], y=(top-crop['y'])/crop['height'],
                width=(right-left)/crop['width'], height=(bottom-top)/crop['height'])


def _transform(box, row, time, metadata, profile):
    if row.get('split'):
        return None, 'split_geometry_requires_final_compositor'
    try:
        sw, sh = float(metadata['width']), float(metadata['height'])
        tw, th = profile['width'], profile['height']
        if min(sw, sh) <= 0 or not math.isfinite(sw + sh):
            raise ValueError
        if row.get('layout') == 'full_frame' or (row.get('crop') or {}).get('full_frame_policy') == 'fit_with_padding':
            scale = min(tw/sw, th/sh)
            fw, fh = sw*scale/tw, sh*scale/th
            return dict(x=(1-fw)/2+box['x']*fw, y=(1-fh)/2+box['y']*fh,
                        width=box['width']*fw, height=box['height']*fh), None
        for key in (row.get('camera') or {}).get('keyframes', []):
            center = key.get('center') or [.5, .5]
            if (len(center) != 2 or not all(math.isfinite(float(v)) for v in center)
                    or not all(0 <= float(v) <= 1 for v in center)
                    or not math.isfinite(float(key.get('zoom', 1)))
                    or float(key.get('zoom', 1)) < 1):
                return None, 'crop_or_source_geometry_missing_or_invalid'
        crop = rect(_interpolate_keyframes(row, time, sw, sh, tw, th))
        if crop:
            return _project(box, crop), None
    except (TypeError, ValueError, KeyError, OverflowError, ZeroDivisionError):
        pass
    return None, 'crop_or_source_geometry_missing_or_invalid'


def _observed_in(value, start, end):
    return isinstance(value, (int, float)) and math.isfinite(value) and start <= value < end


def plan_safe_area(analysis, candidate, profile, preferred_caption, title_rect):
    """Use all sampled faces/GC/OCR per camera interval, without interpolating faces.

    Keep one pair for the whole cut when possible to avoid text motion on payoff.
    Confidence is the minimum supplied evidence confidence, never an accuracy score.
    Missing samples, split panels and unknown geometry require manual review.
    """
    start, end = candidate['start'], candidate['end']
    rows = [r for r in analysis.get('camera_timeline') or [] if r['start'] < end and r['end'] > start]
    boundaries = sorted({start, end} | {max(start, r['start']) for r in rows} | {min(end, r['end']) for r in rows})
    segments, all_obstacles, all_reasons, confidences = [], [], [], []
    for a, b in zip(boundaries, boundaries[1:]):
        covering = [r for r in rows if r['start'] <= a and r['end'] >= b]
        row = covering[0] if len(covering) == 1 else {}
        reasons, obstacles, evidence = [], [], []
        if len(covering) != 1:
            reasons.append('camera_interval_missing_or_ambiguous')
        faces = [o for o in analysis.get('people_observations') or [] if _observed_in(o.get('time'), a, b)]
        if not faces or not any(o.get('face_bbox') for o in faces):
            reasons.append('face_geometry_missing_not_proof_of_absence')
        evidence.extend(('face', o.get('face_bbox'), o.get('time'), o.get('confidence')) for o in faces)
        for g in (analysis.get('broadcast_graphics') or {}).get('intervals', []):
            if g['start'] < b and g['end'] > a:
                for region in g.get('regions') or []:
                    try:
                        box = dict(x=region['x_start'], y=region['y_start'],
                                   width=region['x_end']-region['x_start'], height=region['y_end']-region['y_start'])
                    except (KeyError, TypeError):
                        box = None
                    # Region interval does not prove continuity between sampled frames.
                    evidence.append(('gc', box, None, region.get('confidence')))
        for o in (analysis.get('commercial_visual_s8') or {}).get('texts', []):
            if _observed_in(o.get('observed_at'), a, b) and (not o.get('moment_id') or o['moment_id'] == candidate['candidate_id']):
                evidence.append(('ocr', o.get('bbox'), o['observed_at'], o.get('confidence')))
        if not any(kind in ('gc', 'ocr') for kind, *_ in evidence):
            reasons.append('overlay_geometry_unobserved_not_proof_of_absence')
        for kind, raw, time, confidence in evidence:
            box = rect(raw)
            if not box:
                reasons.append(kind + '_geometry_missing_or_invalid')
                continue
            # GC has interval geometry: conservatively test every delivered crop key.
            times = [time] if time is not None else [a, b] + [k['time'] for k in (row.get('camera') or {}).get('keyframes', []) if a < k['time'] < b]
            for t in times:
                transformed, reason = _transform(box, row, t, analysis.get('metadata') or {}, profile)
                if reason:
                    reasons.append(reason)
                elif transformed:
                    obstacles.append({'kind': kind, 'observed_at': time, 'rect': transformed})
            confidences.append(confidence)
        segments.append(dict(start=a, end=b, obstacles=obstacles, geometry_reasons=sorted(set(reasons))))
        all_obstacles.extend(obstacles)
        all_reasons.extend(reasons)
    titles = [('safe_top', title_rect), ('top', dict(x=.10,y=.04,width=.80,height=.10)),
              ('center_upper', dict(x=.10,y=.46,width=.80,height=.10)),
              ('center_low', dict(x=.10,y=.58,width=.80,height=.10))]
    captions = [('upper_middle', dict(x=.10,y=.18,width=.80,height=.22)),
                ('lower_middle', dict(x=.10,y=.62,width=.80,height=.20)),
                ('top', dict(x=.10,y=.04,width=.80,height=.12)),
                ('center_low', dict(x=.10,y=.58,width=.80,height=.12)),
                ('bottom', dict(x=.10,y=.80,width=.80,height=.12))]
    captions.sort(key=lambda r: r[0] != preferred_caption)
    clear = lambda box: not any(intersects(box, o['rect']) for o in all_obstacles)
    pair = next(((tn, tr, cn, cr) for tn, tr in titles for cn, cr in captions
                 if clear(tr) and clear(cr) and not intersects(tr, cr)), None)
    reasons = sorted(set(all_reasons))
    if not pair:
        reasons.append('no_joint_title_caption_zone_manual_layout_required')
    elif pair[0] != 'safe_top' or pair[2] != preferred_caption:
        reasons.append('observed_face_gc_or_title_caption_conflict_reposition_required')
    numeric = all(isinstance(c, (int, float)) and not isinstance(c, bool) and math.isfinite(c) and 0 <= c <= 1 for c in confidences)
    confidence = min(confidences) if confidences and numeric and not all_reasons and pair else None
    for segment in segments:
        segment.update(title_position=pair[0] if pair else None, title_rect=pair[1] if pair else None,
                       caption_position=pair[2] if pair else None, caption_rect=pair[3] if pair else None,
                       confidence=confidence, safe_area_approved=None,
                       post_render_validation_required=True)
    return dict(segments=segments, confidence=confidence,
                confidence_method='minimum_supplied_evidence_confidence_not_render_safety_probability',
                geometry_scope='sampled_source_boxes_projected_to_output_not_continuous_tracking',
                reposition_required=bool(reasons), reposition_reasons=reasons,
                fallback='manual_layout_and_final_render_review' if all_reasons or not pair else None,
                safe_area_approved=None, post_render_validation_required=True,
                post_render_validation_reason='inspect_final_social_render_faces_gc_text_bounds_and_legibility',
                transition_policy='hold_joint_positions_for_entire_cut_no_text_transition_over_punchline',
                max_title_lines=2, max_caption_lines=2)
