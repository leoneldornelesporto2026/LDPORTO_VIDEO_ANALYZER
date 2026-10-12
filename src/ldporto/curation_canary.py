"""Bounded, non-publishing stage 61 receipt; fixtures never certify real media."""
from copy import deepcopy
import math
from pathlib import Path
import subprocess

from .core import file_hash, digest
from .commercial_gate import targeted_ocr, apply_commercial_refinement, commercial_evidence_state
from .preview_renderer import render_preview, _interpolate_keyframes
from .preview_verifier import verify_preview, zoom_diagnostics
from .safe_area import rect, intersects
from .curator_delivery import overlay_ass, verify_mp4, save_json
from .media_runtime import find_media_tool


def viewport_audit(analysis, candidate, width=1080, height=1920):
    """Project full boxes, never their clipped intersection. Sampled evidence only.

    Head/eyes must be supplied observations, not inferred from a face detector.
    This checks planned geometry and cannot approve encoded text or human review.
    """
    start, end = candidate['start'], candidate['end']
    metadata = analysis.get('metadata') or {}
    rows = analysis.get('camera_director_timeline') or analysis.get('camera_timeline') or []
    samples, reasons = [], set()
    safe = dict(x=.05, y=.05, width=.90, height=.90)
    caption = dict(x=.10, y=.76, width=.80, height=.16)

    def contained(box, region):
        return (box['x'] >= region['x'] and box['y'] >= region['y'] and
                box['x'] + box['width'] <= region['x'] + region['width'] + 1e-6 and
                box['y'] + box['height'] <= region['y'] + region['height'] + 1e-6)

    observations = [('head', o.get('head_bbox'), o.get('time'))
                    for o in analysis.get('people_observations') or []]
    observations += [('eyes', o.get('eyes_bbox'), o.get('time'))
                     for o in analysis.get('people_observations') or []]
    observations += [('text', o.get('bbox'), o.get('observed_at'))
                     for o in (analysis.get('commercial_visual_s8') or {}).get('texts', [])]
    observations += [('gc_or_qr', r.get('bbox'), r.get('observed_at', g.get('observed_at')))
                     for g in (analysis.get('broadcast_graphics') or {}).get('intervals', [])
                     for r in g.get('regions', [])]
    for kind, raw, time in observations:
        if not isinstance(time, (int, float)) or not math.isfinite(time) or not start <= time < end:
            continue
        box = rect(raw)
        matching = [r for r in rows if r['start'] <= time < r['end']]
        if box is None or len(matching) != 1:
            reasons.add('VIEWPORT_GEOMETRY_UNMEASURED')
            continue
        row = matching[0]
        sw, sh = metadata.get('width'), metadata.get('height')
        if not sw or not sh or row.get('split'):
            reasons.add('VIEWPORT_GEOMETRY_UNMEASURED')
            continue
        if row.get('layout') == 'full_frame':
            scale = min(width/sw, height/sh)
            fw, fh = sw*scale/width, sh*scale/height
            projected = dict(x=(1-fw)/2+box['x']*fw, y=(1-fh)/2+box['y']*fh,
                             width=box['width']*fw, height=box['height']*fh)
            crop = dict(x=0, y=0, width=1, height=1)
        else:
            crop = rect(_interpolate_keyframes(row, time, sw, sh, width, height))
            if crop is None:
                reasons.add('VIEWPORT_GEOMETRY_UNMEASURED')
                continue
            projected = dict(x=(box['x']-crop['x'])/crop['width'],
                             y=(box['y']-crop['y'])/crop['height'],
                             width=box['width']/crop['width'], height=box['height']/crop['height'])
        inside = contained(projected, safe)
        conflict = intersects(projected, caption)
        samples.append(dict(kind=kind, source_time=time, source_box=box, source_crop=crop,
                            output_box=projected, inside_safe_area=inside, caption_conflict=conflict))
        if not inside:
            reasons.add('FACE_OR_HEAD_CLIPPED' if kind in ('head', 'eyes') else 'TEXT_OR_GC_CLIPPED')
        if conflict:
            reasons.add('CAPTION_OBSTACLE_CONFLICT')
    for kind in ('head', 'eyes', 'text', 'gc_or_qr'):
        if not any(s['kind'] == kind for s in samples):
            reasons.add(kind.upper() + '_NOT_MEASURED')
    return dict(source_dimensions=[metadata.get('width'), metadata.get('height')],
                output_dimensions=[width, height], safe_rect=safe, proposed_caption_rect=caption,
                samples=samples, reason_codes=sorted(reasons),
                scope='sampled_source_projection_not_encoded_or_continuous_safety',
                preview_approved=False if 'FACE_OR_HEAD_CLIPPED' in reasons else None,
                safe_area_approved=None, publish_ready=False)


