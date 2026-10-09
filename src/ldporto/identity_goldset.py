"""Human-in-the-loop identity evaluation. No automated labels are ground truth.

Track IDs and anonymous human-assigned labels are deliberately separated.
Only compare different tracklets with human labels. Exclude 'unknown'.
"""
import csv
from collections import Counter, defaultdict
from pathlib import Path


FIELDS = ('track_id', 'time', 'scene_id', 'predicted_person_id', 'face_visible',
          'embedding_observed', 'face_quality', 'annotation_label', 'annotation_status', 'notes',
          'embedding_missing_reason', 'review_target')


def _track_class(track):
    if track.get('tracklet_state') == 'micro_tracklet':
        return 'micro_no_embedding' if not track.get('embedding_sample_count') else 'micro_with_embedding'
    return 'stable_no_embedding' if not track.get('embedding_sample_count') else 'stable_with_embedding'


def sample_tracklets(vision, reid, *, limit=96):
    """Deterministic stratified review with priority for ambiguous/embedding-free tracks."""
    grouped = defaultdict(list)
    for obs in vision.get('observations', []):
        if obs.get('track_id'):
            grouped[str(obs['track_id'])].append(obs)
    mapping = reid.get('tracklet_to_person', {})
    strata = defaultdict(list)
    tracks = reid.get('tracklets', [])
    if not tracks:
        tracks = [{'track_id': key, 'tracklet_state': 'micro_tracklet' if len(rows) < 3 else 'stable_tracklet',
                   'embedding_sample_count':sum(row.get('face_embedding') is not None for row in rows)}
                  for key, rows in grouped.items()]
    for track in tracks:
        tid = str(track['track_id'])
        rows = grouped.get(tid, [])
        if not rows:
            continue
        # Favor actual fresh face evidence, not a reused embedding from another frame.
        best = max(rows, key=lambda obs: (bool(obs.get('face_embedding')),
                  bool(obs.get('face_visible')),
                  (obs.get('face_quality') or {}).get('sharpness') or 0,
                  -(obs.get('time') or 0)))
        strata[_track_class(track)].append({
            'track_id':tid, 'time':best.get('time'), 'scene_id':best.get('scene_id'),
            'predicted_person_id':mapping.get(tid), 'face_visible':bool(best.get('face_visible')),
            'embedding_observed':bool(best.get('face_embedding')),
            'face_quality':','.join((best.get('face_quality') or {}).get('rejection_reasons') or []),
            'annotation_label':'', 'annotation_status':'unreviewed', 'notes':'',
            'embedding_missing_reason':best.get('embedding_missing_reason'),
            'review_target':'face' if best.get('face_bbox') else 'body_without_face_proof',
            'review_bbox':best.get('face_bbox') or best.get('bbox')})
    groups = [sorted(strata[key], key=lambda x: (x['time'] or 0, x['track_id']))
              for key in ('micro_no_embedding','micro_with_embedding','stable_no_embedding','stable_with_embedding')]
    # Allocate quotas fairly across nonempty strata; unused slots return to
    # remaining groups. Within a stratum spread picks over the entire timeline.
    quotas = [0]*len(groups)
    remaining = min(limit, sum(len(group) for group in groups))
    while remaining:
        progress = False
        for i, group in enumerate(groups):
            if quotas[i] < len(group) and remaining:
                quotas[i] += 1
                remaining -= 1
                progress = True
        if not progress:
            break
    chosen = []
    for group, count in zip(groups, quotas):
        if count:
            chosen += [group[min(len(group)-1, int((i+.5)*len(group)/count))]
                       for i in range(count)]
    return sorted(chosen, key=lambda x: (x['time'] or 0, x['track_id']))


