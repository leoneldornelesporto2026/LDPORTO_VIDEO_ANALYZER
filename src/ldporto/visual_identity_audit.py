"""Trace observed causes of embedding-free tracklets; no ground truth assumed."""
from collections import Counter, defaultdict


def audit_embedding_gaps(vision, reid=None):
    grouped = defaultdict(list)
    for row in vision.get('observations', []):
        if row.get('track_id'):
            grouped[str(row['track_id'])].append(row)
    state = {t['track_id']:t for t in (reid or {}).get('tracklets', [])}
    reasons, micro_reasons = Counter(), Counter()
    examples = defaultdict(list)
    for tid, rows in grouped.items():
        track = state.get(tid, {})
        micro = track.get('tracklet_state') == 'micro_tracklet'
        if not track:
            times = sorted({r['time'] for r in rows if isinstance(r.get('time'), (int,float))})
            micro = len(times) < 3 or not times or times[-1]-times[0] < 1
        if any(r.get('face_embedding') is not None for r in rows):
            continue
        if not any(r.get('face_visible') for r in rows):
            reason = 'body_only_no_face_detected'
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
        if micro:
            micro_reasons[reason] += 1
        if len(examples[reason]) < 12:
            examples[reason].append(tid)
    return {'tracklet_count':len(grouped),
            'tracklets_without_embedding':sum(reasons.values()),
            'embedding_absence_by_cause':dict(sorted(reasons.items())),
            'micro_without_embedding_by_cause':dict(sorted(micro_reasons.items())),
            'example_tracklet_ids_by_cause':dict(examples),
            'source':'observed_tracking_data',
            'ground_truth':False,
            'limitations':['Sem frames originais nao confirma falsos negativos do detector.',
                           'Razoes legadas desconhecidas nao sao imputadas a um backend.']}
