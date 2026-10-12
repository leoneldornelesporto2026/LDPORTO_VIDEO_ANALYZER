"""Bounded, opt-in body A/B audit. Human truth is never detector output.

This additive protocol leaves production tracking, thresholds and editorial gates
alone. Re-ID/binding predictions can be attached from a separately audited run;
the detector-only runner deliberately does not manufacture identities.
"""
from copy import deepcopy
from itertools import combinations
from pathlib import Path
import hashlib
import math
from time import perf_counter, process_time

from .core import digest
from .visual_review import _sha
from .vision import iou


STRATA = ('wide_shot', 'seated', 'partial_body', 'hidden_face', 'two_people',
          'camera_change', 'overlapping_voices')


def _finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def file_sha(path):
    value = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            value.update(chunk)
    return value.hexdigest()


def manifest_basis(manifest):
    """Annotations/consent are editable; immutable frame/source anchors are not."""
    return digest({k: v for k, v in manifest.items()
                   if k not in ('manifest_sha256', 'ground_truth_consent', 'samples')} | {
        'samples': [{k: v for k, v in s.items() if k != 'human'} for s in manifest['samples']]})


def create_manifest(source, *, count=14, window_seconds=2., windows=None):
    """Plan editable review windows; requested strata are NOT observed scene labels.

    source is supplied metadata {sha256, duration, filename}. No video is opened.
    Each window has one explicit frame anchor; users may edit before derivation.
    """
    duration = source.get('duration')
    if not _sha(source.get('sha256')) or not _finite(duration) or duration <= 0:
        raise ValueError('Source SHA256 and finite measured duration required')
    if not isinstance(count, int) or isinstance(count, bool) or not 10 <= count <= 20:
        raise ValueError('10..20 windows required')
    if not _finite(window_seconds) or window_seconds <= 0:
        raise ValueError('Positive window required')
    if windows is None:
        width = min(window_seconds, duration / count)
        windows = [{'start': i * duration / count,
                    'end': min(duration, (i + 1) * duration / count, i * duration / count + width),
                    'requested_stratum': STRATA[i % len(STRATA)]} for i in range(count)]
    if not 10 <= len(windows) <= 20:
        raise ValueError('10..20 windows required')
    samples = []
    for index, window in enumerate(windows):
        start, end = window['start'], window['end']
        if not all(_finite(v) for v in (start, end)) or not 0 <= start < end <= duration:
            raise ValueError('Invalid window timestamps')
        if any(max(start, s['start']) < min(end, s['end']) for s in samples):
            raise ValueError('Overlapping sample windows')
        samples.append({'sample_id': f'BODY_{index+1:03}', 'start': start, 'end': end,
                        'time': (start + end) / 2,
                        'requested_stratum': window.get('requested_stratum'),
                        'image_evidence': None,
                        'human': {'status': 'unreviewed', 'reviewer': None,
                                  'bodies': None, 'speaker_person': None,
                                  'scene_type': None, 'simultaneous_people': None}})
    result = {'schema_version': 'stage58.body_ab.v1', 'source': deepcopy(source),
              'source_hash_basis': 'supplied_metadata_not_rehashed_media',
              'strata_are_requests_not_labels': True, 'samples': samples,
              'ground_truth_consent': None, 'status': 'READY_FOR_REVIEW',
              'preview_approved': None, 'publish_ready': False}
    result['manifest_sha256'] = manifest_basis(result)
    return result


def validate_manifest(manifest):
    if manifest_basis(manifest) != manifest.get('manifest_sha256'):
        raise ValueError('Manifest anchors changed; regenerate before execution/review')
    source = manifest['source']
    # Reuse the window validator, including source hash and duplicate/overlap checks.
    create_manifest(source, windows=manifest['samples'])
    ids = [s['sample_id'] for s in manifest['samples']]
    if len(set(ids)) != len(ids):
        raise ValueError('Duplicate sample IDs')
    for s in manifest['samples']:
        if not _finite(s['time']) or not s['start'] <= s['time'] < s['end']:
            raise ValueError('Frame timestamp outside window')


