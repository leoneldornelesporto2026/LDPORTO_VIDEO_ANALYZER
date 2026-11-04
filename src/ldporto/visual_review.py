"""Artifact-only visual goldset and paired evaluation. No decoder or inference.

Human identities are anonymous labels; predictions never populate human fields.
Metrics describe this targeted review, not population accuracy or publication gates.
"""
from collections import Counter, defaultdict
from copy import deepcopy
from itertools import combinations
import math

from .core import digest
from .identity_goldset import sample_tracklets, evaluate_annotations
from .visual_identity_audit import audit_embedding_gaps


HUMAN_FIELDS = ('tracklet_identities', 'offscreen', 'active_speaker_person',
                'speaker_person_bindings', 'simultaneous_speakers', 'source_cuts',
                'shot_type', 'bounding_boxes', 'uncertainty', 'reviewer')


def _sha(value):
    return (isinstance(value, str) and len(value) == 64
            and all(c in '0123456789abcdef' for c in value.lower()))


def fallback_diagnosis(analysis):
    """Use per-window evidence, retaining intervals and causes; never infer 95.69%."""
    windows = analysis.get('camera_director_focus_window_audit', [])
    seconds, examples = Counter(), defaultdict(list)
    ordered = sorted(windows, key=lambda r: r['start'])
    last = -math.inf
    for row in ordered:
        start, end = row['start'], row['end']
        if not all(isinstance(v, (int, float)) and math.isfinite(v) for v in (start, end)) or end <= start or start < last:
            raise ValueError('Focus windows must be finite and non-overlapping')
        last = end
        if row.get('focus_person') is None:
            reason = row.get('reason_code') or 'UNKNOWN_REQUIRES_REVIEW'
            seconds[reason] += end - start
            examples[reason].append(deepcopy(row))
    duration = (analysis.get('metadata') or {}).get('duration')
    known_duration = isinstance(duration, (int, float)) and math.isfinite(duration) and duration > 0
    covered = sum(r['end'] - r['start'] for r in ordered)
    return {'status': 'sampled_evidence' if ordered else 'requires_review',
            'fallback_seconds_by_reason': dict(seconds), 'windows_by_reason': dict(examples),
            'audited_seconds': covered if ordered else None,
            'fallback_fraction_of_audited_windows': sum(seconds.values()) / covered if covered else None,
            'unaccounted_video_seconds': max(0., duration - covered) if known_duration and ordered else None,
            'source_sha256': (analysis.get('metadata') or {}).get('sha256'),
            'analysis_sha256': digest(analysis), 'accuracy': None, 'publish_ready': False}


