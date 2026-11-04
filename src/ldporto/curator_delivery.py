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
import os
import re
import shutil
import subprocess
import tempfile
import time
import zipfile

from .curator_bridge import audit_second_curation_package
from .second_curation_decisions import compile_decisions
from .subtitle_style import style_rules, checked_text
from .audio import plan_clip_audio, delivery_audio_filter

CHECKS = ('editorial', 'commercial', 'subtitles', 'camera', 'audio', 'safe_area', 'payoff',
          'listening', 'audio_sync', 'legibility')
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
            'sample_aspect_ratio': videos[0].get('sample_aspect_ratio') if videos else None,
            'display_aspect_ratio': videos[0].get('display_aspect_ratio') if videos else None,
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
                 prefer_stories=True, music_gain=0.10, music_title='Eu Não Vou Parar'):
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
        audio_events = read('audio/sound_events.json', {}).get('events', [])
        words = [json.loads(line) for line in archive.read('transcript/relevant_words.jsonl').decode('utf-8').splitlines() if line] if 'transcript/relevant_words.jsonl' in archive.namelist() else []
        segments = [json.loads(line) for line in archive.read('transcript/relevant_segments.jsonl').decode('utf-8').splitlines() if line]
        qa_pairs = read('editorial/qa_pairs.json', [])
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
    for word in words:
        times = (word.get('start'), word.get('end'))
        if any(not isinstance(t, (int, float)) or isinstance(t, bool) or not math.isfinite(t) for t in times) or not 0 <= times[0] < times[1] <= float(metadata['duration']):
            raise ValueError('INVALID_WORD_INTERVAL')
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
        if item.get('title') is not None and (not isinstance(item['title'], str) or not item['title'].strip()):
            raise ValueError('INVALID_CLIP_TITLE:' + key)
        candidate = by_id[cid]
        # Merged decisions must protect every contributing candidate, as well as
        # other catalog intervals covered by an expanded manual cut.
        covered = [c for c in catalog if c.get('candidate_id') in item.get('decision_ids', [cid])
                   or float(c['start']) < end and float(c['end']) > start]
        if any(c.get('content_type') in COMMERCIAL or
               (c.get('commercial_classification') or {}).get('eligibility') == 'excluded' for c in covered):
            raise ValueError('INTERVAL_CONTAINS_COMMERCIAL:' + key)
        audio_plan = plan_clip_audio(covered, audio_events, start, end,
                                    instrumental=bool(music_file), gain=music_gain, track_title=music_title)
        audio_mode = audio_plan['audio_mode']
        relevant = [{'start': max(0., float(s['start'])-start), 'end': min(end-start, float(s['end'])-start),
                     'text': str(s.get('text') or '')} for s in segments
                    if float(s['start']) < end and float(s['end']) > start and str(s.get('text') or '').strip()]
        relevant_words = [{**{k: w.get(k) for k in ('word_id','segment_id','word','confidence','needs_review','timestamp_suspect',
                                                   'alignment_verified','audio_verified','speech_overlap')},
                           'start': float(w['start'])-start, 'end': float(w['end'])-start}
                          for w in words if isinstance(w.get('start'), (int, float))
                          and isinstance(w.get('end'), (int, float)) and start <= w['start'] < w['end'] <= end]
        camera_rec = camera_rows.get(cid) or {}
        clip_subtitles = (subtitle_reviews.get('candidates') or {}).get(cid, {}) if isinstance(subtitle_reviews, dict) else {}
        changed_bounds = start != candidate['start'] or end != candidate['end'] or len(item.get('decision_ids', [cid])) > 1
        qa = []
        linked = {qid for c in covered for qid in c.get('question_answer_linkage', [])}
        by_question = {q['question_id']: q for q in qa_pairs}
        for qid in sorted(linked):
            q = by_question.get(qid) or {}
            times = [q.get(k) for k in ('question_start', 'question_end', 'answer_start', 'answer_end')]
            known = all(isinstance(t, (int, float)) and not isinstance(t, bool) and math.isfinite(t) for t in times)
            contained = (start <= times[0] < times[1] <= times[2] < times[3] <= end) if known else None
            qa.append({'question_id': qid, 'interval_complete': contained,
                       'question_answer_complete': q.get('question_answer_complete') if contained is True else None,
                       'needs_review': True, 'reason': 'source_pair_requires_review' if contained else
                       ('pair_outside_clip' if contained is False else 'missing_pair_timing')})
        if changed_bounds:
            camera_rec = {}  # Stale keyframes must not describe the edited interval.
            clip_subtitles = {}
        rows.append({'id': key, 'candidate_id': cid, 'start': start, 'end': end, 'duration': end-start,
                     'title_suggestion': str(item.get('title') or ''), 'title_review_required': True,
                     'source_layout_recommendation': item.get('layout'),
                     'camera_recommendations': camera_rec,
                     'camera_evidence_used_to_crop': False,
                     'render_layout': 'source_preserve_blurred_fill',
                     'camera_plan_status': 'not_verified_for_render_no_automatic_zoom',
                     'audio_mode': audio_mode, 'audio_plan': audio_plan,
                     'subtitle_status': clip_subtitles.get('approval_state') or 'DRAFT_REQUIRES_LISTENING',
                     'interval_changed': changed_bounds, 'qa_validation': qa,
                     'preview_approved': None, 'publish_ready': False,
                     'karaoke_allowed': False, 'segments': relevant, 'words': relevant_words,
                     'word_evidence_count': len(relevant_words),
                     'requires_human_review': True})
    plan = {'schema_version': '9.1', 'source_video': str(source_path), 'source_sha256': source_hash,
            'package_sha256': file_sha256(package_path), 'package_path': str(package_path),
            'decisions_sha256': decisions_hash, 'decisions_explicit': bool(decisions_path),
            'decisions_path': str(Path(decisions_path).resolve()) if decisions_path else None,
            'source_probe': info, 'music_file': str(music_file) if music_file else None,
            'music_sha256': file_sha256(music_file) if music_file else None,
            'planning_options': {'prefer_stories': prefer_stories, 'music_gain': music_gain, 'music_title': music_title},
            'curator_integration': {'included': 'local_ffmpeg_bridge', 'independent_app_verified': None},
            'clips': rows, 'output': str(Path(output_dir).resolve()) if output_dir else None,
            'package_readiness': 'READY_FOR_REVIEW_NOT_PUBLISH', 'publication_ready': False,
            'render_profile': {'width': 1080, 'height': 1920, 'fps': 30},
            'mandatory_checks': list(CHECKS)}
    plan['plan_sha256'] = canonical_hash({k: v for k, v in plan.items() if k != 'plan_sha256'})
    return plan


