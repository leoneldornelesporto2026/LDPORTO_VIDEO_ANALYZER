"""Bounded lag search with audio activity and a conservative confidence proxy."""
import math
import numpy as np


def mouth_audio_evidence(rows, audio, rate, audio_start, lags=(-.08, 0., .08)):
    if len(rows) < 8 or np.std([row['lip_opening'] for row in rows]) < .008:
        return None
    if len({row.get('scene_id') for row in rows}) > 1:
        return None
    scores = []
    for lag in lags:
        mouth, envelope = [], []
        for row in rows:
            left = round((row['time'] + lag - .08 - audio_start) * rate)
            right = left + round(.16 * rate)
            if left < 0 or right > len(audio):
                continue
            samples = audio[left:right]
            mouth.append(row['lip_opening'])
            envelope.append(float(np.sqrt(np.mean(samples ** 2))))
        if len(mouth) < 8 or np.std(envelope) < 1e-5 or np.mean(envelope) < 1e-4:
            continue
        correlation = float(np.corrcoef(mouth, envelope)[0, 1])
        if math.isfinite(correlation):
            scores.append((correlation, lag, len(mouth), float(np.mean(envelope))))
    if not scores:
        return None
    correlation, lag, samples, activity = max(scores, key=lambda item: item[0])
    # 2.4 instead of 1.96 penalizes selecting the best of three lag trials.
    lower = math.tanh(math.atanh(max(-.999999, min(.999999, correlation))) - 2.4 / math.sqrt(max(1, samples - 3)))
    upper = math.tanh(math.atanh(max(-.999999, min(.999999, correlation))) + 2.4 / math.sqrt(max(1, samples - 3)))
    return {'correlation': correlation, 'correlation_lower_bound_proxy': lower, 'correlation_upper_bound_proxy': upper,
            'audio_lag_seconds': lag, 'lag_trial_count': len(lags), 'sample_count': samples,
            'audio_activity_rms': activity, 'signal_method': 'mouth_opening_audio_envelope_bounded_lag',
            'confidence_is_calibrated': False}
