"""S9: fail-closed Analyzer -> local Curator production-preview bridge.

The independent Curator application is not bundled with Analyzer. This module
renders reviewable MP4 artifacts with local FFmpeg, but never claims to publish.
No media is synthesized. Manual approval is always tied to cryptographic hashes.
"""
from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
import json
import math
import re
import shutil
import subprocess
import zipfile

from .curator_bridge import audit_second_curation_package
from .second_curation_decisions import compile_decisions

CHECKS = ('editorial', 'commercial', 'subtitles', 'camera', 'audio', 'safe_area', 'payoff')
COMMERCIAL = {'advertisement', 'sponsor_read', 'merchandising', 'commercial_promotion', 'event_promotion', 'self_promotion'}
ID_PATTERN = re.compile(r'^[A-Za-z0-9_-]{1,100}$')


def file_sha256(path):
    h = sha256()
    with Path(path).open('rb') as source:
        for buf in iter(lambda: source.read(4 * 1024 ** 2), b''):
            h.update(buf)
    return h.hexdigest()


def canonical_hash(value):
    return sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8')).hexdigest()


def load_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def save_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    return path


def probe(path):
    exe = shutil.which('ffprobe')
    if not exe:
        raise RuntimeError('ffprobe_unavailable')
    proc = subprocess.run([exe, '-v', 'error', '-show_streams', '-show_format', '-of', 'json', str(path)],
                          capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=60, shell=False)
    if proc.returncode:
        raise ValueError('ffprobe_failed:' + proc.stderr[-450:])
    data = json.loads(proc.stdout)
    streams = data.get('streams') or []
    videos = [x for x in streams if x.get('codec_type') == 'video']
    audios = [x for x in streams if x.get('codec_type') == 'audio']
    video_seconds = float(videos[0].get('duration') or 0) if videos else None
    audio_seconds = float(audios[0].get('duration') or 0) if audios else None
    return {'duration': float(data.get('format', {}).get('duration') or 0),
            'av_duration_delta': abs(video_seconds-audio_seconds) if video_seconds and audio_seconds else None,
            'width': int(videos[0].get('width') or 0) if videos else 0,
            'height': int(videos[0].get('height') or 0) if videos else 0,
            'video_count': len(videos), 'audio_count': len(audios),
            'video_codec': videos[0].get('codec_name') if videos else None,
            'audio_codec': audios[0].get('codec_name') if audios else None}


def _safe_candidate(row):
    commercial = row.get('commercial_classification') or {}
    return (row.get('default_shortlist_eligible') is True and
            row.get('publication_eligible') is True and
            commercial.get('eligibility') == 'eligible' and
            row.get('content_type') not in COMMERCIAL)