def import_decisions(package_path, source_path, decisions_path, *, state_path=None,
                     previous_plan=None, dry_run=False, **planning_options):
    """Rebuild dependents without inference/rendering; commit plan+journal atomically.

    state_path is a NEW import-state file, not an existing analysis or bare plan.
    The input plan is never mutated. Replay of the current operation makes no write.
    A single envelope avoids a plan/journal split on process failure. Single writer
    required; this local importer is not a concurrent database.
    """
    state_file = Path(state_path) if state_path is not None else None
    state = load_json(state_file) if state_file and state_file.exists() else None
    journal = []
    if state is not None:
        if state.get('schema_version') != '37.1' or not isinstance(state.get('journal'), list) or not state['journal']:
            raise ValueError('INVALID_IMPORT_STATE')
        prior_hash = None
        for entry in state['journal']:
            if entry.get('previous_entry_sha256') != prior_hash or canonical_hash(
                    {k: v for k, v in entry.items() if k != 'entry_sha256'}) != entry.get('entry_sha256'):
                raise ValueError('IMPORT_JOURNAL_TAMPERED')
            prior_hash = entry['entry_sha256']
        if state['journal'][-1]['result_plan_sha256'] != state['plan'].get('plan_sha256'):
            raise ValueError('IMPORT_JOURNAL_PLAN_MISMATCH')
        if previous_plan is not None and previous_plan != state['plan']:
            raise ValueError('IMPORT_PREVIOUS_PLAN_MISMATCH')
        previous_plan = state['plan']
        journal = state['journal']
    if previous_plan is not None:
        # The prior decision snapshot is historical here: this operation explicitly
        # replaces decisions and invalidates every approval. Render/release still
        # require current decision bytes; source/package/music remain checked.
        validate_plan(previous_plan, check_decisions=False)
        if file_sha256(package_path) != previous_plan['package_sha256'] or file_sha256(source_path) != previous_plan['source_sha256']:
            raise ValueError('IMPORT_PREVIOUS_PROVENANCE_MISMATCH')
    document = load_json(decisions_path)
    package_hash = file_sha256(package_path)
    if document.get('input_package_sha256') != package_hash:
        raise ValueError('DECISION_PACKAGE_HASH_REQUIRED_OR_MISMATCH')
    options = dict(previous_plan.get('planning_options', {})) if previous_plan else {}
    if previous_plan:
        options.update(music_path=previous_plan.get('music_file'), output_dir=previous_plan.get('output'))
    options.update(planning_options)
    plan = prepare_plan(package_path, source_path, decisions_path=decisions_path, **options)
    validate_plan(plan)
    operation = canonical_hash({'plan_sha256': plan['plan_sha256'], 'decisions': document})
    if journal and journal[-1]['operation_sha256'] == operation:
        return {'plan': plan, 'journal': journal, 'schema_version': '37.1',
                'dry_run': dry_run, 'replayed': True, 'committed': False}
    old_clips = {c['id']: c for c in previous_plan['clips']} if previous_plan else {}
    changes = []
    for clip in plan['clips']:
        old = old_clips.pop(clip['id'], None)
        if old != clip:
            changes.append({'clip_id': clip['id'], 'before_interval': [old['start'], old['end']] if old else None,
                            'after_interval': [clip['start'], clip['end']],
                            'recomputed': ['segments', 'words', 'qa', 'audio', 'camera', 'subtitles'],
                            'approval_invalidated': True})
    changes.extend({'clip_id': cid, 'removed': True, 'approval_invalidated': True} for cid in sorted(old_clips))
    entry = {'operation_sha256': operation, 'previous_entry_sha256': journal[-1]['entry_sha256'] if journal else None,
             'previous_plan_sha256': previous_plan['plan_sha256'] if previous_plan else None,
             'result_plan_sha256': plan['plan_sha256'], 'decisions_sha256': plan['decisions_sha256'],
             'decisions': document, 'source_sha256': plan['source_sha256'],
             'package_sha256': package_hash, 'changes': changes,
             'invalidated': ['preview', 'canary_approval', 'batch_review'], 'publication_ready': False}
    entry['entry_sha256'] = canonical_hash(entry)
    envelope = {'schema_version': '37.1', 'plan': plan, 'journal': journal + [entry]}
    if not dry_run:
        if state_file is None:
            raise ValueError('IMPORT_STATE_PATH_REQUIRED')
        state_file.parent.mkdir(parents=True, exist_ok=True)
        fd, temp_name = tempfile.mkstemp(prefix='.curator_import_', suffix='.json', dir=state_file.parent)
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as handle:
                json.dump(envelope, handle, ensure_ascii=False, allow_nan=False, indent=2)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_name, state_file)
        finally:
            Path(temp_name).unlink(missing_ok=True)
    return {**envelope, 'dry_run': dry_run, 'replayed': False, 'committed': not dry_run}


