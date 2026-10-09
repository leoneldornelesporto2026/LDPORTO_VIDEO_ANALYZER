"""Independent checks against frames of a rendered technical preview."""
from pathlib import Path
import json
import math
import shutil
import subprocess
from .core import ok, finite_or_none
from .media_runtime import find_media_tool


def zoom_diagnostics(timeline, duration=None, min_zoom_duration=6.):
    events, samples = [], []
    target_loss = upscale_violations = 0
    for row in timeline or []:
        keys = (row.get('camera') or {}).get('keyframes', [])
        samples.extend((key.get('time', row['start']), float(key.get('zoom', 1))) for key in keys)
        # A state/request is not delivered motion. Count only observed zoom deltas.
        if row.get('camera_mode') in {'SMART_ZOOM_IN', 'SMART_ZOOM_OUT'} and keys and max(float(k.get('zoom', 1)) for k in keys) - min(float(k.get('zoom', 1)) for k in keys) > .001:
            events.append(row)
        target_loss += int('TARGET_LOST_DURING_ZOOM' in (row.get('decision') or {}).get('reasons', []))
        crop = row.get('crop') or {}
        ratio = crop.get('upscale_ratio')
        upscale_violations += int(isinstance(ratio, (int, float)) and ratio > crop.get('max_upscale_ratio', 2.) + 1e-6)
    samples = sorted(set(samples))
    directions = []
    slopes = []
    for (before_time, before), (after_time, after) in zip(samples, samples[1:]):
        if after_time <= before_time:
            continue
        delta = after - before
        slopes.append(delta / (after_time - before_time))
        if abs(delta) >= .015:
            directions.append((after_time, 1 if delta > 0 else -1))
    reversals = sum(first[1] != second[1] and second[0] - first[0] < min_zoom_duration + 1
                    for first, second in zip(directions, directions[1:]))
    short = sum(row['end'] - row['start'] < min_zoom_duration - .5 for row in events)
    duration = duration or max((row['end'] for row in timeline or []), default=0)
    metrics = {'zoom_event_count': len(events), 'zoom_events_per_minute': len(events) * 60 / duration if duration else None,
               'mean_zoom_factor': sum((float((r.get('camera') or {}).get('zoom_start', 1)) + float((r.get('camera') or {}).get('zoom_end', 1))) / 2 * (r['end'] - r['start']) for r in timeline or []) / duration if duration else None,
               'max_zoom_factor': max((z for _, z in samples), default=1.),
               'short_zoom_count': short, 'rapid_zoom_reversal_count': reversals,
               'zoom_pumping_score': reversals / max(1, len(directions)),
               'zoom_jitter_score': sum(abs(second - first) for first, second in zip(slopes, slopes[1:])) / max(1, len(slopes) - 1),
               'zoom_target_loss_count': target_loss, 'upscale_limit_violation_count': upscale_violations,
               'zoom_metrics_method': 'delivered_keyframe_temporal_diagnostics_not_perceptual_accuracy'}
    issues = []
    for count, kind in ((short, 'SHORT_ZOOM'), (reversals, 'ZOOM_PUMPING'), (target_loss, 'ZOOM_TARGET_LOST'), (upscale_violations, 'UPSCALE_LIMIT_VIOLATION')):
        if count:
            issues.append({'issue_type': kind, 'severity': 'error' if kind in {'ZOOM_TARGET_LOST', 'UPSCALE_LIMIT_VIOLATION'} else 'warning',
                           'evidence': {'count': count}, 'suggested_repair': 'DISABLE_ZOOM_OR_FORCE_SOURCE'})
    return metrics, issues


