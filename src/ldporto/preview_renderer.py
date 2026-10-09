"""Technical Camera Director preview renderer.

This renderer exists to validate camera decisions, not to produce a social-media
final. It consumes the real Director keyframes and can render short canary windows.
"""
from bisect import bisect_right
from pathlib import Path
import math
import shutil
import subprocess
import tempfile
from .core import ok, run_command
from .media_runtime import find_media_tool


def select_canary_intervals(timeline, duration, max_count=6, seconds=4.0):
    """Pick high-risk windows without rendering an entire long video."""
    scored = []
    for row in timeline or []:
        camera = row.get('camera') or {}
        keys = camera.get('keyframes') or []
        zooms = [float(k.get('zoom') or 1.0) for k in keys]
        speeds = [math.hypot(*((k.get('velocity') or [0,0,0])[:2])) for k in keys]
        risk = 0.0
        reasons = []
        if row.get('split'):
            risk += 3; reasons.append('split')
        if row.get('layout') == 'two_shot':
            risk += 2; reasons.append('two_shot')
        if row.get('camera_mode') in {'SMART_ZOOM_IN', 'SMART_ZOOM_OUT'}:
            risk += 4; reasons.append(row['camera_mode'])
        for reason in ('HOOK_EMPHASIS', 'PAYOFF_EMPHASIS', 'SOURCE_ALREADY_CLOSE', 'MICRO_INTERRUPTION_SUPPRESSED'):
            if reason in (row.get('decision') or {}).get('reasons', []):
                risk += 1; reasons.append(reason)
        if row.get('reaction'):
            risk += 2; reasons.append('reaction')
        if row.get('conversation_mode') == 'MONOLOGUE' and row['end'] - row['start'] >= 10:
            risk += .25; reasons.append('long_monologue')
        if max(zooms, default=1) > 1.15:
            risk += 2 + max(zooms)-1.15; reasons.append('zoom')
        if max(speeds, default=0) > .02:
            risk += 2; reasons.append('pan')
        if row.get('focus_confidence') is None or float(row.get('focus_confidence') or 0) < .6:
            risk += 1; reasons.append('low_confidence')
        if (row.get('decision') or {}).get('switch_suppressed'):
            risk += .5; reasons.append('suppressed_switch')
        if (camera.get('transition_in') or '') in ('source_cut','safety_cut','cut'):
            risk += 1; reasons.append(camera.get('transition_in'))
        if risk:
            center = (float(row['start']) + float(row['end']))/2
            start = max(0.0, center-seconds/2)
            end = min(float(duration), start+seconds)
            start = max(0.0, end-seconds)
            scored.append((risk, start, end, reasons))
    # Deterministic risk order and overlap suppression.
    scored.sort(key=lambda x: (-x[0], x[1], x[2], tuple(x[3])))
    chosen = []
    for risk, start, end, reasons in scored:
        if any(max(start,a) < min(end,b) for a,b,_,_ in chosen):
            continue
        chosen.append((start,end,risk,reasons))
        if len(chosen) >= max_count:
            break
    if not chosen and duration > 0:
        chosen.append((0.0, min(float(duration), seconds), 0.0, ['baseline']))
    return [{'start':a,'end':b,'risk_score':r,'reasons':why} for a,b,r,why in sorted(chosen)]


def _fit(frame, width, height, cv2):
    h, w = frame.shape[:2]
    scale = min(width/w, height/h)
    nw, nh = max(1, round(w*scale)), max(1, round(h*scale))
    resized = cv2.resize(frame, (nw, nh), interpolation=cv2.INTER_AREA if scale < 1 else cv2.INTER_LINEAR)
    canvas = __import__('numpy').zeros((height, width, 3), dtype=frame.dtype)
    x, y = (width-nw)//2, (height-nh)//2
    canvas[y:y+nh, x:x+nw] = resized
    return canvas


def _crop(frame, rect, width, height, cv2):
    h, w = frame.shape[:2]
    if not rect:
        return _fit(frame, width, height, cv2)
    x1 = max(0, min(w-1, round(float(rect['x'])*w)))
    y1 = max(0, min(h-1, round(float(rect['y'])*h)))
    x2 = max(x1+1, min(w, round((float(rect['x'])+float(rect['width']))*w)))
    y2 = max(y1+1, min(h, round((float(rect['y'])+float(rect['height']))*h)))
    roi = frame[y1:y2, x1:x2]
    return cv2.resize(roi, (width, height), interpolation=cv2.INTER_AREA if roi.shape[1] > width else cv2.INTER_LINEAR)