def validate_plan(plan, *, check_decisions=True):
    if canonical_hash({k: v for k, v in plan.items() if k != 'plan_sha256'}) != plan.get('plan_sha256'):
        raise ValueError('RENDER_PLAN_TAMPERED')
    for clip in plan.get('clips', []):
        if clip.get('audio_mode') == 'source_plus_instrumental' and (clip.get('audio_plan') or {}).get('policy_version') != '24.1':
            raise ValueError('AUDIO_MIX_POLICY_CHANGED_REPLAN_AND_REVIEW_REQUIRED')
    if file_sha256(plan['source_video']) != plan['source_sha256']:
        raise ValueError('SOURCE_MODIFIED_AFTER_PLANNING')
    if file_sha256(plan['package_path']) != plan['package_sha256']:
        raise ValueError('PACKAGE_MODIFIED_AFTER_PLANNING')
    if plan.get('music_file') and file_sha256(plan['music_file']) != plan['music_sha256']:
        raise ValueError('INSTRUMENTAL_MODIFIED_AFTER_PLANNING')
    if check_decisions and plan.get('decisions_explicit'):
        if not plan.get('decisions_path'):
            raise ValueError('DECISIONS_PATH_UNVERIFIED_REPLAN_REQUIRED')
        if file_sha256(plan['decisions_path']) != plan.get('decisions_sha256'):
            raise ValueError('DECISIONS_MODIFIED_AFTER_PLANNING')