def run_real_canary(analysis, source, candidate_id, output, *, authorized=False, ocr_config=None):
    """Only a supplied short source, exact hash and explicit opt-in can render.

    No ASR, models, publishing, automatic approval or package generation.
    Analysis stays unchanged; output directory must be new.
    """
    report = dict(schema_version='1.0', evidence_kind='real_short_media',
                  unit_fixture_pass=None, real_canary_status='real_canary_not_run',
                  human_approved=False, preview_approved=None, publication_ready=False,
                  publish_ready=False, reason_codes=[], source_sha256=None)
    if not authorized:
        report['reason_codes'] = ['SHORT_MEDIA_AUTHORIZATION_REQUIRED']
        return report
    source = Path(source)
    if not source.is_file():
        report['reason_codes'] = ['SOURCE_MEDIA_MISSING']
        return report
    actual = file_hash(source)
    if actual != (analysis.get('metadata') or {}).get('sha256'):
        report['reason_codes'] = ['SOURCE_HASH_MISMATCH']
        return report
    report['source_sha256'] = actual
    moments = [m for m in analysis.get('main_moments', []) if m.get('moment_id') == candidate_id]
    if len(moments) != 1:
        report['reason_codes'] = ['CANDIDATE_MISSING_OR_AMBIGUOUS']
        return report
    moment = moments[0]
    start, end = moment['ideal_start'], moment['ideal_end']
    duration = (analysis.get('metadata') or {}).get('duration')
    if not all(isinstance(v, (int, float)) and math.isfinite(v) for v in (start, end, duration)) or not (
            0 <= start < end <= duration <= 30 and 10 <= end-start <= 30):
        report['reason_codes'] = ['SHORT_SOURCE_AND_10_TO_30_SECONDS_REQUIRED']
        return report
    # Validate real container duration too, before generating any MP4.
    from .curator_delivery import probe
    try:
        info = probe(source)
    except (RuntimeError, ValueError, OSError, subprocess.TimeoutExpired) as exc:
        report.update(real_canary_status='real_canary_fail', reason_codes=[str(exc)])
        return report
    if not 10 <= info['duration'] <= 30.35 or end > info['duration'] + .05:
        report['reason_codes'] = ['SOURCE_DURATION_MISMATCH']
        return report
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    data = deepcopy(analysis)
    cfg = {**(ocr_config or {}), 'enabled': True}
    visual = targeted_ocr(source, [moment], cfg, limit=1)
    data['commercial_visual_s8'] = visual
    data.setdefault('stage_status', {})['17c_commercial_visual'] = {
        'status': visual['status'], 'reason': visual.get('reason'),
        'measured_frames': visual.get('measured_frames', 0)}
    from .second_curation import build_second_curation_package, validate_references, _understanding_integrity
    from .integrity_contracts import candidate_review_invariants, human_review_queue
    refinement = apply_commercial_refinement(data, data.get('transcript_segments', []),
        visual.get('texts', []), {}, commercial_visual=visual, graphics=data.get('broadcast_graphics'))
    data.update(refinement)
    catalog = build_second_curation_package(data)
    selected = next(c for c in catalog['candidates'] if c['candidate_id'] == candidate_id)
    from .second_curation_export import _final_commercial_classification
    selected['commercial_evidence_state'] = commercial_evidence_state(data, candidate_id)
    selected['commercial_classification'] = _final_commercial_classification(selected)
    refs = validate_references(data, catalog)
    selected.update(candidate_review_invariants(data, selected, refs['status'] == 'resolved',
                                                _understanding_integrity(data)[0]))
    queue = human_review_queue([selected])
    report.update(analysis_sha256=digest(analysis), candidate_id=candidate_id,
                  source_interval=dict(start=start, end=end), ocr=visual,
                  commercial=selected['commercial_classification'],
                  human_review_provisional=selected['human_review_provisional'],
                  human_review_queue=queue['candidate_ids'], review_queue=queue)
    if (selected['commercial_classification'] or {}).get('eligibility') == 'excluded':
        report.update(real_canary_status='real_canary_fail', human_review_queue=[],
                      reason_codes=['EXPLICIT_COMMERCIAL_EXCLUDED'])
        save_json(output/'CANARY61.json', report)
        return report
    rows = data.get('camera_director_timeline') or data.get('camera_timeline') or [
        dict(start=start, end=end, layout='full_frame')]
    data['camera_director_timeline'] = rows
    report['viewport'] = viewport_audit(data, dict(start=start, end=end))
    try:
        if not selected['eligible_for_human_review']:
            raise RuntimeError('CANDIDATE_NOT_ELIGIBLE_FOR_PROVISIONAL_REVIEW')
        if file_hash(source) != actual:
            raise RuntimeError('SOURCE_HASH_MISMATCH')
        rendered = render_preview(source, rows, data['metadata'], output/'camera.mp4',
                                  dict(start=start, end=end), 1080, 1920)
        report['render'] = rendered
        if rendered['status'] != 'ok':
            raise RuntimeError('CAMERA_RENDER_UNAVAILABLE')
        clip = dict(duration=end-start, segments=[dict(start=max(0, s['start']-start),
                    end=min(end-start, s['end']-start), text=s['text'])
                    for s in data.get('transcript_segments', []) if s['start'] < end and s['end'] > start])
        overlay_ass(clip, output/'captions.ass', include_draft=True)
        ffmpeg = find_media_tool('ffmpeg')
        if not ffmpeg:
            raise RuntimeError('FFMPEG_UNAVAILABLE')
        proc = subprocess.run([ffmpeg, '-hide_banner', '-loglevel', 'error', '-nostdin',
            '-i', 'camera.mp4', '-vf', 'ass=captions.ass', '-c:v', 'libx264', '-threads', '2',
            '-preset', 'veryfast', '-c:a', 'aac', '-t', str(end-start), 'preview.mp4'],
            cwd=output.resolve(), capture_output=True, timeout=120, shell=False)
        report['ffmpeg_exit_code'] = proc.returncode
        if proc.returncode:
            raise RuntimeError('FFMPEG_RENDER_FAILED')
        technical = verify_mp4(output/'preview.mp4', end-start)
        validation = verify_preview(output/'preview.mp4',
            dict(source_start=start, duration=end-start, source_width=info['width'], source_height=info['height']), rows)
        rendered_ocr = targeted_ocr(output/'preview.mp4', [dict(moment_id=candidate_id,
            ideal_start=0, ideal_end=end-start)], cfg, limit=1)
        report.update(technical=technical, validation=validation, rendered_ocr=rendered_ocr,
                      draft_captions=True, speech_timestamps=clip['segments'],
                      listening_verified=None, text_legibility_verified=None,
                      caption_sha256=file_hash(output/'captions.ass'),
                      zoom_proposed=zoom_diagnostics(rows)[0]['zoom_event_count'],
                      zoom_encoded_motion=rendered['data'].get('rendered_motion', []))
        failures = set(report['viewport']['reason_codes'])
        if file_hash(source) != actual:
            failures.add('SOURCE_HASH_MISMATCH')
        if [info['width'], info['height']] != [data['metadata'].get('width'), data['metadata'].get('height')]:
            failures.add('SOURCE_GEOMETRY_MISMATCH')
        if technical['status'] == 'BLOCKED':
            failures.update(technical['issues'])
        failures.update(i['issue_type'] for i in validation['data'].get('issues', []))
        if visual.get('status') != 'ok' or rendered_ocr.get('status') != 'ok':
            failures.add('OCR_NOT_FULLY_MEASURED')
        # Caption appearance cannot be certified by successful encoding alone.
        report['human_review_requirements'] = ['text_legibility', 'listening', 'editorial', 'commercial', 'crop']
        report.update(real_canary_status='real_canary_fail' if failures else 'real_canary_pass',
                      reason_codes=sorted(failures),
                      preview_approved=False if 'FACE_OR_HEAD_CLIPPED' in failures else None)
    except (RuntimeError, OSError, subprocess.TimeoutExpired) as exc:
        report.update(real_canary_status='real_canary_fail', reason_codes=[str(exc)], preview_approved=False)
    save_json(output/'CANARY61.json', report)
    return report
