"""Conservative multi-window speaker/person consensus and local visual availability."""
from collections import defaultdict
from copy import deepcopy
from .core import ok
from .temporal import IntervalCursor, VisualIndex, number, union_duration


def _row_confidence(row):
    if row.get('method') == 'user_verified':
        return 1.
    return max(0., min(1., number(row.get('association_confidence', row.get('confidence')))))


def build_global_affinity(turns, known_people, raw_mappings, cfg):
    support = defaultdict(lambda: defaultdict(list))
    for row in raw_mappings:
        speaker = row.get('speaker_id') or row.get('speaker')
        if not speaker or row.get('overlap') or row.get('method') == 'user_verified':
            continue
        candidates = list(row.get('candidates') or [])
        chosen = row.get('person_id') or row.get('visible_person')
        if chosen and not any(candidate.get('person_id') == chosen for candidate in candidates):
            candidates.append({'person_id': chosen, 'correlation': row.get('association_evidence_score'),
                               'confidence': _row_confidence(row)})
        for candidate in candidates:
            person = candidate.get('person_id')
            if person not in known_people:
                continue
            correlation = number(candidate.get('correlation'), None)
            confidence = correlation if correlation is not None else number(candidate.get('confidence'), None)
            if candidate.get('correlation_lower_bound_proxy') is not None and candidate['correlation_lower_bound_proxy'] <= 0:
                continue
            if confidence is None:
                continue
            confidence *= number(candidate.get('track_stability'), 1.)
            support[speaker][person].append({**row, 'mouth_audio_score': correlation,
                'affinity_score': max(-1., min(1., confidence)),
                'evidence_window_id': row.get('evidence_window_id') or
                    f"WINDOW_{speaker}_{row['start']:.6f}_{row['end']:.6f}"})
    summaries, stable, affinity = [], {}, []
    for speaker in sorted({turn.get('speaker') for turn in turns if turn.get('speaker')}):
        ranking = []
        for person, evidence in support[speaker].items():
            independent, seen, last_end = [], set(), -1.
            for row in sorted(evidence, key=lambda value: (value['start'], value['end'])):
                window_id = row['evidence_window_id']
                if window_id in seen or row['start'] < last_end or row['end'] - row['start'] < cfg.get('min_evidence_window_seconds', .5):
                    continue
                independent.append(row)
                seen.add(window_id)
                last_end = row['end']
            positive = [row for row in independent if row['affinity_score'] >= cfg.get('min_confidence', .55)]
            negative = [row for row in independent if row['affinity_score'] <= -.2]
            weight = max(0., sum((row['end'] - row['start']) * row['affinity_score'] for row in positive) -
                            sum((row['end'] - row['start']) * abs(row['affinity_score']) for row in negative))
            mean = sum(row['affinity_score'] for row in positive) / len(positive) if positive else 0.
            pair = {'speaker_id': speaker, 'person_id': person, 'support': weight,
                    'evidence_windows': len(independent), 'positive_windows': len(positive),
                    'negative_windows': len(negative), 'conflicting_windows': 0,
                    'support_seconds': union_duration(positive), 'visibility_coverage': None,
                    'mouth_audio_score': mean if positive else None, 'confidence': None,
                    'method': 'global_mouth_audio_affinity', 'confidence_is_calibrated': False,
                    'evidence_refs': [row['evidence_window_id'] for row in independent]}
            affinity.append(pair)
            ranking.append((weight, person, positive, negative, mean, pair))
        ranking.sort(key=lambda value: (-value[0], value[1]))
        total = sum(value[0] for value in ranking)
        best = ranking[0] if ranking else (0., None, [], [], 0., {})
        weight, person, positive, negative, mean, pair = best
        share = weight / total if total else 0.
        accepted = (len(positive) >= int(cfg.get('min_consensus_windows', 2)) and
                    share >= cfg.get('min_consensus_share', .67) and
                    len(negative) < len(positive) and weight > 0 and
                    (len(ranking) < 2 or weight > ranking[1][0]))
        confidence = min(1., share * mean) if accepted else None
        if accepted:
            stable[speaker] = (person, confidence)
            pair['confidence'] = confidence
        alternatives = [{'person_id': value[1], 'weight': value[0], 'windows': len(value[2]),
                         'negative_windows': len(value[3])} for value in ranking[1:]]
        reason = None if accepted else 'ambiguous_global_affinity' if len(ranking) > 1 and share < cfg.get('min_consensus_share', .67) else 'insufficient_independent_evidence'
        summaries.append({'speaker_id': speaker, 'person_id': person if accepted else None,
            'confidence': confidence, 'support_share': share, 'evidence_windows': len(positive),
            'evidence_count': len(positive), 'positive_windows': len(positive), 'negative_windows': len(negative),
            'conflicting_windows': sum(len(value[2]) for value in ranking[1:]),
            'visibility_coverage': None, 'mouth_audio_score': mean if positive else None,
            'temporal_consistency': share if total else None, 'support_seconds_weighted': weight,
            'support_seconds': union_duration(positive), 'alternatives': alternatives,
            'method': 'global_multi_evidence_affinity' if accepted else 'insufficient_consensus',
            'source': 'diarization_and_independent_mouth_audio_windows', 'unresolved_reason': reason,
            'evidence_refs': [row['evidence_window_id'] for row in positive],
            'evidence': ['diarization', 'mouth_audio_synchrony', 'independent_windows'] if accepted else [],
            'needs_review': True, 'confidence_is_calibrated': False})
    colliding = set()
    for index, left in enumerate(summaries):
        if not left['person_id']:
            continue
        for right in summaries[index + 1:]:
            if left['person_id'] != right['person_id']:
                continue
            left_turns = [turn for turn in turns if turn['speaker'] == left['speaker_id']]
            right_turns = [turn for turn in turns if turn['speaker'] == right['speaker_id']]
            if any(min(first['end'], second['end']) > max(first['start'], second['start']) for first in left_turns for second in right_turns):
                colliding.update((left['speaker_id'], right['speaker_id']))
    for summary in summaries:
        if summary['speaker_id'] in colliding:
            stable.pop(summary['speaker_id'], None)
            summary.update(person_id=None, confidence=None, unresolved_reason='simultaneous_speaker_person_conflict')
    return summaries, stable, affinity