def prepare_plan(package_path, source_path, *, decisions_path=None, music_path=None, output_dir=None,
                 prefer_stories=True):
    """Strictly READY package; source SHA; safe intervals; manual decisions (optional).

    The source URL is metadata, never auto-downloaded or passed to a shell.
    """
    package_path, source_path = Path(package_path).resolve(), Path(source_path).resolve()
    audit = audit_second_curation_package(package_path)
    if not audit['bridge_possible']:
        raise ValueError('SECOND_CURATION_NOT_READY:' + ','.join(audit.get('blockers', [])))
    with zipfile.ZipFile(package_path) as archive:
        def read(name, default=None):
            return json.loads(archive.read(name)) if name in archive.namelist() else default
        metadata = read('source/metadata.json')
        manifest = read('SECOND_CURATION_MANIFEST.json')
        catalog = read('editorial/candidate_catalog.json')['candidates']
        shortlist = read('editorial/default_shortlist.json')['candidate_ids']
        social = read('social/stories_manifest.json', {})
        camera_rows = {r.get('candidate_id'): r for r in read('camera/candidate_camera_plans.json', []) if isinstance(r, dict)}
        subtitle_reviews = read('subtitles/subtitle_review_s7.json', {})
        words = [json.loads(line) for line in archive.read('transcript/relevant_words.jsonl').decode('utf-8').splitlines() if line] if 'transcript/relevant_words.jsonl' in archive.namelist() else []
        segments = [json.loads(line) for line in archive.read('transcript/relevant_segments.jsonl').decode('utf-8').splitlines() if line]
    if not manifest.get('workflow', {}).get('review_ready'):
        raise ValueError('REVIEW_READY_CONTRACT_FALSE')
    if not source_path.is_file():
        raise FileNotFoundError('SOURCE_VIDEO_MISSING')
    source_hash = file_sha256(source_path)
    if not isinstance(metadata.get('sha256'), str) or not re.fullmatch('[0-9a-fA-F]{64}', metadata['sha256']):
        raise ValueError('SOURCE_SHA256_MISSING_OR_INVALID')
    if source_hash.lower() != metadata['sha256'].lower():
        raise ValueError('SOURCE_VIDEO_HASH_MISMATCH')
    info = probe(source_path)
    if info['video_count'] != 1 or info['audio_count'] < 1 or info['duration'] <= 0:
        raise ValueError('SOURCE_MUST_HAVE_VIDEO_AND_AUDIO')
    by_id = {row['candidate_id']: row for row in catalog}
    decisions, decisions_hash = None, None
    if decisions_path:
        decisions = load_json(decisions_path)
        if decisions.get('input_package_sha256') not in (None, file_sha256(package_path)):
            raise ValueError('DECISION_PACKAGE_HASH_MISMATCH')
        compiled = compile_decisions(decisions, {'candidates': catalog}, metadata, segments)
        decisions_hash = file_sha256(decisions_path)
        if not compiled:
            raise ValueError('NO_APPROVED_EDITORIAL_DECISIONS')
        selected = [{'candidate_id': row['candidate_ids'][0], 'start': row['start'], 'end': row['end'],
                     'title': row['title'], 'story_id': row['decision_id'], 'layout': row.get('suggested_layout'),
                     'decision_ids': row['candidate_ids']} for row in compiled]
    elif prefer_stories and social.get('stories'):
        if social.get('story_readiness') not in ('READY', 'REVIEW_REQUIRED'):
            raise ValueError('STORIES_NOT_EDITORIALLY_READY')
        selected = [{'candidate_id': row['candidate_id'], 'start': row['start'], 'end': row['end'],
                     'title': row.get('title'), 'story_id': row['story_id'], 'layout': (row.get('visual_plan') or {}).get('layout_mode')}
                    for row in social['stories']]
    else:
        selected = [{'candidate_id': cid, 'start': by_id[cid]['start'], 'end': by_id[cid]['end'],
                     'title': (by_id[cid].get('generated_copy') or {}).get('title_idea') or 'Trecho selecionado',
                     'story_id': f'SHORT_{index:03}', 'layout': None} for index, cid in enumerate(shortlist, 1)]
    if not selected:
        raise ValueError('NO_SELECTED_CLIPS')
    music_file = Path(music_path).resolve() if music_path else None
    if music_file:
        if not music_file.is_file() or probe(music_file)['audio_count'] < 1:
            raise ValueError('INSTRUMENTAL_MISSING_OR_INVALID')
    rows, seen = [], set()
    for index, item in enumerate(selected, 1):
        cid = item['candidate_id']
        if cid not in by_id or not _safe_candidate(by_id[cid]):
            raise ValueError('COMMERCIAL_OR_UNREVIEWABLE_CANDIDATE:' + str(cid))
        key = item.get('story_id') or f'CLIP_{index:03}'
        if not isinstance(key, str) or not ID_PATTERN.fullmatch(key) or key in seen:
            raise ValueError('INVALID_OR_DUPLICATE_STORY_ID')
        seen.add(key)
        start, end = float(item['start']), float(item['end'])
        if not all(map(math.isfinite, (start, end))) or start < 0 or end <= start or end > min(float(metadata['duration']), info['duration']) + .1:
            raise ValueError('INVALID_CLIP_BOUNDS:' + key)
        if end - start > 600:
            raise ValueError('CLIP_DURATION_LIMIT_EXCEEDED:' + key)
        candidate = by_id[cid]
        is_performance = any(k in str(candidate.get('content_type') or '').lower() + ' ' + str(candidate.get('story_type') or '').lower()
                             for k in ('performance', 'show_musical', 'music_performance', 'concert'))
        # No neural separation here: source soundtrack is always preserved;
        # a low-volume optional instrumental is layered only on non-performances.
        audio_mode = 'original_performance' if is_performance else ('source_plus_instrumental' if music_file else 'source_original')
        relevant = [{'start': max(0., float(s['start'])-start), 'end': min(end-start, float(s['end'])-start),
                     'text': str(s.get('text') or '')} for s in segments
                    if float(s['start']) < end and float(s['end']) > start and str(s.get('text') or '').strip()]
        relevant_words = [{**{k: w.get(k) for k in ('word_id','segment_id','word','confidence','needs_review','timestamp_suspect')},
                           'start': float(w['start'])-start, 'end': float(w['end'])-start}
                          for w in words if isinstance(w.get('start'), (int, float))
                          and isinstance(w.get('end'), (int, float)) and start <= w['start'] < w['end'] <= end]
        camera_rec = camera_rows.get(cid) or {}
        clip_subtitles = (subtitle_reviews.get('candidates') or {}).get(cid, {}) if isinstance(subtitle_reviews, dict) else {}
        rows.append({'id': key, 'candidate_id': cid, 'start': start, 'end': end, 'duration': end-start,
                     'title_suggestion': str(item.get('title') or '')[:140], 'title_review_required': True,
                     'source_layout_recommendation': item.get('layout'),
                     'camera_recommendations': camera_rec,
                     'camera_evidence_used_to_crop': False,
                     'render_layout': 'source_preserve_blurred_fill',
                     'camera_plan_status': 'not_verified_for_render_no_automatic_zoom',
                     'audio_mode': audio_mode, 'subtitle_status': clip_subtitles.get('approval_state') or 'DRAFT_REQUIRES_LISTENING',
                     'karaoke_allowed': False, 'segments': relevant, 'words': relevant_words,
                     'word_evidence_count': len(relevant_words),
                     'requires_human_review': True})
    plan = {'schema_version': '9.1', 'source_video': str(source_path), 'source_sha256': source_hash,
            'package_sha256': file_sha256(package_path), 'package_path': str(package_path),
            'decisions_sha256': decisions_hash, 'decisions_explicit': bool(decisions_path),
            'source_probe': info, 'music_file': str(music_file) if music_file else None,
            'music_sha256': file_sha256(music_file) if music_file else None,
            'clips': rows, 'output': str(Path(output_dir).resolve()) if output_dir else None,
            'package_readiness': 'READY_FOR_REVIEW_NOT_PUBLISH', 'publication_ready': False,
            'render_profile': {'width': 1080, 'height': 1920, 'fps': 30},
            'mandatory_checks': list(CHECKS)}
    plan['plan_sha256'] = canonical_hash({k: v for k, v in plan.items() if k != 'plan_sha256'})
    return plan


