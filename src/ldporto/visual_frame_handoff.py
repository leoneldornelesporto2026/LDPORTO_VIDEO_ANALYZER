"""Sparse, source-bound visual evidence for the existing camera handoff.

No detector, identity resolver, camera planner or editorial approval lives here.
The caller may share one evidence index and one bounded decoder across a batch.
"""
from bisect import bisect_left, bisect_right
from collections import defaultdict
from copy import deepcopy
from functools import lru_cache
import json
import math
from pathlib import Path, PurePosixPath
import re
import tempfile

from .camera_handoff import build_camera_handoff
from .core import digest, file_hash
from .preview_renderer import _interpolate_keyframes


SCHEMA_VERSION = '1.0'
PROFILES = {
    'EDITORIAL_HANDOFF': {'max_frames': 12, 'max_bytes': 2 * 1024 * 1024},
    'FULL_AUDIT': {'max_frames': 48, 'max_bytes': 12 * 1024 * 1024},
}
JSON_ARTIFACTS = ('frame_index.json', 'visual_tracks.json', 'safe_areas.json',
    'camera_keyframes.json', 'scene_transitions.json', 'thumbnail_candidates.json',
    'storyboard.json')
_HASH = re.compile(r'^[a-f0-9]{64}$')


def _number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _confidence(value):
    return value if _number(value) and 0 <= value <= 1 else None


def _rect(value):
    if not isinstance(value, dict) or not all(_number(value.get(k)) for k in ('x', 'y', 'width', 'height')):
        return None
    if (min(value['x'], value['y']) < 0 or min(value['width'], value['height']) <= 0
            or value['x'] + value['width'] > 1.000001 or value['y'] + value['height'] > 1.000001):
        return None
    return {k: float(value[k]) for k in ('x', 'y', 'width', 'height')}


def _rows(analysis, *keys):
    for key in keys:
        value = analysis.get(key)
        if isinstance(value, list):
            return value
        if isinstance(value, dict):
            for subkey in ('observations', 'appearances', 'tracks', 'segments', 'shots'):
                if isinstance(value.get(subkey), list):
                    return value[subkey]
    return []


def _metadata(analysis):
    return analysis.get('metadata') or analysis.get('source/metadata.json') or {}


def _source_size(metadata):
    width, height = metadata.get('width'), metadata.get('height')
    if abs(metadata.get('rotation') or 0) % 180:
        width, height = height, width
    return width, height


def _write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, separators=(',', ':'), allow_nan=False), encoding='utf-8')


@lru_cache(maxsize=1)
def _schema():
    path = Path(__file__).resolve().parents[2] / 'schemas' / 'visual_frame_handoff.schema.json'
    return json.loads(path.read_text(encoding='utf-8'))


def visual_handoff_schema():
    return deepcopy(_schema())


def _intervals(candidate, intervals, duration):
    values = intervals if intervals is not None else [{'start': candidate.get('start'), 'end': candidate.get('end')}]
    result, offset = [], 0.
    for index, row in enumerate(values):
        a, b = row.get('start'), row.get('end')
        if not (_number(a) and _number(b) and 0 <= a < b <= duration + 1e-6):
            raise ValueError('invalid_visual_source_interval')
        if result and a < result[-1]['end'] - 1e-6:
            raise ValueError('overlapping_or_unordered_visual_source_intervals')
        result.append({'interval_index': index, 'start': float(a), 'end': float(b), 'clip_start': offset,
                       'clip_end': offset + b - a})
        offset += b - a
    if not result:
        raise ValueError('visual_source_intervals_missing')
    return result


def _relative(timestamp, intervals):
    for row in intervals:
        if row['start'] - 1e-7 <= timestamp < row['end']:
            return row['clip_start'] + timestamp - row['start'], row['interval_index']
    return None, None


class VisualEvidenceIndex:
    """Index the heavy appearances once; candidate access is O(log N + matches)."""

    def __init__(self, analysis):
        rows = _rows(analysis, 'person_appearances', 'people/person_appearances.json', 'tracklet_observations')
        self.rows = sorted((row for row in rows if _number(row.get('observed_at', row.get('time')))),
                           key=lambda row: row.get('observed_at', row.get('time')))
        self.times = [row.get('observed_at', row.get('time')) for row in self.rows]
        self.track_metadata = {row.get('track_id', row.get('tracklet_id')): row for row in
            _rows(analysis, 'person_tracks', 'people/person_tracks.json')}
        self.source_ref = 'people/person_appearances.json'
        self.source_sha256 = _metadata(analysis).get('sha256')
        self.instrument_rows = _rows(analysis, 'instrument_observations', 'people/instrument_observations.json')
        self.total_observation_count = len(self.rows)
        self.camera_timeline = sorted(_rows(analysis, 'camera_director_timeline', 'camera/camera_director_timeline.json'),
                                      key=lambda row: row['start'])
        self.camera_starts = [row['start'] for row in self.camera_timeline]
        self.camera_timeline_sha256 = digest(self.camera_timeline)
        self.camera_artifact_ref = analysis.get('camera_timeline_artifact_ref') or 'camera/camera_director_timeline.json'
        reference = PurePosixPath(self.camera_artifact_ref)
        if (reference.is_absolute() or '\\' in self.camera_artifact_ref or ':' in self.camera_artifact_ref
                or any(part in ('.', '..') for part in reference.parts)):
            raise ValueError('visual_camera_artifact_reference_unsafe')
        self.shot_bounds = {}
        for row in self.camera_timeline:
            shot = row.get('source_shot_id')
            if shot is not None:
                bounds = self.shot_bounds.setdefault(shot, [row['start'], row['end']])
                bounds[0], bounds[1] = min(bounds[0], row['start']), max(bounds[1], row['end'])

    def select(self, intervals):
        selected = []
        for interval in intervals:
            selected.extend(self.rows[bisect_left(self.times, interval['start']):
                                      bisect_left(self.times, interval['end'])])
        return selected

    def select_camera(self, intervals):
        selected, seen = [], set()
        for interval in intervals:
            first = max(0, bisect_right(self.camera_starts, interval['start']) - 1)
            last = bisect_left(self.camera_starts, interval['end'])
            for position in range(first, last):
                row = self.camera_timeline[position]
                if position not in seen and row['end'] > interval['start']:
                    seen.add(position)
                    selected.append(row)
        return selected

    def select_instruments(self, intervals):
        return [{key: deepcopy(row.get(key)) for key in ('observation_id', 'instrument_id', 'class', 'instrument',
            'start', 'end', 'person_id', 'track_id', 'bbox', 'source', 'evidence_refs', 'confidence', 'status')
            if key in row} for row in self.instrument_rows
            if _number(row.get('start')) and _number(row.get('end')) and row.get('source') and row.get('evidence_refs')
            and any(row['start'] < interval['end'] and row['end'] > interval['start'] for interval in intervals)]


