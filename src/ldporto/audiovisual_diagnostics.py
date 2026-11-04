"""Explain measured mouth/audio windows without accepting identities or changing gates."""
from bisect import bisect_left
from collections import Counter

from .speaker_roles import contemporary_sync, evidence_spans
from .temporal import number


def window_signal_diagnostics(row, cfg):
    candidates = []
    speaker = row.get('speaker_id') or row.get('speaker')
    for candidate in row.get('candidates') or []:
        reasons = []
        checks = [('correlation', 'min_confidence', .55, 'CORRELATION_BELOW_MINIMUM'),
                  ('sample_count', 'min_evidence_samples', 8, 'INSUFFICIENT_MOUTH_SAMPLES'),
                  ('track_stability', 'min_local_track_stability', .5, 'UNSTABLE_TRACK'),
                  ('visibility_coverage', 'min_local_visibility', .6, 'INSUFFICIENT_VISUAL_COVERAGE'),
                  ('face_visibility', 'min_local_face_fraction', .6, 'INSUFFICIENT_FACE_OBSERVATION')]
        for key, setting, default, reason in checks:
            fallback = 1. if key in ('track_stability', 'visibility_coverage', 'face_visibility') else None
            value = number(candidate.get(key), fallback)
            if value is None or value < cfg.get(setting, default):
                reasons.append(reason)
        if number(candidate.get('correlation_lower_bound_proxy'), 0) <= 0:
            reasons.append('NO_BOUNDED_POSITIVE_SYNC')
        lag = number(candidate.get('audio_lag_seconds'), None)
        if lag is None:
            reasons.append('LAG_NOT_MEASURED')
        elif abs(lag) > cfg.get('max_sync_offset_seconds', .12):
            reasons.append('SYNC_OFFSET_OUTSIDE_BOUND')
        spans = evidence_spans(row, candidate)
        center = (spans[0]['start'] + spans[0]['end']) / 2 if spans else (row['start'] + row['end']) / 2
        qualified = contemporary_sync([row], speaker, candidate.get('person_id'), center, cfg,
                                      overlap=bool(row.get('overlap')))
        if not qualified['verified'] and not reasons:
            reasons.append(qualified['reason'])
        candidates.append({key: candidate.get(key) for key in
            ('person_id', 'correlation', 'correlation_lower_bound_proxy', 'correlation_upper_bound_proxy',
             'audio_lag_seconds', 'sample_count', 'mouth_start', 'mouth_end', 'audio_activity_rms',
             'visibility_coverage', 'face_visibility', 'track_stability', 'source_shot_id')})
        candidates[-1].update(local_sync_qualified=qualified['verified'], rejection_reasons=reasons,
                               required_correlation=cfg.get('min_confidence', .55), support_spans=spans)
    screening = row.get('candidate_screening') or {}
    if row.get('method') == 'user_verified':
        status = 'user_verified'
    elif row.get('overlap'):
        status = 'audio_overlap'
    elif any(c['local_sync_qualified'] for c in candidates):
        status = 'qualified_local_signal_pending_independent_consensus'
    elif candidates:
        status = 'measured_signal_below_acceptance_gates'
    elif screening.get('audio_window_below_minimum'):
        status = 'audio_window_too_short'
    elif screening.get('insufficient_mouth_samples'):
        status = 'insufficient_mouth_samples'
    elif screening.get('no_reliable_mouth_audio_signal'):
        status = 'measured_without_reliable_sync'
    else:
        status = 'mouth_signal_unavailable'
    return {'schema_version': '1.0', 'status': status, 'candidates': candidates,
            'candidate_count': len(candidates),
            'qualified_local_candidate_count': sum(c['local_sync_qualified'] for c in candidates),
            'measurement_scope': 'candidate_signal_not_accepted_identity', 'confidence_is_calibrated': False}


def annotate_window_observations(rows, vision, metadata, face_min_pixels):
    """Persist timestamps/quality counters already observed by the perception stage."""
    observations = sorted(vision.get('observations') or [], key=lambda row: row['time'])
    times = [row['time'] for row in observations]
    frame_times = sorted({row['time'] for row in vision.get('frames') or []})
    for row in rows:
        selected = observations[bisect_left(times, row['start']):bisect_left(times, row['end'])]
        faces = [obs for obs in selected if obs.get('face_visible')]
        mouth_times = sorted({obs['time'] for obs in faces if obs.get('lip_opening') is not None})
        widths, heights = [], []
        for obs in faces:
            quality = obs.get('face_quality') or {}
            if isinstance(quality, dict):
                width = number(quality.get('face_width_px'), None)
                height = number(quality.get('face_height_px'), None)
                if width is not None and height is not None:
                    widths.append(width)
                    heights.append(height)
        statuses = Counter('insufficient_face_pixels' if min(width, height) < face_min_pixels else 'observed'
                           for width, height in zip(widths, heights))
        observation = {'schema_version': '1.0', 'source_width': metadata.get('width'),
            'source_height': metadata.get('height'), 'source_fps': metadata.get('fps'),
            'sampled_frame_times': frame_times[bisect_left(frame_times, row['start']):bisect_left(frame_times, row['end'])],
            'face_observation_count': len(faces), 'mouth_observation_count': sum(obs.get('lip_opening') is not None for obs in faces),
            'mouth_frame_times': mouth_times, 'face_pixel_status_counts': dict(statuses),
            'face_pixel_quality_sample_count': len(widths),
            'minimum_observed_face_width_px': min(widths) if widths else None,
            'minimum_observed_face_height_px': min(heights) if heights else None,
            'face_pixel_reference': 'existing_face_embedding_quality_threshold_diagnostic_only',
            'face_pixel_reference_minimum': face_min_pixels,
            'continuous_visibility_verified': False, 'physical_occlusion_verified': None}
        row['visual_measurement'] = observation