def write_annotation_csv(samples, path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=FIELDS, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(samples)
    return path


def read_annotation_csv(path):
    with Path(path).open(encoding='utf-8-sig', newline='') as stream:
        return list(csv.DictReader(stream))


def sample_reid_pairs(reid, *, limit=96):
    """Anonymous, deterministic review of merges, ambiguity and temporal vetoes.

    References point to real tracklets/times, without claiming crops exist.
    This targeted sample cannot estimate population accuracy.
    """
    tracks = {row['track_id']: row for row in reid.get('tracklets', [])}
    identities = {row['person_id']: row for row in reid.get('identities', [])}
    strata = defaultdict(list)
    seen = set()
    for decision in reid.get('merge_decisions', []):
        left = tracks.get(decision['tracklet_id'])
        candidate = identities.get(decision.get('candidate_person_id'), {})
        others = [tracks[tid] for tid in decision.get('candidate_tracklet_ids', candidate.get('track_ids', []))
                  if tid in tracks and tid != decision['tracklet_id']]
        if not left or not others:
            continue
        # Prefer a temporally conflicting witness when the decision is vetoed.
        others.sort(key=lambda row: (
            not (left['first_seen'] <= row['last_seen'] and row['first_seen'] <= left['last_seen'])
            if decision.get('temporal_conflict') else False,
            abs(left['first_seen'] - row['last_seen']), row['track_id']))
        right = others[0]
        key = tuple(sorted((left['track_id'], right['track_id'])))
        if key in seen:
            continue
        seen.add(key)
        kind = ('temporal_veto' if decision.get('temporal_conflict') else
                'merge' if decision.get('accepted') else 'abstention')
        strata[kind].append({'track_id_a': left['track_id'], 'track_id_b': right['track_id'],
            'time_a': left['first_seen'], 'time_b': right['first_seen'],
            'scene_ids_a': left.get('scene_ids', []), 'scene_ids_b': right.get('scene_ids', []),
            'decision_kind': kind, 'embedding_similarity': decision.get('embedding_similarity'),
            'margin': decision.get('margin'), 'reason': decision.get('reason'),
            'annotation_same_person': None, 'annotation_status': 'unreviewed',
            'image_evidence': None})
    selected = []
    groups = [strata[key] for key in ('temporal_veto', 'abstention', 'merge')]
    while len(selected) < max(0, limit) and any(groups):
        for group in groups:
            if group and len(selected) < limit:
                selected.append({'pair_id': f'PAIR_{len(selected)+1:05}', **group.pop(0)})
    return selected


def compare_identity_annotations(before, after, *, max_false_merge_rate=0.0):
    """Compare the exact same human-verified track labels; predictions may differ.

    Records require matching source/protocol SHA256 and annotations. Never interprets
    smaller identity counts or heuristic fragmentation as measured improvement.
    """
    import math
    if not math.isfinite(max_false_merge_rate) or not 0 <= max_false_merge_rate <= 1:
        raise ValueError('max_false_merge_rate deve estar entre 0 e 1')
    for field in ('source_sha256', 'protocol_sha256'):
        value = before.get(field)
        if (not isinstance(value, str) or len(value) != 64
                or any(char not in '0123456789abcdef' for char in value.lower())
                or value.lower() != str(after.get(field) or '').lower()):
            return {'improvement_accepted': None, 'reason': 'same_source_and_protocol_sha256_required'}
    before, after = before.get('annotations', []), after.get('annotations', [])
    def reviewed(rows):
        labels = {}
        for row in rows:
            label = str(row.get('annotation_label') or '').strip()
            if row.get('annotation_status') != 'verified' or label.lower() in ('', '?', 'unknown', 'unresolved', 'uncertain'):
                continue
            tid = str(row['track_id'])
            if tid in labels and labels[tid] != label:
                raise ValueError('Anotacoes conflitantes')
            labels[tid] = label
        return labels
    old_labels, new_labels = reviewed(before), reviewed(after)
    if len(old_labels) < 2 or old_labels != new_labels:
        return {'improvement_accepted': None, 'reason': 'same_verified_track_labels_required'}
    old, new = evaluate_annotations(before), evaluate_annotations(after)
    old_rate = old['false_merge_pairs'] / old['predicted_same_pairs'] if old['predicted_same_pairs'] else 0.0
    new_rate = new['false_merge_pairs'] / new['predicted_same_pairs'] if new['predicted_same_pairs'] else 0.0
    acceptable = (new_rate <= max_false_merge_rate and new_rate <= old_rate
                  and new['false_merge_pairs'] <= old['false_merge_pairs'])
    improved = new['false_split_pairs'] < old['false_split_pairs']
    return {'improvement_accepted': acceptable and improved,
            'reason': 'fragmentation_reduced_with_acceptable_false_merges' if acceptable and improved else 'no_safe_measured_improvement',
            'before': old, 'after': new, 'before_false_merge_rate': old_rate,
            'after_false_merge_rate': new_rate, 'max_false_merge_rate': max_false_merge_rate,
            'scope': 'same_supplied_human_verified_track_labels_only'}


def evaluate_annotations(samples, *, minimum_labeled=2):
    labels = []
    for row in samples:
        label = str(row.get('annotation_label') or '').strip()
        status = str(row.get('annotation_status') or '').strip().lower()
        if label.lower() in ('', '?', 'unknown', 'unresolved', 'uncertain') or status != 'verified':
            continue
        labels.append((str(row['track_id']), label, str(row.get('predicted_person_id') or 'unresolved')))
    if len(labels) < minimum_labeled:
        return {'status':'insufficient_human_annotations', 'total_samples':len(samples),
                'verified_samples':len(labels), 'false_merge_pairs':None,
                'false_split_pairs':None, 'pairwise_precision':None,
                'pairwise_recall':None, 'fragmented_identity_count':None,
                'identity_accuracy_verified':False}
    unique = {}
    for tid, label, predicted in labels:
        if tid in unique and unique[tid] != (label, predicted):
            raise ValueError(f'Anotacoes conflitantes para track_id {tid}')
        unique[tid] = (label, predicted)
    rows = list(unique.values())
    true_same = predicted_same = correct_same = false_merge = false_split = 0
    for i, (truth_a, pred_a) in enumerate(rows):
        for truth_b, pred_b in rows[i+1:]:
            ground = truth_a == truth_b
            proposed = pred_a != 'unresolved' and pred_a == pred_b
            true_same += ground
            predicted_same += proposed
            correct_same += ground and proposed
            false_merge += proposed and not ground
            false_split += ground and not proposed
    by_label = defaultdict(set)
    for tid, (label, predicted) in unique.items():
        by_label[label].add(predicted if predicted != 'unresolved' else 'unresolved_'+tid)
    return {'status':'evaluated_human_verified', 'total_samples':len(samples),
            'verified_samples':len(unique), 'verified_true_identities':len(by_label),
            'false_merge_pairs':false_merge, 'false_split_pairs':false_split,
            'true_same_pairs':true_same, 'predicted_same_pairs':predicted_same,
            'pairwise_precision':correct_same/predicted_same if predicted_same else None,
            'pairwise_recall':correct_same/true_same if true_same else None,
            'fragmented_identity_count':sum(len(ids)>1 for ids in by_label.values()),
            'fragmentation_fraction':sum(len(ids)>1 for ids in by_label.values())/len(by_label),
            'identity_accuracy_verified':True,
            'limitations':['Amostra manual, nao estima acuracia populacional sem desenho amostral e cobertura.',
                           'ID switches internos a um tracklet exigem anotacoes frame a frame.']}


def write_contact_sheet(samples, video_path, output_path, *, columns=5):
    """Optional local-only visual aid to label anonymous faces (no cloud calls)."""
    import cv2
    import numpy as np
    capture = cv2.VideoCapture(str(video_path))
    if not capture.isOpened():
        raise ValueError('Video nao foi aberto; arquivo CSV continua utilizavel sem imagens.')
    width, height = 240, 190
    rows = (len(samples)+columns-1)//columns
    sheet = np.full((max(1, rows)*height, columns*width, 3), 45, dtype=np.uint8)
    try:
        for i, sample in enumerate(samples):
            if sample.get('time') is None:
                continue
            capture.set(cv2.CAP_PROP_POS_MSEC, float(sample['time'])*1000)
            ok, frame = capture.read()
            if not ok:
                continue
            h, w = frame.shape[:2]
            box = sample.get('review_bbox')
            if box:
                x1 = round(box['x']*w); y1 = round(box['y']*h)
                x2 = round((box['x']+box['width'])*w)
                y2 = round((box['y']+box['height'])*h)
                cv2.rectangle(frame, (x1,y1), (x2,y2), (0,255,255), 3)
            scale = min((width-8)/w, (height-62)/h)
            resized = cv2.resize(frame, (max(1,int(w*scale)), max(1,int(h*scale))))
            y, x = divmod(i, columns)
            x *= width; y *= height
            sheet[y:y+resized.shape[0], x:x+resized.shape[1]] = resized
            cv2.putText(sheet, str(sample['track_id'])[:25], (x+3,y+height-23),
                        cv2.FONT_HERSHEY_SIMPLEX, .38, (245,245,245), 1, cv2.LINE_AA)
            cv2.putText(sheet, f"t={float(sample['time']):.2f}", (x+3,y+height-7),
                        cv2.FONT_HERSHEY_SIMPLEX, .38, (245,245,245), 1, cv2.LINE_AA)
            caption = sample.get('embedding_missing_reason') or ('fresh_embedding' if sample.get('embedding_observed') else 'unknown')
            cv2.putText(sheet, caption[:36], (x+3,y+height-39),
                        cv2.FONT_HERSHEY_SIMPLEX, .32, (245,245,245), 1, cv2.LINE_AA)
    finally:
        capture.release()
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if not cv2.imwrite(str(output_path), sheet):
        raise OSError('Nao foi possivel gravar contact sheet.')
    return output_path
