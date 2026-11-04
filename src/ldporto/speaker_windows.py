"""Pure evidence-window geometry and observed mouth-sample diagnostics.

Balanced tails change only an opt-in measurement plan. They do not create
mouth/audio evidence, independent votes, identities or calibrated confidence.
"""
import math


def partition_evidence_slice(start, end, *, max_seconds=3., min_audio_seconds=1.5,
                             policy='legacy'):
    """Partition one already bounded speaker/shot/overlap slice.

The legacy branch preserves the original repeated-addition arithmetic exactly.
Only a legacy tail below the configured audio minimum may be balanced.
"""
    if policy not in ('legacy', 'balanced_tail', 'tail_anchor'):
        raise ValueError('Unknown evidence_window_policy')
    for value in (start, end, max_seconds, min_audio_seconds):
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError('Window bounds and durations must be finite numbers')
    if end < start or max_seconds <= 0 or not 0 < min_audio_seconds <= max_seconds:
        raise ValueError('Invalid evidence-window bounds or duration limits')
    legacy, cursor = [], start
    while cursor < end:
        stop = min(end, cursor + max_seconds)
        if stop <= cursor:
            raise ValueError('Evidence window cannot advance at this timestamp')
        legacy.append((cursor, stop))
        cursor = stop
    if (policy == 'legacy' or len(legacy) < 2 or
            legacy[-1][1] - legacy[-1][0] >= min_audio_seconds):
        return legacy
    if policy == 'tail_anchor':
        left = max(start, end - max_seconds)
        if min_audio_seconds <= end - left <= max_seconds:
            return [*legacy, (left, end)]
        return legacy
    count = math.ceil((end - start) / max_seconds)
    if (end - start) / count < min_audio_seconds:
        return legacy
    balanced = [(start + (end - start) * i / count,
                 end if i + 1 == count else start + (end - start) * (i + 1) / count)
                for i in range(count)]
    # Rounded boundaries must still satisfy both gates; retain legacy otherwise.
    if any(not min_audio_seconds <= b - a <= max_seconds for a, b in balanced):
        return legacy
    return balanced


def mouth_sample_diagnostics(rows):
    """Describe observed samples, without inferring a landmark failure from null.

Missing lip opening can have several causes. Only an explicitly present invalid
numeric value is classified as invalid; no face or landmark detection is run.
"""
    times, missing, invalid = [], 0, 0
    for row in rows:
        lip = row.get('lip_opening')
        if lip is None:
            missing += 1
        elif (isinstance(lip, bool) or not isinstance(lip, (int, float)) or
              not math.isfinite(lip)):
            invalid += 1
        stamp = row.get('time')
        if isinstance(stamp, (int, float)) and not isinstance(stamp, bool) and math.isfinite(stamp):
            times.append(stamp)
    times = sorted(set(times))
    gaps = [b - a for a, b in zip(times, times[1:])]
    return {'observation_count': len(rows), 'unique_timestamp_count': len(times),
            'missing_mouth_observation_count': missing, 'invalid_mouth_value_count': invalid,
            'first_observed_at': times[0] if times else None,
            'last_observed_at': times[-1] if times else None,
            'maximum_observed_gap_seconds': max(gaps) if gaps else None,
            'tracklet_count': len({r.get('track_id') for r in rows}),
            'scope': 'observed_samples; null_does_not_prove_invalid_landmarks'}