def create_goldset(analysis, *, limit=16, window_seconds=4.):
    if not isinstance(limit, int) or not 10 <= limit <= 20:
        raise ValueError('Goldset limit must be 10..20')
    if not math.isfinite(window_seconds) or window_seconds <= 0:
        raise ValueError('Window must be positive and finite')
    metadata = analysis.get('metadata') or {}
    duration = metadata.get('duration')
    if not isinstance(duration, (int, float)) or not math.isfinite(duration) or duration <= 0:
        raise ValueError('Measured source duration required')
    observations = analysis.get('people_observations', [])
    reid = analysis.get('person_reid') or {'tracklets': analysis.get('raw_tracks', [])}
    seeds = sample_tracklets({'observations': observations}, reid, limit=limit * 4)
    windows = analysis.get('camera_director_focus_window_audit', [])
    # Round robin across fallback causes and identity strata, then spread in time.
    strata = defaultdict(list)
    for row in windows:
        strata[row.get('reason_code') or 'unknown'].append((row['start'] + row['end']) / 2)
    for row in seeds:
        if isinstance(row.get('time'), (int, float)) and math.isfinite(row['time']):
            strata['tracklet_review'].append(row['time'])
    for key in strata:
        values = sorted(set(t for t in strata[key] if 0 <= t < duration))
        # Interleave early and late candidates to avoid a prefix-only sample.
        strata[key] = values[::2] + values[1::2][::-1]
    selected = []
    while len(selected) < limit and any(strata.values()):
        for key in sorted(strata):
            if not strata[key] or len(selected) >= limit:
                continue
            time = strata[key].pop(0)
            start = max(0., min(time - window_seconds / 2, duration - window_seconds))
            end = min(duration, start + window_seconds)
            if any(max(start, a) < min(end, b) for a, b, _ in selected):
                continue
            selected.append((start, end, key))
    samples = []
    for start, end, stratum in sorted(selected):
        obs = [deepcopy(r) for r in observations if isinstance(r.get('time'), (int, float)) and start <= r['time'] < end]
        # Vectors are unnecessary for annotation; retain supplied box/provenance fields.
        for row in obs:
            row.pop('face_embedding', None)
        overlap = lambda r: r.get('start', end) < end and r.get('end', start) > start
        evidence = {'observations': obs,
                    'shots': [deepcopy(r) for r in analysis.get('shots', []) if overlap(r)],
                    'active_speaker': [deepcopy(r) for r in analysis.get('active_speaker', []) if overlap(r)],
                    'camera_timeline': [deepcopy(r) for r in analysis.get('camera_director_timeline', []) if overlap(r)],
                    'focus_windows': [deepcopy(r) for r in windows if overlap(r)],
                    'speech_overlaps': [deepcopy(r) for r in analysis.get('speech_overlaps', []) if overlap(r)]}
        samples.append({'sample_id': f'VISUAL_{len(samples)+1:03}', 'start': start, 'end': end,
                        'stratum': stratum, 'evidence': evidence, 'evidence_sha256': digest(evidence),
                        'image_evidence': None, 'annotation_status': 'unreviewed',
                        'human': {key: None for key in HUMAN_FIELDS}})
    return {'schema_version': 'stage50.visual_review.v1', 'source_sha256': metadata.get('sha256'),
            'origin_analysis_sha256': digest(analysis), 'source_filename': metadata.get('filename'),
            'protocol_sha256': digest({'fields': HUMAN_FIELDS, 'window_seconds': window_seconds, 'limit': limit,
                                       'selection': 'deterministic_cause_and_tracklet_nonoverlap_v1'}),
            'samples': samples, 'requested_samples': limit,
            'status': 'READY_FOR_REVIEW' if 10 <= len(samples) <= 20 and _sha(metadata.get('sha256')) else 'PARTIAL',
            'shortfall_reason': 'insufficient_nonoverlapping_evidence' if len(samples) < 10 else None,
            'fallback_diagnosis': fallback_diagnosis(analysis),
            'embedding_gap_diagnosis': audit_embedding_gaps({'observations': observations}, reid),
            'source_hash_basis': 'supplied_metadata_not_rehashed_media',
            'preview_approved': None, 'publish_ready': False}