def _ass_timestamp(seconds):
    cs = int(round(max(0, seconds) * 100))
    return f'{cs//360000}:{(cs//6000)%60:02}:{(cs//100)%60:02}.{cs%100:02}'


def _ass_escape(text):
    return str(text).replace('\\', '＼').replace('{', '（').replace('}', '）').replace('\r', ' ').replace('\n', r'\N')


def overlay_ass(clip, path, *, include_draft=False):
    """ASS text overlay for review: no word-level karaoke without verified timing."""
    rules = style_rules()
    rect = rules['proposed_safe_rect']
    left, right = rect['x'], 1080 - rect['x'] - rect['width']
    top, bottom = rect['y'] + 8, 1920 - rect['y'] - rect['height'] + 8
    header = ('[Script Info]\nScriptType: v4.00+\nPlayResX: 1080\nPlayResY: 1920\nWrapStyle: 2\n'
              '[V4+ Styles]\nFormat: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding\n'
              f'Style: Title,Arial,{rules["title_font_size_px"]},&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,-1,0,0,0,100,100,0,0,3,8,0,8,{left},{right},{top},1\n'
              f'Style: Caption,Arial,{rules["font_size_px"]},&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,-1,0,0,0,100,100,0,0,3,8,0,2,{left},{right},{bottom},1\n'
              '[Events]\nFormat: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text\n')
    lines = []
    if clip.get('title_suggestion'):
        title = checked_text(clip['title_suggestion'], rules['title_max_chars_per_line'],
                             font_size_px=rules['title_font_size_px'], max_width_px=rect['width']-16)
        lines.append(f'Dialogue: 0,0:00:00.00,{_ass_timestamp(min(4, clip["duration"]))},Title,,0,0,0,,{_ass_escape(title)}')
    if include_draft:
        for segment in clip.get('segments', []):
            if segment['end'] > segment['start'] + .1:
                text = checked_text(segment['text'], rules['max_chars_per_line'],
                                    font_size_px=rules['font_size_px'], max_width_px=rect['width']-16)
                lines.append(f'Dialogue: 0,{_ass_timestamp(segment["start"])},{_ass_timestamp(segment["end"])},Caption,,0,0,0,,{_ass_escape(text)}')
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
    if info['video_codec'] != 'h264' or require_audio and info['audio_codec'] != 'aac':
        result['issues'].append('WRONG_DELIVERY_CODEC')
    if info['sample_aspect_ratio'] != '1:1' or info['display_aspect_ratio'] != '9:16':
        result['issues'].append('WRONG_ASPECT_RATIO')
    if abs(info['duration']-float(expected_duration)) > .35:
        result['issues'].append('DURATION_MISMATCH')
    if info['av_duration_delta'] is not None and info['av_duration_delta'] > .25:
        result['issues'].append('AUDIO_VIDEO_DURATION_DESYNC')
    # Container metadata alone does not establish that every frame is playable.
    result['decode_verified'] = False
    exe = shutil.which('ffmpeg')
    if not exe:
        result['issues'].append('FFMPEG_UNAVAILABLE_FOR_INTEGRITY_CHECK')
    else:
        try:
            decoded = subprocess.run([exe, '-hide_banner', '-loglevel', 'error', '-nostdin',
                '-xerror', '-err_detect', 'explode', '-threads', '2', '-i', str(path),
                '-map', '0:v:0', '-map', '0:a:0?' if not require_audio else '0:a:0',
                '-f', 'null', '-'], capture_output=True, text=True, encoding='utf-8',
                errors='replace', shell=False, timeout=max(60, min(3600, float(expected_duration)*20)))
            result['decode_exit_code'] = decoded.returncode
            result['decode_verified'] = decoded.returncode == 0
            if decoded.returncode:
                result['issues'].append('DECODE_INTEGRITY_FAILED')
                result['decode_error'] = decoded.stderr[-650:]
        except subprocess.TimeoutExpired:
            result['issues'].append('DECODE_INTEGRITY_TIMEOUT')
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
    if any((out / (clip['id'] + suffix)).exists() for suffix in ('.mp4', '.ass', '.render.json', '.mp4.partial.mp4')):
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
    args = [shutil.which('ffmpeg'), '-hide_banner', '-loglevel', 'error', '-nostdin', '-y',
            '-filter_complex_threads', '2', '-threads', '2', '-ss', f'{clip["start"]:.6f}',
            '-i', plan['source_video']]
    if clip['audio_mode'] == 'source_plus_instrumental':
        args += ['-stream_loop', '-1', '-i', plan['music_file']]
    audio_plan = clip.get('audio_plan') or plan_clip_audio([], [], clip['start'], clip['end'],
        instrumental=clip['audio_mode'] == 'source_plus_instrumental')
    audio_filter = delivery_audio_filter(audio_plan)
    args += ['-filter_complex', video_filter+';'+audio_filter, '-map', '[v]', '-map', '[a]',
             '-t', f'{clip["duration"]:.6f}', '-r', '30', '-c:v', 'libx264', '-preset', 'veryfast',
             '-threads', '2', '-crf', '20', '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-b:a', '160k', '-movflags', '+faststart',
             mp4.name + '.partial.mp4']
    partial = out / (mp4.name + '.partial.mp4')
    started = time.monotonic()
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
    report = {**technical, 'file': str(mp4)}
    report.update(id=clip['id'], candidate_id=clip['candidate_id'], plan_sha256=plan['plan_sha256'],
                  source_sha256=plan['source_sha256'], package_sha256=plan['package_sha256'],
                  audio_mode=clip['audio_mode'], audio_mix_log={'plan': audio_plan,
                      'filter': audio_filter, 'limiter_ceiling': .95 if clip['audio_mode'] == 'source_plus_instrumental' else None,
                      'encoded_peak_verified': None, 'listening_verified': None}, subtitle_review_required=True,
                  draft_captions_burned=bool(draft_captions),
                  title_suggestion=clip.get('title_suggestion'), render_layout=clip['render_layout'],
                  subtitle_artifacts={'ass': {'file': str(ass), 'sha256': file_sha256(ass)}},
                  preview_approved=None, publish_ready=False,
                  performance={'elapsed_seconds': round(time.monotonic()-started, 3),
                               'encoder_threads': 2, 'filter_threads': 2, 'preset': 'veryfast',
                               'timeout_seconds': max(120, min(3600, clip['duration']*20))},
                  safe_area_human_verified=False, editorial_approved=False, publication_ready=False)
    save_json(out/(clip['id']+'.render.json'), report)
    return report