def validate_plan(plan):
    if canonical_hash({k: v for k, v in plan.items() if k != 'plan_sha256'}) != plan.get('plan_sha256'):
        raise ValueError('RENDER_PLAN_TAMPERED')
    if file_sha256(plan['source_video']) != plan['source_sha256']:
        raise ValueError('SOURCE_MODIFIED_AFTER_PLANNING')
    if file_sha256(plan['package_path']) != plan['package_sha256']:
        raise ValueError('PACKAGE_MODIFIED_AFTER_PLANNING')
    if plan.get('music_file') and file_sha256(plan['music_file']) != plan['music_sha256']:
        raise ValueError('INSTRUMENTAL_MODIFIED_AFTER_PLANNING')


def _ass_timestamp(seconds):
    cs = int(round(max(0, seconds) * 100))
    return f'{cs//360000}:{(cs//6000)%60:02}:{(cs//100)%60:02}.{cs%100:02}'


def _ass_escape(text):
    return str(text).replace('\\', '＼').replace('{', '（').replace('}', '）').replace('\n', ' ').replace('\r', ' ')[:350]


def overlay_ass(clip, path, *, include_draft=False):
    """ASS text overlay for review: no word-level karaoke without verified timing."""
    header = ('[Script Info]\nScriptType: v4.00+\nPlayResX: 1080\nPlayResY: 1920\nWrapStyle: 0\n'
              '[V4+ Styles]\nFormat: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding\n'
              'Style: Title,Arial,67,&H00FFFFFF,&H000000FF,&H00151515,&H90000000,-1,0,0,0,100,100,0,0,1,4,1,8,90,90,155,1\n'
              'Style: Caption,Arial,57,&H00FFFFFF,&H000000FF,&H00151515,&H90000000,-1,0,0,0,100,100,0,0,1,4,1,2,85,85,340,1\n'
              '[Events]\nFormat: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text\n')
    lines = []
    if clip.get('title_suggestion'):
        lines.append(f'Dialogue: 0,0:00:00.00,{_ass_timestamp(min(4, clip["duration"]))},Title,,0,0,0,,{_ass_escape(clip["title_suggestion"])}')
    if include_draft:
        for segment in clip.get('segments', []):
            if segment['end'] > segment['start'] + .1:
                lines.append(f'Dialogue: 0,{_ass_timestamp(segment["start"])},{_ass_timestamp(segment["end"])},Caption,,0,0,0,,{_ass_escape(segment["text"])}')
    path.write_text(header + '\n'.join(lines) + '\n', encoding='utf-8')