def derive_frames(manifest, video, output_dir, *, consent_local=False):
    """Explicit local consent only; decode at most 20 frames, no audio/pipeline."""
    if consent_local is not True:
        raise ValueError('Explicit local image derivation consent required')
    validate_manifest(manifest)
    if file_sha(video) != manifest['source']['sha256'].lower():
        raise ValueError('Source media hash mismatch')
    import cv2
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=False)
    capture = cv2.VideoCapture(str(video))
    result = deepcopy(manifest)
    try:
        if not capture.isOpened():
            raise ValueError('Source cannot be decoded')
        for sample in result['samples']:
            capture.set(cv2.CAP_PROP_POS_MSEC, sample['time'] * 1000)
            ok, frame = capture.read()
            if not ok:
                raise ValueError('Sample frame unavailable')
            path = output / (sample['sample_id'] + '.png')
            if not cv2.imwrite(str(path), frame):
                raise OSError('Frame write failed')
            sample['image_evidence'] = {'path': str(path.resolve()), 'sha256': file_sha(path),
                                        'source_sha256': result['source']['sha256'],
                                        'requested_time': sample['time'],
                                        'decoder_position_ms': capture.get(cv2.CAP_PROP_POS_MSEC),
                                        'consent_local': True}
    finally:
        capture.release()
    result['source_hash_basis'] = 'rehash_local_media_before_derivation'
    result['manifest_sha256'] = manifest_basis(result)
    return result


def run_backend(manifest, cfg, *, mode, consent_local=False, detector_factory=None):
    """Execute only the manifest's frozen images, using existing local backends.

    config must be identical across runs; only body_backend is selected by mode.
    Wall time includes face/embedding work; body time is reported separately.
    """
    if consent_local is not True or mode not in ('baseline', 'candidate'):
        raise ValueError('Explicit local execution consent and baseline/candidate required')
    validate_manifest(manifest)
    import cv2
    from .vision import PersonDetectionEngine
    # Verify ALL anchors before loading a detector or executing any frame.
    for s in manifest['samples']:
        image = s.get('image_evidence') or {}
        if (image.get('consent_local') is not True or not _sha(image.get('sha256'))
                or image.get('source_sha256') != manifest['source']['sha256']
                or image.get('requested_time') != s['time']
                or file_sha(image['path']) != image['sha256']):
            raise ValueError('Consented same-source image/hash required')
    settings = deepcopy(cfg)
    settings['body_backend'] = 'hog' if mode == 'baseline' else 'yolo'
    notes = []
    engine = (detector_factory or PersonDetectionEngine)(settings, notes, True)
    frames = []
    started = perf_counter()
    cpu_started = process_time()
    try:
        for s in manifest['samples']:
            image = s['image_evidence']
            # Recheck immediately before decode (an edited PNG cannot join the pair).
            if file_sha(image['path']) != image['sha256']:
                raise ValueError('Image changed during run')
            frame = cv2.imread(image['path'])
            if frame is None:
                raise ValueError('Derived frame cannot be decoded')
            before = engine.backend_execution().get('successful_calls', {})
            frame_started = perf_counter()
            frame_cpu_started = process_time()
            detections = engine.detect(frame, s['time'], s['sample_id'])
            after = engine.backend_execution().get('successful_calls', {})
            frames.append({'sample_id': s['sample_id'], 'time': s['time'],
                           'image_sha256': image['sha256'],
                           'wall_seconds': perf_counter() - frame_started,
                           'cpu_process_seconds': process_time() - frame_cpu_started,
                           'executed_backends': [name for name in ('hog', 'yolo')
                                                 if after.get(name, 0) > before.get(name, 0)],
                           'detections': [{k: deepcopy(d.get(k)) for k in
                               ('bbox', 'face_bbox', 'face_visible', 'body_visible',
                                'body_detection_source', 'embedding_missing_reason')}
                               for d in detections],
                           'speaker_person': None})
        execution = engine.backend_execution()
        body_seconds = engine.phase_seconds.get('body_detection')
    finally:
        engine.close()
    return {'mode': mode, 'source_sha256': manifest['source']['sha256'],
            'manifest_sha256': manifest['manifest_sha256'], 'config_sha256': digest(cfg),
            'config': deepcopy(cfg), 'frames': frames, 'execution': execution,
            'wall_seconds': perf_counter() - started, 'body_seconds': body_seconds,
            'cpu_process_seconds': process_time() - cpu_started,
            'gpu_kernel_seconds': None,
            'timing_basis': 'wall_clock_not_gpu_kernel_profiler', 'notes': notes,
            'identity_proof': None, 'publish_ready': False}


def _box(box):
    if not isinstance(box, dict) or not all(_finite(box.get(k)) for k in ('x', 'y', 'width', 'height')):
        raise ValueError('Finite normalized body box required')
    if not (0 <= box['x'] < 1 and 0 <= box['y'] < 1 and box['width'] > 0 and box['height'] > 0
            and box['x'] + box['width'] <= 1.000001 and box['y'] + box['height'] <= 1.000001):
        raise ValueError('Body box outside normalized frame')
    return box