def verify_render_dependencies(plan, report, clip):
    """Verify current bytes and bind the report to one planned audiovisual output."""
    if (report.get('id') != clip['id'] or report.get('plan_sha256') != plan['plan_sha256'] or
        report.get('source_sha256') != plan['source_sha256'] or
        report.get('package_sha256') != plan['package_sha256'] or
        report.get('status') != 'TECHNICALLY_VALID_REQUIRES_HUMAN_REVIEW'):
        raise ValueError('RENDER_DEPENDENCY_MISMATCH')
    if not report.get('sha256') or file_sha256(report['file']) != report['sha256']:
        raise ValueError('RENDER_FILE_CHANGED')
    artifacts = report.get('subtitle_artifacts') or {}
    if not artifacts.get('ass'):
        raise ValueError('SUBTITLE_HASH_UNVERIFIED_RE_RENDER_REQUIRED')
    for artifact in artifacts.values():
        if not artifact.get('sha256') or file_sha256(artifact['file']) != artifact['sha256']:
            raise ValueError('SUBTITLE_ARTIFACT_CHANGED')
    return canonical_hash(report)


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
    report_hash = verify_render_dependencies(plan, canary_report, plan['clips'][0])
    if verify_mp4(canary_report['file'], plan['clips'][0]['duration'])['status'] == 'BLOCKED':
        raise ValueError('CANARY_NO_LONGER_VALID')
    return {'schema_version': '9.1', 'plan_sha256': plan['plan_sha256'], 'canary_id': cid,
            'canary_sha256': canary_report['sha256'], 'package_sha256': plan['package_sha256'],
            'source_sha256': plan['source_sha256'], 'reviewer': str(reviewer).strip()[:100],
            'canary_report_sha256': report_hash, 'state': 'PREVIEW_APPROVED',
            'checklist': {k: True for k in CHECKS}, 'approved_at': datetime.now(timezone.utc).isoformat(),
            'batch_authorized': True, 'publication_ready': False}


