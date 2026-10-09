"""S5: conservative audiovisual state, with explicit uncertainty.

An identity is not proof of who currently speaks. Human-labelled reactions are
separated from inferred silent listeners and from confirmed mouth/audio sync.
"""
from collections import defaultdict
from statistics import median
from .temporal import number, union_duration


REACTIONS = {'laugh', 'laughing', 'smile', 'smiling', 'surprise', 'surprised',
             'applause', 'clapping', 'nod', 'nodding'}


def _candidate_for(link, person):
    return next((candidate for candidate in link.get('candidates', [])
                 if candidate.get('person_id') == person), None)


def mixed_audio_window(row, turns):
    """A whole-window mixdown score cannot be reused after an interruption."""
    speaker = row.get('speaker_id') or row.get('speaker')
    start, end = number(row.get('start')), number(row.get('end'))
    return bool(row.get('overlap') or any(
        (turn.get('speaker') or turn.get('speaker_id')) != speaker and
        min(end, turn['end']) > max(start, turn['start']) for turn in turns))


def evidence_spans(row, candidate, turns=None):
    """Audio-time intersection of a window, measured mouth span and speaker turns.

    Signal lag follows audio_time = mouth_time + lag. Legacy evidence without
    measured bounds retains its window, explicitly as a window-based proxy.
    """
    start, end = number(row.get('start'), None), number(row.get('end'), None)
    if start is None or end is None or end <= start:
        return []
    if 'mouth_start' in candidate or 'mouth_end' in candidate:
        left = number(candidate.get('mouth_start'), None)
        right = number(candidate.get('mouth_end'), None)
        lag = number(candidate.get('audio_lag_seconds'), None)
        if left is None or right is None or lag is None or right <= left:
            return []
        start, end = max(start, left + lag), min(end, right + lag)
    if end <= start:
        return []
    if turns is None:
        return [{'start': start, 'end': end}]
    speaker = row.get('speaker_id') or row.get('speaker')
    spans = []
    for turn in turns:
        if (turn.get('speaker') or turn.get('speaker_id')) != speaker:
            continue
        a, b = max(start, turn['start']), min(end, turn['end'])
        if b > a:
            spans.append({'start': a, 'end': b})
    return spans


def contemporary_sync(links, speaker, person, center, cfg, *, overlap=False):
    """Evaluate positive *local* sync in the current evidence window.

    No interpolation through a scene cut; no mixdown attribution for overlap.
    A confidence interval proxy is not a calibrated probability.
    """
    if not person or overlap:
        return {'verified': False, 'reason': 'simultaneous_audio_ambiguous' if overlap else 'no_identity',
                'lag_seconds': None, 'window_refs': []}
    best = []
    for row in links:
        if row.get('overlap') or (row.get('speaker_id') or row.get('speaker')) != speaker:
            continue
        if not (number(row.get('start'), -1) <= center < number(row.get('end'), -1)):
            continue
        candidate = _candidate_for(row, person)
        if not candidate:
            continue
        lower = number(candidate.get('correlation_lower_bound_proxy'), None)
        upper = number(candidate.get('correlation_upper_bound_proxy'), None)
        score = number(candidate.get('correlation'), None)
        lag = number(candidate.get('audio_lag_seconds'), None)
        stability = number(candidate.get('track_stability'), 1.)
        coverage = number(candidate.get('visibility_coverage'), 1.)
        faces = number(candidate.get('face_visibility'), 1.)
        samples = number(candidate.get('sample_count'), 0)
        activity = number(candidate.get('audio_activity_rms'), None)
        measured = evidence_spans(row, candidate)
        if not any(span['start'] <= center < span['end'] for span in measured):
            continue
        # Legacy rows without lower bound/lag may contribute to global
        # identity but are *never* sufficient to confirm current speech.
        if (score is not None and score >= cfg.get('min_confidence', .55) and
                lower is not None and lower > 0 and
                (upper is None or upper > 0) and lag is not None and
                abs(lag) <= cfg.get('max_sync_offset_seconds', .12) and
                stability >= cfg.get('min_local_track_stability', .5) and
                coverage >= cfg.get('min_local_visibility', .6) and
                faces >= cfg.get('min_local_face_fraction', .6) and
                ('audio_activity_rms' not in candidate or
                 (activity is not None and activity >= 1e-4)) and
                samples >= cfg.get('min_evidence_samples', 8)):
            best.append((score, row, candidate))
    if not best:
        return {'verified': False, 'reason': 'no_contemporary_bounded_mouth_audio_evidence',
                'lag_seconds': None, 'window_refs': []}
    best.sort(key=lambda x: -x[0])
    score, row, candidate = best[0]
    rivals = [number(other.get('correlation'), None)
              for other in row.get('candidates', []) if other.get('person_id') != person]
    rivals = [value for value in rivals if value is not None]
    if rivals and score - max(rivals) < cfg.get('min_local_margin', .1):
        return {'verified': False, 'reason': 'local_candidate_margin_insufficient',
                'lag_seconds': candidate.get('audio_lag_seconds'), 'window_refs': []}
    return {'verified': True, 'reason': 'bounded_audio_mouth_synchrony',
            'lag_seconds': candidate.get('audio_lag_seconds'), 'correlation': score,
            'source_shot_id': candidate.get('source_shot_id'),
            'lower_bound_proxy': candidate.get('correlation_lower_bound_proxy'),
            'window_refs': [row.get('evidence_window_id')] if row.get('evidence_window_id') else []}