def verify_mp4(path, expected_duration, *, require_audio=True):
    result = {'file': str(path), 'status': 'BLOCKED', 'issues': []}
    if not Path(path).is_file() or Path(path).stat().st_size < 4096:
        result['issues'].append('OUTPUT_MISSING_OR_EMPTY')
        return result
    try:
        info = probe(path)
    except (RuntimeError, ValueError) as exc:
        result['issues'].append(type(exc).__name__)
        return result
    result['probe'] = info
    if (info['width'], info['height']) != (1080, 1920):
        result['issues'].append('WRONG_DIMENSIONS')
    if info['video_count'] != 1 or require_audio and info['audio_count'] < 1:
        result['issues'].append('MISSING_VIDEO_OR_AUDIO')
    if abs(info['duration']-float(expected_duration)) > .35:
        result['issues'].append('DURATION_MISMATCH')
    if info['av_duration_delta'] is not None and info['av_duration_delta'] > .25:
        result['issues'].append('AUDIO_VIDEO_DURATION_DESYNC')
    result['sha256'] = file_sha256(path)
    result['status'] = 'TECHNICALLY_VALID_REQUIRES_HUMAN_REVIEW' if not result['issues'] else 'BLOCKED'
    return result


def render_clip(plan, clip_index, output_dir, *, draft_captions=False):
    validate_plan(plan)
    clips = plan['clips']
    if not 0 <= clip_index < len(clips):
        raise IndexError('CLIP_INDEX_OUT_OF_RANGE')
    if not shutil.which('ffmpeg'):
        raise RuntimeError('FFMPEG_UNAVAILABLE')
    clip = clips[clip_index]
    out = Path(output_dir).resolve()
    out.mkdir(parents=True, exist_ok=True)
    mp4 = out / (clip['id'] + '.mp4')
    if mp4.exists():
        raise FileExistsError('REFUSING_TO_OVERWRITE_RENDER:' + str(mp4))
    # A relative ASS path avoids Windows filter-expression escaping errors.
    ass = out / (clip['id'] + '.ass')
    overlay_ass(clip, ass, include_draft=draft_captions)
    # Always preserve full content in source frame; blurred fill avoids inventing
    # camera tracking or chopping faces when observations are not verified.
    video_filter = ("[0:v]split=2[bgsrc][fgsrc];"
                    "[bgsrc]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=10:1[bg];"
                    "[fgsrc]scale=1080:1920:force_original_aspect_ratio=decrease[fg];"
                    "[bg][fg]overlay=(W-w)/2:(H-h)/2,setsar=1,format=yuv420p,"
                    f"ass={ass.name}[v]")
    args = [shutil.which('ffmpeg'), '-hide_banner', '-loglevel', 'error', '-nostdin', '-y', '-ss', f'{clip["start"]:.6f}',
            '-i', plan['source_video']]
    if clip['audio_mode'] == 'source_plus_instrumental':
        args += ['-stream_loop', '-1', '-i', plan['music_file']]
        audio_filter = '[0:a:0]volume=1[a0];[1:a:0]volume=0.10[bed];[a0][bed]amix=inputs=2:duration=first:dropout_transition=0[a]'
    else:
        audio_filter = '[0:a:0]anull[a]'
    args += ['-filter_complex', video_filter+';'+audio_filter, '-map', '[v]', '-map', '[a]',
             '-t', f'{clip["duration"]:.6f}', '-r', '30', '-c:v', 'libx264', '-preset', 'veryfast',
             '-crf', '20', '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-b:a', '160k', '-movflags', '+faststart',
             mp4.name + '.partial.mp4']
    partial = out / (mp4.name + '.partial.mp4')
    try:
        proc = subprocess.run(args, cwd=str(out), capture_output=True, text=True, encoding='utf-8', errors='replace',
                              shell=False, timeout=max(120, min(3600, clip['duration']*20)))
        if proc.returncode:
            raise RuntimeError('FFMPEG_RENDER_FAILED:' + proc.stderr[-650:])
        technical = verify_mp4(partial, clip['duration'])
        if technical['status'] == 'BLOCKED':
            raise RuntimeError('RENDER_CRITICAL_ISSUES:' + ','.join(technical['issues']))
        partial.replace(mp4)
    finally:
        partial.unlink(missing_ok=True)
    report = verify_mp4(mp4, clip['duration'])
    report.update(id=clip['id'], candidate_id=clip['candidate_id'], plan_sha256=plan['plan_sha256'],
                  source_sha256=plan['source_sha256'], package_sha256=plan['package_sha256'],
                  audio_mode=clip['audio_mode'], subtitle_review_required=True,
                  draft_captions_burned=bool(draft_captions),
                  safe_area_human_verified=False, editorial_approved=False, publication_ready=False)
    save_json(out/(clip['id']+'.render.json'), report)
    return report