def _interpolate_keyframes(row, timestamp, source_w, source_h, target_w, target_h):
    keys = (row.get('camera') or {}).get('keyframes') or []
    if not keys:
        rect = (row.get('crop') or {}).get('rect_end')
        return rect
    times = [float(k.get('time', row['start'])) for k in keys]
    i = max(0, bisect_right(times, timestamp)-1)
    a = keys[i]
    b = keys[min(i+1, len(keys)-1)]
    ta, tb = float(a.get('time', timestamp)), float(b.get('time', timestamp))
    alpha = 0.0 if tb <= ta else max(0.0, min(1.0, (timestamp-ta)/(tb-ta)))
    ac, bc = a.get('center') or [.5,.5], b.get('center') or [.5,.5]
    center = [float(ac[0])+(float(bc[0])-float(ac[0]))*alpha,
              float(ac[1])+(float(bc[1])-float(ac[1]))*alpha]
    zoom = max(1.0, float(a.get('zoom') or 1)+(float(b.get('zoom') or 1)-float(a.get('zoom') or 1))*alpha)
    target_aspect = target_w/target_h
    source_aspect = source_w/source_h
    if source_aspect >= target_aspect:
        base_h, base_w = 1.0, target_aspect/source_aspect
    else:
        base_w, base_h = 1.0, source_aspect/target_aspect
    cw, ch = base_w/zoom, base_h/zoom
    x = max(0.0, min(1.0-cw, center[0]-cw/2))
    y = max(0.0, min(1.0-ch, center[1]-ch/2))
    return {'x':x,'y':y,'width':cw,'height':ch}


def _row_at(timeline, starts, timestamp):
    if not timeline:
        return None
    i = max(0, bisect_right(starts, timestamp)-1)
    row = timeline[min(i, len(timeline)-1)]
    return row if float(row['start'])-1e-6 <= timestamp < float(row['end'])+1e-6 else None


def build_contact_sheet(source, candidate, output, timeline=None):
    import cv2
    import numpy as np
    from .core import stamp
    source, output = Path(source), Path(output)
    if not source.is_file():
        return {'status': 'unavailable', 'reason': 'source_media_unavailable'}
    cap = cv2.VideoCapture(str(source))
    if not cap.isOpened():
        cap.release()
        return {'status': 'unavailable', 'reason': 'source_not_decodable'}
    start, end = candidate['start'], candidate['end']
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.
    source_duration = (cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0) / fps
    times = [start + (end - start) * fraction for fraction in (0., .25, .5, .75, .99)]
    zoom_rows = [row for row in timeline or [] if row['start'] < end and row['end'] > start and row.get('camera_mode') in ('SMART_ZOOM_IN', 'SMART_ZOOM_OUT')]
    times.append((max(start, zoom_rows[0]['start']) + min(end, zoom_rows[0]['end'])) / 2 if zoom_rows else (start + end) / 2)
    canvas = np.full((2 * 206, 3 * 320, 3), 24, dtype=np.uint8)
    frames = []
    timeline = sorted(timeline or [], key=lambda row: row['start'])
    starts = [row['start'] for row in timeline]
    try:
        for index, timestamp in enumerate(times):
            timestamp = max(0., min(timestamp, max(0., source_duration - 1 / fps)))
            cap.set(cv2.CAP_PROP_POS_MSEC, timestamp * 1000)
            got, frame = cap.read()
            if not got or frame.size == 0:
                return {'status': 'unavailable', 'reason': 'candidate_frame_unavailable', 'time': timestamp}
            source_row = _row_at(timeline, starts, timestamp)
            if index and source_row and source_row.get('layout') in ('single_person', 'two_shot'):
                rect = _interpolate_keyframes(source_row, timestamp, frame.shape[1], frame.shape[0], 540, 960)
                frame = _crop(frame, rect, 180, 320, cv2)
            tile = _fit(frame, 320, 180, cv2)
            column, row_index = index % 3, index // 3
            top, left = row_index * 206, column * 320
            canvas[top:top + 180, left:left + 320] = tile
            label = ('source ' if index == 0 else '') + stamp(timestamp)
            cv2.putText(canvas, label, (left + 8, top + 197), cv2.FONT_HERSHEY_SIMPLEX, .43, (230, 230, 230), 1, cv2.LINE_AA)
            frames.append({'time': timestamp, 'camera_mode': (source_row or {}).get('camera_mode', 'SOURCE_PRESERVE')})
    finally:
        cap.release()
    output.parent.mkdir(parents=True, exist_ok=True)
    encoded, image = cv2.imencode('.jpg', canvas, [cv2.IMWRITE_JPEG_QUALITY, 84])
    if not encoded:
        return {'status': 'unavailable', 'reason': 'contact_sheet_encoding_failed'}
    output.write_bytes(image.tobytes())
    return {'status': 'ok', 'frame_count': len(frames), 'frames': frames,
            'source_and_director_framing': True, 'width': 960, 'height': 412}