def lag_consistency(raw, speaker, person, cfg, turns=None):
    """Check drift across independent evidence windows (does not create identity)."""
    rows = []
    for row in raw:
        if mixed_audio_window(row, turns or []) or (row.get('speaker_id') or row.get('speaker')) != speaker:
            continue
        candidate = _candidate_for(row, person)
        if candidate and number(candidate.get('correlation_lower_bound_proxy'), 0) > 0:
            lag = number(candidate.get('audio_lag_seconds'), None)
            spans = evidence_spans(row, candidate, turns)
            # A lag vote must itself pass the local audio/visual quality and
            # rival-margin gates. Weak windows cannot corroborate one good vote.
            qualified = bool(spans and contemporary_sync(
                [row], speaker, person, (spans[0]['start'] + spans[0]['end']) / 2, cfg)['verified'])
            if qualified and lag is not None and union_duration(spans) >= cfg.get('min_evidence_window_seconds', .5):
                rows.append((number(row.get('start')), number(row.get('end')), lag,
                             row.get('evidence_window_id') or f"WINDOW_{speaker}_{row['start']:.6f}_{row['end']:.6f}"))
    independent, end, seen = [], -1., set()
    for start, stop, lag, reference in sorted(rows):
        if reference not in seen and start >= end and stop-start >= cfg.get('min_evidence_window_seconds', .5):
            independent.append(lag)
            end = stop
            seen.add(reference)
    if not independent:
        return {'status': 'not_measured', 'independent_windows': 0,
                'median_lag_seconds': None, 'spread_seconds': None, 'consistent': False}
    center = median(independent)
    spread = max(abs(lag-center) for lag in independent)
    enough = len(independent) >= cfg.get('min_consensus_windows', 2)
    return {'status': 'measured' if enough else 'insufficient_samples',
            'independent_windows': len(independent), 'median_lag_seconds': center,
            'spread_seconds': spread, 'consistent': enough and
            all(abs(lag) <= cfg.get('max_sync_offset_seconds', .12) for lag in independent) and
            spread <= cfg.get('max_sync_lag_deviation_seconds', .1)}


def classify_people(observed, *, speaker, speaking_person, state, simultaneous):
    """Per-visible-person roles. Reaction requires an explicit observation signal.

    Unknown speakers must not be inferred from placement, smiles or mouth motion.
    """
    people = []
    for person in sorted(observed):
        obj = observed[person]
        if not obj.get('face_visible'):
            continue
        raw_reaction = str(obj.get('reaction_type') or '').lower()
        reaction = raw_reaction if raw_reaction in REACTIONS and obj.get('reaction_detected', False) else None
        if speaking_person == person and state == 'CONFIRMED' and not simultaneous:
            role, reason = 'SPEAKING', 'contemporary_audio_mouth_and_global_identity'
        elif reaction and person != speaking_person:
            role, reason = 'REACTING', 'explicit_reaction_observation'
        elif speaking_person and state == 'CONFIRMED' and person != speaking_person and not simultaneous:
            role, reason = 'LISTENING', 'another_person_has_confirmed_speech'
        else:
            role, reason = 'VISIBLE_UNDETERMINED', 'no_reliable_active_speaker_evidence'
        people.append({'person_id': person, 'role': role, 'reason': reason,
                       'speaker_id': speaker if role == 'SPEAKING' else None,
                       'reaction_type': reaction})
    return people