def compare_goldset(goldset, before, after):
    """Exact reviewed anchors; absent/ambiguous predictions count as abstentions.

    speaker_person_bindings maps a speaker ID to a human anonymous identity label.
    tracklet_identities maps each track ID to that same human label vocabulary.
    Both identities and binding labels must be supplied by the reviewer.
    """
    empty = {'improvement_accepted': None, 'before': None, 'after': None,
             'preview_approved': None, 'publish_ready': False}
    source = goldset.get('source_sha256')
    if (not _sha(source) or not _sha(goldset.get('protocol_sha256')) or
            any(str((a.get('metadata') or {}).get('sha256') or '').lower() != source.lower() for a in (before, after))):
        return {**empty, 'reason': 'same_source_and_review_protocol_required'}
    samples = goldset.get('samples', [])
    if len({s['sample_id'] for s in samples}) != len(samples):
        raise ValueError('Duplicate sample IDs')
    for sample in samples:
        if digest(sample['evidence']) != sample.get('evidence_sha256'):
            return {**empty, 'reason': 'review_evidence_changed'}
    reviewed = [s for s in samples if s.get('annotation_status') == 'verified'
                and (s.get('human') or {}).get('reviewer')
                and isinstance((s.get('human') or {}).get('tracklet_identities'), dict)
                and (s.get('human') or {}).get('uncertainty') is False]
    labels = {}
    for sample in reviewed:
        tracks = {str(o['track_id']) for o in sample['evidence']['observations'] if o.get('track_id')}
        for track, label in sample['human']['tracklet_identities'].items():
            if track not in tracks or not isinstance(label, str) or label.strip().lower() in ('', 'unknown', 'uncertain', '?'):
                raise ValueError('Human labels require an observed track reference')
            if track in labels and labels[track] != label:
                raise ValueError('Conflicting human labels')
            labels[track] = label
    if len(labels) < 2:
        return {**empty, 'reason': 'insufficient_verified_human_labels'}

    def anchor(obs):
        return digest({key: obs.get(key) for key in ('track_id', 'time', 'scene_id', 'face_bbox', 'bbox')})
    anchors = {anchor(obs) for sample in reviewed for obs in sample['evidence']['observations']
               if str(obs.get('track_id') or '') in labels}

    def evaluate(analysis):
        predictions = defaultdict(set)
        matched_tracks = set()
        for obs in analysis.get('people_observations', []):
            tid = str(obs.get('track_id') or '')
            if tid in labels and anchor(obs) in anchors:
                matched_tracks.add(tid)
                if obs.get('person_id'):
                    predictions[tid].add(str(obs['person_id']))
        mapping = (analysis.get('person_reid') or {}).get('tracklet_to_person', {})
        for tid in labels:
            if tid in matched_tracks and mapping.get(tid):
                predictions[tid].add(str(mapping[tid]))
        predicted = {tid: next(iter(ids)) if len(ids) == 1 else None for tid, ids in predictions.items()}
        annotations = [{'track_id': tid, 'annotation_label': label, 'annotation_status': 'verified',
                        'predicted_person_id': predicted.get(tid)} for tid, label in labels.items()]
        metrics = evaluate_annotations(annotations)
        clusters = defaultdict(set)
        for tid, pid in predicted.items():
            if pid:
                clusters[pid].add(labels[tid])
        bindings = false_bindings = abstained = correct = 0
        binding_seconds = false_binding_seconds = abstention_seconds = correct_seconds = 0.
        for sample in reviewed:
            truth = sample['human'].get('speaker_person_bindings')
            if not isinstance(truth, dict):
                continue
            for speaker, identity in truth.items():
                if identity not in labels.values():
                    raise ValueError('Binding truth must reference a reviewed identity')
                rows = [r for r in analysis.get('active_speaker', []) if r.get('speaker_id') == speaker
                        and r['start'] < sample['end'] and r['end'] > sample['start']]
                points = sorted({sample['start'], sample['end']} | {max(sample['start'], r['start']) for r in rows}
                                | {min(sample['end'], r['end']) for r in rows})
                for left, right in zip(points, points[1:]):
                    live = [r for r in rows if r['start'] <= left and r['end'] >= right]
                    ids = {r.get('person_id') for r in live if r.get('person_id')}
                    bindings += 1
                    binding_seconds += right - left
                    if len(ids) != 1 or not all(r.get('person_id') for r in live):
                        abstained += 1
                        abstention_seconds += right - left
                        continue
                    candidates = clusters.get(next(iter(ids)))
                    if not candidates:
                        abstained += 1
                        abstention_seconds += right - left
                    elif candidates != {identity}:
                        false_bindings += 1
                        false_binding_seconds += right - left
                    else:
                        correct += 1
                        correct_seconds += right - left
        resolved_pairs = [(a, b) for a, b in combinations(labels, 2) if predicted.get(a) and predicted.get(b)]
        metrics.update(false_split_pairs=sum(labels[a] == labels[b] and predicted[a] != predicted[b] for a, b in resolved_pairs),
                       identity_abstentions=sum(not predicted.get(t) for t in labels),
                       tracks_without_matching_review_anchor=sum(t not in matched_tracks for t in labels),
                       speaker_person_false_binding_count=false_bindings if bindings else None,
                       speaker_person_binding_windows=bindings, speaker_person_binding_abstentions=abstained,
                       speaker_person_false_binding_seconds=false_binding_seconds if bindings else None,
                       speaker_person_binding_abstention_seconds=abstention_seconds,
                       speaker_person_reviewed_seconds=binding_seconds,
                       verified_binding_coverage=correct_seconds / binding_seconds if binding_seconds else None,
                       predicted_identity_coverage=sum(bool(predicted.get(t)) for t in labels) / len(labels),
                       verified_identity_coverage=sum(bool(predicted.get(t)) and clusters[predicted[t]] == {labels[t]}
                                                      for t in labels) / len(labels),
                       analysis_sha256=digest(analysis), source_sha256=source)
        return metrics
    old, new = evaluate(before), evaluate(after)
    # Coverage/fragmentation alone cannot accept improvement; errors and abstention
    # must not worsen, and binding truth must be present in both versions.
    measured = old['speaker_person_false_binding_count'] is not None and new['speaker_person_false_binding_count'] is not None
    error_keys = ('false_merge_pairs', 'false_split_pairs', 'speaker_person_false_binding_seconds',
                  'identity_abstentions', 'speaker_person_binding_abstention_seconds')
    safe = measured and all(new[k] <= old[k] for k in error_keys)
    improved = safe and any(new[k] < old[k] for k in error_keys[:3])
    return {**empty, 'before': old, 'after': new, 'improvement_accepted': bool(improved) if measured else None,
            'reason': 'paired_human_review_only' if measured else 'binding_labels_required',
            'protocol_sha256': goldset['protocol_sha256'], 'goldset_sha256': digest(goldset),
            'samples': [{'sample_id': s['sample_id'], 'start': s['start'], 'end': s['end'],
                         'origin_analysis_sha256': goldset['origin_analysis_sha256'],
                         'evidence_sha256': s['evidence_sha256']} for s in reviewed],
            'scope': 'targeted_sample_not_population_accuracy_or_render_approval'}
