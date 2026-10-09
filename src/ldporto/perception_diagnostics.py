"""Observed diagnostic evidence. Visibility alone never identifies a speaker."""
from bisect import bisect_left
from collections import defaultdict, Counter
from .temporal import union_duration


def speaker_diagnostics(diarization, vision, raw, summaries, affinity, intervals=None):
    observations = sorted(vision.get('observations', []), key=lambda row: row['time'])
    times = [row['time'] for row in observations]
    turns = defaultdict(list)
    windows = defaultdict(list)
    for row in diarization.get('turns', []):
        turns[row.get('speaker') or row.get('speaker_id')].append(row)
    for row in raw:
        windows[row.get('speaker_id') or row.get('speaker')].append(row)
    result = []
    for summary in summaries:
        speaker = summary['speaker_id']
        selected = []
        for turn in turns[speaker]:
            selected.extend(observations[bisect_left(times, turn['start']):bisect_left(times, turn['end'])])
        # Overlapping turns from one speaker must not double-count observations.
        seen = set()
        selected = [row for row in selected if not ((row['time'], row.get('track_id'), row.get('person_id')) in seen
                    or seen.add((row['time'], row.get('track_id'), row.get('person_id'))))]
        faces = [row for row in selected if row.get('face_visible')]
        mouths = [row for row in faces if row.get('lip_opening') is not None or row.get('mouth_activity') is not None]
        candidates = [row for row in affinity if row['speaker_id'] == speaker]
        delivered = [row for row in intervals or [] if row.get('speaker_id') == speaker]
        tracks = {row.get('track_id') for row in selected if row.get('track_id')}
        people = {row.get('person_id') for row in selected if row.get('person_id')}
        reasons = []
        if not selected:
            reasons.append('NO_VISUAL_OVERLAP')
        if not faces:
            reasons.append('INSUFFICIENT_FACE_OBSERVATION')
        if not mouths:
            reasons.append('MOUTH_SIGNAL_UNAVAILABLE')
        embeddings = sum(row.get('face_embedding') is not None or row.get('face_embedding_available', False) for row in faces)
        if not embeddings:
            reasons.append('EMBEDDING_UNAVAILABLE')
        if len(tracks) > len(people) * 2:
            reasons.append('TRACK_FRAGMENTATION')
        if summary.get('unresolved_reason') == 'ambiguous_global_affinity':
            reasons.append('MULTIPLE_CANDIDATES')
        if summary.get('unresolved_reason') == 'simultaneous_speaker_person_conflict':
            reasons.append('SIMULTANEOUS_CONFLICT')
        if any(row.get('overlap') for row in windows[speaker]):
            reasons.append('OVERLAPPING_AUDIO_UNATTRIBUTABLE')
        if any(row.get('offscreen_state') for row in windows[speaker]) or any(row.get('active_speaker_state') == 'OFFSCREEN' for row in delivered):
            reasons.append('OFFSCREEN_SPEAKER')
        if any((item.get('track_stability') or 1) < .5 for row in windows[speaker] for item in row.get('candidates', [])):
            reasons.append('SHOT_INSTABILITY')
        if not summary.get('person_id') and not any(code in reasons for code in ('MULTIPLE_CANDIDATES', 'SIMULTANEOUS_CONFLICT')):
            reasons.append('LOW_AFFINITY')
        # Causal window failures stay separate: missing face, missing mouth,
        # insufficient statistical bound, simultaneous speech and lag drift.
        window_counts = Counter()
        review_windows = []
        for raw_window in sorted(windows[speaker], key=lambda row: row.get('start', 0)):
            window_counts.update(raw_window.get('candidate_screening') or {})
            candidates_in_window = raw_window.get('candidates') or []
            if raw_window.get('method') == 'user_verified':
                code = 'USER_VERIFIED'
            elif raw_window.get('overlap'):
                code = 'OVERLAPPING_AUDIO'
            elif not candidates_in_window:
                code = 'NO_MOUTH_AUDIO_CANDIDATE'
            elif not any((item.get('correlation_lower_bound_proxy') or 0) > 0 for item in candidates_in_window):
                code = 'NO_BOUNDED_POSITIVE_SYNC'
            elif not any(item.get('person_id') == summary.get('person_id') for item in candidates_in_window):
                code = 'MAPPED_PERSON_NOT_IN_LOCAL_CANDIDATES'
            else:
                code = 'BOUNDED_SYNC_CANDIDATE'
            window_counts[code] += 1
            if code != 'BOUNDED_SYNC_CANDIDATE' and len(review_windows) < 16:
                review_windows.append({'start': raw_window.get('start'), 'end': raw_window.get('end'),
                                       'window_id': raw_window.get('evidence_window_id'), 'reason': code})
        lag_report = summary.get('audio_video_sync') or {}
        if lag_report.get('status') == 'measured' and not lag_report.get('consistent'):
            reasons.append('AUDIO_VIDEO_LAG_INCONSISTENT')
        if not lag_report.get('consistent') and summary.get('person_id'):
            reasons.append('CONTEMPORARY_SYNC_NOT_VERIFIED')
        if any(row.get('active_speaker_state') == 'PROBABLE' for row in delivered):
            reasons.append('GLOBAL_IDENTITY_NOT_CURRENT_SPEECH')
        speech = union_duration(turns[speaker])
        visible_times = sorted({row['time'] for row in faces})
        spans = [{'start': a, 'end': b} for a, b in zip(visible_times, visible_times[1:]) if 0 < b - a <= .6]
        visible_seconds = union_duration([r for r in delivered if r.get('contemporary_face_observed')]) if delivered else union_duration(spans)
        result.append({'speaker_id': speaker, 'person_id': summary.get('person_id'),
                       'speech_duration': speech, 'visible_overlap': visible_seconds,
                       'visible_overlap_basis': 'bounded_sample_intervals' if delivered else 'sample_span_proxy',
                       'association_status': summary.get('association_status', 'UNRESOLVED'),
                       'speech_without_resolved_face_seconds': union_duration([r for r in delivered if r.get('speech_without_resolved_face')]),
                       'observed_wide_shot_seconds': union_duration([r for r in delivered if r.get('wide_shot_observed')]),
                       'no_contemporary_frame_seconds': union_duration([r for r in delivered if r.get('visual_state') == 'NO_CONTEMPORARY_FRAME']),
                       'candidate_people': sorted(people), 'positive_windows': summary.get('positive_windows', 0),
                       'negative_windows': sum(row.get('negative_windows', 0) for row in candidates),
                       'offscreen_windows': sum(row.get('active_speaker_state') == 'OFFSCREEN' for row in delivered),
                       'offscreen_window_basis': 'delivered_active_speaker_windows',
                       'candidate_affinity_evidence': candidates,
                       'simultaneous_conflicts': int('SIMULTANEOUS_CONFLICT' in reasons),
                       'face_visibility': len(faces) / len(selected) if selected else None,
                       'mouth_observations': len(mouths), 'embedding_continuity': embeddings / len(faces) if faces else None,
                       'shot_consistency': {'shot_count': len({row.get('scene_id') for row in selected}),
                                            'track_count': len(tracks)},
                       'affinity_score': summary.get('mouth_audio_score'),
                       'mapping_confidence': summary.get('confidence'), 'mapping_reason': summary.get('method'),
                       'unresolved_reason': summary.get('unresolved_reason'), 'reason_codes': reasons,
                       'window_diagnostics': dict(window_counts), 'review_windows': review_windows,
                       'audio_video_sync': lag_report,
                       'confirmed_intervals': sum(row.get('active_speaker_state') == 'CONFIRMED' for row in delivered),
                       'probable_intervals': sum(row.get('active_speaker_state') == 'PROBABLE' for row in delivered),
                       'overlap_intervals': sum(bool(row.get('overlap')) for row in delivered),
                       'confidence_is_calibrated': False})
    return result