def approve_canary(plan, canary_report, checklist, *, reviewer):
    validate_plan(plan)
    if not reviewer or not str(reviewer).strip():
        raise ValueError('REVIEWER_REQUIRED')
    if any(checklist.get(key) is not True for key in CHECKS):
        raise ValueError('HUMAN_CHECKLIST_NOT_COMPLETE:' + ','.join(k for k in CHECKS if checklist.get(k) is not True))
    if canary_report.get('status') != 'TECHNICALLY_VALID_REQUIRES_HUMAN_REVIEW':
        raise ValueError('CANARY_NOT_TECHNICALLY_VALID')
    cid = canary_report.get('id')
    if cid != plan['clips'][0]['id'] or canary_report.get('plan_sha256') != plan['plan_sha256']:
        raise ValueError('CANARY_PLAN_ID_MISMATCH')
    if file_sha256(canary_report['file']) != canary_report.get('sha256'):
        raise ValueError('CANARY_FILE_CHANGED_SINCE_REVIEW')
    if canary_report['source_sha256'] != plan['source_sha256'] or canary_report['package_sha256'] != plan['package_sha256']:
        raise ValueError('CANARY_PROVENANCE_MISMATCH')
    return {'schema_version': '9.1', 'plan_sha256': plan['plan_sha256'], 'canary_id': cid,
            'canary_sha256': canary_report['sha256'], 'package_sha256': plan['package_sha256'],
            'source_sha256': plan['source_sha256'], 'reviewer': str(reviewer).strip()[:100],
            'checklist': {k: True for k in CHECKS}, 'approved_at': datetime.now(timezone.utc).isoformat(),
            'batch_authorized': True, 'publication_ready': False}


