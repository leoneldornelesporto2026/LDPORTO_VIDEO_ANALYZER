"""Trace observed causes of embedding-free tracklets; no ground truth assumed."""
from collections import Counter, defaultdict
import math


def _category(row):
    reason = row.get('embedding_missing_reason') or ''
    if reason in ('face_detector_unavailable', 'face_detector_error'):
        return reason
    if reason.startswith('sface_unavailable'):
        return 'extractor_unavailable'
    if reason == 'embedding_extraction_failed':
        return 'extractor_error'
    # Only explicit evidence may assert occlusion. Landmark/profile failures
    # are quality signals, not an occlusion diagnosis.
    if row.get('face_occlusion_verified') is True:
        return 'verified_occlusion'
    if not row.get('face_visible'):
        return 'no_face_detected'
    if reason == 'quality_rejected':
        return 'quality_gate'
    if reason == 'embedding_not_due':
        return 'sampling_not_due'
    return 'unknown'


def audit_embedding_gaps(vision, reid=None):
    grouped = defaultdict(list)
    for row in vision.get('observations', []):
        if row.get('track_id'):
            grouped[str(row['track_id'])].append(row)
    summaries = (reid or {}).get('tracklets', [])
    state = {t['track_id']:t for t in summaries}
    reasons, micro_reasons = Counter(), Counter()
    examples = defaultdict(list)
    categories, details = Counter(), Counter()
    track_evidence = []
    availability_only = 0
    for tid, rows in grouped.items():
        track = state.get(tid, {})
        micro = track.get('tracklet_state') == 'micro_tracklet'
        if not track:
            times = sorted({r['time'] for r in rows if isinstance(r.get('time'), (int,float))})
            micro = len(times) < 3 or not times or times[-1]-times[0] < 1
        if any(r.get('face_embedding') is not None for r in rows):
            continue
        if any(r.get('face_embedding_available') is True for r in rows):
            # Compact exports omit vectors. Available != fresh observed, but
            # omission of a vector must not be reported as extraction failure.
            availability_only += 1
            continue
        if not any(r.get('face_visible') for r in rows):
            failures = [r.get('embedding_missing_reason') for r in rows
                        if r.get('embedding_missing_reason') in ('face_detector_unavailable', 'face_detector_error')]
            reason = failures[0] if failures else 'body_only_no_face_detected'
        else:
            explicit = [r.get('embedding_missing_reason') for r in rows if r.get('embedding_missing_reason')]
            if explicit:
                # Choose the most actionable reason for this tracklet.
                priority = ('sface_unavailable', 'quality_rejected', 'embedding_extraction_failed',
                            'embedding_not_due', 'face_detected_without_embedding')
                reason = next((p for p in priority if p in explicit), Counter(explicit).most_common(1)[0][0])
            elif any(r.get('embedding_reused') for r in rows):
                reason = 'reused_embedding_not_in_raw_observations'
            else:
                reason = 'face_detected_embedding_missing_unknown'
        reasons[reason] += 1
        observed_categories = sorted({_category(row) for row in rows})
        quality_reasons = sorted({detail for row in rows
                                 for detail in (row.get('face_quality') or {}).get('rejection_reasons', [])})
        categories.update(observed_categories)
        details.update(quality_reasons)
        track_evidence.append({'track_id': tid, 'micro_tracklet': micro,
                               'primary_cause': reason, 'observed_categories': observed_categories,
                               'quality_rejection_reasons': quality_reasons,
                               'occlusion_verified': True if any(r.get('face_occlusion_verified') is True
                                                                for r in rows) else None})
        if micro:
            micro_reasons[reason] += 1
        if len(examples[reason]) < 12:
            examples[reason].append(tid)
    return {'tracklet_count':len(grouped),
            'tracklets_without_embedding':sum(reasons.values()),
            'tracklets_with_availability_only':availability_only,
            'counts_scope':'distinct_observed_track_id_not_summary_entries',
            'summary_tracklet_count':len(summaries),
            'summary_tracklets_without_embedding':sum(t.get('embedding_sample_count') == 0 for t in summaries),
            'embedding_absence_by_cause':dict(sorted(reasons.items())),
            'micro_without_embedding_by_cause':dict(sorted(micro_reasons.items())),
            'example_tracklet_ids_by_cause':dict(examples),
            'missing_tracklet_evidence':track_evidence,
            'missing_tracklets_by_observed_category':dict(sorted(categories.items())),
            'missing_tracklets_by_quality_reason':dict(sorted(details.items())),
            'category_count_scope':'nonexclusive_tracklets_without_embedding_evidence',
            'source':'observed_tracking_data',
            'ground_truth':False,
            'limitations':['Sem frames originais nao confirma falsos negativos do detector.',
                           'Razoes legadas desconhecidas nao sao imputadas a um backend.']}


def compare_embedding_recovery(before, after):
    """Conservative acceptance of two audit records bound to the same review.

    Quality measures must come from human verified evaluation, not the detector
    gate's own acceptance rate. Missing proof stays null.
    """
    blockers = []
    for key in ('source_sha256', 'sampling_protocol_sha256', 'review_set_sha256'):
        a, b = before.get(key), after.get(key)
        if not (isinstance(a, str) and len(a) == 64 and
                all(c in '0123456789abcdef' for c in a.lower()) and a == b):
            blockers.append(key + '_missing_or_mismatched')
    for record in (before, after):
        metrics = record.get('verified_quality') or {}
        if metrics.get('human_verified') is not True:
            blockers.append('human_quality_unverified')
        for key in ('usable_face_fraction', 'false_merge_pair_rate'):
            value = metrics.get(key)
            if (isinstance(value, bool) or not isinstance(value, (int, float)) or
                    not math.isfinite(value) or not 0 <= value <= 1):
                blockers.append(key + '_missing_or_invalid')
        for key in ('tracklet_count', 'tracklets_without_embedding'):
            value = record.get(key)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                blockers.append(key + '_invalid')
        if (isinstance(record.get('tracklet_count'), int) and
                isinstance(record.get('tracklets_without_embedding'), int) and
                not 0 <= record['tracklets_without_embedding'] <= record['tracklet_count']):
            blockers.append('inconsistent_tracklet_counts')
    if blockers:
        return {'comparable':False, 'reduction_accepted':None, 'blockers':sorted(set(blockers))}
    old, new = before['verified_quality'], after['verified_quality']
    # Absolute reduction with no worsening of the missing fraction prevents a
    # changed tracklet denominator from creating an apparent gain.
    reduced = (after['tracklets_without_embedding'] < before['tracklets_without_embedding'] and
               after['tracklet_count'] > 0 and before['tracklet_count'] > 0 and
               after['tracklets_without_embedding']/after['tracklet_count'] <=
               before['tracklets_without_embedding']/before['tracklet_count'])
    quality_safe = (new['usable_face_fraction'] >= old['usable_face_fraction'] and
                    new['false_merge_pair_rate'] <= old['false_merge_pair_rate'])
    return {'comparable':True, 'reduction_accepted':reduced and quality_safe,
            'quality_not_worse':quality_safe, 'blockers':[]}