def border_geometry_evidence(gray, np, *, dark_level=8, min_dark_fraction=.94,
                             min_inner_brightness=34, min_luma_jump=23):
    """Detect geometric matte candidates, not mere dark pixels at frame edges.

    Requires a nearly solid dark stripe and a sharper/brighter neighboring band.
    This is a heuristic candidate, not proof a crop failed. A normal black studio
    background remains unflagged unless a straight rail boundary is visible.
    Pixels alone cannot distinguish a source matte from a rendering defect.
    """
    h, w = gray.shape[:2]
    if min(w, h) < 40:
        return {'possible_padding': False, 'rails': [], 'reason': 'small_frame'}
    rails = []
    unresolved_edge = False
    # Walk inward from all four sides, rather than assuming one bar thickness.
    for side, pixels in [('top', gray), ('bottom', gray[::-1]),
                         ('left', gray.T), ('right', gray.T[::-1])]:
        fractions = np.mean(pixels < dark_level, axis=1)
        limit = max(2, int(len(pixels) * .40))
        depth = 0
        while depth < limit and fractions[depth] >= min_dark_fraction:
            depth += 1
        if depth == 1 or depth >= limit:
            unresolved_edge = True
        if depth < 2 or depth >= limit:
            continue
        outer = pixels[:depth]
        inner = pixels[depth:depth + max(2, min(6, depth))]
        internal_brightness = float(np.median(inner))
        jump = internal_brightness - float(np.median(outer))
        # A straight boundary must have contrast along most of its length.
        # Opposite-axis bars intersect at corners; compare the central span.
        margin = max(1, round(pixels.shape[1] * .10))
        boundary_fraction = float(np.mean(
            np.median(inner[:, margin:-margin], axis=0) -
            np.median(outer[:, margin:-margin], axis=0) >= min_luma_jump))
        if internal_brightness >= min_inner_brightness and jump >= min_luma_jump and boundary_fraction >= .90:
            rails.append({'side': side, 'width_px': depth,
                          'width_fraction': round(depth / len(pixels), 5),
                          'dark_fraction': round(float(np.mean(outer < dark_level)), 3),
                          'boundary_fraction': round(boundary_fraction, 3),
                          'inner_median': round(internal_brightness, 1), 'luma_jump': round(jump, 1)})
    return {'possible_padding': bool(rails), 'rails': rails,
            'reason': 'hard_dark_rail_with_interior_contrast' if rails else (
                'ambiguous_edge_geometry' if unresolved_edge else
                'insufficient_luminance' if float(np.percentile(gray, 95)) < min_inner_brightness else 'no_geometric_bar_evidence')}


def _border_crop_context(row, timestamp, expected, width, height):
    """Use the same effective transform as the technical renderer; no source inference."""
    from .preview_renderer import _interpolate_keyframes
    sw, sh = expected.get('source_width'), expected.get('source_height')
    known_size = all(isinstance(v, (int, float)) and math.isfinite(v) and v > 0 for v in (sw, sh))
    rect = None
    if row and row.get('layout') != 'full_frame':
        if row.get('layout') == 'split_candidate' and row.get('split'):
            return {'mode': 'split', 'effective_crop': None, 'expected_rails_px': None}
        if known_size:
            rect = _interpolate_keyframes(row, timestamp, sw, sh, width, height)
        elif not (row.get('camera') or {}).get('keyframes'):
            rect = (row.get('crop') or {}).get('rect_end')
        else:
            return {'mode': 'unknown', 'effective_crop': None, 'expected_rails_px': None}
    if rect:
        return {'mode': 'crop_resize', 'effective_crop': rect,
                'expected_rails_px': dict.fromkeys(('top', 'bottom', 'left', 'right'), 0)}
    padding = None
    if known_size:
        scale = min(width / sw, height / sh)
        nw, nh = max(1, round(sw * scale)), max(1, round(sh * scale))
        x, y = (width - nw) // 2, (height - nh) // 2
        padding = {'left': x, 'right': width - nw - x, 'top': y, 'bottom': height - nh - y}
    return {'mode': 'fit_with_padding', 'effective_crop': None, 'expected_rails_px': padding}