def _matches(truth, predictions, threshold):
    """Maximum-cardinality bipartite match, so crowded frames don't inflate FP/FN."""
    edges = {i: sorted([j for j, p in enumerate(predictions)
                        if iou(_box(t['bbox']), _box(p['bbox'])) >= threshold],
                       key=lambda j: -iou(t['bbox'], predictions[j]['bbox']))
             for i, t in enumerate(truth)}
    assigned = {}
    def augment(i, seen):
        for j in edges[i]:
            if j in seen:
                continue
            seen.add(j)
            if j not in assigned or augment(assigned[j], seen):
                assigned[j] = i
                return True
        return False
    for i in edges:
        augment(i, set())
    return {i: j for j, i in assigned.items()}


def compare_ab(manifest, baseline, candidate, *, body_iou=.5):
    """Accuracy only on complete, consented human frame annotations.

    Anonymous human instance_id anchors bridge backend-specific track IDs.
    None bodies means unreviewed; [] is an explicitly verified empty frame.
    """
    validate_manifest(manifest)
    if not _finite(body_iou) or not 0 < body_iou <= 1:
        raise ValueError('Invalid evaluation IoU')
    result = {'schema_version': 'stage58.body_ab_report.v1', 'status': 'NOT_MEASURED',
              'manifest_sha256': manifest['manifest_sha256'], 'goldset_sha256': digest(manifest),
              'evaluation_iou': body_iou, 'improvement_accepted': None,
              'editorial_benefit': {'status': 'NOT_MEASURED', 'value': None},
              'publish_ready': False, 'preview_approved': None,
              'scope': 'supplied_targeted_frames_only_not_population_accuracy',
              'quality_threshold_changes': None}
    result['source_sha256'] = manifest['source']['sha256']
    result['run_sha256'] = {'baseline': digest(baseline), 'candidate': digest(candidate)}
    ids = {s['sample_id']: s for s in manifest['samples']}
    for mode, run in (('baseline', baseline), ('candidate', candidate)):
        if (run.get('mode') != mode or run.get('source_sha256') != manifest['source']['sha256']
                or run.get('manifest_sha256') != manifest['manifest_sha256']
                or digest(run.get('config')) != run.get('config_sha256')):
            return {**result, 'reason': 'source_manifest_mode_or_config_mismatch'}
        rows = run.get('frames', [])
        if len(rows) != len(ids) or {r['sample_id'] for r in rows} != set(ids):
            return {**result, 'reason': 'same_complete_frame_set_required'}
        for row in rows:
            s = ids[row['sample_id']]
            image = s.get('image_evidence') or {}
            if (image.get('consent_local') is not True
                    or image.get('source_sha256') != manifest['source']['sha256']
                    or image.get('requested_time') != s['time']
                    or not _sha(image.get('sha256')) or row.get('image_sha256') != image['sha256']
                    or row.get('time') != s['time']):
                return {**result, 'reason': 'frame_hash_or_timestamp_mismatch'}
    if baseline['config_sha256'] != candidate['config_sha256']:
        return {**result, 'reason': 'same_parameters_required'}
    consent = manifest.get('ground_truth_consent') or {}
    reviewed = {s['sample_id']: s for s in manifest['samples']
                if consent.get('allowed') is True and consent.get('reviewer')
                and consent.get('source_sha256') == manifest['source']['sha256']
                and consent.get('manifest_sha256') == manifest['manifest_sha256']
                and s['human'].get('status') == 'verified' and s['human'].get('reviewer')
                and isinstance(s['human'].get('bodies'), list)}

    def evaluate(run, expected):
        execution = run.get('execution') or {}
        # Execution is independently auditable; availability does not count.
        sources = {d.get('body_detection_source') for f in run['frames']
                   for d in f.get('detections', []) if d.get('body_visible') is True}
        executed = execution.get('successful_backends') or []
        verified_backend = (expected in executed and not (sources - {expected}) and executed == [expected]
                            and all(f.get('executed_backends') == [expected] for f in run['frames']))
        description = {'detection_count': sum(d.get('body_visible') is True for f in run['frames'] for d in f.get('detections', [])),
                       'backend_availability': execution.get('initialized'),
                       'execution': deepcopy(execution), 'backend_substitution_verified': verified_backend,
                       'wall_seconds': run.get('wall_seconds'), 'body_seconds': run.get('body_seconds'),
                       'cpu_process_seconds': run.get('cpu_process_seconds'),
                       'gpu_kernel_seconds': run.get('gpu_kernel_seconds'),
                       'timing_basis': run.get('timing_basis'),
                       'config_sha256': run['config_sha256'],
                       'frame_audit': [{k: deepcopy(f.get(k)) for k in
                           ('sample_id', 'time', 'image_sha256', 'executed_backends',
                            'wall_seconds', 'cpu_process_seconds')} for f in run['frames']],
                       'body': {'status': 'NOT_MEASURED', 'precision': None, 'recall': None},
                       'reid': {'status': 'NOT_MEASURED', 'false_merge': None, 'false_split': None, 'abstentions': None},
                       'speaker_person': {'status': 'NOT_MEASURED', 'false_bindings': None, 'abstentions': None}}
        tp = fp = fn = 0
        instances = {}
        binding_rows = []
        for frame in run['frames']:
            sample = reviewed.get(frame['sample_id'])
            if sample is None:
                continue
            truth = sample['human']['bodies']
            predictions = [d for d in frame.get('detections', []) if d.get('body_visible') is True]
            for d in predictions:
                _box(d['bbox'])
            seen = set()
            for t in truth:
                _box(t['bbox'])
                instance = t.get('instance_id')
                if not isinstance(instance, str) or not instance.strip() or instance in seen:
                    raise ValueError('Unique human instance IDs required per frame')
                seen.add(instance)
            matched = _matches(truth, predictions, body_iou)
            tp += len(matched); fp += len(predictions) - len(matched); fn += len(truth) - len(matched)
            for i, t in enumerate(truth):
                label = t.get('identity_label')
                if not isinstance(label, str) or label.strip().lower() in ('', 'unknown', '?', 'uncertain'):
                    continue
                entry = instances.setdefault(t['instance_id'], {'label': label, 'predictions': set()})
                if entry['label'] != label:
                    raise ValueError('Conflicting human instance identity')
                p = predictions[matched[i]].get('person_id') if i in matched else None
                if p is not None and (not isinstance(p, str) or not p.strip()):
                    raise ValueError('Predicted anonymous person ID must be a nonempty string or null')
                entry['predictions'].add(p or None)
            if isinstance(sample['human'].get('speaker_person'), dict):
                binding_rows.append((sample['human']['speaker_person'], frame.get('speaker_person') or {}))
        if reviewed:
            description['body'] = {'status': 'MEASURED', 'true_positive': tp, 'false_positive': fp, 'false_negative': fn,
                                   'reviewed_frames': len(reviewed), 'precision': tp/(tp+fp) if tp+fp else None,
                                   'recall': tp/(tp+fn) if tp+fn else None}
        resolved = {k: next(iter(v['predictions'])) if len(v['predictions']) == 1 else None for k, v in instances.items()}
        if len(instances) >= 2:
            pairs = [(a, b) for a, b in combinations(instances, 2) if resolved[a] and resolved[b]]
            description['reid'] = {'status': 'MEASURED',
                'false_merge': sum(instances[a]['label'] != instances[b]['label'] and resolved[a] == resolved[b] for a, b in pairs),
                'false_split': sum(instances[a]['label'] == instances[b]['label'] and resolved[a] != resolved[b] for a, b in pairs),
                'abstentions': sum(not p for p in resolved.values()), 'reviewed_instances': len(instances)}
        clusters = {}
        for instance, pid in resolved.items():
            if pid:
                clusters.setdefault(pid, set()).add(instances[instance]['label'])
        if binding_rows:
            false = abstained = total = 0
            for truth, proposed in binding_rows:
                for speaker, label in truth.items():
                    if label not in {v['label'] for v in instances.values()}:
                        raise ValueError('Speaker truth requires reviewed anonymous identity')
                    total += 1
                    labels = clusters.get(proposed.get(speaker))
                    if not labels:
                        abstained += 1
                    elif labels != {label}:
                        false += 1
            if total:
                description['speaker_person'] = {'status': 'MEASURED', 'false_bindings': false,
                                                 'abstentions': abstained, 'reviewed_bindings': total}
        return description
    result['baseline'] = evaluate(baseline, 'hog')
    result['candidate'] = evaluate(candidate, 'yolo')
    result['reason'] = 'consented_human_review_required' if not reviewed else 'paired_targeted_human_review'
    if reviewed:
        result['status'] = 'MEASURED'
    a, b = result['baseline'], result['candidate']
    if reviewed and a['backend_substitution_verified'] and b['backend_substitution_verified']:
        if all(v[k]['status'] == 'MEASURED' for v in (a, b) for k in ('reid', 'speaker_person')):
            keys = (('reid', 'false_merge'), ('reid', 'false_split'), ('reid', 'abstentions'),
                    ('speaker_person', 'false_bindings'), ('speaker_person', 'abstentions'),
                    ('body', 'false_positive'), ('body', 'false_negative'))
            result['improvement_accepted'] = (b['reid']['false_merge'] == 0
                                              and b['speaker_person']['false_bindings'] == 0
                                              and all(b[k][m] <= a[k][m] for k, m in keys)
                                              and any(b[k][m] < a[k][m] for k, m in keys))
    return result