def verify_approval(plan, approval, canary_report):
    validate_plan(plan)
    if (approval.get('batch_authorized') is not True or not str(approval.get('reviewer') or '').strip() or
        approval.get('canary_id') != plan['clips'][0]['id'] or
        approval.get('canary_report_sha256') != canonical_hash(canary_report) or
        approval.get('plan_sha256') != plan['plan_sha256'] or
        approval.get('canary_sha256') != file_sha256(canary_report['file']) or
        approval.get('source_sha256') != plan['source_sha256'] or
        approval.get('package_sha256') != plan['package_sha256'] or
        any(approval.get('checklist', {}).get(k) is not True for k in CHECKS)):
        raise ValueError('CANARY_APPROVAL_INVALIDATED_OR_INCOMPLETE')
    verify_render_dependencies(plan, canary_report, plan['clips'][0])
    if verify_mp4(canary_report['file'], plan['clips'][0]['duration'])['status'] == 'BLOCKED':
        raise ValueError('CANARY_NO_LONGER_VALID')


def render_batch(plan, approval, canary_report, output_dir, *, draft_captions=False):
    verify_approval(plan, approval, canary_report)
    destination = Path(output_dir).resolve()
    destination.mkdir(parents=True, exist_ok=True)
    reports = []
    for i, row in enumerate(plan['clips']):
        try:
            if i == 0:
                # Reuse the reviewed canary only when its file already has the same
                # planned name in the destination; no silent overwrite/copy.
                if Path(canary_report['file']).resolve() == (destination/(row['id']+'.mp4')):
                    reports.append(canary_report)
                    continue
            if i == 0:
                original = Path(canary_report['file']).resolve()
                copied = destination / (row['id'] + '.mp4')
                if copied.exists() or (destination/(row['id']+'.render.json')).exists():
                    raise FileExistsError('REFUSING_TO_OVERWRITE_REVIEWED_CANARY')
                shutil.copy2(original, copied)
                report = {**canary_report, **verify_mp4(copied, row['duration']),
                          'reused_reviewed_canary': True}
                reports.append(report)
                save_json(destination/(row['id']+'.render.json'), report)
            else:
                reports.append(render_clip(plan, i, destination, draft_captions=draft_captions))
        except (RuntimeError, ValueError, OSError, subprocess.TimeoutExpired) as exc:
            # An item failure must not discard reviewed media or stop later Stories.
            failure = {'id': row['id'], 'candidate_id': row['candidate_id'],
                       'file': str(destination/(row['id']+'.mp4')), 'status': 'BLOCKED',
                       'issues': [type(exc).__name__ + ':' + str(exc)[:1000]],
                       'plan_sha256': plan['plan_sha256'], 'source_sha256': plan['source_sha256'],
                       'package_sha256': plan['package_sha256'], 'sha256': None,
                       'preview_approved': None, 'publish_ready': False, 'publication_ready': False}
            reports.append(failure)
            sidecar = destination/(row['id']+'.render.json')
            if not sidecar.exists():
                save_json(sidecar, failure)
    summary = {'state': 'REVIEW_BATCH_RENDERED_NOT_PUBLISHABLE' if all(x['status'].startswith('TECHNICALLY_VALID') for x in reports)
               else ('PARTIAL' if any(x['status'].startswith('TECHNICALLY_VALID') for x in reports) else 'BLOCKED'), 'plan_sha256': plan['plan_sha256'], 'canary_approval_sha256': canonical_hash(approval),
               'clips': reports, 'publication_ready': False,
               'canary_approval': approval, 'canary_report': canary_report,
               'review_required_per_clip': list(CHECKS),
               'note': 'Each MP4 is independently playable. No batch member is implicitly approved by canary approval.'}
    save_json(destination/'BATCH_REVIEW_MANIFEST.json', summary)
    return summary


