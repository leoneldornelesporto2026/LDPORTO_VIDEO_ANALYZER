"""Human-in-the-loop identity evaluation. No automated labels are ground truth.

Track IDs and anonymous human-assigned labels are deliberately separated.
Only compare different tracklets with human labels. Exclude 'unknown'.
"""
import csv
from collections import Counter, defaultdict
from pathlib import Path


FIELDS = ('track_id', 'time', 'scene_id', 'predicted_person_id', 'face_visible',
          'embedding_observed', 'face_quality', 'annotation_label', 'annotation_status', 'notes')


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
    width, height = 240, 165
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
            scale = min((width-8)/w, (height-36)/h)
            resized = cv2.resize(frame, (max(1,int(w*scale)), max(1,int(h*scale))))
            y, x = divmod(i, columns)
            x *= width; y *= height
            sheet[y:y+resized.shape[0], x:x+resized.shape[1]] = resized
            cv2.putText(sheet, str(sample['track_id'])[:25], (x+3,y+height-23),
                        cv2.FONT_HERSHEY_SIMPLEX, .38, (245,245,245), 1, cv2.LINE_AA)
            cv2.putText(sheet, f"t={float(sample['time']):.2f}", (x+3,y+height-7),
                        cv2.FONT_HERSHEY_SIMPLEX, .38, (245,245,245), 1, cv2.LINE_AA)
    finally:
        capture.release()
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if not cv2.imwrite(str(output_path), sheet):
        raise OSError('Nao foi possivel gravar contact sheet.')
    return output_path