class SparseFrameProvider:
    """One CPU decoder, bounded JPEG cache, no inference and no media mutation.

    OpenCV reported timestamps/indices are explicitly identified as decoder data;
    this does not certify source CFR or independently measure frame accuracy.
    """

    def __init__(self, source, *, metadata=None, max_frames=384, max_bytes=40 * 1024 * 1024,
                 max_width=720, jpeg_quality=80):
        self.source = Path(source)
        self.metadata = metadata or {}
        self.max_frames, self.max_bytes = max_frames, max_bytes
        self.max_width, self.jpeg_quality = max_width, jpeg_quality
        self.cache, self.cache_bytes, self.decoded_frames = {}, 0, 0
        self.capture = None
        self.source_sha256 = None

    def __enter__(self):
        import cv2
        self.source_sha256 = file_hash(self.source)
        expected = self.metadata.get('sha256')
        if expected and self.source_sha256 != expected:
            raise ValueError('visual_frame_provider_source_sha256_mismatch')
        self.capture = cv2.VideoCapture(str(self.source))
        if not self.capture.isOpened():
            self.close()
            raise ValueError('visual_source_not_decodable')
        return self

    def close(self):
        if self.capture is not None:
            self.capture.release()
            self.capture = None

    def __exit__(self, *_):
        self.close()

    def get(self, timestamp):
        """Warm a shared cache before allocating optional adaptive extra frames."""
        return self(timestamp, None)

    def __call__(self, timestamp, output):
        import cv2
        if self.capture is None:
            raise ValueError('visual_frame_provider_not_open')
        # No rounding to an assumed CFR frame number.
        key = round(float(timestamp), 6)
        if key not in self.cache:
            if len(self.cache) >= self.max_frames:
                return {'captured': False, 'reason': 'global_frame_budget_exhausted'}
            self.capture.set(cv2.CAP_PROP_POS_MSEC, timestamp * 1000.)
            got, frame = self.capture.read()
            if not got or frame is None or not frame.size:
                return {'captured': False, 'reason': 'source_frame_decode_failed'}
            self.decoded_frames += 1
            source_h, source_w = frame.shape[:2]
            expected_w, expected_h = _source_size(self.metadata)
            if expected_w and expected_h and (source_w, source_h) != (expected_w, expected_h):
                return {'captured': False, 'reason': 'source_resolution_metadata_mismatch'}
            actual = self.capture.get(cv2.CAP_PROP_POS_MSEC) / 1000.
            fps = self.capture.get(cv2.CAP_PROP_FPS)
            for _ in range(2):
                if actual >= timestamp - 1e-6 or fps <= 0:
                    break
                got, next_frame = self.capture.read()
                if not got or next_frame is None or not next_frame.size:
                    break
                frame = next_frame
                self.decoded_frames += 1
                actual = self.capture.get(cv2.CAP_PROP_POS_MSEC) / 1000.
            tolerance = max(.1, 2. / fps) if fps > 0 else .1
            timestamp_known = _number(actual) and abs(actual - timestamp) <= tolerance
            pos = self.capture.get(cv2.CAP_PROP_POS_FRAMES) - 1
            scale = min(1., self.max_width / source_w)
            if scale < 1.:
                frame = cv2.resize(frame, (round(source_w * scale), round(source_h * scale)), interpolation=cv2.INTER_AREA)
            ok, encoded = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, self.jpeg_quality])
            if not ok:
                return {'captured': False, 'reason': 'source_frame_encode_failed'}
            blob = encoded.tobytes()
            if self.cache_bytes + len(blob) > self.max_bytes:
                return {'captured': False, 'reason': 'global_frame_byte_budget_exhausted'}
            info = {'captured': True, 'source_time_s': actual if timestamp_known else timestamp,
                'source_frame_index': round(pos) if timestamp_known and _number(pos) and pos >= 0 else None,
                'timestamp_provenance': 'opencv_decoder_reported' if timestamp_known else 'seek_request_decode_timestamp_unavailable',
                'timestamp_independently_verified': False, 'width': frame.shape[1], 'height': frame.shape[0],
                'media_source_sha256': self.source_sha256,
                'source_decoded_width': source_w, 'source_decoded_height': source_h,
                'capture_method': 'opencv_cpu_sparse_seek', 'quality': 'representative_source_frame_not_final_crop'}
            self.cache[key] = (blob, info)
            self.cache_bytes += len(blob)
        blob, info = self.cache[key]
        if output is not None:
            Path(output).write_bytes(blob)
        return deepcopy(info)