def border_temporal_report(samples):
    """Proved refers to recurring geometric rails, never their source/render origin."""
    unexpected, intended = [], []
    for sample in samples:
        padding = sample['crop_context']['expected_rails_px']
        for rail in sample['rails']:
            entry = {**rail, 'frame': sample['frame'], 'time': sample['time'],
                     'crop_context': sample['crop_context'], 'segment': sample['segment']}
            if padding is not None and padding[rail['side']] > 0 and abs(rail['width_px'] - padding[rail['side']]) <= 2:
                intended.append(entry)
            else:
                unexpected.append(entry)
    stable = {}
    # Match width, transform mode and segment; retain the effective crop per sample.
    for entry in unexpected:
        matches = [r for r in unexpected if r['side'] == entry['side'] and
                   abs(r['width_px'] - entry['width_px']) <= 2 and
                   r['crop_context']['mode'] == entry['crop_context']['mode'] and
                   r['segment'] == entry['segment']]
        if len(matches) >= 3:
            stable[entry['side']] = max(stable.get(entry['side'], 0), len(matches))
    pairs = [('top', 'bottom'), ('left', 'right')]
    paired = False
    for a, b in pairs:
        for entry in unexpected:
            if entry['side'] != a:
                continue
            frames = {x['frame'] for x in unexpected if x['side'] == a and
                      x['segment'] == entry['segment'] and abs(x['width_px'] - entry['width_px']) <= 2}
            opposite = {x['frame'] for x in unexpected if x['side'] == b and
                        x['segment'] == entry['segment'] and abs(x['width_px'] - entry['width_px']) <= 2}
            paired |= len(frames & opposite) >= 3
    insufficient = len(samples) < 3 or any(s['reason'] in (
        'small_frame', 'insufficient_luminance', 'ambiguous_edge_geometry') for s in samples)
    state = ('proved' if paired else 'borderline') if unexpected else ('unknown' if insufficient else 'clear')
    return {'status': state, 'proof_scope': 'sampled_recurring_bar_geometry_only_not_render_origin',
            'render_origin_proved': None, 'review_required': bool(unexpected) or insufficient,
            'sampled_frames': len(samples), 'stable_sides': sorted(stable),
            'matching_frame_counts': stable, 'unexpected_rail_samples': len(unexpected),
            'expected_padding_rail_samples': len(intended),
            'samples': samples, 'preview_approved': None, 'publish_ready': False}


def _ffprobe(path):
    exe = find_media_tool('ffprobe')
    if not exe:
        return None
    proc = subprocess.run([exe, '-v','error','-show_streams','-show_format','-of','json',str(path)],
                          capture_output=True,text=True,encoding='utf-8',errors='replace',shell=False,timeout=30)
    if proc.returncode:
        return None
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError:
        return None


