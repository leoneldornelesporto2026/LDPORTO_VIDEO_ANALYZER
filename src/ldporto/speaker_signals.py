"""Bounded lag search with audio activity and a conservative confidence proxy."""
import math
import numpy as np


def mouth_audio_evidence(rows, audio, rate, audio_start, lags=(-.08, 0., .08)):
    # Repeated observations of the same frame are not independent samples.
    unique = {}
    for row in rows:
        stamp = row['time']
        if not math.isfinite(stamp) or not math.isfinite(row['lip_opening']):
            return None
        if stamp in unique and (unique[stamp]['lip_opening'] != row['lip_opening'] or
                                unique[stamp].get('scene_id') != row.get('scene_id')):
            return None
        unique[stamp] = row
    rows = [unique[stamp] for stamp in sorted(unique)]
    if len(rows) < 8 or np.std([row['lip_opening'] for row in rows]) < .008:
        return None
    if len({row.get('scene_id') for row in rows}) > 1:
        return None
    scores = []
    for lag in lags:
        mouth, envelope, stamps = [], [], []
        for row in rows:
            left = round((row['time'] + lag - .08 - audio_start) * rate)
            right = left + round(.16 * rate)
            if left < 0 or right > len(audio):
                continue
            samples = audio[left:right]
            mouth.append(row['lip_opening'])
            stamps.append(row['time'])
            envelope.append(float(np.sqrt(np.mean(samples ** 2))))
        if len(mouth) < 8 or np.std(envelope) < 1e-5 or np.mean(envelope) < 1e-4:
            continue
        correlation = float(np.corrcoef(mouth, envelope)[0, 1])
        if math.isfinite(correlation):
            scores.append((correlation, lag, len(mouth), float(np.mean(envelope)), min(stamps), max(stamps)))
    if not scores:
        return None
    correlation, lag, samples, activity, mouth_start, mouth_end = max(scores, key=lambda item: item[0])
    # 2.4 instead of 1.96 penalizes selecting the best of three lag trials.
    lower = math.tanh(math.atanh(max(-.999999, min(.999999, correlation))) - 2.4 / math.sqrt(max(1, samples - 3)))
    upper = math.tanh(math.atanh(max(-.999999, min(.999999, correlation))) + 2.4 / math.sqrt(max(1, samples - 3)))
    return {'correlation': correlation, 'correlation_lower_bound_proxy': lower, 'correlation_upper_bound_proxy': upper,
            'audio_lag_seconds': lag, 'lag_trial_count': len(lags), 'sample_count': samples,
            'mouth_start': mouth_start, 'mouth_end': mouth_end,
            'temporal_support_basis': 'matched_mouth_sample_span',
            'audio_activity_rms': activity, 'signal_method': 'mouth_opening_audio_envelope_bounded_lag',
            'confidence_is_calibrated': False}