def _camera_rows(analysis, intervals, metadata, evidence_index):
    scoped = {'metadata': metadata, 'camera_director_timeline': evidence_index.select_camera(intervals)}
    adapted = build_camera_handoff(scoped, intervals=intervals)
    source_width, source_height = _source_size(metadata)
    rows = []
    for index, row in enumerate(adapted['segments']):
        a, _ = _relative(row['start'], intervals)
        b = a + row['end'] - row['start']
        camera = row.get('camera') or {}
        rect = _rect((row.get('crop') or {}).get('rect_end'))
        keys = []
        original_keys = camera.get('keyframes') or []
        times = sorted(set([row['start'], row['end']] + [key['time'] for key in original_keys
            if _number(key.get('time')) and row['start'] < key['time'] < row['end']]))
        for timestamp in times:
            effective = None
            if row['recommended_composition'] in ('FOCUS_PERSON_9X16', 'DUO_STAGE') and metadata.get('width') and metadata.get('height'):
                effective = _rect(_interpolate_keyframes(row, timestamp, source_width, source_height, 1080, 1920))
            keys.append({'source_time_s': timestamp, 'clip_time_s': a + timestamp - row['start'],
                         'crop_source_normalized': effective,
                         'transform': 'crop_resize' if effective else 'source_contain',
                         'at_end_exclusive_boundary': timestamp == row['end']})
        rows.append({'keyframe_group_id': 'CAM_' + digest([index, row['director_id'], row['start'], row['end']])[:16],
            'source_shot_id': row.get('source_shot_id'), 'director_id': row.get('director_id'),
            'source_timeline_ref': evidence_index.camera_artifact_ref,
            'source_shot_start_s': evidence_index.shot_bounds.get(row.get('source_shot_id'), [None, None])[0],
            'source_shot_end_s': evidence_index.shot_bounds.get(row.get('source_shot_id'), [None, None])[1],
            'source_start_s': row['start'], 'source_end_s': row['end'], 'clip_start_s': a, 'clip_end_s': b,
            'source_interval_index': row['source_interval_index'], 'mode': row['recommended_composition'],
            'composition_intent': row['composition_intent'], 'target_ids': row['target_person_ids'],
            'crop_source_normalized': rect, 'keyframes': keys,
            'source_camera': deepcopy(camera),
            'interpolation': 'existing_preview_renderer_linear_center_and_zoom_then_clamped_crop',
            'easing': 'linear', 'transition_in': camera.get('transition_in'),
            'transition_out': camera.get('transition_out'), 'transition_duration_s': None,
            'speed_limit': None, 'speed_limit_status': 'not_serialized_by_source_contract',
            'confidence': None, 'reason_codes': row['reason_codes'],
            'fallback': row['fallback_composition'], 'terminal_fallback': row['terminal_fallback'],
            'verification_history': [], 'render_status': 'UNVERIFIED',
            'evidence': row['evidence'], 'review_required': True})
    return rows, evidence_index.camera_timeline_sha256