def finalize_batch(plan, batch_manifest, reviews):
    """Release file hashes only after independent human approval of every MP4."""
    validate_plan(plan)
    if batch_manifest.get('state') != 'REVIEW_BATCH_RENDERED_NOT_PUBLISHABLE' or batch_manifest.get('plan_sha256') != plan['plan_sha256']:
        raise ValueError('BATCH_NOT_READY_FOR_FINAL_REVIEW')
    verify_approval(plan, batch_manifest.get('canary_approval') or {}, batch_manifest.get('canary_report') or {})
    if batch_manifest.get('canary_approval_sha256') != canonical_hash(batch_manifest['canary_approval']):
        raise ValueError('BATCH_CANARY_APPROVAL_CHANGED')
    expected_ids = [c['id'] for c in plan['clips']]
    actual_ids = [c['id'] for c in batch_manifest.get('clips', [])]
    if not expected_ids or len(set(actual_ids)) != len(actual_ids) or set(actual_ids) != set(expected_ids):
        raise ValueError('BATCH_MEMBERSHIP_MISMATCH')
    approved = {entry['id']: entry for entry in reviews.get('clips', [])}
    if len(approved) != len(reviews.get('clips', [])) or set(approved) != set(expected_ids):
        raise ValueError('MISSING_PER_CLIP_APPROVAL')
    for clip in batch_manifest['clips']:
        row = next(x for x in plan['clips'] if x['id'] == clip['id'])
        report_hash = verify_render_dependencies(plan, clip, row)
        decision = approved.get(clip['id'])
        if (not decision or decision.get('sha256') != file_sha256(clip['file']) or
            decision.get('plan_sha256') != plan['plan_sha256'] or
            decision.get('render_report_sha256') != report_hash or
            any(decision.get('checklist', {}).get(key) is not True for key in CHECKS) or
            not str(decision.get('reviewer') or '').strip()):
            raise ValueError('CRITICAL_PER_CLIP_REVIEW_PENDING:' + clip['id'])
        if verify_mp4(clip['file'], next(x['duration'] for x in plan['clips'] if x['id'] == clip['id']))['status'] == 'BLOCKED':
            raise ValueError('CRITICAL_RENDER_FAILURE:' + clip['id'])
    return {'state': 'REVIEWED_FINAL_FILES', 'publication_ready': False,
            'publication_is_separate_manual_action': True, 'plan_sha256': plan['plan_sha256'],
            'files': [{'id': c['id'], 'sha256': file_sha256(c['file']), 'path': c['file']} for c in batch_manifest['clips']],
            'review_completed_at': datetime.now(timezone.utc).isoformat()}