def build_active_speaker(diarization, vision, raw_mappings, cfg):
    turns = diarization.get('turns', [])
    raw = deepcopy(raw_mappings or [])
    if not turns:
        return ok({'mappings': raw, 'mapping_summary': [], 'intervals': [], 'coverage': 0.},
                  'unavailable', ['Sem diarização: active_person permanece null.'])
    known = {person['person_id'] for person in vision.get('people', []) if person.get('person_id')}
    known |= {observation['person_id'] for observation in vision.get('observations', []) if observation.get('person_id')}
    summaries, stable, affinity = build_global_affinity(turns, known, raw, cfg)
    duration = max(t['end'] for t in turns)
    bounds = {0., duration}
    for collection in (turns, raw):
        for r in collection:
            bounds.update((max(0., r['start']), min(duration, r['end'])))
    frames = vision.get('frames', [])
    # Scene changes are hard visibility boundaries, not merely nearest-frame hints.
    scene_bounds = []
    previous = object()
    for f in sorted(frames, key=lambda r: r['time']):
        if f.get('scene_id') != previous:
            scene_bounds.append(f['time'])
            previous = f.get('scene_id')
    bounds.update(scene_bounds)
    for scene in vision.get("scene_intervals", []):
        bounds.update((scene["start"], scene["end"]))
    step = cfg.get('window_seconds', .5)
    bounds.update(i*step for i in range(int(duration/step)+1))
    ordered = sorted(x for x in bounds if 0 <= x <= duration)
    turns_cursor, raw_cursor = IntervalCursor(turns), IntervalCursor(raw)
    visual = VisualIndex(vision)
    scene_cursor = IntervalCursor(vision.get("scene_intervals", []))
    intervals, mappings = [], []
    for a, b in zip(ordered, ordered[1:]):
        mid = (a+b)/2
        active = turns_cursor.at(mid)
        links = raw_cursor.at(mid)
        scene = next(iter(scene_cursor.at(mid)), {})
        frame, observed = visual.near(mid, scene.get('start', 0.), scene.get('end', duration),
                                      cfg.get('max_observation_gap_seconds', .6))
        speakers = sorted({t['speaker'] for t in active})
        for speaker in speakers:
            direct = [r for r in links if (r.get('speaker_id') or r.get('speaker')) == speaker]
            manual = {r.get('person_id') or r.get('visible_person') for r in direct if r.get('method') == 'user_verified'}
            person, confidence = stable.get(speaker, (None, None))
            method = 'consensus_continuity' if person else 'unresolved'
            if len(manual) == 1:
                person, confidence, method = next(iter(manual)), 1., 'user_verified'
            elif len(manual) > 1:
                person, confidence, method = None, None, 'conflicting_manual_mapping'
            observed_person = observed.get(person)
            valid = bool(observed_person and observed_person.get('face_visible'))
            unresolved = 'conflicting_manual_mapping' if method=='conflicting_manual_mapping' else None
            if person not in known:
                person, confidence = None, None
                unresolved = unresolved or 'insufficient_consensus'
            elif not valid:
                person, confidence = None, None
                unresolved = 'mapped_person_not_visually_available'
            evidence = ['diarization']
            if person:
                evidence += ['user_verified_mapping' if method == 'user_verified' else 'speaker_person_consensus', 'face_visible']
                if observed_person.get('mouth_activity') is not None:
                    evidence.append('mouth_activity')
            local_correlation = next((r.get('association_evidence_score') for r in direct
                                      if (r.get('person_id') or r.get('visible_person')) == person), None)
            observed_at = frame['time'] if frame else None
            observation_age = abs(mid-observed_at) if observed_at is not None else None
            if len(speakers) > 1:
                speaker_state = 'MULTIPLE_SPEAKERS'
            elif person:
                speaker_state = 'KNOWN_PERSON'
            elif active and not frame:
                speaker_state = 'INSUFFICIENT_EVIDENCE'
            elif active and frame and (not observed or unresolved == 'mapped_person_not_visually_available'):
                speaker_state = 'OFFSCREEN_SPEAKER'
            elif active:
                speaker_state = 'UNKNOWN_PERSON' if direct or stable.get(speaker) else 'NO_CLEAR_SPEAKER'
            else:
                speaker_state = 'NO_CLEAR_SPEAKER'
            face_quality = None
            landmark_quality = None
            if observed_person:
                face_quality = observed_person.get('face_quality')
                if face_quality is None:
                    face_quality = observed_person.get('sharpness')
                landmarks = observed_person.get('landmarks')
                if landmarks is not None:
                    landmark_quality = 1.0 if landmarks else 0.0
            row = {'start': a, 'end': b, 'speaker_id': speaker, 'speaker': speaker,
                   'person_id': person, 'visible_person': person, 'active_person': person,
                   'state': speaker_state,
                   'confidence': confidence, 'association_confidence': confidence,
                   'mapping_confidence': confidence, 'confidence_is_calibrated': False,
                   'diarization_support': True,
                   'speaker_person_mapping_support': confidence,
                   'mouth_activity_score': observed_person.get('mouth_activity') if observed_person else None,
                   'mouth_audio_score': local_correlation, 'visibility_score': 1. if valid else 0.,
                   'contemporary_visual_presence': valid,
                   'face_quality': face_quality, 'landmark_quality': landmark_quality,
                   'temporal_continuity': confidence if person else None,
                   'visual_observed_at': observed_at, 'observation_age': observation_age,
                   'offscreen_state': speaker_state == 'OFFSCREEN_SPEAKER',
                   'evidence': evidence, 'method': method if person else 'unresolved',
                   'overlap': len(speakers) > 1, 'needs_review': person is None or method != 'user_verified',
                   'unresolved_reason': unresolved if not person else None}
            mappings.append(row)
            intervals.append({k: v for k, v in row.items() if k not in ('speaker', 'visible_person', 'association_confidence')})
    speech = union_duration(turns)
    covered = union_duration([r for r in intervals if r['person_id']])
    for summary in summaries:
        srows = [r for r in intervals if r['speaker_id'] == summary['speaker_id']]
        total_s = union_duration(srows)
        summary['visibility_coverage'] = union_duration([r for r in srows if r['person_id']])/total_s if total_s else 0.
    # Generated by GitHub Copilot - Oct-05-2026
    ages=sorted(row['observation_age'] for row in intervals if row.get('observation_age') is not None)
    metrics={'diarized_speech_seconds':speech,'known_person_speech_seconds':covered,
             'active_speaker_coverage':covered/speech if speech else None,
             'speaker_person_mapping_coverage':union_duration([turn for turn in turns if turn['speaker'] in stable])/speech if speech else None,
             'speaker_person_high_confidence_coverage':union_duration([turn for turn in turns if turn['speaker'] in stable and stable[turn['speaker']][1] >= .8])/speech if speech else None,
             'active_speaker_high_confidence_coverage':union_duration([row for row in intervals if row['person_id'] and (row['confidence'] or 0) >= .8])/speech if speech else None,
             'ambiguous_mapping_fraction':union_duration([turn for turn in turns if any(summary['speaker_id'] == turn['speaker'] and summary['unresolved_reason'] == 'ambiguous_global_affinity' for summary in summaries)])/speech if speech else None,
             'offscreen_speaker_fraction':union_duration([row for row in intervals if row['state']=='OFFSCREEN_SPEAKER'])/speech if speech else None,
             'unknown_person_fraction':union_duration([row for row in intervals if not row['person_id']])/speech if speech else None,
             'conflicting_mapping_fraction':union_duration([row for row in intervals if row.get('unresolved_reason')=='conflicting_manual_mapping'])/speech if speech else None,
             'mapping_support_windows':sum(summary['evidence_windows'] for summary in summaries),
             'mapping_support_window_count':len({reference for summary in summaries for reference in summary['evidence_refs']}),
             'observation_age_mean':sum(ages)/len(ages) if ages else None,
             'observation_age_p25':ages[int((len(ages)-1)*.25)] if ages else None,
             'observation_age_p50':ages[int((len(ages)-1)*.5)] if ages else None,
             'observation_age_p75':ages[int((len(ages)-1)*.75)] if ages else None,
             'observation_age_p95':ages[int((len(ages)-1)*.95)] if ages else None,
             'observation_age_method':'sample_distance_seconds'}
    return ok({'mappings': mappings, 'mapping_summary': summaries, 'affinity': affinity,
               'active_speaker_evidence': raw, 'intervals': intervals,
               'coverage': covered/speech if speech else 0.,'metrics':metrics},
              'ok' if speech and covered >= .8*speech else 'partial',
              ['Active speaker: consenso de janelas independentes + presença contemporânea; scores heurísticos, não calibrados.'])
