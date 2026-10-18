"""Independent, read-only reconstruction of an R6.3 compact ZIP.

The reader deliberately imports neither the exporter nor local analysis/media
resolvers. Every reconstructed reference must resolve inside the supplied ZIP.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import io
import json
import math
from pathlib import Path, PurePosixPath
import re
import stat
import zipfile


ROOT_FILES = {'MANIFEST.json', 'FILE_INDEX.json', 'checksums.sha256'}
MAX_MEMBERS = 10000
MAX_FILE_BYTES = 64 * 1024 * 1024
MAX_UNCOMPRESSED_BYTES = 512 * 1024 * 1024
ALLOWED_SUFFIXES = {'.json', '.jsonl', '.txt', '.md', '.jpg', '.jpeg', '.webp', '.png', '.pdf', '.sha256'}
NAVIGATION_KEYS = ('scene_index', 'reels_index', 'series_index', 'segments', 'words',
                   'trajectories', 'atlas_index', 'camera_decisions', 'safe_areas',
                   'coverage', 'limitations')
PIECE_REFERENCES = {'editorial_ref': 'editorial', 'source_intervals_ref': 'source_intervals',
                    'visual_storyboard_ref': 'visual_storyboard', 'camera_geometry_ref': 'camera_geometry',
                    'caption_evidence_ref': 'caption_evidence'}
COUNT_KEYS = ('scene_count', 'shot_count', 'reel_count', 'story_part_count', 'series_count',
              'frame_count', 'contact_sheet_count', 'trajectory_count', 'segment_count', 'word_count')
ID_REFERENCES = {
    'scene_id': 'scenes', 'scene_ids': 'scenes',
    'frame_id': 'frames', 'frame_ids': 'frames', 'representative_frames': 'frames',
    'thumbnail_frame_ids': 'frames', 'selected_frame_ids': 'frames',
    'trajectory_id': 'trajectories', 'trajectory_ids': 'trajectories',
    'decision_id': 'decisions', 'decision_ids': 'decisions',
    'region_id': 'safe_areas', 'safe_area_ids': 'safe_areas',
    'segment_id': 'segments', 'segment_ids': 'segments', 'canonical_segment_ids': 'segments',
    'source_segment_ids': 'segments', 'transcript_segment_ids': 'segments', 'context_segment_ids': 'segments',
    'word_id': 'words', 'word_ids': 'words',
    'canonical_word_ids': 'words', 'candidate_id': 'candidates', 'candidate_ids': 'candidates',
    'series_id': 'series', 'series_ids': 'series', 'story_id': 'parts', 'story_ids': 'parts',
    'part_id': 'parts', 'part_ids': 'parts', 'previous_part_id': 'parts', 'next_part_id': 'parts',
    'source_unit_id': 'parts', 'unit_id': 'parts', 'unit_ids': 'parts',
    'source_shot_id': 'shots', 'shot_id': 'shots', 'shot_ids': 'shots',
}
APPROVAL_FLAGS = {'preview_approved', 'human_approved', 'publication_ready', 'publish_ready'}
HASH_RE = re.compile(r'^[a-fA-F0-9]{64}$')


def _sha(payload):
    return hashlib.sha256(payload).hexdigest()


def _records_digest(value):
    return _sha(json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False,
                           separators=(',', ':')).encode('utf8'))


def _number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _safe_path(value):
    if not isinstance(value, str) or not value or value != value.strip():
        return False
    if any(ord(c) < 32 for c in value) or '\\' in value or ':' in value:
        return False
    path = PurePosixPath(value)
    return (not path.is_absolute() and all(p not in {'', '.', '..'} for p in value.split('/'))
            and path.as_posix() == value)


def _unique_json_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate JSON key: ' + key)
        result[key] = value
    return result


def _json(payload):
    def invalid_constant(value):
        raise ValueError('non-finite JSON constant: ' + value)
    return json.loads(payload.decode('utf-8-sig'), object_pairs_hook=_unique_json_keys,
                      parse_constant=invalid_constant)


class _Reader:
    def __init__(self):
        self.errors = []
        self.files = {}
        self.documents = {}
        self.source = {}
        self.tables = {}
        self.counts = {}
        self.trajectory_index = None
        self.trajectory_shard_count = 0

    def error(self, code, location, detail):
        if len(self.errors) < 2000:
            self.errors.append(f'{code}:{location}:{detail}')

    def document(self, name, *, required=True):
        if not _safe_path(name) or name not in self.files:
            if required:
                self.error('missing_reference', str(name), 'file must exist inside ZIP')
            return {}
        if name not in self.documents:
            try:
                self.documents[name] = _json(self.files[name])
            except (ValueError, UnicodeError) as exc:
                self.error('invalid_json', name, str(exc))
                self.documents[name] = {}
        value = self.documents[name]
        if not isinstance(value, dict):
            self.error('invalid_document', name, 'expected object')
            return {}
        return value

    def rows(self, doc, key, location):
        rows = doc.get(key)
        if not isinstance(rows, list) or any(not isinstance(r, dict) for r in rows):
            self.error('invalid_rows', location, f'{key} must be an array of objects')
            return []
        return rows

    def trajectory_rows(self, doc, location):
        if doc.get('storage') != 'indexed_shards':
            return self.rows(doc, 'trajectories', location)
        if doc.get('trajectories'):
            self.error('duplicate_geometry_storage', location, 'indexed shards must be the only coordinate storage')
        mapping = doc.get('trajectory_index')
        if not isinstance(mapping, dict) or any(not isinstance(k, str) or not _safe_path(v) for k, v in mapping.items()):
            self.error('invalid_trajectory_index', location, 'trajectory ID to shard path mapping is required')
            mapping = {}
        self.trajectory_index = mapping
        output, paths, actual_mapping = [], set(), {}
        for shard in self.rows(doc, 'shards', location):
            name = shard.get('path')
            if (not _safe_path(name) or not name.startswith('03_PEOPLE/trajectories/')
                    or not name.endswith('.json') or name in paths):
                self.error('invalid_trajectory_shard_path', location, repr(name))
                continue
            paths.add(name)
            if name not in self.files or shard.get('bytes') != len(self.files.get(name, b'')) or shard.get('sha256') != _sha(self.files.get(name, b'')):
                self.error('trajectory_shard_checksum', name, 'bytes or SHA256 differs from shard ledger')
                continue
            rows = self.rows(self.document(name), 'trajectories', name)
            identifiers = [r.get('trajectory_id') for r in rows]
            declared = shard.get('trajectory_ids')
            if (not isinstance(declared, list) or any(not isinstance(i, str) for i in declared)
                    or len(declared) != len(set(declared)) or set(declared) != set(identifiers)):
                self.error('trajectory_shard_inventory', name, 'declared trajectory IDs must match shard contents exactly')
            for identifier in identifiers:
                if not isinstance(identifier, str) or identifier in actual_mapping:
                    self.error('duplicate_sharded_trajectory', name, repr(identifier))
                else:
                    actual_mapping[identifier] = name
            output.extend(rows)
        if mapping != actual_mapping:
            self.error('trajectory_index_completeness', location, 'every trajectory must map to its exact unique shard')
        self.trajectory_shard_count = len(paths)
        return output

    def table(self, rows, keys, kind):
        result = {}
        for i, row in enumerate(rows):
            identifier = next((row[k] for k in keys if row.get(k) is not None), None)
            if not isinstance(identifier, str) or not identifier or identifier in result:
                self.error('invalid_or_duplicate_id', kind, f'row {i}: {identifier!r}')
            else:
                result[identifier] = row
        self.tables[kind] = result
        return result

    def interval(self, row, location, *, zero_allowed=False):
        a, b = row.get('start'), row.get('end')
        if not (_number(a) and _number(b) and 0 <= a <= b <= self.source['duration']
                and (zero_allowed or a < b)):
            self.error('invalid_interval', location, 'expected finite source interval within duration')
            return False
        return True

    def bbox(self, box, location):
        if not isinstance(box, dict) or not all(_number(box.get(k)) for k in ('x', 'y', 'width', 'height')):
            self.error('invalid_bbox', location, 'expected finite normalized x/y/width/height')
            return
        x, y, w, h = (box[k] for k in ('x', 'y', 'width', 'height'))
        if min(x, y) < 0 or min(w, h) <= 0 or x+w > 1.000001 or y+h > 1.000001:
            self.error('invalid_bbox', location, 'rectangle leaves normalized source')

    def load(self, path):
        with zipfile.ZipFile(path) as archive:
            members = archive.infolist()
            if len(members) > MAX_MEMBERS or sum(m.file_size for m in members) > MAX_UNCOMPRESSED_BYTES:
                self.error('archive_limit', 'ZIP', 'entry count or uncompressed size exceeds bound')
                return
            seen = set()
            for member in members:
                name = member.filename
                check_name = name[:-1] if member.is_dir() else name
                if not _safe_path(check_name) or name.casefold() in seen:
                    self.error('unsafe_or_duplicate_path', name, 'path must be unique relative POSIX path')
                    continue
                seen.add(name.casefold())
                mode = member.external_attr >> 16
                if (stat.S_ISLNK(mode) or stat.S_IFMT(mode) not in {0, stat.S_IFREG, stat.S_IFDIR}
                        or member.flag_bits & 1):
                    self.error('unsafe_member', name, 'links, special files and encryption are unsupported')
                    continue
                if member.is_dir():
                    continue
                if member.file_size > MAX_FILE_BYTES or PurePosixPath(name).suffix.lower() not in ALLOWED_SUFFIXES:
                    self.error('invalid_member', name, 'unsupported payload type or file size')
                    continue
                self.files[name] = archive.read(member)
        if not ROOT_FILES <= self.files.keys():
            self.error('missing_root_contract', 'ZIP', str(sorted(ROOT_FILES-self.files.keys())))

    def integrity(self):
        manifest = self.document('MANIFEST.json')
        index = self.document('FILE_INDEX.json')
        if manifest.get('schema_version') != 'r6.3' or manifest.get('profile') != 'SECOND_CURATION_COMPACT':
            self.error('invalid_schema', 'MANIFEST.json', 'expected r6.3 SECOND_CURATION_COMPACT')
        if not isinstance(manifest.get('revision'), str) or not manifest['revision'].strip():
            self.error('missing_revision', 'MANIFEST.json', 'non-empty revision required')
        if (manifest.get('state') != 'PARTIAL' or
                any(manifest.get(k) is not False for k in ('preview_approved', 'human_approved', 'publication_ready'))):
            self.error('approval_gate', 'MANIFEST.json', 'compact evidence is PARTIAL without approvals')
        if manifest.get('file_index_ref') != 'FILE_INDEX.json' or manifest.get('checksums_ref') != 'checksums.sha256':
            self.error('invalid_root_reference', 'MANIFEST.json', 'root integrity references are fixed')
        if manifest.get('file_index_sha256') != _sha(self.files.get('FILE_INDEX.json', b'')):
            self.error('file_index_hash', 'MANIFEST.json', 'FILE_INDEX SHA256 differs')
        source = manifest.get('source')
        if not isinstance(source, dict):
            self.error('source_identity', 'MANIFEST.json', 'source object required')
            return manifest
        if not isinstance(source.get('sha256'), str) or not HASH_RE.fullmatch(source['sha256']):
            self.error('source_identity', 'MANIFEST.json', 'full SHA256 required; filename is not identity')
        if not all(_number(source.get(k)) and source[k] > 0 for k in ('duration', 'width', 'height', 'fps')):
            self.error('source_dimensions', 'MANIFEST.json', 'finite positive duration/dimensions/fps required')
        if source.get('video_id') is not None and not isinstance(source['video_id'], str):
            self.error('source_identity', 'MANIFEST.json', 'video_id must be string or null')
        if source.get('title') is not None and not isinstance(source['title'], str):
            self.error('source_identity', 'MANIFEST.json', 'title must be string or null')
        self.source = source
        listed = {}
        for row in self.rows(index, 'files', 'FILE_INDEX.json'):
            name = row.get('path')
            if not _safe_path(name) or name in listed or name in ROOT_FILES:
                self.error('invalid_index_path', 'FILE_INDEX.json', repr(name))
                continue
            listed[name] = row
            if (not isinstance(row.get('bytes'), int) or isinstance(row.get('bytes'), bool) or row['bytes'] < 0
                    or not isinstance(row.get('sha256'), str) or not HASH_RE.fullmatch(row['sha256'])
                    or not isinstance(row.get('category'), str) or not row['category']):
                self.error('invalid_file_index_row', name, 'bytes, SHA256 and category are required')
            if name not in self.files:
                self.error('missing_indexed_file', name, 'payload is absent')
            elif row.get('bytes') != len(self.files[name]) or row.get('sha256') != _sha(self.files[name]):
                self.error('payload_checksum', name, 'bytes or SHA256 differs from FILE_INDEX')
        if set(listed) != set(self.files)-ROOT_FILES:
            self.error('file_index_completeness', 'FILE_INDEX.json', 'index must cover every payload exactly once')
        checksums = {}
        try:
            for line in self.files.get('checksums.sha256', b'').decode('utf8').splitlines():
                match = re.fullmatch(r'([a-fA-F0-9]{64})[ \t]+\*?(.+)', line)
                if not match or not _safe_path(match[2]) or match[2] in checksums:
                    self.error('invalid_checksum_line', 'checksums.sha256', line[:180])
                    continue
                checksums[match[2]] = match[1].lower()
        except UnicodeError as exc:
            self.error('invalid_checksums', 'checksums.sha256', str(exc))
        if set(checksums) != set(self.files)-{'checksums.sha256'}:
            self.error('checksum_completeness', 'checksums.sha256', 'must cover payload, MANIFEST and FILE_INDEX')
        for name, checksum in checksums.items():
            if name in self.files and checksum != _sha(self.files[name]):
                self.error('archive_checksum', name, 'SHA256 differs from checksums.sha256')
        return manifest

    def scan(self, value, location):
        if isinstance(value, dict):
            for key, child in value.items():
                here = f'{location}/{key}'
                if key in APPROVAL_FLAGS and child is True:
                    self.error('approval_gate', here, 'evidence export cannot create approval')
                if key == 'source_sha256' and child != self.source['sha256']:
                    self.error('source_identity', here, 'source SHA256 differs from MANIFEST')
                if key in ID_REFERENCES and child is not None:
                    values = child if isinstance(child, list) else [child]
                    table = self.tables.get(ID_REFERENCES[key], {})
                    for identifier in values:
                        if not isinstance(identifier, str) or identifier not in table:
                            self.error('unresolved_id', here, repr(identifier))
                coordinate_declaration = (here.endswith('/coordinate_contract/bbox') and
                                          child == 'normalized_source_xywh')
                if key in {'bbox', 'face_bbox', 'body_bbox', 'head_bbox', 'rect_start', 'rect_end', 'crop_rect'} and child is not None and not coordinate_declaration:
                    self.bbox(child, here)
                elif key == 'crop' and isinstance(child, dict) and {'x', 'y', 'width', 'height'} <= child.keys():
                    self.bbox(child, here)
                if (key.endswith('_ref') and isinstance(child, str) and
                        ('/' in child or PurePosixPath(child).suffix.lower() in ALLOWED_SUFFIXES)):
                    filename, separator, fragment = child.partition('#')
                    if not _safe_path(filename) or filename not in self.files:
                        self.error('unresolved_file_reference', here, child)
                    elif separator and fragment:
                        target = self.document(filename)
                        components = fragment[1:].split('/') if fragment.startswith('/') else [fragment]
                        try:
                            for component in components:
                                component = component.replace('~1', '/').replace('~0', '~')
                                target = target[int(component)] if isinstance(target, list) else target[component]
                        except (KeyError, IndexError, ValueError, TypeError):
                            self.error('unresolved_json_fragment', here, child)
                if key.endswith('_refs') and isinstance(child, list):
                    for reference in child:
                        if isinstance(reference, str) and ('/' in reference or PurePosixPath(reference).suffix.lower() in ALLOWED_SUFFIXES):
                            filename = reference.partition('#')[0]
                            if not _safe_path(filename) or filename not in self.files:
                                self.error('unresolved_file_reference', here, reference)
                if key == 'confidence' and child is not None and (not _number(child) or not 0 <= child <= 1):
                    self.error('invalid_confidence', here, repr(child))
                self.scan(child, here)
        elif isinstance(value, list):
            for i, child in enumerate(value):
                self.scan(child, f'{location}/{i}')

    def _piece(self, row, kind, index):
        docs = {}
        for ref, key in PIECE_REFERENCES.items():
            docs[key] = self.document(row.get(ref))
        identifier = next((row[k] for k in ('candidate_id', 'reel_id', 'story_id', 'part_id', 'id') if row.get(k)), None)
        intervals = self.rows(docs['source_intervals'], 'intervals', f'{kind}/{identifier}')
        if not intervals:
            self.error('empty_piece_intervals', f'{kind}/{identifier}', 'source mapping is required')
        cursor = 0.
        for i, interval in enumerate(intervals):
            self.interval(interval, f'{kind}/{identifier}/interval/{i}')
            a, b = interval.get('clip_start'), interval.get('clip_end')
            if not (_number(a) and _number(b) and abs(a-cursor) < 1e-5
                    and abs((b-a)-(interval.get('end', 0)-interval.get('start', 0))) < 1e-5):
                self.error('invalid_clip_mapping', f'{kind}/{identifier}/interval/{i}', 'relative clip times must be contiguous and preserve duration')
            if _number(b):
                cursor = b
        beats = self.rows(docs['visual_storyboard'], 'beats', f'{kind}/{identifier}/storyboard')
        for i, beat in enumerate(beats):
            if not self.interval(beat, f'{kind}/{identifier}/beat/{i}'):
                continue
            parent = next((r for r in intervals if _number(r.get('start')) and _number(r.get('end'))
                           and r['start'] <= beat['start'] < beat['end'] <= r['end']+1e-6), None)
            if not parent:
                self.error('beat_outside_piece', f'{kind}/{identifier}/beat/{i}', 'beat cannot bridge source gaps')
            elif not (all(_number(beat.get(k)) for k in ('clip_start', 'clip_end')) and
                      abs(beat['clip_start']-(parent['clip_start']+beat['start']-parent['start'])) < 1e-5 and
                      abs(beat['clip_end']-(parent['clip_start']+beat['end']-parent['start'])) < 1e-5):
                self.error('invalid_beat_mapping', f'{kind}/{identifier}/beat/{i}', 'absolute and clip-relative times disagree')
        for name, doc in docs.items():
            if doc.get('piece_id') not in {None, identifier}:
                self.error('piece_identity', f'{kind}/{identifier}/{name}', 'piece_id differs from index')
            self.scan(doc, f'{kind}/{identifier}/{name}')
        if self.trajectory_index is not None:
            geometry = docs['camera_geometry']
            required_shards = {self.trajectory_index[tid] for tid in geometry.get('trajectory_ids', [])
                               if tid in self.trajectory_index}
            declared_shards = geometry.get('trajectory_shard_refs')
            if (not isinstance(declared_shards, list) or len(declared_shards) != len(set(declared_shards))
                    or set(declared_shards) != required_shards):
                self.error('piece_trajectory_shard_inventory', f'{kind}/{identifier}', 'piece shard refs must match its trajectory IDs exactly')
        collected = {key: set() for key in self.tables}
        def collect(value):
            if isinstance(value, dict):
                for key, child in value.items():
                    if key in ID_REFERENCES:
                        values = child if isinstance(child, list) else [child]
                        collected[ID_REFERENCES[key]].update(v for v in values if isinstance(v, str))
                    collect(child)
            elif isinstance(value, list):
                for child in value:
                    collect(child)
        collect(docs)
        collect(row)
        for fid in collected['frames']:
            frame = self.tables['frames'].get(fid, {})
            t = frame.get('source_time_s')
            if _number(t) and not any(r.get('start', math.inf) <= t < r.get('end', -math.inf) for r in intervals):
                self.error('frame_outside_piece', f'{kind}/{identifier}', fid)
        # Share the already validated global rows instead of duplicating large
        # coordinate collections for overlapping Reels and Story proposals.
        resolved = {key: [self.tables[key][rid] for rid in sorted(ids) if rid in self.tables[key]]
                    for key, ids in collected.items() if ids}
        return {'index': deepcopy(row), **deepcopy(docs), 'resolved': resolved}

    def reconstruct(self, manifest):
        nav = self.document('00_OVERVIEW/navigation_index.json')
        entries = nav.get('entries')
        if not isinstance(entries, dict):
            self.error('navigation_contract', 'navigation_index.json', 'entries object is required')
            return {}
        docs = {key: self.document(entries.get(key)) for key in NAVIGATION_KEYS}
        scenes = self.rows(docs['scene_index'], 'scenes', entries.get('scene_index'))
        reels = self.rows(docs['reels_index'], 'reels', entries.get('reels_index'))
        parts = self.rows(docs['series_index'], 'parts', entries.get('series_index'))
        series = self.rows(docs['series_index'], 'series', entries.get('series_index'))
        segments = self.rows(docs['segments'], 'segments', entries.get('segments'))
        words = self.rows(docs['words'], 'words', entries.get('words'))
        trajectories = self.trajectory_rows(docs['trajectories'], entries.get('trajectories'))
        frames = self.rows(docs['atlas_index'], 'frames', entries.get('atlas_index'))
        sheets = self.rows(docs['atlas_index'], 'contact_sheets', entries.get('atlas_index'))
        decisions = self.rows(docs['camera_decisions'], 'decisions', entries.get('camera_decisions'))
        regions = self.rows(docs['safe_areas'], 'regions', entries.get('safe_areas'))
        for rows, keys, kind in [(scenes, ('scene_id',), 'scenes'), (reels, ('candidate_id', 'reel_id', 'id'), 'candidates'),
            (parts, ('story_id', 'part_id', 'id'), 'parts'), (series, ('series_id', 'id'), 'series'),
            (segments, ('segment_id',), 'segments'), (words, ('word_id',), 'words'),
            (trajectories, ('trajectory_id',), 'trajectories'), (frames, ('frame_id',), 'frames'),
            (decisions, ('decision_id',), 'decisions'), (regions, ('region_id',), 'safe_areas')]:
            self.table(rows, keys, kind)
        shot_ids = set()
        for scene in scenes:
            self.interval(scene, 'scene/' + str(scene.get('scene_id')))
            value = scene.get('shot_ids')
            if not isinstance(value, list) or any(not isinstance(v, str) or not v for v in value):
                self.error('missing_shot_index', str(scene.get('scene_id')), 'shot_ids array required, including when empty')
            else:
                shot_ids.update(value)
        self.tables['shots'] = {sid: {'shot_id': sid} for sid in shot_ids}
        if entries.get('shot_transitions'):
            shot_doc = self.document(entries['shot_transitions'])
            shot_rows = self.rows(shot_doc, 'shots', entries['shot_transitions'])
            actual_shots = self.table(shot_rows, ('shot_id',), 'shots')
            if set(actual_shots) != shot_ids:
                self.error('shot_index_completeness', entries['shot_transitions'], 'all shots must be associated with source scenes')
            for shot in shot_rows:
                self.interval(shot, 'shot/' + str(shot.get('shot_id')))
        for i, row in enumerate(segments):
            self.interval(row, f'segment/{i}')
            if not isinstance(row.get('text'), str):
                self.error('transcript_text', f'segment/{i}', 'canonical literal text must be a string')
        for i, row in enumerate(words):
            self.interval(row, f'word/{i}', zero_allowed=True)
            if not isinstance(row.get('word', row.get('text')), str):
                self.error('transcript_text', f'word/{i}', 'canonical token must be a string')
        for kind, rows, declaration, document in [
                ('segments', segments, 'segments_digest', docs['segments']),
                ('words', words, 'words_digest', docs['words'])]:
            expected = (manifest.get('canonical_transcript') or {}).get(declaration)
            calculated = _records_digest(rows)
            if expected is not None and expected != calculated:
                self.error('canonical_transcript_digest', kind, 'records differ from declared canonical content')
            if document.get('canonical_records_sha256') not in {None, calculated}:
                self.error('canonical_transcript_digest', kind, 'document records checksum differs')
        for row in trajectories:
            loc = 'trajectory/' + str(row.get('trajectory_id'))
            self.interval(row, loc, zero_allowed=True)
            shot = self.tables['shots'].get(row.get('source_shot_id'), {})
            shot_scenes = ([shot] if 'start' in shot and 'end' in shot else
                [scene for scene in scenes if row.get('source_shot_id') in scene.get('shot_ids', [])])
            if row.get('source_shot_id') is not None and not any(
                    scene['start']-1e-6 <= row.get('start', -1) <= row.get('end', math.inf) <= scene['end']+1e-6
                    for scene in shot_scenes if _number(scene.get('start')) and _number(scene.get('end'))):
                self.error('trajectory_crosses_shot', loc, 'trajectory validity must stay within its declared source shot scene')
            keys = self.rows(row, 'keyframes', loc)
            previous = -math.inf
            for key in keys:
                time = key.get('source_time_s')
                if not (_number(time) and row.get('start', math.inf) <= time <= row.get('end', -math.inf) and time > previous):
                    self.error('invalid_trajectory_keyframe_time', loc, 'keyframes must be ordered within validity interval')
                if _number(time):
                    previous = time
                self.bbox(key.get('bbox'), loc + '/keyframe')
            if not keys:
                self.error('empty_trajectory', loc, 'no measured coordinates')
        for row in decisions:
            loc = 'decision/' + str(row.get('decision_id'))
            self.interval(row, loc)
            camera = row.get('camera') or {}
            previous = -math.inf
            for key in camera.get('keyframes', []):
                time = key.get('time', key.get('source_time_s'))
                center = key.get('center')
                if not (_number(time) and 0 <= time <= self.source['duration'] and time > previous):
                    self.error('invalid_camera_keyframe_time', loc, 'absolute source keyframes must be ordered')
                if _number(time):
                    previous = time
                if not isinstance(center, list) or len(center) != 2 or not all(_number(v) and 0 <= v <= 1 for v in center):
                    self.error('invalid_camera_center', loc, 'normalized center required')
                if not _number(key.get('zoom')) or key['zoom'] < 1:
                    self.error('invalid_camera_zoom', loc, 'finite zoom >=1 required')
        image_paths_by_hash = {}
        for row in frames:
            previous = image_paths_by_hash.setdefault(row.get('sha256'), row.get('path'))
            if previous != row.get('path'):
                self.error('duplicate_image_payload', str(row.get('frame_id')), 'same image bytes must use one shared path')
        for row in frames + sheets:
            name = row.get('path')
            if not _safe_path(name) or name not in self.files or row.get('sha256') != _sha(self.files.get(name, b'')):
                self.error('atlas_asset', str(name), 'image reference/hash is unresolved')
                continue
            is_frame = row in frames
            try:
                from PIL import Image
                with Image.open(io.BytesIO(self.files[name])) as im:
                    size = im.size
                    im.verify()
            except Exception as exc:
                self.error('frame_decode' if is_frame else 'contact_sheet_decode', str(name), str(exc))
                continue
            if is_frame:
                if not _number(row.get('source_time_s')) or not 0 <= row['source_time_s'] < self.source['duration']:
                    self.error('frame_time', str(name), 'frame must be inside original source')
                if row.get('source_sha256') != self.source['sha256']:
                    self.error('source_identity', str(name), 'frame belongs to another source')
                if tuple(size) != (row.get('width'), row.get('height')):
                    self.error('frame_dimensions', str(name), 'encoded image dimensions differ from atlas')
                if abs(size[0]/size[1]-self.source['width']/self.source['height']) > .02:
                    self.error('frame_aspect', str(name), 'source aspect ratio must be preserved')
        for name, payload in self.files.items():
            if name.endswith('.json'):
                self.document(name)
        for name, doc in self.documents.items():
            if name not in {'MANIFEST.json', 'FILE_INDEX.json'}:
                self.scan(doc, name)
        self.counts = {'scene_count': len(scenes), 'shot_count': len(self.tables['shots']), 'reel_count': len(reels),
            'story_part_count': len(parts), 'series_count': len(series), 'frame_count': len(frames),
            'contact_sheet_count': len(sheets), 'trajectory_count': len(trajectories),
            'segment_count': len(segments), 'word_count': len(words), 'decision_count': len(decisions),
            'safe_area_count': len(regions), 'file_count': len(self.files)}
        self.counts['trajectory_shard_count'] = self.trajectory_shard_count
        declarations = [('MANIFEST.json', manifest.get('declared_counts')),
                        (entries.get('coverage'), docs['coverage'].get('declared_counts', docs['coverage']))]
        for location, counts in declarations:
            if not isinstance(counts, dict):
                self.error('missing_declared_counts', str(location), 'inventory declaration required')
                continue
            for key in COUNT_KEYS:
                if key not in counts:
                    self.error('missing_declared_count', str(location), key)
            for key, actual in self.counts.items():
                if key in counts and (isinstance(counts[key], bool) or counts[key] != actual):
                    self.error('declared_count_mismatch', str(location), f'{key}: declared={counts[key]!r}, actual={actual}')
        rebuilt_reels = {cid: self._piece(row, 'reel', i) for i, (cid, row) in enumerate(self.tables['candidates'].items())}
        rebuilt_parts = {sid: self._piece(row, 'story', i) for i, (sid, row) in enumerate(self.tables['parts'].items())}
        return {'source': deepcopy(self.source), 'scene_index': deepcopy(self.tables['scenes']),
            'candidate_index': rebuilt_reels, 'story_index': {'series': deepcopy(self.tables['series']), 'parts': rebuilt_parts},
            'transcript': {'segments': deepcopy(self.tables['segments']), 'words': deepcopy(self.tables['words'])},
            'visual_atlas': deepcopy(docs['atlas_index']), 'trajectories': self.tables['trajectories'],
            'trajectory_shards': deepcopy(self.trajectory_index),
            'camera_decisions': self.tables['decisions'], 'safe_areas': self.tables['safe_areas'],
            'coverage': deepcopy(docs['coverage']), 'limitations': deepcopy(docs['limitations'])}


def inspect_compact_handoff(path, *, reconstruct=True):
    """Validate and reconstruct only ZIP-contained evidence; never extract files.

    Failure is a result, not a partial approval. ``reconstruct=False`` keeps a
    small integrity report while still exercising the independent reconstruction.
    """
    reader = _Reader()
    reconstructed = None
    try:
        reader.load(Path(path))
        if not reader.errors:
            manifest = reader.integrity()
            if not reader.errors:
                reconstructed = reader.reconstruct(manifest)
    except (OSError, zipfile.BadZipFile, RuntimeError, ValueError, KeyError, TypeError, OverflowError) as exc:
        reader.error('reader_error', 'ZIP', f'{type(exc).__name__}: {exc}')
    result = {'schema_version': 'r6.3-reader-1', 'status': 'failed' if reader.errors else 'valid',
        'errors': reader.errors, 'counts': reader.counts, 'source': deepcopy(reader.source),
        'zip_only': True, 'local_analysis_accessed': False, 'media_accessed': False,
        'models_executed': False, 'approval_created': False}
    if reconstruct and not reader.errors:
        result['reconstructed'] = reconstructed
    return result
