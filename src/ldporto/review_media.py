"""Hash-bound, read-only access to curator media. Resolving never approves it."""
import html
import json
import math
from pathlib import Path, PurePosixPath
import re

from .core import file_hash


def _sha(value):
    return isinstance(value, str) and re.fullmatch(r'[0-9a-f]{64}', value) is not None


def _interval(start, end):
    return (all(isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)
                for v in (start, end)) and 0 <= start < end)


def _relative(value):
    if not isinstance(value, str) or '\\' in value or ':' in value:
        raise ValueError('unsafe_media_reference')
    path = PurePosixPath(value)
    if path.is_absolute() or not path.parts or any(p in ('..', '.') for p in value.split('/')):
        raise ValueError('unsafe_media_reference')
    return path


def build_source_media_references(metadata, candidate, preview_manifest=None):
    """Bind by source hash, candidate ID AND interval; paths alone prove nothing."""
    start, end = candidate.get('start'), candidate.get('end')
    source_hash = metadata.get('sha256')
    if not _sha(source_hash) or not _interval(start, end):
        return None
    previews = []
    manifest = preview_manifest or {}
    if manifest.get('source_sha256') == source_hash:
        for row in manifest.get('results') or []:
            if (row.get('candidate_id') != candidate.get('candidate_id') or
                    not _interval(row.get('start'), row.get('end')) or
                    row['start'] != start or row['end'] != end or
                    not _sha(row.get('sha256')) or type(row.get('bytes')) is not int or row['bytes'] <= 0):
                continue
            relative = str(row.get('preview_path', '')).replace('\\', '/')
            _relative(relative)
            previews.append({'locator': {'type': 'relative_to_review_media_root', 'path': relative},
                'sha256': row['sha256'], 'bytes': row['bytes'], 'source_sha256': source_hash,
                'candidate_id': candidate['candidate_id'], 'start': start, 'end': end,
                'observed_video_duration': row.get('observed_video_duration'),
                'layout': row.get('layout'), 'resolution': row.get('output_resolution'),
                'audio': row.get('audio'), 'preview_approved': False, 'audio_verified': None,
                'publication_ready': False})
    return {'schema_version': '1.0', 'candidate_id': candidate.get('candidate_id'),
        'source_sha256': source_hash, 'source_interval': {'start': start, 'end': end},
        'original_video': {'locator': {'type': 'source_sha256', 'sha256': source_hash},
                           'media_fragment': f'#t={start},{end}'},
        'original_audio': {'locator': {'type': 'source_sha256', 'sha256': source_hash},
                           'kind': 'original_video_audio_stream', 'media_fragment': f'#t={start},{end}'},
        'existing_previews': previews, 'media_included': False,
        'human_audio_verified': None, 'preview_approved': False, 'publication_ready': False}


def validate_media_references(refs, metadata, candidate):
    """Check portable bindings without claiming to have inspected external media."""
    expected = build_source_media_references(metadata, candidate)
    if expected is None or not isinstance(refs, dict):
        return ['invalid_source_media_binding']
    actual = {**refs, 'existing_previews': []}
    errors = [] if actual == expected else ['source_media_binding_disagreement']
    for row in refs.get('existing_previews') or []:
        try:
            _relative(row['locator']['path'])
            if (row['locator']['type'] != 'relative_to_review_media_root' or
                    row['candidate_id'] != candidate['candidate_id'] or
                    row['source_sha256'] != metadata.get('sha256') or
                    (row['start'], row['end']) != (candidate['start'], candidate['end']) or
                    not _sha(row['sha256']) or type(row['bytes']) is not int or row['bytes'] <= 0 or
                    row.get('preview_approved') is not False or row.get('publication_ready') is not False):
                raise ValueError('preview_binding')
        except (KeyError, TypeError, ValueError):
            errors.append('invalid_preview_binding')
    return errors


def resolve_review_media(refs, original_path=None, kind='video', preview_root=None, preview_index=0):
    if kind not in {'video', 'audio', 'preview'}:
        raise ValueError('unsupported_review_media_kind')
    interval = refs.get('source_interval') or {}
    if not _interval(interval.get('start'), interval.get('end')) or not _sha(refs.get('source_sha256')):
        raise ValueError('invalid_source_media_binding')
    if kind == 'preview':
        row = refs['existing_previews'][preview_index]
        if (row['source_sha256'] != refs['source_sha256'] or row['candidate_id'] != refs['candidate_id'] or
                (row['start'], row['end']) != (interval['start'], interval['end'])):
            raise ValueError('preview_source_disagreement')
        root = Path(preview_root).resolve(strict=True)
        relative = _relative(row['locator']['path'])
        path = root.joinpath(*relative.parts)
        # Reject junction/symlink escapes, including ancestors, before reading.
        for parent in [path, *path.parents]:
            if parent == root:
                break
            if parent.is_symlink() or getattr(parent.lstat(), 'st_file_attributes', 0) & 0x400:
                raise ValueError('unsafe_media_reference')
        path = path.resolve(strict=True)
        if not path.is_relative_to(root) or path.stat().st_size != row['bytes']:
            raise ValueError('preview_size_or_path_disagreement')
        expected = row['sha256']
        start, end = 0, interval['end'] - interval['start']
    else:
        path = Path(original_path).resolve(strict=True)
        expected = refs['source_sha256']
        start, end = interval['start'], interval['end']
    if not _sha(expected) or not path.is_file() or file_hash(path) != expected:
        raise ValueError('review_media_hash_disagreement')
    return {'path': path, 'start': start, 'end': end, 'kind': kind,
            'sha256': expected, 'candidate_id': refs['candidate_id'], 'publication_ready': False}


def review_player_html(resolved):
    """Local player with exact initial seek and bounded playback; no autoplay."""
    tag = 'audio' if resolved['kind'] == 'audio' else 'video'
    start, end = resolved['start'], resolved['end']
    if not _interval(start, end):
        raise ValueError('invalid_player_interval')
    uri = html.escape(resolved['path'].as_uri() + f'#t={start},{end}', quote=True)
    label = html.escape(str(resolved['candidate_id']))
    timing = json.dumps({'start': start, 'end': end}, allow_nan=False)
    return (f'<!doctype html><meta charset="utf-8"><title>Revisão {label}</title>'
        f'<h1>{label}</h1><p>Revisão pendente. Abrir ou assistir não aprova a prévia ou a publicação.</p>'
        f'<p>Intervalo de reprodução: {start:.2f}–{end:.2f} s. SHA-256: {resolved["sha256"]}</p>'
        f'<{tag} id="media" controls preload="metadata" style="max-width:100%" src="{uri}"></{tag}>'
        '<script>const m=document.getElementById("media"),t=' + timing + ';'
        'm.addEventListener("loadedmetadata",()=>{m.currentTime=t.start});'
        'm.addEventListener("play",()=>{if(m.currentTime<t.start||m.currentTime>=t.end)m.currentTime=t.start});'
        'm.addEventListener("timeupdate",()=>{if(m.currentTime>=t.end)m.pause()});</script>')