def verify_approval(plan, approval, canary_report):
    validate_plan(plan)
    if (not approval.get('batch_authorized') or approval.get('plan_sha256') != plan['plan_sha256'] or
        approval.get('canary_sha256') != file_sha256(canary_report['file']) or
        approval.get('source_sha256') != plan['source_sha256'] or
        approval.get('package_sha256') != plan['package_sha256'] or
        any(approval.get('checklist', {}).get(k) is not True for k in CHECKS)):
        raise ValueError('CANARY_APPROVAL_INVALIDATED_OR_INCOMPLETE')
    if verify_mp4(canary_report['file'], plan['clips'][0]['duration'])['status'] == 'BLOCKED':
        raise ValueError('CANARY_NO_LONGER_VALID')


def render_batch(plan, approval, canary_report, output_dir, *, draft_captions=False):
    verify_approval(plan, approval, canary_report)
    destination = Path(output_dir).resolve()
    destination.mkdir(parents=True, exist_ok=True)
    reports = []
    for i, row in enumerate(plan['clips']):
        if i == 0:
            # Reuse the reviewed canary only when its file already has the same
            # planned name in the destination; no silent overwrite/copy.
            if Path(canary_report['file']).resolve() == (destination/(row['id']+'.mp4')):
                reports.append(canary_report)
                continue
        if i == 0:
            original = Path(canary_report['file']).resolve()
            copied = destination / (row['id'] + '.mp4')
            if copied.exists():
                raise FileExistsError('REFUSING_TO_OVERWRITE_REVIEWED_CANARY')
            shutil.copy2(original, copied)
            report = verify_mp4(copied, row['duration'])
            report.update({k: canary_report[k] for k in ('id', 'candidate_id', 'plan_sha256', 'source_sha256', 'package_sha256', 'audio_mode', 'subtitle_review_required', 'draft_captions_burned', 'safe_area_human_verified', 'editorial_approved', 'publication_ready')})
            reports.append(report)
            save_json(destination/(row['id']+'.render.json'), report)
        else:
            reports.append(render_clip(plan, i, destination, draft_captions=draft_captions))
    summary = {'state': 'REVIEW_BATCH_RENDERED_NOT_PUBLISHABLE' if all(x['status'].startswith('TECHNICALLY_VALID') for x in reports)
               else 'BLOCKED', 'plan_sha256': plan['plan_sha256'], 'canary_approval_sha256': canonical_hash(approval),
               'clips': reports, 'publication_ready': False,
               'review_required_per_clip': list(CHECKS),
               'note': 'Each MP4 is independently playable. No batch member is implicitly approved by canary approval.'}
    save_json(destination/'BATCH_REVIEW_MANIFEST.json', summary)
    return summary


def finalize_batch(plan, batch_manifest, reviews):
    """Release file hashes only after independent human approval of every MP4."""
    validate_plan(plan)
    if batch_manifest.get('state') != 'REVIEW_BATCH_RENDERED_NOT_PUBLISHABLE' or batch_manifest.get('plan_sha256') != plan['plan_sha256']:
        raise ValueError('BATCH_NOT_READY_FOR_FINAL_REVIEW')
    approved = {entry['id']: entry for entry in reviews.get('clips', [])}
    if len(approved) != len(batch_manifest['clips']):
        raise ValueError('MISSING_PER_CLIP_APPROVAL')
    for clip in batch_manifest['clips']:
        decision = approved.get(clip['id'])
        if (not decision or decision.get('sha256') != file_sha256(clip['file']) or
            any(decision.get('checklist', {}).get(key) is not True for key in CHECKS) or
            not decision.get('reviewer')):
            raise ValueError('CRITICAL_PER_CLIP_REVIEW_PENDING:' + clip['id'])
        if verify_mp4(clip['file'], next(x['duration'] for x in plan['clips'] if x['id'] == clip['id']))['status'] == 'BLOCKED':
            raise ValueError('CRITICAL_RENDER_FAILURE:' + clip['id'])
    return {'state': 'REVIEWED_FINAL_FILES', 'publication_ready': False,
            'publication_is_separate_manual_action': True, 'plan_sha256': plan['plan_sha256'],
            'files': [{'id': c['id'], 'sha256': file_sha256(c['file']), 'path': c['file']} for c in batch_manifest['clips']],
            'review_completed_at': datetime.now(timezone.utc).isoformat()}