def tracking_profile(observations, shots, duration, bin_seconds=60):
    tracks = defaultdict(list)
    for row in observations:
        if row.get('track_id'):
            tracks[row['track_id']].append(row)
    bins = [{'start': start, 'end': min(duration, start + bin_seconds),
             'tracks_created_per_minute': 0, 'micro_tracks_per_minute': 0, 'face_only_tracks': 0,
             'body_only_tracks': 0, 'face_body_tracks': 0, 'embedding_missing_rate': None,
             'shot_transition_density': 0} for start in range(0, max(1, int(duration + .999)), bin_seconds)]
    missing = defaultdict(int)
    counts = defaultdict(int)
    for rows in tracks.values():
        times = sorted({row['time'] for row in rows})
        index = min(len(bins) - 1, int(times[0] // bin_seconds))
        row = bins[index]
        counts[index] += 1
        row['tracks_created_per_minute'] += 60 / max(1, row['end'] - row['start'])
        visual = sum(b - a for a, b in zip(times, times[1:]) if b - a <= 1.2)
        row['micro_tracks_per_minute'] += (60 / max(1, row['end'] - row['start'])) if len(times) < 3 or visual < 1 else 0
        face, body = any(item.get('face_visible') for item in rows), any(item.get('body_visible') for item in rows)
        row['face_body_tracks' if face and body else 'face_only_tracks' if face else 'body_only_tracks'] += 1
        missing[index] += not any(item.get('face_embedding') is not None for item in rows)
    for shot in shots:
        if shot.get('start', 0) > 0:
            bins[min(len(bins) - 1, int(shot['start'] // bin_seconds))]['shot_transition_density'] += 1
    for index, row in enumerate(bins):
        row['embedding_missing_rate'] = missing[index] / counts[index] if counts[index] else None
    return {'schema_version': '1.0', 'bin_seconds': bin_seconds, 'raw_tracklets': len(tracks), 'bins': bins,
            'measurement_basis': 'observed track_id; creation is first observed sample; micro threshold 3 samples/1s'}