def render_preview(source, timeline, metadata, output, interval=None, output_width=540, output_height=960):
    try:
        import cv2
    except ImportError as exc:
        return ok({}, 'unavailable', [f'OpenCV indisponível para preview: {exc}'])
    source, output = Path(source), Path(output)
    if not source.is_file():
        return ok({}, 'unavailable', ['Arquivo fonte não está disponível para renderizar preview.'])
    output.parent.mkdir(parents=True, exist_ok=True)
    start = float((interval or {}).get('start', 0.0))
    end = float((interval or {}).get('end', metadata.get('duration') or 0.0))
    if end <= start:
        raise ValueError('Intervalo de preview inválido.')
    cap = cv2.VideoCapture(str(source))
    if not cap.isOpened():
        return ok({}, 'unavailable', ['OpenCV não abriu o vídeo fonte para preview.'])
    fps = float(cap.get(cv2.CAP_PROP_FPS) or metadata.get('fps') or 25.0)
    fps = fps if math.isfinite(fps) and fps > 0 else 25.0
    cap.set(cv2.CAP_PROP_POS_MSEC, start*1000)
    source_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or metadata.get('width') or 1)
    source_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or metadata.get('height') or 1)
    timeline = sorted(timeline or [], key=lambda r: (float(r['start']), float(r['end'])))
    starts = [float(r['start']) for r in timeline]
    with tempfile.TemporaryDirectory(prefix='ldporto_preview_') as td:
        silent = Path(td)/'silent.mp4'
        writer = cv2.VideoWriter(str(silent), cv2.VideoWriter_fourcc(*'mp4v'), fps,
                                 (int(output_width), int(output_height)))
        if not writer.isOpened():
            cap.release()
            return ok({}, 'unavailable', ['OpenCV não abriu VideoWriter para preview.'])
        frame_count = 0
        try:
            while True:
                got, frame = cap.read()
                if not got:
                    break
                pos = cap.get(cv2.CAP_PROP_POS_MSEC)/1000.0
                timestamp = pos if pos > 0 else start + frame_count/fps
                if timestamp < start-1/fps:
                    continue
                if timestamp >= end:
                    break
                rotation = int(round(float(metadata.get('rotation') or 0))) % 360
                # Generated by GitHub Copilot - Oct-05-2026
                if hasattr(cv2,'CAP_PROP_ORIENTATION_AUTO') and cap.get(cv2.CAP_PROP_ORIENTATION_AUTO):
                    rotation=0
                if rotation == 90:
                    frame = cv2.rotate(frame, cv2.ROTATE_90_CLOCKWISE)
                elif rotation == 180:
                    frame = cv2.rotate(frame, cv2.ROTATE_180)
                elif rotation == 270:
                    frame = cv2.rotate(frame, cv2.ROTATE_90_COUNTERCLOCKWISE)
                sh, sw = frame.shape[:2]
                row = _row_at(timeline, starts, timestamp)
                if not row or row.get('layout') == 'full_frame':
                    rendered = _fit(frame, output_width, output_height, cv2)
                elif row.get('layout') == 'split_candidate' and row.get('split'):
                    split = row['split']
                    left = _crop(frame, split.get('left_crop'), output_width//2, output_height, cv2)
                    right = _crop(frame, split.get('right_crop'), output_width-output_width//2, output_height, cv2)
                    rendered = __import__('numpy').concatenate([left, right], axis=1)
                else:
                    rect = _interpolate_keyframes(row, timestamp, sw, sh, output_width, output_height)
                    rendered = _crop(frame, rect, output_width, output_height, cv2)
                writer.write(rendered)
                frame_count += 1
        finally:
            writer.release(); cap.release()
        if frame_count == 0:
            return ok({}, 'unavailable', ['Preview não recebeu frames no intervalo solicitado.'])
        # Add source audio for the exact canary interval when ffmpeg is available.
        ffmpeg = find_media_tool('ffmpeg')
        if ffmpeg:
            cmd = [ffmpeg, '-hide_banner', '-loglevel', 'error', '-y', '-ss', f'{start:.6f}', '-i', str(source),
                   '-i', str(silent), '-map', '1:v:0', '-map', '0:a?', '-c:v', 'copy', '-c:a', 'aac',
                   '-shortest', str(output)]
            proc = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace', shell=False,timeout=120)
            if proc.returncode:
                shutil.copy2(silent, output)
            audio_muxed = proc.returncode == 0
        else:
            shutil.copy2(silent, output); audio_muxed = False
    return ok({'path': str(output.resolve()), 'start': start, 'end': end, 'duration': end-start,
               'width': int(output_width), 'height': int(output_height), 'fps': fps,
               'frames': frame_count, 'audio_muxed': audio_muxed,
               'source_width': sw, 'source_height': sh,
               'timing_mode': 'source_seek_with_cfr_technical_preview',
               'keyframes_consumed': True, 'final_social_render': False},
              'ok', ['Preview técnico CFR; o renderizador social final continua fora desta etapa.'], [output])