def verify_preview(path, expected=None, timeline=None, severity_thresholds=None):
    try:
        import cv2
        import numpy as np
    except ImportError as exc:
        return ok({'preview': str(Path(path).resolve()), 'border_report': border_temporal_report([]),
                   'preview_approved': None, 'publish_ready': False}, 'unavailable', [f'OpenCV/Numpy indisponível no Preview Verifier: {exc}'])
    path = Path(path)
    if not path.is_file():
        return ok({'preview': str(path.resolve()), 'border_report': border_temporal_report([]),
                   'preview_approved': None, 'publish_ready': False},
                  'unavailable', ['Preview renderizado não encontrado.'])
    expected = expected or {}
    thresholds = {'border_fraction': .12, 'edge_face_margin': .015, 'face_width_fraction': .75,
                  'max_flow_px_per_second': 900., 'duration_tolerance': .25, 'av_sync_tolerance': .20}
    thresholds.update(severity_thresholds or {})
    cap = cv2.VideoCapture(str(path))
    # Generated by GitHub Copilot - Oct-05-2026
    if not cap.isOpened():
        cap.release()
        return ok({'schema_version':'1.0', 'issues':[{'severity':'error', 'issue_type':'UNDECODABLE_PREVIEW'}],
                   'verifier_uses_rendered_frames':False, 'sampled_frames':0,
                   'border_report': border_temporal_report([]), 'preview_approved': None, 'publish_ready': False}, 'unavailable')
    width, height = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = float(cap.get(cv2.CAP_PROP_FPS) or expected.get('fps') or 25.)
    frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    duration = frame_count/fps if fps > 0 else None
    issues, sampled, flow_peak = [], 0, 0.0
    face_frames, clipped_frames, focused_frames, focused_face_frames = 0, 0, 0, 0
    face_sizes, headrooms = [], []
    face = cv2.CascadeClassifier(cv2.data.haarcascades+'haarcascade_frontalface_default.xml')
    previous = None
    border_candidates = []
    stride = max(1, round(fps/5))
    index = 0
    try:
        while True:
            got, frame = cap.read()
            if not got:
                break
            if index % stride:
                index += 1
                continue
            sampled += 1
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            source_time = expected.get('source_start', 0) + index / fps
            source_row = next((row for row in timeline or [] if row['start'] <= source_time < row['end']), {})
            geometry_evidence = border_geometry_evidence(gray, np)
            border_candidates.append({'frame': index, 'time': round(source_time, 4),
                                      'segment': [source_row.get('start'), source_row.get('end')],
                                      'rails': geometry_evidence['rails'], 'reason': geometry_evidence['reason'],
                                      'crop_context': _border_crop_context(source_row, source_time, expected, width, height)})
            faces = face.detectMultiScale(gray, 1.1, 5, minSize=(24,24)) if not face.empty() else []
            face_frames += int(len(faces) > 0)
            focused_frames += int(bool(source_row.get('focus_person')))
            focused_face_frames += int(bool(source_row.get('focus_person')) and len(faces) > 0)
            for face_x, face_y, face_width, face_height in faces:
                face_sizes.append(float(face_height / height))
                headrooms.append(float(face_y / height))
                margin = thresholds['edge_face_margin']
                if (face_x/width < margin or face_y/height < margin or
                        (face_x+face_width)/width > 1-margin or (face_y+face_height)/height > 1-margin):
                    clipped_frames += 1
                    issues.append({'interval': None, 'severity':'error', 'issue_type':'FACE_OR_HEAD_CLIPPED',
                                   'evidence': {'frame':index,'bbox':[int(face_x),int(face_y),int(face_width),int(face_height)]},
                                   'suggested_repair':'REDUCE_ZOOM_OR_FORCE_SOURCE'})
                if face_width/width > thresholds['face_width_fraction']:
                    issues.append({'interval':None,'severity':'warning','issue_type':'EXCESSIVE_ZOOM',
                                   'evidence':{'frame':index,'face_width_fraction':float(face_width/width)},
                                   'suggested_repair':'REDUCE_ZOOM'})
            small = cv2.resize(gray, (160, max(1, round(160*height/width))))
            if previous is not None:
                flow = cv2.calcOpticalFlowFarneback(previous, small, None, .5, 3, 15, 3, 5, 1.2, 0)
                magnitude = np.sqrt(flow[...,0]**2+flow[...,1]**2)
                px_per_second = float(np.median(magnitude)) * fps / stride * (width/160)
                flow_peak = max(flow_peak, px_per_second)
                if px_per_second > thresholds['max_flow_px_per_second']:
                    issues.append({'interval':None,'severity':'warning','issue_type':'EXCESSIVE_MOTION',
                                   'evidence':{'frame':index,'estimated_flow_px_per_second':px_per_second},
                                   'suggested_repair':'INCREASE_DAMPING_OR_FORCE_SOURCE'})
            previous = small
            index += 1
    finally:
        cap.release()
    border_report = border_temporal_report(border_candidates)
    if border_report['review_required']:
        issues.append({'interval': None, 'severity': 'warning',
                       'issue_type': 'UNEXPECTED_BORDER' if border_report['stable_sides'] else 'BORDER_REVIEW_REQUIRED',
                       'evidence': {'detector': 'four_side_width_crop_temporal_v3',
                                    'status': border_report['status'],
                                    'sides': border_report['stable_sides'],
                                    'matching_frame_counts': border_report['matching_frame_counts'],
                                    'sampled_frames': sampled},
                       'suggested_repair': 'REVIEW_SOURCE_MATTE_AND_EFFECTIVE_CROP_BEFORE_APPROVAL'})
    if not sampled:
        issues.append({'interval':None,'severity':'error','issue_type':'NO_RENDERED_FRAMES'})
    if focused_frames and not focused_face_frames:
        issues.append({'interval':None, 'severity':'warning', 'issue_type':'TARGET_VISIBILITY_UNVERIFIED',
                       'evidence':{'focused_samples': focused_frames, 'detected_face_samples': 0},
                       'suggested_repair':'REVIEW_OR_FORCE_SOURCE'})
    start = expected.get('source_start', 0)
    selected_timeline = [row for row in timeline or [] if row['start'] < start + (duration or 0) and row['end'] > start]
    zoom_metrics, zoom_issues = zoom_diagnostics(selected_timeline, duration,
                                                expected.get('min_zoom_duration', 6.))
    issues.extend(zoom_issues)
    if expected.get('width') and width != int(expected['width']) or expected.get('height') and height != int(expected['height']):
        issues.append({'interval':None,'severity':'error','issue_type':'OUTPUT_DIMENSIONS',
                       'evidence':{'actual':[width,height],'expected':[expected.get('width'),expected.get('height')]},
                       'suggested_repair':'RERENDER_EXPECTED_DIMENSIONS'})
    if expected.get('duration') is not None and duration is not None and abs(duration-float(expected['duration'])) > thresholds['duration_tolerance']:
        issues.append({'interval':None,'severity':'error','issue_type':'DURATION_MISMATCH',
                       'evidence':{'actual':duration,'expected':float(expected['duration'])},
                       'suggested_repair':'RERENDER_INTERVAL'})
    probe = _ffprobe(path)
    av_delta = None
    if probe:
        streams = probe.get('streams', [])
        vd = [float(s['duration']) for s in streams if s.get('codec_type')=='video' and s.get('duration')]
        ad = [float(s['duration']) for s in streams if s.get('codec_type')=='audio' and s.get('duration')]
        if vd and ad:
            av_delta = abs(vd[0]-ad[0])
            if av_delta > thresholds['av_sync_tolerance']:
                issues.append({'interval':None,'severity':'warning','issue_type':'AV_DURATION_DELTA',
                               'evidence':{'seconds':av_delta},'suggested_repair':'REMUX_AUDIO'})
    # Deduplicate repeated issue types while keeping worst/first concrete evidence.
    order = {'info':0,'warning':1,'error':2,'critical':3}
    unique = {}
    for issue in issues:
        key = issue['issue_type']
        if key not in unique or order.get(issue['severity'],0) > order.get(unique[key]['severity'],0):
            unique[key] = issue
    issues = list(unique.values())
    status = 'partial' if issues else 'ok'
    return ok({'schema_version':'1.0','preview':str(path.resolve()),'sampled_frames':sampled,
               **zoom_metrics,
               'face_visible_fraction': face_frames / sampled if sampled else None,
               'target_visible_fraction': None,
               'target_visibility_reason': 'generic_face_detector_cannot_verify_person_identity',
               'focused_frame_face_presence_fraction': focused_face_frames / focused_frames if focused_frames else None,
               'mean_face_size': sum(face_sizes) / len(face_sizes) if face_sizes else None,
               'mean_headroom': sum(headrooms) / len(headrooms) if headrooms else None,
               'edge_cutoff_count': clipped_frames,
               'border_detector_method': 'contrast_and_temporal_bar_geometry_v2',
               # Legacy identifier retained for existing consumers; precise method follows.
               'border_geometry_method': 'four_side_width_crop_temporal_v3',
               'border_report': border_report, 'preview_approved': None, 'publish_ready': False,
               'unconfirmed_border_candidates': sum(bool(s['rails']) for s in border_candidates),
               'output_dimensions':[width,height],'duration':finite_or_none(duration),
               'av_duration_delta':finite_or_none(av_delta),'estimated_pan_flow_peak_px_per_second':finite_or_none(flow_peak),
               'issues':issues,'issue_count':len(issues),'verifier_uses_rendered_frames':True,
               'safe_area_approved':None, 'safe_area_validation_scope':'technical_camera_preview_without_social_overlays',
               'social_safe_area_post_render_validation_required':True}, status,
              ['Face clipping depende do detector visual disponível; ausência de detecção não prova ausência de erro.'])