def _selection(intervals, camera, fps, maximum):
    """Prefer cuts/risk, retain temporal spread; omitted events remain in JSON."""
    epsilon = min(.05, .5 / fps) if _number(fps) and fps > 0 else .02
    proposals = {}
    def add(timestamp, interval_index, reason, priority):
        span = intervals[interval_index]
        timestamp = round(max(span['start'], min(timestamp, span['end'] - min(epsilon, (span['end'] - span['start']) / 4))), 6)
        key = (timestamp, interval_index)
        if key not in proposals:
            proposals[key] = {'requested_source_time_s': timestamp, 'source_interval_index': interval_index,
                              'sampling_reasons': [], 'priority': priority}
        proposals[key]['sampling_reasons'].append(reason)
        proposals[key]['priority'] = max(priority, proposals[key]['priority'])
    for span in intervals:
        for fraction in (0., .25, .5, .75, 1.):
            add(span['start'] + (span['end'] - span['start']) * fraction, span['interval_index'],
                'interval_boundary' if fraction in (0., 1.) else 'stable_temporal_coverage', 4 if fraction in (0., 1.) else 1)
    previous = None
    for row in camera:
        if previous is None or row['source_shot_id'] != previous['source_shot_id'] or row['source_interval_index'] != previous['source_interval_index']:
            actual_cut = row['source_shot_start_s'] is not None and abs(row['source_start_s'] - row['source_shot_start_s']) < 1e-6
            add(row['source_start_s'], row['source_interval_index'],
                'source_shot_boundary' if actual_cut else 'selected_interval_boundary_inside_shot', 3)
        if row['target_ids'] and (previous is None or row['target_ids'] != previous['target_ids']):
            add((row['source_start_s'] + row['source_end_s']) / 2, row['source_interval_index'], 'target_change', 5)
        if len(row['keyframes']) > 2 or (row['evidence'] or {}).get('movement_present_in_timeline'):
            add((row['source_start_s'] + row['source_end_s']) / 2, row['source_interval_index'], 'camera_motion_or_crop_risk', 5)
        previous = row
    # First/last anchors are invariant as the adaptive frame budget grows. A batch
    # caller can warm these for every piece before allocating optional extra frames.
    ordered = sorted(proposals.values(), key=lambda row: row['requested_source_time_s'])
    chosen = []
    if len(ordered) <= maximum:
        chosen = ordered
    elif maximum == 1:
        chosen = [ordered[len(ordered) // 2]]
    else:
        chosen = [ordered[0], ordered[-1]]
        remaining = ordered[1:-1]
        for index in range(maximum - 2):
            left, right = index * len(remaining) // (maximum - 2), (index + 1) * len(remaining) // (maximum - 2)
            chosen.append(max(remaining[left:right], key=lambda row: (row['priority'], -row['requested_source_time_s'])))
    return sorted(chosen, key=lambda row: row['requested_source_time_s']), len(ordered)


def plan_frame_times(analysis, candidate, *, intervals=None, evidence_index=None, max_frames=12):
    """Read-only sampling prepass; ``provider.get(time)`` warms shared anchors."""
    if not isinstance(max_frames, int) or isinstance(max_frames, bool) or max_frames <= 0:
        raise ValueError('visual_handoff_frame_limit_invalid')
    metadata = _metadata(analysis)
    spans = _intervals(candidate, intervals, metadata['duration'])
    index = evidence_index or VisualEvidenceIndex(analysis)
    camera, _ = _camera_rows(analysis, spans, metadata, index)
    selected, proposed = _selection(spans, camera, metadata.get('fps'), max_frames)
    return {'requests': selected, 'sampling_proposals': proposed, 'source_intervals': spans}


def _tracks(observations, index, intervals, revision):
    grouped = defaultdict(list)
    for row in observations:
        grouped[(row.get('track_id', row.get('tracklet_id')), row.get('scene_id'))].append(row)
    tracks, protected = [], []
    for (track_id, scene_id), rows in sorted(grouped.items(), key=lambda item: str(item[0])):
        if not track_id:
            continue
        metadata = index.track_metadata.get(track_id) or {}
        points = []
        for row in rows:
            timestamp = row.get('observed_at', row.get('time'))
            relative, interval_index = _relative(timestamp, intervals)
            if relative is None:
                continue
            boxes = {}
            for label, key in (('person', 'body_bbox'), ('face', 'face_bbox'), ('hands', 'hands_bbox'),
                               ('instrument', 'instrument_bbox'), ('microphone', 'microphone_bbox')):
                box = _rect(row.get(key))
                if label == 'person' and row.get('bbox_kind') == 'body' and box is None:
                    box = _rect(row.get('bbox'))
                if ((label == 'face' and row.get('face_visible') is False)
                        or (label == 'person' and row.get('body_visible') is False)):
                    continue
                if box:
                    boxes[label] = box
                    protected.append({'source_time_s': timestamp, 'clip_time_s': relative,
                        'source_interval_index': interval_index, 'track_id': track_id, 'scene_id': scene_id,
                        'region_type': label, 'bbox_source_normalized': box,
                        'confidence': _confidence(row.get('confidence')), 'provenance': row.get('appearance_id'),
                        'temporal_scope': 'observed_sample_only_no_interpolation'})
            points.append({'source_time_s': timestamp, 'clip_time_s': relative,
                'source_interval_index': interval_index, 'bboxes': boxes,
                'confidence': _confidence(row.get('confidence')), 'face_visible': row.get('face_visible'),
                'body_visible': row.get('body_visible'), 'occlusion': row.get('occlusion'),
                'appearance_id': row.get('appearance_id'), 'source_observation_index': row.get('source_observation_index')})
        gaps = [{'source_start_s': a['source_time_s'], 'source_end_s': b['source_time_s'],
                 'status': 'unsampled_no_continuous_visibility_claim'} for a, b in zip(points, points[1:])
                if b['source_time_s'] - a['source_time_s'] > 1.]
        tracks.append({'visual_track_id': 'VT_' + digest([index.source_sha256, revision, track_id, scene_id])[:16],
            'track_id': track_id, 'person_id': rows[0].get('person_id'), 'scene_id': scene_id,
            'class': 'person', 'role': 'unknown', 'role_status': 'unknown', 'identity_confirmed': False,
            'identity_scope': metadata.get('identity_status', 'within_track_only'),
            'source_first_seen_s': metadata.get('first_seen'), 'source_last_seen_s': metadata.get('last_seen'),
            'provenance': index.source_ref, 'observations': points, 'gaps': gaps,
            'interpolation_allowed': False, 'cross_cut_identity_propagation': False})
    return tracks, protected


def project_source_bbox(box, *, crop=None, source_size=(1920, 1080), target_size=(1080, 1920)):
    """Project a measured region into a proposed output; never certify its safety."""
    box, crop = _rect(box), _rect(crop)
    if box is None:
        return {'status': 'unknown', 'bbox_final_normalized': None}
    if crop is not None:
        values = ((box['x'] - crop['x']) / crop['width'], (box['y'] - crop['y']) / crop['height'],
                  box['width'] / crop['width'], box['height'] / crop['height'])
        transform = 'crop_resize'
    else:
        sw, sh = source_size
        tw, th = target_size
        if not all(_number(v) and v > 0 for v in (sw, sh, tw, th)):
            return {'status': 'unknown', 'bbox_final_normalized': None}
        scale = min(tw / sw, th / sh)
        values = ((tw - sw * scale) / (2 * tw) + box['x'] * sw * scale / tw,
                  (th - sh * scale) / (2 * th) + box['y'] * sh * scale / th,
                  box['width'] * sw * scale / tw, box['height'] * sh * scale / th)
        transform = 'source_contain'
    x, y, w, h = values
    clipped = x < -1e-6 or y < -1e-6 or x + w > 1.000001 or y + h > 1.000001
    x2, y2 = min(1., x + w), min(1., y + h)
    visible = {'x': max(0., x), 'y': max(0., y), 'width': max(0., x2 - max(0., x)), 'height': max(0., y2 - max(0., y))}
    return {'status': 'outside_proposed_crop' if visible['width'] <= 0 or visible['height'] <= 0 else 'clipped_by_proposed_crop' if clipped else 'projected_not_verified',
            'bbox_final_normalized': visible if visible['width'] > 0 and visible['height'] > 0 else None,
            'transform': transform, 'final_render_verified': False}


def _safe_areas(protected, camera, metadata, platform_margins):
    starts = [row['source_start_s'] for row in camera]
    source_width, source_height = _source_size(metadata)
    for region in protected:
        position = bisect_right(starts, region['source_time_s']) - 1
        row = camera[position] if position >= 0 else None
        crop = None
        if row and region['source_time_s'] < row['source_end_s'] and row['mode'] in ('FOCUS_PERSON_9X16', 'DUO_STAGE'):
            crop = _rect(_interpolate_keyframes({'start': row['source_start_s'], 'camera': row['source_camera'],
                'crop': {'rect_end': row['crop_source_normalized']}}, region['source_time_s'],
                source_width, source_height, 1080, 1920))
        region['output_projection'] = project_source_bbox(region['bbox_source_normalized'], crop=crop,
            source_size=(source_width, source_height))
        region['fallback_recommendation'] = ('SOURCE_FIT_BLUR' if region['output_projection']['status'] in
            ('outside_proposed_crop', 'clipped_by_proposed_crop') else None)
        region['camera_keyframe_group_id'] = row['keyframe_group_id'] if row and region['source_time_s'] < row['source_end_s'] else None
    return {'protected_regions': protected, 'protected_regions_scope': 'observed_samples_only',
        'unobserved_region_types': ['head_full_extent', 'mouth', 'hands_if_not_observed', 'instruments_if_not_observed', 'important_text_if_not_observed'],
        'platform_margins': platform_margins,
        'platform_margins_status': 'caller_configured_not_platform_certified' if platform_margins else 'unknown',
        'overlay_zones': {'title': {'status': 'unknown', 'rect': None},
                          'caption': {'status': 'unknown', 'rect': None}, 'cta': {'status': 'unknown', 'rect': None}},
        'overlay_approval': False, 'reason_codes': ['spatial_samples_do_not_prove_continuous_free_space',
            'final_crop_and_platform_collision_review_required'], 'final_render_verified': False}


def _storyboard(camera, frames, candidate, intervals):
    beats = []
    for row in camera:
        if (not beats or beats[-1]['source_shot_id'] != row['source_shot_id']
                or beats[-1]['source_interval_index'] != row['source_interval_index']
                or abs(beats[-1]['source_end_s'] - row['source_start_s']) > 1e-5):
            beats.append({'beat_id': 'BEAT_%04d' % (len(beats) + 1), 'source_shot_id': row['source_shot_id'],
                'source_interval_index': row['source_interval_index'], 'source_start_s': row['source_start_s'],
                'source_end_s': row['source_end_s'], 'clip_start_s': row['clip_start_s'], 'clip_end_s': row['clip_end_s'],
                'participant_ids': [], 'observed_action': None, 'action_status': 'unknown',
                'emotion_hypothesis': None, 'narrative_purpose': 'source_visual_context_requires_editor_review',
                'camera_keyframe_refs': [], 'frame_refs': [], 'overlay_suggestion': None,
                'editorial_risks': ['caption_and_overlay_review_required', 'source_sampling_is_sparse']})
        beat = beats[-1]
        beat['source_end_s'], beat['clip_end_s'] = row['source_end_s'], row['clip_end_s']
        beat['camera_keyframe_refs'].append(row['keyframe_group_id'])
        beat['participant_ids'] = sorted(set(beat['participant_ids'] + row['target_ids']))
    if not beats:
        for span in intervals:
            beats.append({'beat_id': 'BEAT_%04d' % (len(beats) + 1), 'source_shot_id': None,
                'source_interval_index': span['interval_index'], 'source_start_s': span['start'], 'source_end_s': span['end'],
                'clip_start_s': span['clip_start'], 'clip_end_s': span['clip_end'], 'participant_ids': [],
                'observed_action': None, 'action_status': 'unknown', 'emotion_hypothesis': None,
                'narrative_purpose': 'source_interval_requires_editor_review', 'camera_keyframe_refs': [],
                'frame_refs': [], 'overlay_suggestion': None, 'editorial_risks': ['camera_evidence_missing']})
    for beat in beats:
        beat['frame_refs'] = [frame['frame_id'] for frame in frames
            if beat['source_start_s'] <= frame['source_time_s'] < beat['source_end_s']]
    return {'beats': beats, 'transcript_literal': candidate.get('transcript_literal', candidate.get('literal_text')),
        'source_segment_ids': candidate.get('source_segment_ids', candidate.get('segment_ids', candidate.get('evidence_segment_ids', []))),
        'transcript_gaps': candidate.get('transcript_gaps', []),
        'transcript_gaps_status': 'provided' if 'transcript_gaps' in candidate else 'unknown',
        'transcript_coverage_status': 'existing_literal_source_scope_not_word_alignment',
        'caption_status': candidate.get('caption_status') or (candidate.get('caption_preflight') or {}).get('status'),
        'transcript_is_existing_candidate_data': True, 'editorial_state': 'PARTIAL',
        'preview_approved': False, 'publish_ready': False}


def _contact_sheet(root, frames, camera, candidate_id):
    if not frames:
        return {'status': 'unavailable', 'reason': 'no_captured_source_frames', 'path': None}
    import cv2
    import numpy as np
    columns, tile_w, tile_h = 3, 320, 226
    canvas = np.full((math.ceil(len(frames) / columns) * tile_h, columns * tile_w, 3), 22, dtype=np.uint8)
    for index, frame in enumerate(frames):
        image = cv2.imdecode(np.fromfile(str(root / frame['relative_path']), dtype=np.uint8), cv2.IMREAD_COLOR)
        if image is None:
            raise ValueError('visual_selected_frame_not_decodable')
        h, w = image.shape[:2]
        scale = min(tile_w / w, 180 / h)
        image = cv2.resize(image, (round(w * scale), round(h * scale)), interpolation=cv2.INTER_AREA)
        top, left = index // columns * tile_h, index % columns * tile_w
        ih, iw = image.shape[:2]
        ox, oy = left + (tile_w - iw) // 2, top + (180 - ih) // 2
        canvas[oy:oy + ih, ox:ox + iw] = image
        for row in camera:
            if row['source_start_s'] <= frame['source_time_s'] < row['source_end_s']:
                rect = (_rect(_interpolate_keyframes({'start': row['source_start_s'], 'camera': row['source_camera'],
                    'crop': {'rect_end': row['crop_source_normalized']}}, frame['source_time_s'],
                    frame.get('source_decoded_width', 1920), frame.get('source_decoded_height', 1080), 1080, 1920))
                    if row['mode'] in ('FOCUS_PERSON_9X16', 'DUO_STAGE') else None)
                if rect:
                    cv2.rectangle(canvas, (ox + round(rect['x'] * iw), oy + round(rect['y'] * ih)),
                        (ox + round((rect['x'] + rect['width']) * iw), oy + round((rect['y'] + rect['height']) * ih)), (0, 180, 255), 2)
                break
        lines = [frame['frame_id'] + ' src %.3fs' % frame['source_time_s'],
                 'clip %.3fs %s' % (frame['clip_time_s'], frame.get('source_shot_id') or 'shot unknown')]
        for line_index, line in enumerate(lines):
            cv2.putText(canvas, line[:55], (left + 5, top + 197 + line_index * 18),
                        cv2.FONT_HERSHEY_SIMPLEX, .37, (235, 235, 235), 1, cv2.LINE_AA)
    path = root / 'contact_sheets' / 'timeline.jpg'
    ok, encoded = cv2.imencode('.jpg', canvas, [cv2.IMWRITE_JPEG_QUALITY, 76])
    if not ok:
        raise ValueError('visual_contact_sheet_encode_failed')
    encoded.tofile(str(path))
    return {'status': 'captured_source_frames_annotated', 'path': 'contact_sheets/timeline.jpg',
        'sha256': file_hash(path), 'frame_ids': [frame['frame_id'] for frame in frames],
        'crop_annotation': 'orange_interpolated_proposed_crop_not_render_verified', 'candidate_id': candidate_id}


def build_visual_frame_handoff(analysis, candidate, destination, *, source_sha256, package_sha256,
        revision, media_path=None, profile='EDITORIAL_HANDOFF', intervals=None, frame_provider=None,
        evidence_index=None, platform_margins=None, max_frames=None, max_bytes=None):
    """Write one new candidate/Story-part directory and return its manifest.

    ``intervals`` are ordered source spans. Clip time concatenates their lengths;
    an original gap is never silently exported as continuous media or tracking.
    Existing destination directories are never overwritten.
    """
    metadata = _metadata(analysis)
    if not (_HASH.fullmatch(str(source_sha256)) and _HASH.fullmatch(str(package_sha256))):
        raise ValueError('visual_handoff_source_or_package_sha256_invalid')
    if metadata.get('sha256') != source_sha256:
        raise ValueError('visual_handoff_source_sha256_mismatch')
    if not revision or profile not in PROFILES or not _number(metadata.get('duration')):
        raise ValueError('visual_handoff_revision_profile_or_duration_invalid')
    candidate_id = candidate.get('story_id') or candidate.get('candidate_id')
    if not isinstance(candidate_id, str) or not re.fullmatch(r'[A-Za-z0-9_.-]+', candidate_id) or candidate_id in ('.', '..'):
        raise ValueError('visual_handoff_candidate_id_invalid')
    destination = Path(destination)
    if destination.exists():
        raise FileExistsError('visual_handoff_revision_already_exists')
    spans = _intervals(candidate, intervals, metadata['duration'])
    limits = dict(PROFILES[profile])
    if max_frames is not None:
        limits['max_frames'] = max_frames
    if max_bytes is not None:
        limits['max_bytes'] = max_bytes
    if not all(isinstance(limits[key], int) and not isinstance(limits[key], bool) and limits[key] > 0 for key in limits):
        raise ValueError('visual_handoff_limits_invalid')
    if frame_provider is None and media_path is not None:
        with SparseFrameProvider(media_path, metadata=metadata) as provider:
            return build_visual_frame_handoff(analysis, candidate, destination, source_sha256=source_sha256,
                package_sha256=package_sha256, revision=revision, profile=profile, intervals=intervals,
                frame_provider=provider, evidence_index=evidence_index, platform_margins=platform_margins,
                max_frames=limits['max_frames'], max_bytes=limits['max_bytes'])
    if isinstance(frame_provider, SparseFrameProvider) and frame_provider.source_sha256 != source_sha256:
        raise ValueError('visual_frame_provider_source_sha256_mismatch')
    evidence_index = evidence_index or VisualEvidenceIndex(analysis)
    observations = evidence_index.select(spans)
    instruments = evidence_index.select_instruments(spans)
    camera, timeline_hash = _camera_rows(analysis, spans, metadata, evidence_index)
    selected, proposed_count = _selection(spans, camera, metadata.get('fps'), limits['max_frames'])
    tracks, protected = _tracks(observations, evidence_index, spans, revision)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.visual_handoff_', dir=destination.parent) as temporary:
        root = Path(temporary) / 'bundle'
        (root / 'selected_frames').mkdir(parents=True)
        (root / 'contact_sheets').mkdir()
        frames, missing = [], []
        for request in selected:
            timestamp = request['requested_source_time_s']
            frame_id = 'FRAME_' + digest([source_sha256, candidate_id, revision, timestamp])[:16]
            relative_path = 'selected_frames/' + frame_id + '.jpg'
            info = frame_provider(timestamp, root / relative_path) if frame_provider else {'captured': False, 'reason': 'source_frame_provider_unavailable'}
            if not info.get('captured') or not (root / relative_path).is_file():
                missing.append({**request, 'reason': info.get('reason', 'provider_did_not_write_frame')})
                continue
            actual = info.get('source_time_s', timestamp)
            clip_time, interval_index = _relative(actual, spans)
            if clip_time is None or interval_index != request['source_interval_index']:
                (root / relative_path).unlink()
                missing.append({**request, 'reason': 'decoded_timestamp_outside_requested_interval'})
                continue
            row = next((row for row in camera if row['source_start_s'] <= actual < row['source_end_s']), None)
            frames.append({**info, 'frame_id': frame_id, 'source_time_s': actual,
                'requested_source_time_s': timestamp, 'clip_time_s': clip_time,
                'source_interval_index': interval_index, 'source_frame_index': info.get('source_frame_index'),
                'source_shot_id': row['source_shot_id'] if row else None, 'scene_id': None,
                'event_type': request['sampling_reasons'][0], 'sampling_reasons': request['sampling_reasons'],
                'relative_path': relative_path, 'sha256': file_hash(root / relative_path),
                'confidence': None, 'thumbnail_reference': frame_id, 'final_render_frame': False})
        common = {'schema_version': SCHEMA_VERSION, 'candidate_id': candidate_id}
        contact = _contact_sheet(root, frames, camera, candidate_id)
        _write(root / 'contact_sheets/index.json', {**common, **contact})
        payloads = {
            'frame_index.json': {**common, 'source_sha256': source_sha256, 'frames': frames,
                'missing_frames': missing, 'sampling_proposals': proposed_count,
                'omitted_sampling_proposals': proposed_count - len(selected), 'contact_sheet': contact},
            'visual_tracks.json': {**common, 'tracks': tracks, 'observation_count': len(observations),
                'instrument_observations': instruments, 'instrument_observation_count': len(instruments),
                'instrument_measurement_status': 'provided_evidence_requires_review' if instruments else 'NOT_MEASURED',
                'source_observation_count': evidence_index.total_observation_count,
                'heavy_evidence_ref': 'FULL_AUDIT.zip#' + evidence_index.source_ref,
                'coordinate_space': 'normalized_oriented_source', 'landmarks_status': 'unavailable_in_current_appearance_contract'},
            'safe_areas.json': {**common, **_safe_areas(protected, camera, metadata, platform_margins)},
            'camera_keyframes.json': {**common, 'camera_engine': 'ldporto.camera_director',
                'adapter': 'ldporto.camera_handoff', 'timeline_sha256': timeline_hash,
                'source_timeline_ref': evidence_index.camera_artifact_ref,
                'renderer_owner': 'VIDEO_CURATOR', 'segments': camera,
                'execution_scope': 'recommendation_not_render_or_approval', 'preview_approved': False, 'publish_ready': False},
            'scene_transitions.json': {**common, 'transitions': [
                {'source_time_s': row['source_start_s'], 'clip_time_s': row['clip_start_s'],
                 'source_shot_id': row['source_shot_id'],
                 'event': ('source_shot_boundary' if row['source_shot_start_s'] is not None
                    and abs(row['source_start_s'] - row['source_shot_start_s']) < 1e-6
                    else 'selected_interval_start_inside_shot'),
                 'source_shot_start_s': row['source_shot_start_s'],
                 'provenance': evidence_index.camera_artifact_ref, 'shot_scale': 'unknown',
                 'lighting_change': None, 'occlusion_change': None}
                for index, row in enumerate(camera) if index == 0 or row['source_shot_id'] != camera[index - 1]['source_shot_id']
                    or row['source_interval_index'] != camera[index - 1]['source_interval_index']]},
            'thumbnail_candidates.json': {**common, 'candidates': [
                {'frame_id': frame['frame_id'], 'source_time_s': frame['source_time_s'],
                 'clip_time_s': frame['clip_time_s'], 'relative_path': frame['relative_path'], 'sha256': frame['sha256'],
                 'score': None, 'eligibility': 'UNVERIFIED', 'reason_codes': ['source_frame_captured',
                     'blur_face_instrument_legibility_and_text_region_require_review'], 'text_region': None}
                for frame in frames], 'selection_status': 'human_review_required'},
            'storyboard.json': {**common, **_storyboard(camera, frames, candidate, spans)},
        }
        for name, payload in payloads.items():
            _write(root / name, payload)
        files = [{'path': str(path.relative_to(root)).replace('\\', '/'), 'sha256': file_hash(path), 'bytes': path.stat().st_size}
                 for path in sorted(root.rglob('*')) if path.is_file()]
        gaps = []
        if missing:
            gaps.append('requested_source_frames_missing')
        if proposed_count > len(selected):
            gaps.append('sampling_limited_by_profile_frame_budget')
        if not camera:
            gaps.append('camera_timeline_unavailable')
        if not observations:
            gaps.append('spatial_observations_unavailable')
        manifest = {**common, 'producer': 'ldporto.visual_frame_handoff', 'revision': revision,
            'parent_candidate_id': candidate.get('candidate_id'), 'kind': 'STORY' if candidate.get('story_id') else 'REEL',
            'source_sha256': source_sha256, 'input_package_sha256': package_sha256,
            'profile': profile, 'limits': limits, 'source_intervals': spans,
            'time_convention': {'source': 'absolute_original_media_seconds', 'clip': 'concatenated_selected_intervals_seconds',
                'interval_end': 'exclusive', 'source_gaps_are_not_clip_media': True},
            'coordinate_convention': {'bbox': 'normalized_xywh_0_1', 'origin': 'top_left',
                'reference': 'oriented_decoded_source', 'source_to_pixel': 'x*width,y*height,w*width,h*height',
                'source_to_crop': '(source_xy-crop_xy)/crop_wh', 'crop_to_final': 'resize_to_target',
                'source_contain_to_final': 'uniform_min_scale_centered', 'rotation_degrees': metadata.get('rotation', 0),
                'rotation_evidence_status': 'source_metadata_not_independent_probe',
                'dynamic_crop': 'camera_keyframes.json', 'render_geometry_verified': False},
            'media': {key: metadata.get(key) for key in ('width', 'height', 'fps', 'duration', 'rotation')},
            'target': {'width': 1080, 'height': 1920}, 'files': files,
            'payload_bytes': sum(row['bytes'] for row in files),
            'coverage': {'requested_frames': len(selected), 'captured_frames': len(frames),
                'missing_frames': len(missing), 'sampling_proposals': proposed_count,
                'continuous_visual_coverage': None, 'observation_count': len(observations),
                'continuous_visibility_established': False},
            'gaps': gaps, 'confidence': None,
            'dependencies': [{'path': evidence_index.camera_artifact_ref, 'content_sha256': timeline_hash},
                {'path': evidence_index.source_ref, 'package_sha256': package_sha256,
                 'access': 'filtered_time_index_not_copied_full_per_candidate'}],
            'editorial_state': 'PARTIAL', 'review_required': True, 'preview_approved': False, 'publish_ready': False}
        _write(root / 'visual_handoff_manifest.json', manifest)
        total_bytes = sum(path.stat().st_size for path in root.rglob('*') if path.is_file())
        if total_bytes > limits['max_bytes']:
            raise ValueError('visual_handoff_candidate_byte_budget_exceeded:' + str(total_bytes))
        result = validate_visual_frame_handoff(root)
        if not result['valid']:
            raise ValueError('visual_handoff_validation_failed:' + ','.join(result['errors']))
        root.replace(destination)
    return manifest


def validate_visual_frame_handoff(directory):
    """Reopen all artifacts; reject traversal, modified hashes and invalid geometry."""
    root, errors = Path(directory), []
    try:
        manifest = json.loads((root / 'visual_handoff_manifest.json').read_text(encoding='utf-8'))
    except (OSError, ValueError) as exc:
        return {'valid': False, 'errors': ['visual_manifest_unreadable:' + type(exc).__name__]}
    if manifest.get('schema_version') != SCHEMA_VERSION:
        errors.append('visual_schema_version')
    import jsonschema
    schema = _schema()
    validator = jsonschema.Draft202012Validator(schema)
    if list(validator.iter_errors(manifest)):
        return {'valid': False, 'errors': ['visual_manifest_schema_invalid']}
    if manifest.get('preview_approved') is not False or manifest.get('publish_ready') is not False:
        errors.append('visual_approval_not_authorized')
    for key in ('source_sha256', 'input_package_sha256'):
        if not _HASH.fullmatch(str(manifest.get(key))):
            errors.append('visual_invalid_' + key)
    spans = manifest.get('source_intervals') or []
    try:
        expected_spans = _intervals({}, spans, manifest['media']['duration'])
        if expected_spans != spans:
            errors.append('visual_manifest_interval_mapping_invalid')
    except (ValueError, TypeError, KeyError):
        return {'valid': False, 'errors': ['visual_manifest_intervals_invalid']}
    declared = set()
    for record in manifest.get('files', []):
        name = record.get('path', '')
        parts = PurePosixPath(name)
        if (not name or '\\' in name or ':' in name or parts.is_absolute()
                or any(part in ('..', '.') for part in parts.parts) or name in declared):
            errors.append('visual_unsafe_or_duplicate_path:' + name)
            continue
        declared.add(name)
        path = root.joinpath(*parts.parts)
        if path.is_symlink() or any(parent.is_symlink() for parent in path.parents if parent != root.parent):
            errors.append('visual_symlink_path:' + name)
            continue
        if not path.is_file() or root.resolve() not in path.resolve().parents:
            errors.append('visual_missing_or_external_file:' + name)
            continue
        if file_hash(path) != record.get('sha256') or path.stat().st_size != record.get('bytes'):
            errors.append('visual_integrity_mismatch:' + name)
    actual = {str(path.relative_to(root)).replace('\\', '/') for path in root.rglob('*') if path.is_file()}
    if actual != declared | {'visual_handoff_manifest.json'}:
        errors.append('visual_undeclared_or_missing_files')
    for name in (*JSON_ARTIFACTS, 'contact_sheets/index.json'):
        if name not in declared:
            errors.append('visual_required_artifact_missing:' + name)
    def inspect(value, context):
        if isinstance(value, dict):
            if all(key in value for key in ('x', 'y', 'width', 'height')) and _rect(value) is None:
                errors.append('visual_invalid_bbox:' + context)
            if 'source_time_s' in value and 'clip_time_s' in value:
                absolute, relative = value['source_time_s'], value['clip_time_s']
                expected = None
                if _number(absolute):
                    expected, _ = _relative(absolute, spans)
                    if value.get('at_end_exclusive_boundary'):
                        ending = next((span for span in spans if abs(span['end'] - absolute) < 1e-6), None)
                        if ending:
                            expected = ending['clip_end']
                if expected is None or not _number(relative) or abs(expected - relative) > 1e-5:
                    errors.append('visual_time_basis_mismatch:' + context)
            if all(key in value for key in ('source_start_s', 'source_end_s', 'clip_start_s', 'clip_end_s')):
                a, b = value['source_start_s'], value['source_end_s']
                span = next((span for span in spans if _number(a) and _number(b) and
                             span['start'] <= a < b <= span['end'] + 1e-6), None)
                if (span is None or not _number(value['clip_start_s']) or not _number(value['clip_end_s'])
                        or abs(value['clip_start_s'] - span['clip_start'] - a + span['start']) > 1e-5
                        or abs(value['clip_end_s'] - value['clip_start_s'] - b + a) > 1e-5):
                    errors.append('visual_interval_time_basis_mismatch:' + context)
            for key, child in value.items():
                inspect(child, context + '/' + key)
        elif isinstance(value, list):
            for index, child in enumerate(value):
                inspect(child, context + '/' + str(index))
        elif isinstance(value, float) and not math.isfinite(value):
            errors.append('visual_non_finite_number:' + context)
    loaded = {}
    for name in JSON_ARTIFACTS:
        try:
            value = json.loads((root / name).read_text(encoding='utf-8'))
            loaded[name] = value
            if value.get('schema_version') != SCHEMA_VERSION or value.get('candidate_id') != manifest.get('candidate_id'):
                errors.append('visual_artifact_identity_mismatch:' + name)
            artifact_schema = {**schema, '$ref': '#/$defs/' + name.removesuffix('.json')}
            if list(jsonschema.Draft202012Validator(artifact_schema).iter_errors(value)):
                errors.append('visual_artifact_schema_invalid:' + name)
            inspect(value, name)
        except (OSError, ValueError, TypeError):
            errors.append('visual_json_unreadable:' + name)
    frames = (loaded.get('frame_index.json') or {}).get('frames') or []
    for frame in frames:
        if frame.get('captured') is not True or frame.get('relative_path') not in declared:
            errors.append('visual_frame_capture_or_reference_invalid')
        record = next((record for record in manifest.get('files', []) if record.get('path') == frame.get('relative_path')), {})
        if frame.get('sha256') != record.get('sha256'):
            errors.append('visual_frame_hash_reference_invalid')
    if len(frames) != manifest.get('coverage', {}).get('captured_frames'):
        errors.append('visual_frame_count_mismatch')
    total = sum(path.stat().st_size for path in root.rglob('*') if path.is_file())
    if total > manifest.get('limits', {}).get('max_bytes', 0):
        errors.append('visual_candidate_byte_budget_exceeded')
    return {'valid': not errors, 'errors': sorted(set(errors)), 'file_count': len(actual), 'total_bytes': total,
            'candidate_id': manifest.get('candidate_id'), 'captured_frames': len(frames)}
