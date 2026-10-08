"""S5: conservative audiovisual state, with explicit uncertainty.

An identity is not proof of who currently speaks. Human-labelled reactions are
separated from inferred silent listeners and from confirmed mouth/audio sync.
"""
from collections import defaultdict
from statistics import median
from .temporal import number


REACTIONS = {'laugh', 'laughing', 'smile', 'smiling', 'surprise', 'surprised',
             'applause', 'clapping', 'nod', 'nodding'}


def _candidate_for(link, person):
    return next((candidate for candidate in link.get('candidates', [])
                 if candidate.get('person_id') == person), None)


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
        # Legacy rows without lower bound/lag may contribute to global
        # identity but are *never* sufficient to confirm current speech.
        if (score is not None and score >= cfg.get('min_confidence', .55) and
                lower is not None and lower > 0 and
                (upper is None or upper > 0) and lag is not None and
                abs(lag) <= cfg.get('max_sync_offset_seconds', .12) and
                stability >= cfg.get('min_local_track_stability', .5) and
                coverage >= cfg.get('min_local_visibility', .6) and
                faces >= cfg.get('min_local_face_fraction', .6) and
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
            'lower_bound_proxy': candidate.get('correlation_lower_bound_proxy'),
            'window_refs': [row.get('evidence_window_id')] if row.get('evidence_window_id') else []}


def lag_consistency(raw, speaker, person, cfg):
    """Check drift across independent evidence windows (does not create identity)."""
    rows = []
    for row in raw:
        if row.get('overlap') or (row.get('speaker_id') or row.get('speaker')) != speaker:
            continue
        candidate = _candidate_for(row, person)
        if candidate and number(candidate.get('correlation_lower_bound_proxy'), 0) > 0:
            lag = number(candidate.get('audio_lag_seconds'), None)
            if lag is not None:
                rows.append((number(row.get('start')), number(row.get('end')), lag))
    independent, end = [], -1.
    for start, stop, lag in sorted(rows):
        if start >= end and stop-start >= cfg.get('min_evidence_window_seconds', .5):
            independent.append(lag)
            end = stop
    if not independent:
        return {'status': 'not_measured', 'independent_windows': 0,
                'median_lag_seconds': None, 'spread_seconds': None, 'consistent': False}
    center = median(independent)
    spread = max(abs(lag-center) for lag in independent)
    enough = len(independent) >= cfg.get('min_consensus_windows', 2)
    return {'status': 'measured' if enough else 'insufficient_samples',
            'independent_windows': len(independent), 'median_lag_seconds': center,
            'spread_seconds': spread, 'consistent': enough and spread <= cfg.get('max_sync_lag_deviation_seconds', .1)}


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