def conservative_repair(timeline, validation):
    """One bounded closed-loop repair: severe crop errors fall back to source."""
    from copy import deepcopy
    severe = {issue.get('issue_type') for issue in validation.get('issues', [])}
    repairable = severe & {'FACE_OR_HEAD_CLIPPED', 'EXCESSIVE_ZOOM', 'SHORT_ZOOM', 'ZOOM_PUMPING', 'ZOOM_TARGET_LOST', 'UPSCALE_LIMIT_VIOLATION', 'TARGET_VISIBILITY_UNVERIFIED'}
    if not repairable:
        return list(timeline), []
    out, repaired = [], []
    for row in timeline:
        new = deepcopy(row)
        affected = [issue for issue in validation.get('issues', []) if issue.get('issue_type') in repairable and
                (not issue.get('interval') or row['start'] < issue['interval'][1] and row['end'] > issue['interval'][0])]
        if row.get('layout') != 'full_frame' and affected:
            new['layout'] = 'full_frame'
            new['focus_person'] = None
            new['split'] = None
            new['camera_mode'] = 'SOURCE_PRESERVE'
            new['zoom_mode'] = 'SOURCE_PRESERVE'
            if new.get('camera'):
                new['camera'].update(zoom_start=1., zoom_end=1., zoom_target=1., movement_style='hold', tracking_mode='source_preserve')
                for key in new['camera'].get('keyframes', []):
                    key.update(zoom=1., target=[.5, .5, 1.], center=[.5, .5], velocity=[0., 0., 0.], acceleration=[0., 0., 0.])
            new['crop'] = {**(row.get('crop') or {}), 'safe': False, 'rect_end': None,
                           'full_frame_policy':'fit_with_padding'}
            new['repair'] = {'origin':'preview_verifier','action':'conservative_source_fallback',
                             'reason_codes':sorted(repairable)}
            repaired.append(row.get('director_id'))
        out.append(new)
    return out, repaired
